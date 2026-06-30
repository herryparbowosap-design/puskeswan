"""
Modul penyimpanan foto — pola presigned URL.

Backend TIDAK pernah mengalirkan byte foto. Backend hanya menerbitkan
"tiket" (presigned URL); file naik/turun langsung antara client dan S3.
Alasan: hemat memori app server (penting di Emergent), dan bucket bisa
tetap privat (PDP — foto kasus/peternak tidak boleh publik).

S3-compatible: jalan untuk AWS S3 maupun Cloudflare R2 / MinIO hanya
dengan mengubah env, tanpa ubah kode.

Env (set di Emergent, JANGAN commit):
  S3_ENDPOINT_URL    kosong=AWS; isi untuk R2/MinIO (mis. https://<acc>.r2.cloudflarestorage.com)
  S3_REGION          AWS: mis. ap-southeast-3 (Jakarta); R2: auto
  S3_ACCESS_KEY_ID
  S3_SECRET_ACCESS_KEY
  S3_BUCKET          mis. puskeswan-foto
"""
from __future__ import annotations

import os
import os.path
import uuid
from datetime import datetime
from typing import Optional

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth import current_user, require_roles

BUCKET = os.getenv("S3_BUCKET", "puskeswan-foto")
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def _client():
    region = os.getenv("S3_REGION") or ""
    endpoint = os.getenv("S3_ENDPOINT_URL") or ""
    # AWS (tanpa endpoint custom): paksa endpoint REGIONAL agar presigned PUT
    # tidak kena 307 redirect dari host global s3.amazonaws.com.
    if not endpoint and region and region != "auto":
        endpoint = f"https://s3.{region}.amazonaws.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        region_name=None if region in ("", "auto") else region,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def build_key(prefix: str, filename: str) -> str:
    """Key unik & rapi, mis. pelayanan/<id>/<uuid>.jpg"""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _IMG_EXT:
        ext = ".jpg"
    return f"{prefix.strip('/')}/{uuid.uuid4().hex}{ext}"


def presign_upload(key: str, content_type: str, expires: int = 900) -> str:
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def presign_download(key: str, expires: int = 900) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=expires,
    )


# ---------------------------------------------------------------------------
# Model: disimpan di record (pelayanan/ternak/peternak) — KEY, bukan URL.
# URL selalu di-presign saat akan ditampilkan (kedaluwarsa, aman).
# ---------------------------------------------------------------------------
class FotoRef(BaseModel):
    key: str
    content_type: str = "image/jpeg"
    diunggah_oleh: str
    diunggah_pada: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/foto", tags=["foto"])


class MintaUpload(BaseModel):
    prefix: str                       # "pelayanan/<id>" | "ternak/<id>" | "peternak/<id>"
    filename: str
    content_type: str = "image/jpeg"


class UploadDibuat(BaseModel):
    key: str
    upload_url: str                   # client PUT file ke sini, langsung ke S3


@router.post("/presign-upload", response_model=UploadDibuat)
def minta_upload(body: MintaUpload, user=Depends(require_roles("petugas", "admin"))):
    if not body.content_type.startswith("image/"):
        from fastapi import HTTPException
        raise HTTPException(400, "hanya file gambar")
    key = build_key(body.prefix, body.filename)
    return UploadDibuat(key=key, upload_url=presign_upload(key, body.content_type))


class UrlFoto(BaseModel):
    url: str


@router.get("/url", response_model=UrlFoto)
def url_foto(key: str, _user=Depends(current_user)):
    return UrlFoto(url=presign_download(key))
