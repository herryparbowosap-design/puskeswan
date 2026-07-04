"""Webhook WhatsApp (Cloud API) — pintu pendaftaran via WA (inbound).

Alur task-specific (patuh aturan Meta Jan 2026 — bukan AI tujuan-umum):
  nama → kalurahan → ternak (teks) → buat pendaftaran (status 'baru', sumber 'wa').
Pengguna memulai chat, jadi balasan teks-bebas berada di jendela 24 jam (GRATIS).
Hasil tetap masuk ANTRIAN; petugas verifikasi & susun ternak di layar (human-gate).

Endpoint PUBLIK (dipanggil Meta):
  GET  /api/wa/webhook  → verifikasi (echo hub.challenge bila token cocok)
  POST /api/wa/webhook  → terima pesan; selalu balas 200 cepat.

Env:
  WA_VERIFY_TOKEN=<token verifikasi webhook>   (wajib untuk GET)
  WA_APP_SECRET=<app secret>                    (opsional; jika diisi, signature diverifikasi)
  + kredensial WA_* dari notifikasi.py untuk mengirim balasan.
"""
import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, Response

from db import get_db
import notifikasi
import pendaftaran as pendaftaran_mod
from wa_petugas import cari_petugas_by_no
from wa_alur_petugas import proses_petugas
from interaction_log import catat_interaksi
from wa_konsultasi import (
    jawab_konsultasi, format_balasan_konsultasi,
    MENU_UTAMA, TEKS_MULAI_KONSULTASI, TEKS_INFO,
)

router = APIRouter(prefix="/wa", tags=["wa"])

KONTAK = "081328105535"
SESI_KEDALUWARSA_JAM = 24


@router.get("/webhook")
async def verify(request: Request):
    qp = request.query_params
    mode = qp.get("hub.mode")
    token = qp.get("hub.verify_token")
    challenge = qp.get("hub.challenge")
    expected = os.getenv("WA_VERIFY_TOKEN")
    if mode == "subscribe" and expected and token == expected:
        return Response(content=challenge or "", media_type="text/plain")
    return Response(content="forbidden", status_code=403)


def _verifikasi_signature(raw: bytes, header: str | None) -> bool:
    secret = os.getenv("WA_APP_SECRET")
    if not secret:
        return True  # tidak dipaksakan bila app secret tak diset
    if not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, header)


def _ekstrak_pesan(payload: dict):
    """Ambil (wa_id, nama_profil, msg_id, teks) dari payload pertama; None jika bukan pesan teks."""
    try:
        change = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None
    msgs = change.get("messages")
    if not msgs:
        return None  # status/delivery events — abaikan
    m = msgs[0]
    if m.get("type") != "text":
        return (m.get("from"), None, m.get("id"), None)  # non-teks → balas panduan
    nama = None
    for c in change.get("contacts", []) or []:
        if c.get("wa_id") == m.get("from"):
            nama = (c.get("profile") or {}).get("name")
    return (m.get("from"), nama, m.get("id"), (m.get("text") or {}).get("body", "").strip())


async def _cocokkan_kalurahan(db, teks):
    """Cari kalurahan berdasarkan nama (contains, case-insensitive)."""
    if not teks:
        return None
    w = await db.wilayah.find_one(
        {"level": "kalurahan", "nama": {"$regex": teks.strip(), "$options": "i"}},
        {"_id": 0, "id": 1, "nama": 1, "parent_id": 1},
    )
    return w


