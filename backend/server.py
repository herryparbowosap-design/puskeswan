import os
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import get_client, get_db
import storage_s3


async def ensure_indexes(db):
    await db.peternak.create_index([("nama", "text"), ("kontak", "text"), ("nik", "text")])
    await db.peternak.create_index([("koordinat", "2dsphere")])
    await db.ternak.create_index("peternak_id")
    await db.pelayanan.create_index([("kategori", 1), ("tgl", 1)])
    await db.pelayanan.create_index("peternak.wilayah_id")
    await db.wilayah.create_index([("level", 1), ("parent_id", 1)])
    await db.penyakit.create_index("kategori")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_client().admin.command("ping")
    await ensure_indexes(get_db())
    yield
    get_client().close()


app = FastAPI(title="SIM Puskeswan", version="0.1.0", lifespan=lifespan)

origins = [o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    try:
        await get_client().admin.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    return {"status": "ok", "service": "puskeswan", "mongo": mongo_ok}


app.include_router(storage_s3.router, prefix="/api")
