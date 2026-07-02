"""Pelayanan — tulang punggung pencatatan kunjungan keswan.
Slice 1c-i: fokus kategori KESWAN (pengobatan). Kategori lain menyusul."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import current_user, require_roles

router = APIRouter(prefix="/pelayanan", tags=["pelayanan"])

KATEGORI_DIDUKUNG = {"KESWAN", "VAKSINASI", "PKB", "GANGREP", "IB", "LAB", "DESINFEKSI", "PEMBINAAN", "KONSULTASI", "ADUAN"}


class FotoIn(BaseModel):
    key: str
    content_type: str = "image/jpeg"


class HewanIn(BaseModel):
    ternak_id: Optional[str] = None
    jenis_hewan: str
    kelamin: Optional[str] = None
    umur: Optional[str] = None
    jumlah: int = 1


class ObatPakaiIn(BaseModel):
    obat_id: Optional[str] = None
    nama: str                                 # snapshot nama dagang
    jumlah: float
    satuan: str                               # snapshot satuan (ml/tablet/…)
    catatan: Optional[str] = None             # mis. "20 mg/kg × 300 kg ÷ 200 mg/ml"


class PelayananIn(BaseModel):
    kategori: str = "KESWAN"
    tgl: Optional[str] = None                 # ISO YYYY-MM-DD; default hari ini
    peternak_id: str
    hewan: Optional[HewanIn] = None
    berat_kg: Optional[float] = None
    obat: Optional[list[ObatPakaiIn]] = None
    detail: Optional[dict] = None             # field spesifik per kategori (vaksin, PKB, dll)
    penyakit_id: Optional[str] = None         # = kode iSIKHNAS (mis. "ND")
    diagnosa_teks: Optional[str] = None
    isikhnas_id: Optional[str] = None
    tindakan: Optional[str] = None
    prognosa: Optional[str] = None            # Fausta | Dubius | Infausta
    modalitas: Optional[str] = None           # Pasif | Aktif | Semiaktif | Yanduwan/Vaksinasi
    metode_layanan: Optional[str] = None
    keterangan: Optional[str] = None
    foto: Optional[list[FotoIn]] = None
    sumber: Optional[str] = None               # kanal input: manual | wa-petugas
    draft: Optional[bool] = None               # True = perlu dilengkapi (mis. dari WA)


@router.post("")
async def create_pelayanan(body: PelayananIn, user=Depends(require_roles("petugas", "admin"))):
    if body.kategori not in KATEGORI_DIDUKUNG:
        raise HTTPException(400, f"kategori {body.kategori} belum didukung (menyusul)")
    db = get_db()
    p = await db.peternak.find_one({"id": body.peternak_id}, {"_id": 0})
    if not p:
        raise HTTPException(400, "peternak tidak ditemukan")
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex,
        "kategori": body.kategori,
        "tgl": body.tgl or now.date().isoformat(),
        "petugas_id": user["id"],
        "peternak": {
            "peternak_id": p["id"],
            "nama": p["nama"],
            "wilayah_id": p.get("kalurahan_id"),
            "alamat": p.get("alamat_detail"),
        },
        "hewan": body.hewan.model_dump() if body.hewan else None,
        "berat_kg": body.berat_kg,
        "obat": [o.model_dump() for o in (body.obat or [])],
        "penyakit_id": body.penyakit_id,
        "diagnosa_teks": body.diagnosa_teks,
        "isikhnas_id": body.isikhnas_id,
        "tindakan": body.tindakan,
        "prognosa": body.prognosa,
        "modalitas": body.modalitas,
        "metode_layanan": body.metode_layanan,
        "keterangan": body.keterangan,
        "foto": [
            {"key": f.key, "content_type": f.content_type, "diunggah_oleh": user["id"], "diunggah_pada": now}
            for f in (body.foto or [])
        ],
        "detail": {**(body.detail or {}), "kategori": body.kategori},
        "sumber_input": body.sumber or "manual",
        "draft": bool(body.draft),
        "perlu_dilengkapi": bool(body.draft),
        "dikonfirmasi_oleh": None,
        "created_by": user["id"],
        "created_at": now,
    }
    await db.pelayanan.insert_one(doc)
    doc.pop("_id", None)
    # Pengurangan stok otomatis (best-effort, tak memblok bila gagal)
    try:
        from stok import potong_stok_pelayanan
        ringkas = await potong_stok_pelayanan(
            db, doc["id"], doc.get("tgl"),
            [o.model_dump() for o in (body.obat or [])], user
        )
        if ringkas["dipotong"] or ringkas["dilewati"]:
            await db.pelayanan.update_one({"id": doc["id"]}, {"$set": {"stok": ringkas}})
            doc["stok"] = ringkas
    except Exception:
        pass
    return doc


@router.get("")
async def list_pelayanan(
    peternak_id: Optional[str] = None,
    kategori: Optional[str] = None,
    tgl_dari: Optional[str] = None,
    tgl_sampai: Optional[str] = None,
    limit: int = 100,
    _user=Depends(current_user),
):
    flt = {}
    if peternak_id:
        flt["peternak.peternak_id"] = peternak_id
    if kategori:
        flt["kategori"] = kategori
    if tgl_dari or tgl_sampai:
        rng = {}
        if tgl_dari:
            rng["$gte"] = tgl_dari
        if tgl_sampai:
            rng["$lte"] = tgl_sampai
        flt["tgl"] = rng
    return await get_db().pelayanan.find(flt, {"_id": 0}).sort("tgl", -1).limit(min(limit, 500)).to_list(500)


@router.get("/{pid}")
async def get_pelayanan(pid: str, _user=Depends(current_user)):
    d = await get_db().pelayanan.find_one({"id": pid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "pelayanan tidak ditemukan")
    return d


@router.delete("/{pid}")
async def delete_pelayanan(pid: str, _user=Depends(require_roles("admin"))):
    db = get_db()
    r = await db.pelayanan.delete_one({"id": pid})
    if r.deleted_count == 0:
        raise HTTPException(404, "pelayanan tidak ditemukan")
    try:
        from stok import kembalikan_stok_pelayanan
        await kembalikan_stok_pelayanan(db, pid)
    except Exception:
        pass
    return {"ok": True}