async def _proses(db, wa_id, nama_profil, teks):
    """State machine: menu -> (konsultasi | pendaftaran | info). Mengembalikan teks balasan."""
    low = (teks or "").lower().strip()
    sesi = await db.wa_sesi.find_one({"wa_id": wa_id}, {"_id": 0})

    # kedaluwarsa -> reset
    if sesi:
        ts = sesi.get("updated_at")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - ts > timedelta(hours=SESI_KEDALUWARSA_JAM):
                sesi = None

    async def simpan(step, data):
        await db.wa_sesi.update_one(
            {"wa_id": wa_id},
            {"$set": {"wa_id": wa_id, "step": step, "data": data, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    async def hapus():
        await db.wa_sesi.delete_one({"wa_id": wa_id})

    def _mulai_daftar():
        return ("Baik, kita daftarkan Anda untuk layanan Puskeswan Godean. 🐾\n"
                "Siapa *nama lengkap* Anda?\n_(ketik *batal* untuk berhenti)_")

    # batal kapan saja
    if low in ("batal", "cancel", "stop"):
        await hapus()
        return "Baik, sesi diakhiri. Kirim pesan apa saja untuk membuka *menu* lagi. Terima kasih."

    # kembali ke menu kapan saja
    if low in ("menu", "0"):
        await simpan("menu", (sesi or {}).get("data") or {})
        return MENU_UTAMA

    # belum ada sesi -> tampilkan MENU (bukan langsung pendaftaran)
    if not sesi:
        await simpan("menu", {})
        return MENU_UTAMA

    step = sesi.get("step")
    data = sesi.get("data") or {}

    # jalan pintas "daftar" dari mana saja (kecuali sedang di tengah pendaftaran)
    if low in ("daftar", "pendaftaran") and step not in ("nama", "wilayah", "ternak"):
        await simpan("nama", data)
        return _mulai_daftar()

    # ---------- MENU ----------
    if step == "menu":
        if low in ("1", "konsultasi", "konsul", "tanya"):
            await simpan("konsultasi", data)
            return TEKS_MULAI_KONSULTASI
        if low in ("2", "daftar", "pendaftaran"):
            await simpan("nama", data)
            return _mulai_daftar()
        if low in ("3", "info", "jadwal", "alamat"):
            return TEKS_INFO + "\n\n" + MENU_UTAMA
        return "Mohon balas dengan *angka* 1, 2, atau 3.\n\n" + MENU_UTAMA

    # ---------- KONSULTASI ----------
    if step == "konsultasi":
        hasil = await jawab_konsultasi(teks)
        balasan = format_balasan_konsultasi(hasil)
        if hasil.get("perlu_pendaftaran"):
            data["keluhan_konsultasi"] = hasil.get("ringkas_keluhan") or teks[:200]
        await simpan("konsultasi", data)
        return balasan

    # ---------- PENDAFTARAN ----------
    if step == "nama":
        if not teks:
            return "Mohon ketik nama lengkap Anda."
        data["nama"] = teks[:80]
        await simpan("wilayah", data)
        return (f"Terima kasih, {data['nama']}.\n"
                "Sebutkan *kalurahan* Anda (mis. Sidoarum, Sidoluhur, Sidomulyo, "
                "Sidoagung, Sidokarto, Sidorejo, Sidomoyo).")

    if step == "wilayah":
        w2 = await _cocokkan_kalurahan(db, teks)
        if w2:
            data["kalurahan_id"] = w2["id"]
            data["kapanewon_id"] = w2.get("parent_id")
            data["wilayah_nama"] = w2["nama"]
        else:
            data["wilayah_teks"] = teks[:80]
        await simpan("ternak", data)
        konfirmasi_wil = f"Wilayah: *{data.get('wilayah_nama', teks)}*.\n" if teks else ""
        return (f"{konfirmasi_wil}Sebutkan *hewan/ternak* Anda beserta jumlahnya "
                "(mis. _3 sapi, 10 ayam, 1 kambing_).")

    if step == "ternak":
        data["ternak_teks"] = teks[:300]
        catatan = f"[via WhatsApp] Ternak: {data.get('ternak_teks', '-')}"
        if data.get("wilayah_teks"):
            catatan += f" | Wilayah (teks): {data['wilayah_teks']}"
        if data.get("keluhan_konsultasi"):
            catatan += f" | Keluhan (konsultasi): {data['keluhan_konsultasi']}"
        sumber = "wa_konsultasi" if data.get("keluhan_konsultasi") else "wa"
        try:
            await pendaftaran_mod.buat_pendaftaran(pendaftaran_mod.PendaftaranIn(
                nama=data.get("nama") or nama_profil or "(tanpa nama)",
                kontak=wa_id,
                kapanewon_id=data.get("kapanewon_id"),
                kalurahan_id=data.get("kalurahan_id"),
                catatan=catatan,
                sumber=sumber,
            ))
        except Exception:
            await hapus()
            return ("Maaf, terjadi kendala menyimpan pendaftaran. Silakan coba lagi nanti "
                    f"atau hubungi {KONTAK}.")
        await hapus()
        return ("✅ *Pendaftaran Anda terkirim* dan menunggu verifikasi petugas Puskeswan Godean.\n"
                f"Jika ada pertanyaan, hubungi {KONTAK}. Terima kasih!")

    # step tak dikenal -> kembali ke menu
    await simpan("menu", {})
    return MENU_UTAMA


@router.post("/webhook")
async def terima(request: Request):
    raw = await request.body()
    if not _verifikasi_signature(raw, request.headers.get("X-Hub-Signature-256")):
        return Response(content="bad signature", status_code=403)
    try:
        import json
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {"ok": True}

    parsed = _ekstrak_pesan(payload)
    if not parsed:
        return {"ok": True}  # bukan pesan (status/delivery) — abaikan
    wa_id, nama_profil, msg_id, teks = parsed
    if not wa_id:
        return {"ok": True}

    db = get_db()
    # idempotensi: Meta bisa mengirim ulang webhook
    if msg_id:
        sudah = await db.wa_pesan_diproses.find_one({"msg_id": msg_id}, {"_id": 0, "msg_id": 1})
        if sudah:
            return {"ok": True}
        await db.wa_pesan_diproses.update_one(
            {"msg_id": msg_id},
            {"$set": {"msg_id": msg_id, "at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    if teks is None:
        balasan = "Mohon kirim *teks*. Ketik *daftar* untuk memulai pendaftaran Puskeswan Godean."
    else:
        try:
            petugas = await cari_petugas_by_no(db, wa_id)
            if petugas:
                balasan = await proses_petugas(db, petugas, wa_id, teks)
            else:
                balasan = await _proses(db, wa_id, nama_profil, teks)
        except Exception:
            balasan = f"Maaf, terjadi kendala. Coba lagi atau hubungi {KONTAK}."

    # Catat interaksi (gagal-diam; tak memblokir balasan)
    try:
        peran = "petugas" if await cari_petugas_by_no(db, wa_id) else "warga"
    except Exception:
        peran = "warga"
    await catat_interaksi(
        db, wa_id=wa_id, nama=nama_profil, peran=peran,
        teks_masuk=teks, balasan=balasan,
    )

    if balasan:
        await notifikasi.kirim_teks_wa(wa_id, balasan)
    return {"ok": True}
