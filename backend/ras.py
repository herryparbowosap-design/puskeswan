"""Master ras ternak — cascade dari spesies. GET publik (data referensi)."""
from typing import Optional

from fastapi import APIRouter

from db import get_db

router = APIRouter(prefix="/ras", tags=["ras"])


@router.get("/spesies")
async def list_spesies():
    return sorted(await get_db().ras_ternak.distinct("spesies"))


@router.get("")
async def list_ras(spesies: Optional[str] = None):
    flt = {"spesies": spesies} if spesies else {}
    return await get_db().ras_ternak.find(flt, {"_id": 0}).sort("nama", 1).to_list(500)
