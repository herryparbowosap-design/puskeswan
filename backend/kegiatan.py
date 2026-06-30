"""Kegiatan massal — vaksinasi/desinfeksi/pembinaan dll yang TIDAK terikat
ke satu peternak. Dicatat per wilayah (kalurahan) dengan jumlah sasaran.

Masuk ke rekap bulanan sebagai seksi terpisah ("Kegiatan massal") agar tidak
dobel-hitung dengan pelayanan per-peternak.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db import get_db
from auth import require_roles

router = APIRouter(prefix="/kegiatan", tags=["kegiatan"])

KATEGORI_DIDUKUNG = {"VAKSINASI", "DESINFEKSI", "PEMBINAAN", "PKB", "GANGREP", "IB", "LAB", "KONSULTASI", "ADUAN", "KESWAN"}


class ObatPakai(BaseModel):
    obat_id: Optional[str] = None
    nama: str
    jumlah: float
    satuan: Optional[str] = None
    catatan: Optional[str] = None


class FotoRef(BaseModel):
    key: str
    content_type: Optional[str] = None


class KegiatanIn(BaseModel):
    kategori: str
    tgl: Optional[str] = None
    modalitas: Optional[str] = None
    kalurahan_id: Optional[str] = None
    lokasi: Optional[str] = None
    jumlah_sasaran: Optional[int] = None
    detail: Optional[dict] = None
    obat: Optional[list[ObatPakai]] = None
    keterangan: Optional[str] = None
    foto: Optional[list[FotoRef]] = None


@router.post("")
async def create_kegiatan(body: KegiatanIn, user=Depends(require_roles("petugas", "admin"))):
    if body.kategori not in KATEGORI_DIDUKUNG:
        raise HTTPException(400, f"kategori {body.kategori} belum didukung")
    db = get_db()
    wil_nama = None
    if body.kalurahan_id:
        w = await db.wilayah.find_one({"id": body.kalurahan_id}, {"_id": 0, "nama": 1})
        wil_nama = w["nama"] if w else None
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex,
        "kategori": body.kategori,
        "tgl": body.tgl or now.date().isoformat(),
        "petugas_id": user["id"],
        "modalitas": body.modalitas,
        "kalurahan_id": body.kalurahan_id,
        "wilayah_nama": wil_nama,
        "lokasi": body.lokasi,
        "jumlah_sasaran": body.jumlah_sasaran,
        "obat": [o.model_dump() for o in (body.obat or [])],
        "keterangan": body.keterangan,
        "foto": [
            {"key": f.key, "content_type": f.content_type, "diunggah_oleh": user["id"], "diunggah_pada": now}
            for f in (body.foto or [])
        ],
        "detail": {**(body.detail or {}), "kategori": body.kategori},
        "created_by": user["id"],
        "created_at": now,
    }
    await db.kegiatan.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_kegiatan(
    tahun: Optional[int] = None,
    bulan: Optional[int] = None,
    kalurahan_id: Optional[str] = None,
    limit: int = 200,
    _user=Depends(require_roles("petugas", "admin")),
):
    flt = {}
    if tahun and bulan:
        s_dari = f"{tahun:04d}-{bulan:02d}-01"
        s_sampai = f"{tahun:04d}-{bulan + 1:02d}-01" if bulan < 12 else f"{tahun + 1:04d}-01-01"
        flt["tgl"] = {"$gte": s_dari, "$lt": s_sampai}
    if kalurahan_id:
        flt["kalurahan_id"] = kalurahan_id
    n = min(max(limit, 1), 500)
    return await get_db().kegiatan.find(flt, {"_id": 0}).sort("tgl", -1).limit(n).to_list(n)


@router.delete("/{kid}")
async def delete_kegiatan(kid: str, _user=Depends(require_roles("admin"))):
    r = await get_db().kegiatan.delete_one({"id": kid})
    if r.deleted_count == 0:
        raise HTTPException(404, "kegiatan tidak ditemukan")
    return {"ok": True}
