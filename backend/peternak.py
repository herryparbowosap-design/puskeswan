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
