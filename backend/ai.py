"""AI iSIKHNAS — strukturkan catatan lapangan bebas + usulkan kode iSIKHNAS.

Human-in-the-loop: endpoint ini TIDAK menyimpan apa pun. Ia hanya
mengembalikan SARAN (diagnosa, tindakan, prognosa, usulan kode) yang
WAJIB diperiksa & dikonfirmasi petugas sebelum disimpan lewat /pelayanan.

Grounding: kode hanya boleh berasal dari crosswalk/penyakit yang ada di DB
(AI tidak mengarang kode). Setiap kode usulan divalidasi ulang ke master.
"""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import require_roles

router = APIRouter(prefix="/ai", tags=["ai"])

AI_MODEL = os.getenv("AI_MODEL", "claude-haiku-4-5-20251001")

SYSTEM = (
    "Anda asisten medis veteriner untuk Puskeswan (pusat kesehatan hewan) di Indonesia. "
    "Dari catatan lapangan bebas seorang petugas/dokter hewan, hasilkan struktur rekam medis "
    "ringkas DAN usulkan kode penyakit iSIKHNAS.\n"
    "Aturan:\n"
    "- Kode WAJIB dipilih HANYA dari TABEL REFERENSI yang diberikan. JANGAN mengarang kode.\n"
    "- Jika tidak ada kode yang cocok, kembalikan usulan_kode sebagai array kosong.\n"
    "- Ini konteks hewan ternak/peliharaan, bukan manusia.\n"
    "- prognosa hanya boleh salah satu: Fausta, Dubius, Infausta, atau null.\n"
    "- Balas HANYA JSON valid, tanpa markdown, tanpa teks lain.\n"
    'Format: {"diagnosa_teks": str, "tindakan": str|null, '
    '"prognosa": "Fausta"|"Dubius"|"Infausta"|null, '
    '"usulan_kode": [{"kode": str, "alasan": str}]}'
)


class SaranIn(BaseModel):
    teks: str
    jenis_hewan: Optional[str] = None


@router.post("/saran")
async def saran_isikhnas(body: SaranIn, _user=Depends(require_roles("petugas", "admin"))):
    if not body.teks or len(body.teks.strip()) < 5:
        raise HTTPException(400, "catatan terlalu pendek")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "AI belum dikonfigurasi (ANTHROPIC_API_KEY kosong)")

    db = get_db()
    cw = await db.crosswalk_isikhnas.find(
        {"kode": {"$nin": ["-", "", None]}},
        {"_id": 0, "label": 1, "padanan": 1, "kode": 1, "kategori": 1},
    ).to_list(500)
    cw_map = {c["kode"]: c for c in cw}
    ref_lines = "\n".join(
        f"{c['kode']} = {c.get('label', '')} ({c.get('padanan', '')})" for c in cw
    )
    user_msg = (
        f"Jenis hewan: {body.jenis_hewan or '-'}\n"
        f"Catatan lapangan:\n{body.teks}\n\n"
        f"TABEL REFERENSI KODE iSIKHNAS:\n{ref_lines}"
    )

    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=AI_MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:
        raise HTTPException(502, f"AI gagal: {e}")

    data = _parse_json(raw)

    usulan = []
    for u in (data.get("usulan_kode") or [])[:5]:
        kode = (u.get("kode") or "").strip()
        if not kode:
            continue
        pen = await db.penyakit.find_one({"kode": kode}, {"_id": 0, "kode": 1, "nama": 1, "kategori": 1})
        if pen:
            usulan.append({"kode": kode, "nama": pen["nama"], "kategori": pen.get("kategori"), "alasan": u.get("alasan", "")})
        elif kode in cw_map:
            c = cw_map[kode]
            usulan.append({"kode": kode, "nama": c.get("label") or kode, "kategori": c.get("kategori"), "alasan": u.get("alasan", "")})
        # kode di luar referensi diabaikan (anti-halusinasi)

    prognosa = data.get("prognosa")
    return {
        "diagnosa_teks": data.get("diagnosa_teks") or "",
        "tindakan": data.get("tindakan"),
        "prognosa": prognosa if prognosa in ("Fausta", "Dubius", "Infausta") else None,
        "usulan_kode": usulan,
        "model": AI_MODEL,
        "catatan": "Saran AI — wajib diperiksa & dikonfirmasi petugas sebelum disimpan.",
    }


