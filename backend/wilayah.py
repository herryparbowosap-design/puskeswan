"""Wilayah bertingkat — cascade kapanewon > kalurahan > padukuhan.
GET publik (data referensi); POST hanya admin."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from db import get_db
from auth import require_roles

router = APIRouter(prefix="/wilayah", tags=["wilayah"])


@router.get("")
async def list_wilayah(
    level: Optional[str] = None,
    parent_id: Optional[str] = None,
    q: Optional[str] = None,
):
    flt = {}
    if level:
        flt["level"] = level
    if parent_id:
        flt["parent_id"] = parent_id
    if q:
        flt["nama"] = {"$regex": q, "$options": "i"}
    return await get_db().wilayah.find(flt, {"_id": 0}).sort("nama", 1).to_list(2000)


class WilayahIn(BaseModel):
    nama: str
    level: str            # kapanewon | kalurahan | padukuhan
    parent_id: Optional[str] = None
    kode: Optional[str] = None


@router.post("")
async def create_wilayah(body: WilayahIn, _user=Depends(require_roles("admin"))):
    doc = body.model_dump()
    doc["id"] = uuid.uuid4().hex
    await get_db().wilayah.insert_one(doc)
    doc.pop("_id", None)
    return doc
