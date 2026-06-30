"""Rekap laporan bulanan — agregasi data tercatat menjadi ringkasan bulanan,
menggantikan rekap manual. v1: pelayanan (KESWAN) per penyakit/wilayah/petugas/
metode/prognosa + pemakaian obat + mutasi ternak (termasuk kematian) + peternak/
pendaftaran baru. Agregasi di Python (volume bulanan kecil). Mudah diperluas saat
kategori pelayanan lain ditambahkan."""
from datetime import datetime, timezone
from typing import Optional
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends

from db import get_db
from auth import require_roles

router = APIRouter(prefix="/laporan", tags=["laporan"])


def _range_str(tahun: int, bulan: int):
    return f"{tahun:04d}-{bulan:02d}-01", f"{tahun:04d}-{bulan:02d}-31"


def _range_dt(tahun: int, bulan: int):
    dari = datetime(tahun, bulan, 1, tzinfo=timezone.utc)
    sampai = datetime(tahun + 1, 1, 1, tzinfo=timezone.utc) if bulan == 12 else datetime(tahun, bulan + 1, 1, tzinfo=timezone.utc)
    return dari, sampai


@router.get("/bulanan")
async def laporan_bulanan(
    tahun: int,
    bulan: int,
    kalurahan_id: Optional[str] = None,
    _user=Depends(require_roles("petugas", "admin")),
):
    db = get_db()
    s_dari, s_sampai = _range_str(tahun, bulan)
    d_dari, d_sampai = _range_dt(tahun, bulan)

    # ---- pelayanan ----
    pflt = {"tgl": {"$gte": s_dari, "$lte": s_sampai}}
    if kalurahan_id:
        pflt["peternak.wilayah_id"] = kalurahan_id
    pels = await db.pelayanan.find(pflt, {"_id": 0}).to_list(5000)

    per_kategori, per_metode, per_prognosa = Counter(), Counter(), Counter()
    per_penyakit, per_wilayah, per_petugas = Counter(), Counter(), Counter()
    obat_agg = defaultdict(lambda: {"jumlah": 0.0, "satuan": ""})
    for p in pels:
        per_kategori[p.get("kategori") or "-"] += 1
        if p.get("metode_layanan"):
            per_metode[p["metode_layanan"]] += 1
        if p.get("prognosa"):
            per_prognosa[p["prognosa"]] += 1
        if p.get("penyakit_id"):
            per_penyakit[p["penyakit_id"]] += 1
        wid = (p.get("peternak") or {}).get("wilayah_id")
        if wid:
            per_wilayah[wid] += 1
        if p.get("petugas_id"):
            per_petugas[p["petugas_id"]] += 1
        for o in (p.get("obat") or []):
            nm = o.get("nama") or "?"
            obat_agg[nm]["jumlah"] += float(o.get("jumlah") or 0)
            obat_agg[nm]["satuan"] = o.get("satuan") or obat_agg[nm]["satuan"]

    penyakit_list = []
    for kode, n in per_penyakit.most_common():
        pen = await db.penyakit.find_one({"kode": kode}, {"_id": 0, "nama": 1})
        penyakit_list.append({"kode": kode, "nama": pen["nama"] if pen else kode, "jumlah": n})

    wilayah_list = []
    for wid, n in per_wilayah.most_common():
        w = await db.wilayah.find_one({"id": wid}, {"_id": 0, "nama": 1})
        wilayah_list.append({"kalurahan_id": wid, "nama": w["nama"] if w else wid, "jumlah": n})

    petugas_list = []
    for uid, n in per_petugas.most_common():
        u = await db.users.find_one({"id": uid}, {"_id": 0, "nama": 1})
        petugas_list.append({"petugas_id": uid, "nama": u["nama"] if u else uid, "jumlah": n})

    obat_list = sorted(
        [{"nama": k, "jumlah": round(v["jumlah"], 2), "satuan": v["satuan"]} for k, v in obat_agg.items()],
        key=lambda x: -x["jumlah"],
    )

    # ---- mutasi ternak (datetime) ----
    mut = await db.mutasi_ternak.find({"tgl": {"$gte": d_dari, "$lt": d_sampai}}, {"_id": 0}).to_list(5000)
    mutasi = Counter()
    for m in mut:
        mutasi[m.get("jenis") or "-"] += int(m.get("jumlah") or 1)

    pet_baru = await db.peternak.count_documents({"created_at": {"$gte": d_dari, "$lt": d_sampai}})
    daftar_baru = await db.pendaftaran.count_documents({"created_at": {"$gte": d_dari, "$lt": d_sampai}})
    daftar_konf = await db.pendaftaran.count_documents(
        {"created_at": {"$gte": d_dari, "$lt": d_sampai}, "status": "dikonfirmasi"}
    )

    return {
        "periode": {"tahun": tahun, "bulan": bulan, "dari": s_dari, "sampai": s_sampai},
        "filter_kalurahan_id": kalurahan_id,
        "pelayanan": {
            "total": len(pels),
            "per_kategori": dict(per_kategori),
            "per_metode": dict(per_metode),
            "per_prognosa": dict(per_prognosa),
            "per_penyakit": penyakit_list,
            "per_wilayah": wilayah_list,
            "per_petugas": petugas_list,
        },
        "obat": obat_list,
        "ternak_mutasi": dict(mutasi),
        "peternak_baru": pet_baru,
        "pendaftaran": {"baru": daftar_baru, "dikonfirmasi": daftar_konf},
    }