SYSTEM_OBAT = (
    "Anda asisten yang membaca LABEL/kemasan obat hewan (veteriner) di Indonesia dari FOTO. "
    "Ekstrak HANYA informasi yang BENAR-BENAR terbaca pada label. JANGAN menebak atau mengarang. "
    "Bila suatu field tidak tertera atau tidak terbaca jelas, isi null.\n"
    "Keterangan field:\n"
    "- nama_dagang: nama merek di kemasan\n"
    "- zat_aktif: bahan/zat aktif (mis. Oksitetrasiklin)\n"
    "- konsentrasi: ANGKA mg per 1 satuan (mis. label '200 mg/ml' -> 200). Hanya angka.\n"
    "- satuan: salah satu ml|tablet|bolus|sachet|kapsul|gram\n"
    "- dosis_per_kg: ANGKA mg/kg bila tertera (sering TIDAK ada di kotak -> null)\n"
    "- rute: IM|IV|SC|oral|topikal bila tertera\n"
    "- waktu_henti_daging_hari: ANGKA hari bila tertera\n"
    "- waktu_henti_susu_jam: ANGKA jam bila tertera\n"
    "Balas HANYA JSON valid, tanpa markdown, tanpa teks lain.\n"
    'Format: {"nama_dagang": str|null, "zat_aktif": str|null, "konsentrasi": number|null, '
    '"satuan": str|null, "dosis_per_kg": number|null, "rute": str|null, '
    '"waktu_henti_daging_hari": number|null, "waktu_henti_susu_jam": number|null}'
)


class GambarIn(BaseModel):
    image_base64: str
    media_type: str = "image/jpeg"


class BacaObatIn(BaseModel):
    image_base64: Optional[str] = None        # kompat lama: 1 foto
    media_type: str = "image/jpeg"
    images: Optional[list[GambarIn]] = None    # baru: bisa beberapa foto (depan/belakang dll)


def _num_or_null(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


class InfoObatIn(BaseModel):
    nama: str


SYSTEM_OBAT_NAMA = (
    "Anda asisten formularium obat hewan (veteriner) di Indonesia. Dari NAMA DAGANG/merek obat "
    "yang diketik petugas, berikan perkiraan data formularium untuk MEMPERCEPAT pengisian. "
    "Ini SARAN AWAL yang WAJIB diverifikasi petugas terhadap kemasan asli — JANGAN dianggap final.\n"
    "Aturan penting:\n"
    "- Jika Anda TIDAK yakin pada suatu angka, isi null (lebih baik kosong daripada salah). "
    "JANGAN mengarang konsentrasi/dosis/waktu henti.\n"
    "- konsentrasi: ANGKA mg per 1 satuan (mis. '200 mg/ml' -> 200).\n"
    "- satuan: salah satu ml|tablet|bolus|sachet|kapsul|gram.\n"
    "- dosis_per_kg: ANGKA mg/kg bila umum diketahui, selain itu null.\n"
    "- rute: IM|IV|SC|oral|topikal bila umum, selain itu null.\n"
    "- waktu_henti_daging_hari / waktu_henti_susu_jam: ANGKA bila umum diketahui, selain itu null.\n"
    "Balas HANYA JSON valid tanpa markdown.\n"
    'Format: {"nama_dagang": str|null, "zat_aktif": str|null, "konsentrasi": number|null, '
    '"satuan": str|null, "dosis_per_kg": number|null, "rute": str|null, '
    '"waktu_henti_daging_hari": number|null, "waktu_henti_susu_jam": number|null}'
)


@router.post("/info-obat")
async def info_obat(body: InfoObatIn, _user=Depends(require_roles("petugas", "admin"))):
    nama = (body.nama or "").strip()
    if len(nama) < 2:
        raise HTTPException(400, "nama obat terlalu pendek")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "AI belum dikonfigurasi (ANTHROPIC_API_KEY kosong)")
    try:
        raw = await _panggil_ai(SYSTEM_OBAT_NAMA, f"Nama dagang obat: {nama[:120]}", max_tokens=400)
    except Exception as e:
        raise HTTPException(502, f"AI gagal: {e}")
    data = _parse_json(raw)
    return {
        "nama_dagang": data.get("nama_dagang") or nama,
        "zat_aktif": data.get("zat_aktif") or None,
        "konsentrasi": _num_or_null(data.get("konsentrasi")),
        "satuan": data.get("satuan") or None,
        "dosis_per_kg": _num_or_null(data.get("dosis_per_kg")),
        "rute": data.get("rute") or None,
        "waktu_henti_daging_hari": _num_or_null(data.get("waktu_henti_daging_hari")),
        "waktu_henti_susu_jam": _num_or_null(data.get("waktu_henti_susu_jam")),
        "model": AI_MODEL,
        "catatan": "Saran AI dari nama — WAJIB diverifikasi dengan kemasan asli sebelum simpan.",
    }


