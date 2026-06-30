"""Master obat — formularium ringkas untuk kalkulator dosis & pencatatan pemakaian.
7 field 'minimal bertanggung jawab': nama dagang, zat aktif, konsentrasi, satuan,
dosis/kg, rute, waktu henti (daging/susu). Konsentrasi = mg per 1 satuan
(mis. 200 = 200 mg/ml) — jembatan mg -> ml agar dosis tidak salah."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import require_roles, current_user

router = APIRouter(prefix="/obat", tags=["obat"])


class ObatIn(BaseModel):
    nama_dagang: str
    zat_aktif: Optional[str] = None
    konsentrasi: Optional[float] = None        # mg per 1 satuan
    satuan: str = "ml"                          # ml | tablet | bolus | sachet | ...
    dosis_per_kg: Optional[float] = None        # mg/kg BB
    rute: Optional[str] = None                  # IM | IV | SC | oral | topikal
    waktu_henti_daging_hari: Optional[int] = None
    waktu_henti_susu_jam: Optional[int] = None
    aktif: bool = True


class ObatPatch(BaseModel):
    nama_dagang: Optional[str] = None
    zat_aktif: Optional[str] = None
    konsentrasi: Optional[float] = None
    satuan: Optional[str] = None
    dosis_per_kg: Optional[float] = None
    rute: Optional[str] = None
    waktu_henti_daging_hari: Optional[int] = None
    waktu_henti_susu_jam: Optional[int] = None
    aktif: Optional[bool] = None


@router.get("")
async def list_obat(q: Optional[str] = None, semua: bool = False, _user=Depends(current_user)):
    flt = {} if semua else {"aktif": {"$ne": False}}
    if q:
        flt["$or"] = [
            {"nama_dagang": {"$regex": q, "$options": "i"}},
            {"zat_aktif": {"$regex": q, "$options": "i"}},
        ]
    return await get_db().obat.find(flt, {"_id": 0}).sort("nama_dagang", 1).to_list(500)


@router.post("")
async def create_obat(body: ObatIn, user=Depends(require_roles("petugas", "admin"))):
    now = datetime.now(timezone.utc)
    doc = {"id": uuid.uuid4().hex, **body.model_dump(), "created_by": user["id"], "created_at": now}
    await get_db().obat.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/{oid}")
async def update_obat(oid: str, body: ObatPatch, user=Depends(require_roles("petugas", "admin"))):
    upd = body.model_dump(exclude_unset=True)
    if not upd:
        raise HTTPException(400, "tidak ada perubahan")
    upd["updated_at"] = datetime.now(timezone.utc)
    r = await get_db().obat.update_one({"id": oid}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "obat tidak ditemukan")
    return await get_db().obat.find_one({"id": oid}, {"_id": 0})


@router.delete("/{oid}")
async def delete_obat(oid: str, _user=Depends(require_roles("admin"))):
    r = await get_db().obat.delete_one({"id": oid})
    if r.deleted_count == 0:
        raise HTTPException(404, "obat tidak ditemukan")
    return {"ok": True}
