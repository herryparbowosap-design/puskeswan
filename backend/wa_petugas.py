"""Whitelist nomor WA petugas — memetakan nomor WhatsApp ke akun petugas.

Dipakai webhook untuk membedakan pesan dari PETUGAS (terdaftar) vs PETERNAK
(nomor tak dikenal → alur pendaftaran biasa). Setiap entri petugas via WA nanti
diatribusikan ke akun ini (akuntabilitas). Admin yang mengelola; tidak ada PIN
(pengaman = atribusi + bisa dicabut + pelayanan via WA selalu draft).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import require_roles
from notifikasi import normalisasi_no

router = APIRouter(prefix="/wa-petugas", tags=["wa-petugas"])


class WaPetugasIn(BaseModel):
    user_id: str
    no: str
    aktif: bool = True


async def cari_petugas_by_no(db, no_wa) -> Optional[dict]:
    """Lookup nomor (apa adanya / ternormalisasi) → entri petugas aktif, atau None."""
    n = normalisasi_no(no_wa)
    if not n:
        return None
    return await db.wa_petugas.find_one({"no": n, "aktif": True}, {"_id": 0})


@router.get("")
async def list_wa_petugas(_user=Depends(require_roles("admin"))):
    return await get_db().wa_petugas.find({}, {"_id": 0}).sort("nama", 1).to_list(500)


@router.post("")
async def tambah_wa_petugas(body: WaPetugasIn, user=Depends(require_roles("admin"))):
    db = get_db()
    no = normalisasi_no(body.no)
    if not no:
        raise HTTPException(400, "nomor WA tidak valid")
    u = await db.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1, "nama": 1, "username": 1, "roles": 1})
    if not u:
        raise HTTPException(404, "akun petugas tidak ditemukan")
    # satu nomor hanya untuk satu petugas
    lain = await db.wa_petugas.find_one({"no": no, "user_id": {"$ne": body.user_id}})
    if lain:
        raise HTTPException(409, f"nomor sudah terdaftar untuk {lain.get('nama')}")
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex,
        "no": no,
        "user_id": u["id"],
        "nama": u.get("nama"),
        "username": u.get("username"),
        "aktif": body.aktif,
        "created_by": user["id"],
        "created_at": now,
    }
    # upsert per (no) — daftar ulang menimpa
    await db.wa_petugas.update_one({"no": no}, {"$set": doc}, upsert=True)
    return doc


@router.patch("/{wid}")
async def ubah_aktif(wid: str, aktif: bool, _user=Depends(require_roles("admin"))):
    r = await get_db().wa_petugas.update_one({"id": wid}, {"$set": {"aktif": aktif}})
    if r.matched_count == 0:
        raise HTTPException(404, "entri tidak ditemukan")
    return {"ok": True, "aktif": aktif}


@router.delete("/{wid}")
async def hapus_wa_petugas(wid: str, _user=Depends(require_roles("admin"))):
    r = await get_db().wa_petugas.delete_one({"id": wid})
    if r.deleted_count == 0:
        raise HTTPException(404, "entri tidak ditemukan")
    return {"ok": True}