@router.post("/baca-obat")
async def baca_obat(body: BacaObatIn, _user=Depends(require_roles("petugas", "admin"))):
    # Kumpulkan daftar gambar (dukung 1 foto lama atau banyak foto baru)
    gambar = list(body.images or [])
    if not gambar and body.image_base64:
        gambar = [GambarIn(image_base64=body.image_base64, media_type=body.media_type)]
    gambar = [g for g in gambar if g.image_base64][:5]
    if not gambar:
        raise HTTPException(400, "gambar kosong")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "AI belum dikonfigurasi (ANTHROPIC_API_KEY kosong)")
    instruksi = (
        "Baca label obat dari SEMUA foto berikut (bisa beberapa sisi kemasan: depan, belakang, dus). "
        "Gabungkan informasinya menjadi satu, kembalikan JSON sesuai format."
        if len(gambar) > 1 else
        "Baca label obat pada foto ini dan kembalikan JSON sesuai format."
    )
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": g.media_type, "data": g.image_base64}}
        for g in gambar
    ]
    content.append({"type": "text", "text": instruksi})
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=AI_MODEL,
            max_tokens=512,
            system=SYSTEM_OBAT,
            messages=[{"role": "user", "content": content}],
        )
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:
        raise HTTPException(502, f"AI gagal: {e}")

    data = _parse_json(raw)
    return {
        "nama_dagang": data.get("nama_dagang") or None,
        "zat_aktif": data.get("zat_aktif") or None,
        "konsentrasi": _num_or_null(data.get("konsentrasi")),
        "satuan": data.get("satuan") or None,
        "dosis_per_kg": _num_or_null(data.get("dosis_per_kg")),
        "rute": data.get("rute") or None,
        "waktu_henti_daging_hari": _num_or_null(data.get("waktu_henti_daging_hari")),
        "waktu_henti_susu_jam": _num_or_null(data.get("waktu_henti_susu_jam")),
        "model": AI_MODEL,
        "jumlah_foto": len(gambar),
        "catatan": "Hasil baca AI dari label — periksa & koreksi angka sebelum simpan.",
    }


def _parse_json(raw: str) -> dict:
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                pass
    return {"diagnosa_teks": "", "usulan_kode": []}


