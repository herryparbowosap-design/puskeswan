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


class BacaObatIn(BaseModel):
    image_base64: str
    media_type: str = "image/jpeg"


def _num_or_null(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


@router.post("/baca-obat")
async def baca_obat(body: BacaObatIn, _user=Depends(require_roles("petugas", "admin"))):
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
            max_tokens=512,
            system=SYSTEM_OBAT,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": body.media_type, "data": body.image_base64}},
                {"type": "text", "text": "Baca label obat pada foto ini dan kembalikan JSON sesuai format."},
            ]}],
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
