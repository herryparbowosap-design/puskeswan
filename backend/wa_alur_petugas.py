"""Alur WhatsApp untuk PETUGAS terverifikasi (whitelist).

Menu:
  1) Catat peternak + ternak baru   → Fase B (langsung jadi; AI susun-ternak)
  2) Catat pelayanan (draft)          → Fase C (AI merapikan; SELALU draft)
  status                              → antrian & jumlah peternak

Prinsip keamanan:
  - Hanya nomor petugas terdaftar yang sampai ke sini (routing di webhook).
  - Pelayanan via WA SELALU disimpan sebagai DRAFT (perlu dilengkapi di app):
    kode iSIKHNAS, dosis presisi, foto dirapikan petugas di aplikasi.
  - Angka medis obat di-ANCHOR ke formularium (bukan dikarang AI).
  - Batas panggilan AI per entri (anti-boros). Task-locked (tak melayani hal lain).
"""
import os
from datetime import datetime, timezone, timedelta

import notifikasi
import ai as ai_mod
import peternak as peternak_mod
import ternak as ternak_mod
import pelayanan as pelayanan_mod

SESI_JAM = 24
MAX_AI = 4
KONTAK = "081328105535"


def _user_obj(petugas):
    return {"id": petugas["user_id"], "nama": petugas.get("nama"), "roles": ["petugas"]}


async def _sesi(db, wa_id):
    s = await db.wa_sesi_petugas.find_one({"wa_id": wa_id}, {"_id": 0})
    if s:
        ts = s.get("updated_at")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - ts > timedelta(hours=SESI_JAM):
                return None
    return s


