"""Auto-seed saat startup — idempotent. Master di-load bila kosong;
admin dibuat dari env bila belum ada. Deploy-from-GitHub jadi swasembada."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from db import get_db
from auth import hash_password

SEED_FILE = Path(__file__).parent / "seed-master-puskeswan.json"


async def seed_master_if_empty():
    db = get_db()
    if await db.penyakit.count_documents({}) > 0:
        return
    if not SEED_FILE.exists():
        return
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    if data.get("penyakit"):
        await db.penyakit.insert_many(data["penyakit"])
    if data.get("ras_ternak"):
        await db.ras_ternak.insert_many(data["ras_ternak"])
    if data.get("referensi"):
        await db.referensi.insert_many(
            [{"nama": k, "nilai": v} for k, v in data["referensi"].items()]
        )
    if data.get("crosswalk_isikhnas"):
        await db.crosswalk_isikhnas.insert_many(data["crosswalk_isikhnas"])


async def seed_admin_if_missing():
    db = get_db()
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        return
    if await db.users.find_one({"username": username}):
        return
    await db.users.insert_one({
        "id": uuid.uuid4().hex,
        "nama": "Administrator",
        "username": username,
        "password_hash": hash_password(password),
        "roles": ["admin"],
        "wilayah_id": None,
        "peternak_id": None,
        "aktif": True,
        "created_at": datetime.now(timezone.utc),
    })


SEED_WILAYAH = Path(__file__).parent / "seed-wilayah-godean.json"


async def seed_wilayah_if_empty():
    db = get_db()
    if await db.wilayah.count_documents({}) > 0:
        return
    if not SEED_WILAYAH.exists():
        return
    data = json.loads(SEED_WILAYAH.read_text(encoding="utf-8"))
    if data:
        await db.wilayah.insert_many(data)


# ── Ras lengkap per spesies (upsert idempoten; sumber: rumpun Kementan/Disnak) ──
RAS_SEED = [
    {
        "id": "ras-sapi-bali",
        "spesies": "Sapi",
        "nama": "Bali"
    },
    {
        "id": "ras-sapi-madura",
        "spesies": "Sapi",
        "nama": "Madura"
    },
    {
        "id": "ras-sapi-aceh",
        "spesies": "Sapi",
        "nama": "Aceh"
    },
    {
        "id": "ras-sapi-peranakan-ongole-po",
        "spesies": "Sapi",
        "nama": "Peranakan Ongole (PO)"
    },
    {
        "id": "ras-sapi-pesisir",
        "spesies": "Sapi",
        "nama": "Pesisir"
    },
    {
        "id": "ras-sapi-limosin",
        "spesies": "Sapi",
        "nama": "Limosin"
    },
    {
        "id": "ras-sapi-simmental",
        "spesies": "Sapi",
        "nama": "Simmental"
    },
    {
        "id": "ras-sapi-brahman",
        "spesies": "Sapi",
        "nama": "Brahman"
    },
    {
        "id": "ras-sapi-brangus",
        "spesies": "Sapi",
        "nama": "Brangus"
    },
    {
        "id": "ras-sapi-friesian-holstein-fh",
        "spesies": "Sapi",
        "nama": "Friesian Holstein (FH)"
    },
    {
        "id": "ras-sapi-jersey",
        "spesies": "Sapi",
        "nama": "Jersey"
    },
    {
        "id": "ras-sapi-ongole",
        "spesies": "Sapi",
        "nama": "Ongole"
    },
    {
        "id": "ras-kerbau-lumpur-kalang",
        "spesies": "Kerbau",
        "nama": "Lumpur (Kalang)"
    },
    {
        "id": "ras-kerbau-sungai-murrah",
        "spesies": "Kerbau",
        "nama": "Sungai (Murrah)"
    },
    {
        "id": "ras-kerbau-toraja-tedong",
        "spesies": "Kerbau",
        "nama": "Toraja (Tedong)"
    },
    {
        "id": "ras-kerbau-sumbawa",
        "spesies": "Kerbau",
        "nama": "Sumbawa"
    },
    {
        "id": "ras-kerbau-moa",
        "spesies": "Kerbau",
        "nama": "Moa"
    },
    {
        "id": "ras-kerbau-pampangan",
        "spesies": "Kerbau",
        "nama": "Pampangan"
    },
    {
        "id": "ras-kambing-peranakan-etawah-pe",
        "spesies": "Kambing",
        "nama": "Peranakan Etawah (PE)"
    },
    {
        "id": "ras-kambing-kacang",
        "spesies": "Kambing",
        "nama": "Kacang"
    },
    {
        "id": "ras-kambing-kaligesing",
        "spesies": "Kambing",
        "nama": "Kaligesing"
    },
    {
        "id": "ras-kambing-senduro",
        "spesies": "Kambing",
        "nama": "Senduro"
    },
    {
        "id": "ras-kambing-jawarandu",
        "spesies": "Kambing",
        "nama": "Jawarandu"
    },
    {
        "id": "ras-kambing-bligon",
        "spesies": "Kambing",
        "nama": "Bligon"
    },
    {
        "id": "ras-kambing-boer",
        "spesies": "Kambing",
        "nama": "Boer"
    },
    {
        "id": "ras-kambing-saanen",
        "spesies": "Kambing",
        "nama": "Saanen"
    },
    {
        "id": "ras-kambing-gembrong",
        "spesies": "Kambing",
        "nama": "Gembrong"
    },
    {
        "id": "ras-domba-garut",
        "spesies": "Domba",
        "nama": "Garut"
    },
    {
        "id": "ras-domba-ekor-tipis",
        "spesies": "Domba",
        "nama": "Ekor Tipis"
    },
    {
        "id": "ras-domba-ekor-gemuk-donggala-kibas",
        "spesies": "Domba",
        "nama": "Ekor Gemuk (Donggala/Kibas)"
    },
    {
        "id": "ras-domba-texel-dombos",
        "spesies": "Domba",
        "nama": "Texel (Dombos)"
    },
    {
        "id": "ras-domba-batur",
        "spesies": "Domba",
        "nama": "Batur"
    },
    {
        "id": "ras-domba-merino",
        "spesies": "Domba",
        "nama": "Merino"
    },
    {
        "id": "ras-domba-dorper",
        "spesies": "Domba",
        "nama": "Dorper"
    },
    {
        "id": "ras-domba-suffolk",
        "spesies": "Domba",
        "nama": "Suffolk"
    },
    {
        "id": "ras-kuda-sumbawa",
        "spesies": "Kuda",
        "nama": "Sumbawa"
    },
    {
        "id": "ras-kuda-sandel-sumba",
        "spesies": "Kuda",
        "nama": "Sandel (Sumba)"
    },
    {
        "id": "ras-kuda-gayo",
        "spesies": "Kuda",
        "nama": "Gayo"
    },
    {
        "id": "ras-kuda-batak",
        "spesies": "Kuda",
        "nama": "Batak"
    },
    {
        "id": "ras-kuda-minahasa",
        "spesies": "Kuda",
        "nama": "Minahasa"
    },
    {
        "id": "ras-kuda-thoroughbred",
        "spesies": "Kuda",
        "nama": "Thoroughbred"
    },
    {
        "id": "ras-babi-landrace",
        "spesies": "Babi",
        "nama": "Landrace"
    },
    {
        "id": "ras-babi-yorkshire-large-white",
        "spesies": "Babi",
        "nama": "Yorkshire (Large White)"
    },
    {
        "id": "ras-babi-duroc",
        "spesies": "Babi",
        "nama": "Duroc"
    },
    {
        "id": "ras-babi-lokal",
        "spesies": "Babi",
        "nama": "Lokal"
    },
    {
        "id": "ras-ayam-broiler",
        "spesies": "Ayam",
        "nama": "Broiler"
    },
    {
        "id": "ras-ayam-petelur-layer",
        "spesies": "Ayam",
        "nama": "Petelur (Layer)"
    },
    {
        "id": "ras-ayam-kampung",
        "spesies": "Ayam",
        "nama": "Kampung"
    },
    {
        "id": "ras-ayam-joper",
        "spesies": "Ayam",
        "nama": "Joper"
    },
    {
        "id": "ras-ayam-pelung",
        "spesies": "Ayam",
        "nama": "Pelung"
    },
    {
        "id": "ras-ayam-kedu",
        "spesies": "Ayam",
        "nama": "Kedu"
    },
    {
        "id": "ras-ayam-sentul",
        "spesies": "Ayam",
        "nama": "Sentul"
    },
    {
        "id": "ras-ayam-cemani",
        "spesies": "Ayam",
        "nama": "Cemani"
    },
    {
        "id": "ras-ayam-bangkok",
        "spesies": "Ayam",
        "nama": "Bangkok"
    },
    {
        "id": "ras-itik-mojosari",
        "spesies": "Itik",
        "nama": "Mojosari"
    },
    {
        "id": "ras-itik-tegal",
        "spesies": "Itik",
        "nama": "Tegal"
    },
    {
        "id": "ras-itik-magelang",
        "spesies": "Itik",
        "nama": "Magelang"
    },
    {
        "id": "ras-itik-alabio",
        "spesies": "Itik",
        "nama": "Alabio"
    },
    {
        "id": "ras-itik-peking",
        "spesies": "Itik",
        "nama": "Peking"
    },
    {
        "id": "ras-itik-hibrida",
        "spesies": "Itik",
        "nama": "Hibrida"
    },
    {
        "id": "ras-kelinci-lokal",
        "spesies": "Kelinci",
        "nama": "Lokal"
    },
    {
        "id": "ras-kelinci-new-zealand-white",
        "spesies": "Kelinci",
        "nama": "New Zealand White"
    },
    {
        "id": "ras-kelinci-rex",
        "spesies": "Kelinci",
        "nama": "Rex"
    },
    {
        "id": "ras-kelinci-anggora",
        "spesies": "Kelinci",
        "nama": "Anggora"
    },
    {
        "id": "ras-kelinci-flemish-giant",
        "spesies": "Kelinci",
        "nama": "Flemish Giant"
    },
    {
        "id": "ras-kelinci-lop",
        "spesies": "Kelinci",
        "nama": "Lop"
    },
    {
        "id": "ras-anjing-lokal-kampung",
        "spesies": "Anjing",
        "nama": "Lokal / Kampung"
    },
    {
        "id": "ras-anjing-kintamani",
        "spesies": "Anjing",
        "nama": "Kintamani"
    },
    {
        "id": "ras-anjing-golden-retriever",
        "spesies": "Anjing",
        "nama": "Golden Retriever"
    },
    {
        "id": "ras-anjing-labrador",
        "spesies": "Anjing",
        "nama": "Labrador"
    },
    {
        "id": "ras-anjing-poodle",
        "spesies": "Anjing",
        "nama": "Poodle"
    },
    {
        "id": "ras-anjing-shih-tzu",
        "spesies": "Anjing",
        "nama": "Shih Tzu"
    },
    {
        "id": "ras-anjing-pomeranian",
        "spesies": "Anjing",
        "nama": "Pomeranian"
    },
    {
        "id": "ras-anjing-bulldog",
        "spesies": "Anjing",
        "nama": "Bulldog"
    },
    {
        "id": "ras-anjing-lainnya",
        "spesies": "Anjing",
        "nama": "Lainnya"
    },
    {
        "id": "ras-kucing-domestik-kampung",
        "spesies": "Kucing",
        "nama": "Domestik / Kampung"
    },
    {
        "id": "ras-kucing-persia",
        "spesies": "Kucing",
        "nama": "Persia"
    },
    {
        "id": "ras-kucing-anggora",
        "spesies": "Kucing",
        "nama": "Anggora"
    },
    {
        "id": "ras-kucing-maine-coon",
        "spesies": "Kucing",
        "nama": "Maine Coon"
    },
    {
        "id": "ras-kucing-british-shorthair",
        "spesies": "Kucing",
        "nama": "British Shorthair"
    },
    {
        "id": "ras-kucing-bengal",
        "spesies": "Kucing",
        "nama": "Bengal"
    },
    {
        "id": "ras-kucing-sphynx",
        "spesies": "Kucing",
        "nama": "Sphynx"
    },
    {
        "id": "ras-kucing-lainnya",
        "spesies": "Kucing",
        "nama": "Lainnya"
    },
    {
        "id": "ras-puyuh-petelur",
        "spesies": "Puyuh",
        "nama": "Petelur"
    },
    {
        "id": "ras-puyuh-pedaging",
        "spesies": "Puyuh",
        "nama": "Pedaging"
    },
    {
        "id": "ras-puyuh-lokal",
        "spesies": "Puyuh",
        "nama": "Lokal"
    },
    {
        "id": "ras-mentok-lokal",
        "spesies": "Mentok",
        "nama": "Lokal"
    },
    {
        "id": "ras-angsa-lokal",
        "spesies": "Angsa",
        "nama": "Lokal"
    }
]

async def seed_ras_upsert():
    """Tambah ras yang belum ada (match by spesies+nama). Idempoten & aman di DB berisi."""
    db = get_db()
    ditambah = 0
    for r in RAS_SEED:
        res = await db.ras_ternak.update_one(
            {"spesies": r["spesies"], "nama": r["nama"]},
            {"$setOnInsert": r},
            upsert=True,
        )
        if getattr(res, "upserted_id", None) is not None:
            ditambah += 1
    if ditambah:
        print(f"[seed] ras_ternak: +{ditambah} ras baru")
    return ditambah


# ── Obat contoh (idempoten; SILAKAN SUNTING sesuai sediaan/label di lapangan) ──
OBAT_SEED = [
    {"nama_dagang": "Oksitetrasiklin LA (mis. Vet-Oxy LA)", "zat_aktif": "Oksitetrasiklin",
     "konsentrasi": 200, "satuan": "ml", "dosis_per_kg": 20, "rute": "IM",
     "waktu_henti_daging_hari": 28, "waktu_henti_susu_jam": 168, "aktif": True},
    {"nama_dagang": "Penstrep", "zat_aktif": "Penisilin + Streptomisin",
     "konsentrasi": None, "satuan": "ml", "dosis_per_kg": None, "rute": "IM",
     "waktu_henti_daging_hari": 23, "waktu_henti_susu_jam": 72, "aktif": True},
    {"nama_dagang": "Vetadryl", "zat_aktif": "Difenhidramin HCl",
     "konsentrasi": 10, "satuan": "ml", "dosis_per_kg": 1, "rute": "IM/IV",
     "waktu_henti_daging_hari": None, "waktu_henti_susu_jam": None, "aktif": True},
    {"nama_dagang": "Biosan TP", "zat_aktif": "Multivitamin / roboransia",
     "konsentrasi": None, "satuan": "ml", "dosis_per_kg": None, "rute": "IM",
     "waktu_henti_daging_hari": None, "waktu_henti_susu_jam": None, "aktif": True},
    {"nama_dagang": "Sulfidol / Sulfa", "zat_aktif": "Sulfadimidin",
     "konsentrasi": 200, "satuan": "ml", "dosis_per_kg": None, "rute": "IM/IV",
     "waktu_henti_daging_hari": 10, "waktu_henti_susu_jam": 72, "aktif": True},
]


async def seed_obat_if_empty():
    """Isi obat contoh hanya bila koleksi kosong. Idempoten."""
    db = get_db()
    if await db.obat.count_documents({}) > 0:
        return 0
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)
    docs = [{"id": _uuid.uuid4().hex, **o, "created_by": "seed", "created_at": now} for o in OBAT_SEED]
    await db.obat.insert_many(docs)
    print(f"[seed] obat: +{len(docs)} obat contoh")
    return len(docs)
