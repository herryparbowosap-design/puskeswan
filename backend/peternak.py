"""Peternak — create, list/search, get. Registry opsional koordinat."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import current_user, require_roles

router = APIRouter(prefix="/peternak", tags=["peternak"])


class KoordinatIn(BaseModel):
    lat: float
    lng: float


class PeternakIn(BaseModel):
    nama: str
    kontak: str
    nik: Optional[str] = None
    kapanewon_id: Optional[str] = None
    kalurahan_id: Optional[str] = None
    padukuhan_id: Optional[str] = None
    alamat_detail: Optional[str] = None
    koordinat: Optional[KoordinatIn] = None
    catatan: Optional[str] = None


@router.post("")
async def create_peternak(body: PeternakIn, user=Depends(require_roles("petugas", "admin"))):
    doc = body.model_dump()
    if body.koordinat:
        doc["koordinat"] = {"type": "Point", "coordinates": [body.koordinat.lng, body.koordinat.lat]}
    doc.update({
        "id": uuid.uuid4().hex,
        "dibuat_oleh": user["id"],
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
    })
    await get_db().peternak.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_peternak(q: Optional[str] = None, limit: int = 50, _user=Depends(current_user)):
    flt = {}
    if q:
        flt = {"$or": [
            {"nama": {"$regex": q, "$options": "i"}},
            {"kontak": {"$regex": q, "$options": "i"}},
            {"nik": {"$regex": q, "$options": "i"}},
        ]}
    return await get_db().peternak.find(flt, {"_id": 0}).sort("created_at", -1).limit(min(limit, 200)).to_list(200)


@router.get("/{pid}")
async def get_peternak(pid: str, _user=Depends(current_user)):
    p = await get_db().peternak.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "peternak tidak ditemukan")
    return p


class PeternakPatch(BaseModel):
    nama: Optional[str] = None
    kontak: Optional[str] = None
    nik: Optional[str] = None
    kapanewon_id: Optional[str] = None
    kalurahan_id: Optional[str] = None
    padukuhan_id: Optional[str] = None
    alamat_detail: Optional[str] = None
    koordinat: Optional[KoordinatIn] = None
    catatan: Optional[str] = None


@router.patch("/{pid}")
async def update_peternak(pid: str, body: PeternakPatch, user=Depends(require_roles("petugas", "admin"))):
    db = get_db()
    upd = body.model_dump(exclude_unset=True)
    if "koordinat" in upd:
        upd["koordinat"] = (
            {"type": "Point", "coordinates": [body.koordinat.lng, body.koordinat.lat]}
            if body.koordinat else None
        )
    if not upd:
        raise HTTPException(400, "tidak ada perubahan")
    upd["updated_at"] = datetime.now(timezone.utc)
    r = await db.peternak.update_one({"id": pid}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "peternak tidak ditemukan")
    return await db.peternak.find_one({"id": pid}, {"_id": 0})


@router.delete("/{pid}")
async def delete_peternak(pid: str, cascade: bool = False, _user=Depends(require_roles("admin"))):
    db = get_db()
    if not await db.peternak.find_one({"id": pid}):
        raise HTTPException(404, "peternak tidak ditemukan")
    n_ternak = await db.ternak.count_documents({"peternak_id": pid})
    n_pel = await db.pelayanan.count_documents({"peternak.peternak_id": pid})
    if (n_ternak or n_pel) and not cascade:
        raise HTTPException(409, f"Peternak punya {n_ternak} ternak & {n_pel} pelayanan. Hapus paksa untuk menghapus semuanya.")
    if cascade:
        tids = [t["id"] for t in await db.ternak.find({"peternak_id": pid}, {"id": 1}).to_list(5000)]
        if tids:
            await db.mutasi_ternak.delete_many({"ternak_id": {"$in": tids}})
        await db.ternak.delete_many({"peternak_id": pid})
        await db.pelayanan.delete_many({"peternak.peternak_id": pid})
    await db.peternak.delete_one({"id": pid})
    return {"ok": True, "dihapus": {"peternak": 1, "ternak": n_ternak if cascade else 0, "pelayanan": n_pel if cascade else 0}}
