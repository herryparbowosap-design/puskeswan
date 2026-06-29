"""Ternak — create, list/filter, ras cascade, status via mutasi."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import current_user, require_roles

router = APIRouter(prefix="/ternak", tags=["ternak"])

STATUS_DARI_MUTASI = {"mati": "mati", "jual": "dijual", "potong": "dipotong"}


class TernakIn(BaseModel):
    peternak_id: str
    spesies: str
    ras_id: Optional[str] = None
    mode: str = "individu"            # individu | populasi
    eartag: Optional[str] = None
    jenis_kelamin: Optional[str] = None
    tgl_lahir: Optional[str] = None
    jml_deklarasi: Optional[int] = None


@router.post("")
async def create_ternak(body: TernakIn, user=Depends(require_roles("petugas", "admin"))):
    db = get_db()
    if not await db.peternak.find_one({"id": body.peternak_id}):
        raise HTTPException(400, "peternak tidak ditemukan")
    doc = body.model_dump()
    doc.update({
        "id": uuid.uuid4().hex,
        "status": "aktif",
        "tgl_status": None,
        "jml_verifikasi": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": None,
    })
    await db.ternak.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_ternak(
    peternak_id: Optional[str] = None,
    status: Optional[str] = None,
    _user=Depends(current_user),
):
    flt = {}
    if peternak_id:
        flt["peternak_id"] = peternak_id
    if status:
        flt["status"] = status
    return await get_db().ternak.find(flt, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)


class MutasiIn(BaseModel):
    jenis: str                        # lahir | mati | jual | beli | potong
    jumlah: int = 1
    catatan: Optional[str] = None


@router.post("/{tid}/mutasi")
async def catat_mutasi(tid: str, body: MutasiIn, user=Depends(require_roles("petugas", "admin"))):
    db = get_db()
    t = await db.ternak.find_one({"id": tid})
    if not t:
        raise HTTPException(404, "ternak tidak ditemukan")
    now = datetime.now(timezone.utc)
    await db.mutasi_ternak.insert_one({
        "id": uuid.uuid4().hex,
        "ternak_id": tid,
        "jenis": body.jenis,
        "jumlah": body.jumlah,
        "tgl": now,
        "catatan": body.catatan,
        "dicatat_oleh": user["id"],
        "created_at": now,
    })
    new_status = STATUS_DARI_MUTASI.get(body.jenis)
    if new_status:
        await db.ternak.update_one(
            {"id": tid},
            {"$set": {"status": new_status, "tgl_status": now, "updated_at": now}},
        )
    return {"ok": True, "status_baru": new_status or t.get("status")}