# ---------------------------------------------------------------------------
# AI baca KTP — ekstrak nama/NIK/alamat untuk MEMPERCEPAT input pendaftaran.
# PDP: foto KTP TIDAK disimpan. Hanya field hasil yang dikembalikan; petugas
# wajib memeriksa & mengoreksi. Endpoint butuh login (petugas/admin).
# ---------------------------------------------------------------------------
SYSTEM_KTP = (
    "Anda asisten input data untuk Puskeswan di Indonesia. Dari foto KTP, baca teks yang TERCETAK "
    "dan kembalikan datanya untuk mempercepat pendaftaran. JANGAN mengarang; jika tidak terbaca, beri null.\n"
    "Balas HANYA JSON valid tanpa markdown.\n"
    'Format: {"nama": str|null, "nik": str|null, "alamat": str|null}'
)


class BacaKtpIn(BaseModel):
    image_base64: str
    media_type: str = "image/jpeg"


@router.post("/baca-ktp")
async def baca_ktp(body: BacaKtpIn, _user=Depends(require_roles("petugas", "admin"))):
    if not body.image_base64:
        raise HTTPException(400, "gambar kosong")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(503, "AI belum dikonfigurasi (ANTHROPIC_API_KEY kosong)")
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=AI_MODEL,
            max_tokens=400,
            system=SYSTEM_KTP,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": body.media_type, "data": body.image_base64}},
                {"type": "text", "text": "Baca KTP ini, kembalikan JSON nama/nik/alamat sesuai format."},
            ]}],
        )
        raw = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:
        raise HTTPException(502, f"AI gagal: {e}")
    data = _parse_json(raw)
    nik = (data.get("nik") or "")
    nik = "".join(ch for ch in str(nik) if ch.isdigit()) or None
    return {
        "nama": data.get("nama") or None,
        "nik": nik,
        "alamat": data.get("alamat") or None,
        "model": AI_MODEL,
        "catatan": "Hasil baca AI dari KTP — foto tidak disimpan. Periksa & koreksi sebelum simpan.",
    }


# ---------------------------------------------------------------------------
# AI susun ternak — dari deskripsi bebas ke daftar ternak terstruktur.
# Tidak menyimpan; mengembalikan draft untuk diperiksa/diedit petugas.
# ---------------------------------------------------------------------------
SYSTEM_TERNAK = (
    "Anda asisten input data ternak untuk Puskeswan di Indonesia. Dari kalimat bebas peternak, "
    "susun daftar ternak terstruktur. JANGAN mengarang detail yang tak disebut.\n"
    "Aturan:\n"
    "- spesies: gunakan istilah umum Indonesia (Sapi, Kambing, Domba, Kerbau, Kuda, Babi, Ayam, Itik, "
    "Kelinci, Anjing, Kucing, Puyuh, Mentok, Angsa). Jika lain, tulis apa adanya.\n"
    "- Jika jumlah > 1 → mode 'populasi' dan isi jml_deklarasi. Jika 1 ekor → mode 'individu'.\n"
    "- jenis_kelamin hanya 'Jantan'/'Betina'/null. ras null jika tak disebut.\n"
    "- Balas HANYA JSON valid tanpa markdown.\n"
    'Format: {"ternak": [{"spesies": str, "ras": str|null, "mode": "individu"|"populasi", '
    '"jml_deklarasi": int|null, "jenis_kelamin": "Jantan"|"Betina"|null, "catatan": str|null}]}'
)


class SusunTernakIn(BaseModel):
    teks: str


