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
