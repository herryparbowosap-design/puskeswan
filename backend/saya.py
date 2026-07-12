"""Beranda Peternak — endpoint swalayan untuk peternak yang login.

Prinsip keamanan: `peternak_id` SELALU diambil dari akun yang login (token),
TIDAK PERNAH dari query/param. Jadi peternak hanya bisa melihat datanya sendiri
dan tak bisa mengintip data peternak lain dengan mengganti id.

Akun peternak ditautkan ke record peternak lewat field `users.peternak_id`,
di-provision oleh admin (lihat auth.py: POST /admin/peternak/{pid}/akun).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from auth import require_roles

router = APIRouter(prefix="/saya", tags=["saya"])


async def _my_peternak(user: dict) -> dict:
    """Ambil record peternak milik akun yang login. 409 bila belum ditautkan."""
    pid = user.get("peternak_id")
    if not pid:
        raise HTTPException(409, "Akun Anda belum ditautkan ke data peternak. Hubungi petugas Puskeswan.")
    p = await get_db().peternak.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Data peternak tertaut tidak ditemukan. Hubungi petugas.")
    return p


@router.get("/profil")
async def profil(user=Depends(require_roles("peternak"))):
    return await _my_peternak(user)


@router.get("/ternak")
async def ternak(user=Depends(require_roles("peternak"))):
    p = await _my_peternak(user)
    return await get_db().ternak.find(
        {"peternak_id": p["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(500).to_list(500)


@router.get("/pelayanan")
async def pelayanan(limit: int = 50, user=Depends(require_roles("peternak"))):
    p = await _my_peternak(user)
    return await get_db().pelayanan.find(
        {"peternak.peternak_id": p["id"]}, {"_id": 0}
    ).sort("tgl", -1).limit(min(max(limit, 1), 200)).to_list(200)


@router.get("/pendaftaran")
async def pendaftaran(user=Depends(require_roles("peternak"))):
    """Permintaan kunjungan yang masih diproses (dicocokkan via peternak_id ATAU kontak)."""
    p = await _my_peternak(user)
    cocok = [{"peternak_id": p["id"]}]
    if p.get("kontak"):
        cocok.append({"kontak": p["kontak"]})
    flt = {"status": {"$in": ["baru", "verifikasi"]}, "$or": cocok}
    return await get_db().pendaftaran.find(
        flt, {"_id": 0, "id": 1, "status": 1, "jenis_layanan": 1, "catatan": 1, "created_at": 1}
    ).sort("created_at", -1).limit(50).to_list(50)


@router.get("/ringkasan")
async def ringkasan(user=Depends(require_roles("peternak"))):
    """Angka ringkas untuk kartu Beranda Peternak."""
    db = get_db()
    p = await _my_peternak(user)
    pid = p["id"]
    jml_ternak = await db.ternak.count_documents({"peternak_id": pid, "status": {"$ne": "nonaktif"}})
    jml_pelayanan = await db.pelayanan.count_documents({"peternak.peternak_id": pid})

    terakhir = await db.pelayanan.find(
        {"peternak.peternak_id": pid}, {"_id": 0, "tgl": 1, "kategori": 1}
    ).sort("tgl", -1).limit(1).to_list(1)
    pelayanan_terakhir = terakhir[0] if terakhir else None

    cocok = [{"peternak_id": pid}]
    if p.get("kontak"):
        cocok.append({"kontak": p["kontak"]})
    pendaftaran_menunggu = await db.pendaftaran.count_documents(
        {"status": {"$in": ["baru", "verifikasi"]}, "$or": cocok}
    )

    return {
        "nama": p.get("nama"),
        "jumlah_ternak": jml_ternak,
        "jumlah_pelayanan": jml_pelayanan,
        "pelayanan_terakhir": pelayanan_terakhir,
        "pendaftaran_menunggu": pendaftaran_menunggu,
    }
