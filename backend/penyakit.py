"""Master penyakit iSIKHNAS — pencarian untuk pemilihan kode. GET publik."""
from typing import Optional

from fastapi import APIRouter

from db import get_db

router = APIRouter(prefix="/penyakit", tags=["penyakit"])


@router.get("")
async def cari_penyakit(q: Optional[str] = None, kategori: Optional[str] = None, limit: int = 30):
    flt = {}
    if kategori:
        flt["kategori"] = kategori
    if q:
        flt["$or"] = [
            {"nama": {"$regex": q, "$options": "i"}},
            {"kode": {"$regex": q, "$options": "i"}},
            {"alternatif": {"$regex": q, "$options": "i"}},
        ]
    return await get_db().penyakit.find(flt, {"_id": 0}).sort("nama", 1).limit(min(limit, 100)).to_list(100)