async def _simpan(db, wa_id, mode, step, data, ai_calls=0):
    await db.wa_sesi_petugas.update_one(
        {"wa_id": wa_id},
        {"$set": {"wa_id": wa_id, "mode": mode, "step": step, "data": data,
                  "ai_calls": ai_calls, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def _hapus(db, wa_id):
    await db.wa_sesi_petugas.delete_one({"wa_id": wa_id})


async def _cocokkan_kalurahan(db, teks):
    if not teks:
        return None
    return await db.wilayah.find_one(
        {"level": "kalurahan", "nama": {"$regex": teks.strip(), "$options": "i"}},
        {"_id": 0, "id": 1, "nama": 1, "parent_id": 1},
    )


def _menu(nama):
    return (f"Halo *{nama}* 👋 (petugas terverifikasi).\n\n"
            "*Menu* — ketik angka:\n"
            "1) Catat *peternak + ternak* baru\n"
            "2) Catat *pelayanan* (draft)\n\n"
            "_Ketik *status* untuk antrian, *batal* untuk berhenti._")


async def _status(db):
    n_baru = await db.pendaftaran.count_documents({"status": "baru"})
    n_pet = await db.peternak.count_documents({})
    return (f"📊 *Status Puskeswan Godean*\n"
            f"• Pendaftaran menunggu verifikasi: *{n_baru}*\n"
            f"• Total peternak terdaftar: *{n_pet}*")


# ---------------------------------------------------------------- Fase B
async def _alur_peternak(db, petugas, wa_id, teks, sesi):
    step = sesi.get("step")
    data = sesi.get("data") or {}
    ai_calls = sesi.get("ai_calls", 0)

    if step == "nama":
        data["nama"] = teks[:80]
        await _simpan(db, wa_id, "peternak", "kontak", data, ai_calls)
        return "No. HP peternak? _(ketik *-* bila tak ada)_"

    if step == "kontak":
        data["kontak"] = "-" if teks.strip() == "-" else teks.strip()[:30]
        await _simpan(db, wa_id, "peternak", "wilayah", data, ai_calls)
        return "Kalurahan peternak? (mis. Sidoarum)"

    if step == "wilayah":
        w = await _cocokkan_kalurahan(db, teks)
        if w:
            data["kalurahan_id"] = w["id"]
            data["kapanewon_id"] = w.get("parent_id")
            data["wilayah_nama"] = w["nama"]
        else:
            data["wilayah_teks"] = teks[:80]
        await _simpan(db, wa_id, "peternak", "ternak", data, ai_calls)
        return "Sebutkan *ternaknya* (mis. _3 sapi PO betina, 10 ayam_). AI akan menyusun."

    if step == "ternak":
        try:
            draft = await ai_mod.susun_ternak_core(teks)
        except Exception:
            draft = []
        data["ternak_draft"] = draft
        await _simpan(db, wa_id, "peternak", "konfirmasi", data, ai_calls + 1)
        if not draft:
            return ("AI tak menemukan ternak dari teks itu. Ketik ulang deskripsi ternak, "
                    "atau *batal*.")
        baris = "\n".join(
            f"{i+1}. {t['spesies']}"
            + (f" · {t['jml_deklarasi']} ekor" if t.get("mode") == "populasi" and t.get("jml_deklarasi") else "")
            + (f" · {t['jenis_kelamin']}" if t.get("jenis_kelamin") else "")
            for i, t in enumerate(draft)
        )
        return (f"Draft ternak:\n{baris}\n\nBalas *ya* untuk simpan, *ulang* untuk ketik ternak lagi, *batal*.")

    if step == "konfirmasi":
        low = teks.lower().strip()
        if low == "ulang":
            await _simpan(db, wa_id, "peternak", "ternak", data, ai_calls)
            return "Ketik ulang deskripsi ternak."
        if low != "ya":
            return "Balas *ya* untuk simpan, *ulang*, atau *batal*."
        u = _user_obj(petugas)
        p = await peternak_mod.create_peternak(peternak_mod.PeternakIn(
            nama=data.get("nama") or "(tanpa nama)",
            kontak=data.get("kontak") or "-",
            kapanewon_id=data.get("kapanewon_id"),
            kalurahan_id=data.get("kalurahan_id"),
            alamat_detail=data.get("wilayah_teks"),
        ), user=u)
        n = 0
        for t in data.get("ternak_draft", []):
            await ternak_mod.create_ternak(ternak_mod.TernakIn(
                peternak_id=p["id"], spesies=t["spesies"], mode=t.get("mode", "individu"),
                jenis_kelamin=t.get("jenis_kelamin"),
                jml_deklarasi=t.get("jml_deklarasi") if t.get("mode") == "populasi" else None,
            ), user=u)
            n += 1
        await _hapus(db, wa_id)
        return (f"✅ Peternak *{p['nama']}* tersimpan dengan *{n}* ternak.\n"
                "Ketik *menu* untuk tindakan lain.")

    await _hapus(db, wa_id)
    return _menu(petugas.get("nama") or "Petugas")


# ---------------------------------------------------------------- Fase C
async def _cocokkan_obat(db, ai_obat):
    """Cocokkan nama obat AI ke formularium. Dosis/aturan TIDAK dikarang AI —
    obat_id & satuan diambil dari formularium. Kembalikan (list_pelayanan, luar_formularium)."""
    hasil, luar = [], []
    for o in ai_obat or []:
        nama = (o.get("nama") or "").strip()
        if not nama:
            continue
        jml = o.get("jumlah")
        try:
            jml = float(jml) if jml is not None else 0.0
        except (TypeError, ValueError):
            jml = 0.0
        m = await db.obat.find_one(
            {"$or": [{"nama_dagang": {"$regex": nama, "$options": "i"}},
                     {"zat_aktif": {"$regex": nama, "$options": "i"}}]},
            {"_id": 0, "id": 1, "nama_dagang": 1, "satuan": 1},
        )
        if m:
            hasil.append({"obat_id": m["id"], "nama": m["nama_dagang"], "jumlah": jml,
                          "satuan": m.get("satuan") or "-", "catatan": None})
        else:
            hasil.append({"obat_id": None, "nama": nama, "jumlah": jml,
                          "satuan": (o.get("satuan") or "-"), "catatan": "di luar formularium"})
            luar.append(nama)
    return hasil, luar


def _ringkas_pelayanan(nama_peternak, draft):
    obat = draft.get("obat_match") or []
    obat_txt = "\n".join(f"  • {o['nama']} — {o['jumlah']} {o['satuan']}"
                         + (f" ⚠ {o['catatan']}" if o.get("catatan") else "") for o in obat) or "  -"
    return (f"*Draft pelayanan — {nama_peternak}*\n"
            f"Kategori: {draft.get('kategori', 'KESWAN')}\n"
            f"Hewan: {draft.get('hewan_teks') or '-'}\n"
            f"Keluhan: {draft.get('keluhan') or '-'}\n"
            f"Tindakan: {draft.get('tindakan') or '-'}\n"
            f"Obat:\n{obat_txt}\n"
            f"Modalitas: {draft.get('modalitas') or '-'}\n\n"
            "Balas *ya* untuk simpan DRAFT, kirim ulang deskripsi untuk perbaiki, atau *batal*.")


async def _susun_dan_ringkas(db, wa_id, petugas, data, teks, ai_calls):
    try:
        draft = await ai_mod.susun_pelayanan_core(teks)
    except Exception:
        draft = {}
    obat_match, luar = await _cocokkan_obat(db, draft.get("obat"))
    draft["obat_match"] = obat_match
    data["draft"] = draft
    await _simpan(db, wa_id, "pelayanan", "konfirmasi", data, ai_calls + 1)
    return _ringkas_pelayanan(data.get("peternak_nama", "?"), draft)


async def _alur_pelayanan(db, petugas, wa_id, teks, sesi):
    step = sesi.get("step")
    data = sesi.get("data") or {}
    ai_calls = sesi.get("ai_calls", 0)

    if step == "cari":
        rows = await db.peternak.find(
            {"nama": {"$regex": teks.strip(), "$options": "i"}},
            {"_id": 0, "id": 1, "nama": 1, "kalurahan_id": 1},
        ).limit(6).to_list(6)
        if not rows:
            return "Peternak tidak ditemukan. Ketik nama lain, atau *menu*."
        if len(rows) == 1:
            data["peternak_id"] = rows[0]["id"]
            data["peternak_nama"] = rows[0]["nama"]
            await _simpan(db, wa_id, "pelayanan", "deskripsi", data, ai_calls)
            return (f"Catat untuk *{rows[0]['nama']}*.\n"
                    "Jelaskan pelayanannya (keluhan, tindakan, obat & jumlah).")
        data["kandidat"] = [{"id": r["id"], "nama": r["nama"]} for r in rows]
        await _simpan(db, wa_id, "pelayanan", "pilih", data, ai_calls)
        daftar = "\n".join(f"{i+1}. {r['nama']}" for i, r in enumerate(rows))
        return f"Ditemukan beberapa:\n{daftar}\n\nBalas *nomor* peternak yang dimaksud."

    if step == "pilih":
        try:
            idx = int(teks.strip()) - 1
            kand = data.get("kandidat", [])
            chosen = kand[idx]
        except (ValueError, IndexError):
            return "Balas *nomor* yang valid (mis. 1)."
        data["peternak_id"] = chosen["id"]
        data["peternak_nama"] = chosen["nama"]
        await _simpan(db, wa_id, "pelayanan", "deskripsi", data, ai_calls)
        return (f"Catat untuk *{chosen['nama']}*.\n"
                "Jelaskan pelayanannya (keluhan, tindakan, obat & jumlah).")

    if step == "deskripsi":
        return await _susun_dan_ringkas(db, wa_id, petugas, data, teks, ai_calls)

    if step == "konfirmasi":
        low = teks.lower().strip()
        if low == "ya":
            draft = data.get("draft") or {}
            ket_bits = ["[via WA petugas — DRAFT, lengkapi di aplikasi]"]
            luar = [o["nama"] for o in (draft.get("obat_match") or []) if o.get("catatan")]
            if luar:
                ket_bits.append("Obat di luar formularium: " + ", ".join(luar))
            try:
                obat_in = [pelayanan_mod.ObatPakaiIn(
                    obat_id=o.get("obat_id"), nama=o["nama"], jumlah=o["jumlah"],
                    satuan=o["satuan"], catatan=o.get("catatan")) for o in (draft.get("obat_match") or [])]
                body = pelayanan_mod.PelayananIn(
                    kategori=draft.get("kategori", "KESWAN"),
                    peternak_id=data["peternak_id"],
                    hewan=pelayanan_mod.HewanIn(jenis_hewan=draft["hewan_teks"], jumlah=1) if draft.get("hewan_teks") else None,
                    diagnosa_teks=draft.get("keluhan"),
                    tindakan=draft.get("tindakan"),
                    modalitas=draft.get("modalitas"),
                    obat=obat_in,
                    keterangan=" | ".join(ket_bits),
                    sumber="wa-petugas",
                    draft=True,
                )
                await pelayanan_mod.create_pelayanan(body, user=_user_obj(petugas))
            except Exception:
                await _hapus(db, wa_id)
                return f"Maaf, gagal menyimpan. Coba lagi atau catat di aplikasi. ({KONTAK})"
            await _hapus(db, wa_id)
            return ("✅ Tersimpan sebagai *DRAFT*.\n"
                    "Lengkapi di aplikasi: kode iSIKHNAS, dosis presisi, foto. Terima kasih.")
        if low == "batal":
            await _hapus(db, wa_id)
            return "Dibatalkan. Ketik *menu* untuk pilihan."
        # selain itu: anggap koreksi → susun ulang (berbatas)
        if ai_calls >= MAX_AI:
            return ("Batas perbaikan AI tercapai. Balas *ya* untuk simpan draft apa adanya, "
                    "atau *batal*.")
        return await _susun_dan_ringkas(db, wa_id, petugas, data, teks, ai_calls)

    await _hapus(db, wa_id)
    return _menu(petugas.get("nama") or "Petugas")


# ---------------------------------------------------------------- dispatcher
async def proses_petugas(db, petugas, wa_id, teks):
    low = (teks or "").lower().strip()
    nama = petugas.get("nama") or "Petugas"

    if low in ("batal", "cancel", "stop"):
        await _hapus(db, wa_id)
        return "Dibatalkan. Ketik *menu* untuk pilihan."
    if low in ("status", "antrian"):
        return await _status(db)
    if low in ("menu", "help", "mulai"):
        await _hapus(db, wa_id)
        return _menu(nama)

    sesi = await _sesi(db, wa_id)
    if not sesi or not sesi.get("mode"):
        # di menu utama → pilih
        if low in ("1", "1)", "peternak"):
            await _simpan(db, wa_id, "peternak", "nama", {})
            return "Catat peternak baru.\nSiapa *nama* peternak?"
        if low in ("2", "2)", "pelayanan"):
            await _simpan(db, wa_id, "pelayanan", "cari", {})
            return "Catat pelayanan.\nKetik *nama peternak* yang dilayani."
        return _menu(nama)

    if sesi.get("mode") == "peternak":
        return await _alur_peternak(db, petugas, wa_id, teks, sesi)
    if sesi.get("mode") == "pelayanan":
        return await _alur_pelayanan(db, petugas, wa_id, teks, sesi)

    await _hapus(db, wa_id)
    return _menu(nama)
