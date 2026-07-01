"""Modul Stok — obat & alat kesehatan. Berbasis KARTU STOK (transaksi):
saldo = akumulasi transaksi, bukan angka yang diedit langsung.

Jenis transaksi:
  - masuk        : penerimaan (pembelian/droping/hibah). Boleh batch + kedaluwarsa.
  - keluar       : pemakaian/rusak/kedaluwarsa/dibuang (manual). (Pengurangan
                   otomatis dari pelayanan menyusul di slice berikutnya.)
  - penyesuaian  : koreksi (mis. hasil opname). jumlah bertanda (bisa +/-).

Setiap transaksi menyimpan `mutasi` (efek bertanda ke saldo) agar saldo = Σ mutasi.
Slice ini melacak SALDO TOTAL per item; batch/ED dicatat sebagai metadata + daftar
"mendekati kedaluwarsa" (pelacakan sisa per-batch/FEFO menyusul).
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db import get_db
from auth import require_roles

router = APIRouter(prefix="/stok", tags=["stok"])

TIPE = {"obat", "alkes"}
JENIS = {"masuk", "keluar", "penyesuaian"}


class ItemIn(BaseModel):
    tipe: str = "obat"
    nama: str
    satuan: str
    obat_id: Optional[str] = None          # tautan opsional ke formularium obat
    stok_minimum: Optional[float] = None    # ambang peringatan stok menipis
    aktif: bool = True


class TransaksiIn(BaseModel):
    item_id: str
    jenis: str                              # masuk | keluar | penyesuaian
    jumlah: float                           # masuk/keluar: magnitudo; penyesuaian: bertanda
    tgl: Optional[str] = None
    batch: Optional[str] = None
    exp: Optional[str] = None               # ISO YYYY-MM-DD (obat masuk)
    sumber: Optional[str] = None            # pembelian/droping/hibah/pemakaian/rusak/kedaluwarsa/opname
    catatan: Optional[str] = None


async def _saldo_map(db, item_ids=None):
    flt = {"item_id": {"$in": item_ids}} if item_ids is not None else {}
    txs = await db.stok_transaksi.find(flt, {"_id": 0, "item_id": 1, "mutasi": 1}).to_list(100000)
    m = defaultdict(float)
    for t in txs:
        m[t["item_id"]] += t.get("mutasi", 0) or 0
    return m


def _rapikan(x):
    """Tampilkan bilangan bulat tanpa .0."""
    try:
        f = float(x)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return x


# --------------------------------------------------------------- ITEM
@router.get("/item")
async def list_item(
    tipe: Optional[str] = None,
    _user=Depends(require_roles("petugas", "admin")),
):
    db = get_db()
    flt = {}
    if tipe in TIPE:
        flt["tipe"] = tipe
    items = await db.stok_item.find(flt, {"_id": 0}).sort("nama", 1).to_list(2000)
    saldo = await _saldo_map(db)
    for it in items:
        s = saldo.get(it["id"], 0)
        it["saldo"] = _rapikan(s)
        it["stok_rendah"] = it.get("stok_minimum") is not None and s <= it["stok_minimum"]
    return items


@router.post("/item")
async def create_item(body: ItemIn, user=Depends(require_roles("petugas", "admin"))):
    if body.tipe not in TIPE:
        raise HTTPException(400, "tipe harus obat/alkes")
    if not body.nama.strip() or not body.satuan.strip():
        raise HTTPException(400, "nama & satuan wajib")
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex,
        "tipe": body.tipe,
        "nama": body.nama.strip(),
        "satuan": body.satuan.strip(),
        "obat_id": body.obat_id,
        "stok_minimum": body.stok_minimum,
        "aktif": body.aktif,
        "created_by": user["id"],
        "created_at": now,
    }
    await db.stok_item.insert_one(doc)
    doc.pop("_id", None)
    doc["saldo"] = 0
    doc["stok_rendah"] = False
    return doc


@router.patch("/item/{iid}")
async def edit_item(iid: str, body: ItemIn, _user=Depends(require_roles("petugas", "admin"))):
    if body.tipe not in TIPE:
        raise HTTPException(400, "tipe harus obat/alkes")
    r = await get_db().stok_item.update_one({"id": iid}, {"$set": {
        "tipe": body.tipe, "nama": body.nama.strip(), "satuan": body.satuan.strip(),
        "obat_id": body.obat_id, "stok_minimum": body.stok_minimum, "aktif": body.aktif,
    }})
    if r.matched_count == 0:
        raise HTTPException(404, "item tidak ditemukan")
    return {"ok": True}


@router.delete("/item/{iid}")
async def delete_item(iid: str, cascade: bool = False, _user=Depends(require_roles("admin"))):
    db = get_db()
    n_tx = await db.stok_transaksi.count_documents({"item_id": iid})
    if n_tx and not cascade:
        raise HTTPException(409, f"item punya {n_tx} transaksi; hapus dengan ?cascade=true untuk force")
    if cascade:
        await db.stok_transaksi.delete_many({"item_id": iid})
    r = await db.stok_item.delete_one({"id": iid})
    if r.deleted_count == 0:
        raise HTTPException(404, "item tidak ditemukan")
    return {"ok": True, "transaksi_terhapus": n_tx if cascade else 0}


@router.get("/item/{iid}")
async def detail_item(iid: str, _user=Depends(require_roles("petugas", "admin"))):
    db = get_db()
    it = await db.stok_item.find_one({"id": iid}, {"_id": 0})
    if not it:
        raise HTTPException(404, "item tidak ditemukan")
    saldo = (await _saldo_map(db, [iid])).get(iid, 0)
    it["saldo"] = _rapikan(saldo)
    it["stok_rendah"] = it.get("stok_minimum") is not None and saldo <= it["stok_minimum"]
    txs = await db.stok_transaksi.find({"item_id": iid}, {"_id": 0}).sort("tgl", -1).limit(200).to_list(200)
    return {"item": it, "transaksi": txs}


# --------------------------------------------------------------- TRANSAKSI
@router.post("/transaksi")
async def create_transaksi(body: TransaksiIn, user=Depends(require_roles("petugas", "admin"))):
    if body.jenis not in JENIS:
        raise HTTPException(400, "jenis harus masuk/keluar/penyesuaian")
    db = get_db()
    it = await db.stok_item.find_one({"id": body.item_id}, {"_id": 0, "id": 1, "nama": 1, "satuan": 1})
    if not it:
        raise HTTPException(400, "item tidak ditemukan")
    if body.jenis == "masuk":
        if body.jumlah <= 0:
            raise HTTPException(400, "jumlah masuk harus > 0")
        mutasi = abs(body.jumlah)
    elif body.jenis == "keluar":
        if body.jumlah <= 0:
            raise HTTPException(400, "jumlah keluar harus > 0")
        mutasi = -abs(body.jumlah)
    else:  # penyesuaian — bertanda
        mutasi = body.jumlah
    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex,
        "item_id": body.item_id,
        "item_nama": it["nama"],
        "satuan": it.get("satuan"),
        "jenis": body.jenis,
        "mutasi": mutasi,
        "tgl": body.tgl or now.date().isoformat(),
        "batch": body.batch,
        "exp": body.exp,
        "sumber": body.sumber,
        "catatan": body.catatan,
        "petugas_id": user["id"],
        "created_at": now,
    }
    await db.stok_transaksi.insert_one(doc)
    doc.pop("_id", None)
    saldo = (await _saldo_map(db, [body.item_id])).get(body.item_id, 0)
    return {"transaksi": doc, "saldo": _rapikan(saldo), "saldo_minus": saldo < 0}


@router.delete("/transaksi/{tid}")
async def delete_transaksi(tid: str, _user=Depends(require_roles("admin"))):
    r = await get_db().stok_transaksi.delete_one({"id": tid})
    if r.deleted_count == 0:
        raise HTTPException(404, "transaksi tidak ditemukan")
    return {"ok": True}


# --------------------------------------------------------------- KEDALUWARSA
@router.get("/kedaluwarsa")
async def mendekati_kedaluwarsa(
    hari: int = Query(90, ge=1, le=730),
    _user=Depends(require_roles("petugas", "admin")),
):
    """Penerimaan (masuk) dengan tanggal ED dalam `hari` ke depan (info; belum FEFO)."""
    batas = (date.today() + timedelta(days=hari)).isoformat()
    hari_ini = date.today().isoformat()
    rows = await get_db().stok_transaksi.find(
        {"jenis": "masuk", "exp": {"$ne": None, "$lte": batas}}, {"_id": 0}
    ).sort("exp", 1).to_list(500)
    for r in rows:
        r["kedaluwarsa"] = bool(r.get("exp") and r["exp"] < hari_ini)
    return rows
