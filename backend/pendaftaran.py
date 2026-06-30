"""Pendaftaran mandiri (channel-agnostic).

Pemilik/peternak mengajukan IDENTITAS + TERNAK lewat pintu apa pun (web/QR,
nanti WA). Data masuk ANTRIAN (status 'baru') — BUKAN data resmi. Petugas/admin
lalu KONFIRMASI (idealnya tatap muka) untuk menjadikannya peternak+ternak resmi.

Prinsip: PERMOHONAN dipisah dari REKAM MEDIS. Pendaftaran hanya identitas+ternak;
diagnosa/obat/iSIKHNAS tetap diisi petugas lewat /pelayanan setelah memeriksa.
Gerbang konfirmasi manusia menjaga data tetap bersih (anti spam/duplikat/palsu).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db
from auth import require_roles
import peternak as peternak_mod
import ternak as ternak_mod

router = APIRouter(prefix="/pendaftaran", tags=["pendaftaran"])


class KoordinatIn(BaseModel):
    lat: float
    lng: float


class TernakDraft(BaseModel):
    spesies: str
    ras_id: Optional[str] = None
    mode: str = "individu"
    eartag: Optional[str] = None
    jenis_kelamin: Optional[str] = None
    tgl_lahir: Optional[str] = None
    jml_deklarasi: Optional[int] = None


class PendaftaranIn(BaseModel):
    nama: str
    kontak: str
    nik: Optional[str] = None
    kapanewon_id: Optional[str] = None
    kalurahan_id: Optional[str] = None
    padukuhan_id: Optional[str] = None
    alamat_detail: Optional[str] = None
    koordinat: Optional[KoordinatIn] = None
    catatan: Optional[str] = None
    ternak: list[TernakDraft] = []
    sumber: str = "web"                 # penanda kanal: web | qr | wa | kios


class KonfirmasiIn(BaseModel):
    """Data FINAL (boleh diedit petugas di layar sebelum konfirmasi)."""
    nama: str
    kontak: str
    nik: Optional[str] = None
    kapanewon_id: Optional[str] = None
    kalurahan_id: Optional[str] = None
    padukuhan_id: Optional[str] = None
    alamat_detail: Optional[str] = None
    koordinat: Optional[KoordinatIn] = None
    ternak: list[TernakDraft] = []


@router.post("")
async def buat_pendaftaran(body: PendaftaranIn):
    """PUBLIK — pintu mandiri (web/QR). Hasil masuk antrian, BUKAN data resmi."""
    if not body.nama.strip() or not body.kontak.strip():
        raise HTTPException(400, "nama & kontak wajib diisi")
    if len(body.ternak) > 50:
        raise HTTPException(400, "terlalu banyak ternak dalam satu pendaftaran")
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex,
        "status": "baru",
        "sumber": body.sumber or "web",
        "nama": body.nama.strip(),
        "kontak": body.kontak.strip(),
        "nik": body.nik,
        "kapanewon_id": body.kapanewon_id,
        "kalurahan_id": body.kalurahan_id,
        "padukuhan_id": body.padukuhan_id,
        "alamat_detail": body.alamat_detail,
        "koordinat": {"type": "Point", "coordinates": [body.koordinat.lng, body.koordinat.lat]} if body.koordinat else None,
        "catatan": body.catatan,
        "ternak": [t.model_dump() for t in body.ternak],
        "peternak_id": None,
        "created_at": now,
    }
    await get_db().pendaftaran.insert_one(doc)
    return {"ok": True, "id": doc["id"], "status": "baru",
            "pesan": "Pendaftaran diterima. Menunggu verifikasi petugas."}


@router.get("")
async def list_pendaftaran(status: Optional[str] = "baru", _user=Depends(require_roles("petugas", "admin"))):
    flt = {} if not status or status == "semua" else {"status": status}
    return await get_db().pendaftaran.find(flt, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/count")
async def count_baru(_user=Depends(require_roles("petugas", "admin"))):
    return {"baru": await get_db().pendaftaran.count_documents({"status": "baru"})}


@router.get("/{pid}")
async def get_pendaftaran(pid: str, _user=Depends(require_roles("petugas", "admin"))):
    d = await get_db().pendaftaran.find_one({"id": pid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "pendaftaran tidak ditemukan")
    return d


@router.post("/{pid}/konfirmasi")
async def konfirmasi(pid: str, body: KonfirmasiIn, user=Depends(require_roles("petugas", "admin"))):
    db = get_db()
    d = await db.pendaftaran.find_one({"id": pid})
    if not d:
        raise HTTPException(404, "pendaftaran tidak ditemukan")
    if d.get("status") == "dikonfirmasi":
        raise HTTPException(409, "pendaftaran sudah dikonfirmasi")

    p = await peternak_mod.create_peternak(
        peternak_mod.PeternakIn(
            nama=body.nama, kontak=body.kontak, nik=body.nik,
            kapanewon_id=body.kapanewon_id, kalurahan_id=body.kalurahan_id, padukuhan_id=body.padukuhan_id,
            alamat_detail=body.alamat_detail,
            koordinat=peternak_mod.KoordinatIn(lat=body.koordinat.lat, lng=body.koordinat.lng) if body.koordinat else None,
        ),
        user=user,
    )
    n_ternak = 0
    for t in body.ternak:
        await ternak_mod.create_ternak(
            ternak_mod.TernakIn(
                peternak_id=p["id"], spesies=t.spesies, ras_id=t.ras_id, mode=t.mode,
                eartag=t.eartag, jenis_kelamin=t.jenis_kelamin, tgl_lahir=t.tgl_lahir, jml_deklarasi=t.jml_deklarasi,
            ),
            user=user,
        )
        n_ternak += 1

    await db.pendaftaran.update_one({"id": pid}, {"$set": {
        "status": "dikonfirmasi", "peternak_id": p["id"],
        "dikonfirmasi_oleh": user["id"], "dikonfirmasi_pada": datetime.now(timezone.utc),
    }})
    return {"ok": True, "peternak": p, "ternak_dibuat": n_ternak}


@router.post("/{pid}/tolak")
async def tolak(pid: str, user=Depends(require_roles("petugas", "admin"))):
    r = await get_db().pendaftaran.update_one(
        {"id": pid, "status": {"$ne": "dikonfirmasi"}},
        {"$set": {"status": "ditolak", "ditolak_oleh": user["id"], "ditolak_pada": datetime.now(timezone.utc)}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "pendaftaran tidak ditemukan / sudah dikonfirmasi")
    return {"ok": True, "status": "ditolak"}