async def _panggil_ai(system, teks, max_tokens=700):
    """Panggilan AI teks→teks (mengembalikan string mentah). Melempar bila gagal."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY kosong")
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=api_key)
    resp = await client.messages.create(
        model=AI_MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": teks[:1000]}],
    )
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()


async def susun_ternak_core(teks: str) -> list:
    """Inti susun-ternak — dipakai endpoint & webhook petugas. Mengembalikan list draft."""
    teks = (teks or "").strip()
    if len(teks) < 3:
        return []
    raw = await _panggil_ai(SYSTEM_TERNAK, teks, max_tokens=700)
    data = _parse_json(raw)
    out = []
    for t in (data.get("ternak") or [])[:50]:
        if not isinstance(t, dict) or not t.get("spesies"):
            continue
        mode = "populasi" if t.get("mode") == "populasi" else "individu"
        jml = _num_or_null(t.get("jml_deklarasi"))
        out.append({
            "spesies": str(t.get("spesies")).strip()[:40],
            "ras": (t.get("ras") or None),
            "mode": mode,
            "jml_deklarasi": int(jml) if (mode == "populasi" and jml) else None,
            "jenis_kelamin": t.get("jenis_kelamin") if t.get("jenis_kelamin") in ("Jantan", "Betina") else None,
            "catatan": (t.get("catatan") or None),
        })
    return out


@router.post("/susun-ternak")
async def susun_ternak(body: SusunTernakIn, _user=Depends(require_roles("petugas", "admin"))):
    teks = (body.teks or "").strip()
    if len(teks) < 3:
        raise HTTPException(400, "deskripsi terlalu pendek")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "AI belum dikonfigurasi (ANTHROPIC_API_KEY kosong)")
    try:
        out = await susun_ternak_core(teks)
    except Exception as e:
        raise HTTPException(502, f"AI gagal: {e}")
    return {"ternak": out, "model": AI_MODEL, "catatan": "Draft AI — periksa & edit sebelum simpan."}


# ---------------------------------------------------------------------------
# AI susun pelayanan (untuk jalur PETUGAS via WA) — ekstrak deskripsi bebas
# menjadi draft pelayanan. Angka medis (obat) DIANCHOR ke formularium oleh
# pemanggil, BUKAN dikarang AI. Hasil = DRAFT, difinalisasi petugas di app.
# ---------------------------------------------------------------------------
SYSTEM_PELAYANAN = (
    "Anda asisten input rekam pelayanan kesehatan hewan untuk Puskeswan di Indonesia. "
    "Dari deskripsi bebas PETUGAS, susun draft pelayanan. JANGAN mengarang; kosongkan (null) yang tak disebut. "
    "JANGAN menentukan dosis/aturan pakai obat — cukup tulis NAMA obat & JUMLAH bila disebut.\n"
    "kategori salah satu: KESWAN (pengobatan), VAKSINASI, PKB, GANGREP, IB, LAB, KONSULTASI, ADUAN. "
    "Default KESWAN bila pengobatan/keluhan klinis.\n"
    "Balas HANYA JSON valid tanpa markdown.\n"
    'Format: {"kategori": str, "hewan_teks": str|null, "keluhan": str|null, "tindakan": str|null, '
    '"obat": [{"nama": str, "jumlah": number|null, "satuan": str|null}], '
    '"modalitas": "Pasif"|"Aktif"|"Semiaktif"|null}'
)


async def susun_pelayanan_core(teks: str) -> dict:
    """Inti susun-pelayanan. Mengembalikan dict draft (obat belum dicocokkan formularium)."""
    teks = (teks or "").strip()
    if len(teks) < 3:
        return {}
    raw = await _panggil_ai(SYSTEM_PELAYANAN, teks, max_tokens=700)
    data = _parse_json(raw)
    kat = data.get("kategori")
    if kat not in ("KESWAN", "VAKSINASI", "PKB", "GANGREP", "IB", "LAB", "KONSULTASI", "ADUAN"):
        kat = "KESWAN"
    obat = []
    for o in (data.get("obat") or [])[:20]:
        if isinstance(o, dict) and o.get("nama"):
            obat.append({"nama": str(o["nama"]).strip()[:80],
                         "jumlah": _num_or_null(o.get("jumlah")),
                         "satuan": (o.get("satuan") or None)})
    mod = data.get("modalitas")
    return {
        "kategori": kat,
        "hewan_teks": (data.get("hewan_teks") or None),
        "keluhan": (data.get("keluhan") or None),
        "tindakan": (data.get("tindakan") or None),
        "obat": obat,
        "modalitas": mod if mod in ("Pasif", "Aktif", "Semiaktif") else None,
    }
