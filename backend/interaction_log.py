"""Log interaksi WhatsApp + deteksi sinyal dini wabah.

Dua nilai sekaligus, mengikuti pelajaran dari sistem KIE NAKESWAN (drh. Edi):

1. LOGGING = EVALUASI GRATIS. Setiap pesan masuk & balasan dicatat terstruktur
   ke koleksi `interaction_logs`. Berbulan kemudian, ini menjadi dataset evaluasi
   siap-analisis tanpa usaha tambahan (volume, topik, jam sibuk, pola wilayah).

2. SINYAL DINI PROAKTIF. Tiap interaksi diperiksa kata kunci gejala PHMS
   (Penyakit Hewan Menular Strategis: Rabies, PMK, ASF, AI, Antraks, dll).
   Endpoint `/log/sinyal-dini` mengagregasi dugaan per wilayah per minggu dan
   menandai LONJAKAN di atas ambang — mengubah temuan "126 interaksi/minggu =
   sinyal wabah" (yang di sistem lain baru ketahuan SETELAH kejadian) menjadi
   peringatan yang muncul SAAT polanya terbentuk.

Prinsip: `catat_interaksi` TIDAK PERNAH melempar exception — pencatatan yang gagal
tak boleh memblokir balasan ke warga. Endpoint analitik hanya untuk admin.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from db import get_db
from auth import require_roles

router = APIRouter(prefix="/log", tags=["log"])


# --- Kamus gejala PHMS (kata kunci → nama penyakit) ----------------------------
# Dicocokkan sebagai substring huruf-kecil pada teks pesan warga. Sengaja longgar
# (mengutamakan sensitivitas untuk sinyal dini); positif-palsu disaring petugas.
GEJALA_PHMS = {
    "Rabies": ["rabies", "anjing gila", "digigit anjing", "gigit anjing", "gigitan anjing",
               "kucing menggigit", "takut air", "hidrofobia"],
    "PMK": ["pmk", "mulut dan kuku", "lepuh", "melepuh", "ngiler", "hipersalivasi",
            "air liur berlebih", "pincang", "kuku lepas", "sariawan sapi"],
    "ASF": ["asf", "flu babi", "demam babi afrika", "babi mati mendadak", "babi mati massal"],
    "AI": ["flu burung", "avian influenza", "ayam mati mendadak", "unggas mati massal",
           "jengger biru", "tetelo"],
    "Antraks": ["antraks", "anthrax", "radang limpa", "sapi mati mendadak keluar darah"],
    "LSD": ["lsd", "lumpy skin", "benjol kulit", "bungkul kulit"],
    "Brucellosis": ["brucella", "brucellosis", "keluron", "abortus menular", "keguguran ternak"],
}

# Kata kunci kategori topik (untuk analitik ringan; bukan diagnosis).
KATA_KATEGORI = {
    "KELUHAN_PENYAKIT": ["sakit", "gejala", "demam", "mati", "lemas", "tidak mau makan",
                         "mencret", "diare", "luka", "bengkak", "batuk", "pilek"],
    "VAKSINASI": ["vaksin", "vaksinasi", "imunisasi"],
    "REPRODUKSI": ["kawin suntik", "inseminasi", "ib ", "birahi", "bunting", "melahirkan", "beranak"],
    "PENDAFTARAN": ["daftar", "pendaftaran", "layanan"],
    "OBAT": ["obat", "antibiotik", "vitamin", "dosis"],
}

# Ambang lonjakan sinyal dini: minggu berjalan disebut "lonjakan" bila jumlah
# dugaan >= AMBANG_MINIMUM dan >= FAKTOR_LONJAKAN x rata-rata minggu sebelumnya.
AMBANG_MINIMUM = 3
FAKTOR_LONJAKAN = 2.0


def deteksi_dugaan_phms(teks: str) -> list[str]:
    """Kembalikan daftar nama penyakit PHMS yang gejalanya terindikasi di teks."""
    if not teks:
        return []
    low = teks.lower()
    hit = []
    for penyakit, kunci in GEJALA_PHMS.items():
        if any(k in low for k in kunci):
            hit.append(penyakit)
    return hit


def klasifikasi_kategori(teks: str) -> str:
    """Tebak kategori topik dari kata kunci. Default 'LAINNYA'."""
    if not teks:
        return "LAINNYA"
    low = teks.lower()
    for kategori, kunci in KATA_KATEGORI.items():
        if any(k in low for k in kunci):
            return kategori
    return "LAINNYA"


def _iso_minggu(dt: datetime) -> str:
    """Kunci minggu ISO 'YYYY-Www' (mis. 2026-W27) untuk pengelompokan."""
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


async def catat_interaksi(
    db,
    wa_id: str,
    nama: Optional[str],
    peran: str,                    # 'warga' | 'petugas'
    teks_masuk: Optional[str],
    balasan: Optional[str],
    *,
    wilayah_id: Optional[str] = None,
    wilayah_nama: Optional[str] = None,
    langkah: Optional[str] = None,  # step state-machine, bila ada
) -> None:
    """Catat satu interaksi ke `interaction_logs`. Tidak pernah melempar."""
    try:
        dugaan = deteksi_dugaan_phms(teks_masuk or "")
        doc = {
            "ts": datetime.now(timezone.utc),
            "minggu": _iso_minggu(datetime.now(timezone.utc)),
            "wa_id": wa_id,
            "nama": nama or None,
            "peran": peran,
            "teks_masuk": (teks_masuk or "")[:2000],
            "balasan": (balasan or "")[:2000],
            "kategori": klasifikasi_kategori(teks_masuk or ""),
            "dugaan_phms": dugaan,
            "flag_darurat": bool(dugaan),
            "wilayah_id": wilayah_id,
            "wilayah_nama": wilayah_nama,
            "langkah": langkah,
        }
        await db.interaction_logs.insert_one(doc)
    except Exception:
        # Pencatatan gagal tak boleh mengganggu alur balasan warga.
        pass


async def ensure_indexes_log(db) -> None:
    """Index koleksi log. Dipanggil dari server.ensure_indexes."""
    await db.interaction_logs.create_index([("ts", -1)])
    await db.interaction_logs.create_index([("minggu", 1), ("wilayah_id", 1)])
    await db.interaction_logs.create_index("flag_darurat")
    await db.interaction_logs.create_index("kategori")


# --- Endpoint analitik (admin) -------------------------------------------------

@router.get("/interaksi")
async def daftar_interaksi(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    kategori: Optional[str] = None,
    hanya_darurat: bool = False,
    _user=Depends(require_roles("admin")),
):
    """Log interaksi terbaru (paginasi), untuk audit & tinjauan kualitas."""
    db = get_db()
    q: dict = {}
    if kategori:
        q["kategori"] = kategori
    if hanya_darurat:
        q["flag_darurat"] = True
    total = await db.interaction_logs.count_documents(q)
    cur = db.interaction_logs.find(q, {"_id": 0}).sort("ts", -1).skip(skip).limit(limit)
    return {"total": total, "items": await cur.to_list(limit)}


@router.get("/ringkasan")
async def ringkasan(
    hari: int = Query(30, ge=1, le=365),
    _user=Depends(require_roles("admin")),
):
    """Statistik ringkas periode terakhir — fondasi dashboard evaluasi."""
    db = get_db()
    sejak = datetime.now(timezone.utc) - timedelta(days=hari)
    dasar = {"ts": {"$gte": sejak}}
    total = await db.interaction_logs.count_documents(dasar)
    unik = len(await db.interaction_logs.distinct("wa_id", dasar))
    darurat = await db.interaction_logs.count_documents({**dasar, "flag_darurat": True})
    per_kategori = await db.interaction_logs.aggregate([
        {"$match": dasar},
        {"$group": {"_id": "$kategori", "jumlah": {"$sum": 1}}},
        {"$sort": {"jumlah": -1}},
    ]).to_list(50)
    return {
        "periode_hari": hari,
        "total_interaksi": total,
        "pengirim_unik": unik,
        "interaksi_darurat": darurat,
        "per_kategori": [{"kategori": r["_id"], "jumlah": r["jumlah"]} for r in per_kategori],
    }


@router.get("/sinyal-dini")
async def sinyal_dini(
    minggu_amati: int = Query(8, ge=2, le=52),
    _user=Depends(require_roles("admin", "petugas")),
):
    """Deteksi lonjakan dugaan PHMS per wilayah per minggu.

    Mengagregasi interaksi ber-flag PHMS beberapa minggu terakhir, lalu untuk tiap
    (penyakit × wilayah) membandingkan jumlah minggu TERBARU dengan rata-rata
    minggu sebelumnya. Tandai 'lonjakan' bila melewati ambang. Ini peringatan dini
    berbasis percakapan warga — pelengkap surveilans pasif SKDR.
    """
    db = get_db()
    sejak = datetime.now(timezone.utc) - timedelta(weeks=minggu_amati)
    rows = await db.interaction_logs.aggregate([
        {"$match": {"ts": {"$gte": sejak}, "flag_darurat": True}},
        {"$unwind": "$dugaan_phms"},
        {"$group": {
            "_id": {"penyakit": "$dugaan_phms",
                    "wilayah": {"$ifNull": ["$wilayah_nama", "(tak diketahui)"]},
                    "minggu": "$minggu"},
            "jumlah": {"$sum": 1},
        }},
    ]).to_list(2000)

    # Susun deret waktu per (penyakit, wilayah).
    deret: dict = {}
    semua_minggu = set()
    for r in rows:
        k = (r["_id"]["penyakit"], r["_id"]["wilayah"])
        deret.setdefault(k, {})[r["_id"]["minggu"]] = r["jumlah"]
        semua_minggu.add(r["_id"]["minggu"])

    if not semua_minggu:
        return {"minggu_amati": minggu_amati, "minggu_terbaru": None, "peringatan": [], "seri": []}

    minggu_terbaru = max(semua_minggu)
    peringatan = []
    seri = []
    for (penyakit, wilayah), per_minggu in deret.items():
        terbaru = per_minggu.get(minggu_terbaru, 0)
        sebelum = [v for m, v in per_minggu.items() if m != minggu_terbaru]
        rata_sebelum = (sum(sebelum) / len(sebelum)) if sebelum else 0.0
        lonjakan = (terbaru >= AMBANG_MINIMUM and
                    terbaru >= FAKTOR_LONJAKAN * max(rata_sebelum, 0.5))
        entri = {
            "penyakit": penyakit,
            "wilayah": wilayah,
            "minggu_terbaru": terbaru,
            "rata_minggu_sebelumnya": round(rata_sebelum, 1),
            "lonjakan": lonjakan,
        }
        seri.append(entri)
        if lonjakan:
            peringatan.append(entri)

    peringatan.sort(key=lambda e: e["minggu_terbaru"], reverse=True)
    seri.sort(key=lambda e: e["minggu_terbaru"], reverse=True)
    return {
        "minggu_amati": minggu_amati,
        "minggu_terbaru": minggu_terbaru,
        "ambang": {"minimum": AMBANG_MINIMUM, "faktor_lonjakan": FAKTOR_LONJAKAN},
        "peringatan": peringatan,
        "seri": seri,
    }
