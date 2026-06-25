"""
Seed master ke MongoDB dari seed-master-puskeswan.json.
Jalankan sekali setelah deploy:  python seed_loader.py
Idempotent (delete+insert), jadi aman dijalankan ulang.
"""
import asyncio
import json
import os
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "puskeswan")
SEED = Path(__file__).parent / "seed-master-puskeswan.json"


async def main():
    data = json.loads(SEED.read_text(encoding="utf-8"))
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]

    if data.get("penyakit"):
        await db.penyakit.delete_many({})
        await db.penyakit.insert_many(data["penyakit"])
    if data.get("ras_ternak"):
        await db.ras_ternak.delete_many({})
        await db.ras_ternak.insert_many(data["ras_ternak"])
    if data.get("referensi"):
        await db.referensi.delete_many({})
        await db.referensi.insert_many(
            [{"nama": k, "nilai": v} for k, v in data["referensi"].items()]
        )
    if data.get("crosswalk_isikhnas"):
        await db.crosswalk_isikhnas.delete_many({})
        await db.crosswalk_isikhnas.insert_many(data["crosswalk_isikhnas"])

    print("penyakit  :", await db.penyakit.count_documents({}))
    print("ras_ternak:", await db.ras_ternak.count_documents({}))
    print("referensi :", await db.referensi.count_documents({}))
    print("crosswalk :", await db.crosswalk_isikhnas.count_documents({}))


if __name__ == "__main__":
    asyncio.run(main())
