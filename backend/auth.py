"""Autentikasi + RBAC. Semua route di bawah /api (prefix ditambah di server)."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

from db import get_db

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-ganti-di-produksi")
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 12

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


def create_token(sub: str, roles: list[str]) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": sub, "roles": roles, "exp": exp}, JWT_SECRET, algorithm=JWT_ALG)


class LoginInput(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    nama: str
    roles: list[str]
    peternak_id: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


async def current_user(token: str = Depends(oauth2)) -> dict:
    cred_exc = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "token tidak valid",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        username = payload.get("sub")
        if not username:
            raise cred_exc
    except JWTError:
        raise cred_exc
    user = await get_db().users.find_one({"username": username, "aktif": True})
    if not user:
        raise cred_exc
    return user


def require_roles(*roles: str):
    async def checker(user: dict = Depends(current_user)) -> dict:
        if not set(roles) & set(user.get("roles", [])):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "akses ditolak")
        return user
    return checker


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginInput):
    user = await get_db().users.find_one({"username": body.username, "aktif": True})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "username atau password salah")
    token = create_token(user["username"], user.get("roles", []))
    return TokenOut(
        access_token=token,
        user=UserOut(id=user["id"], nama=user["nama"], roles=user.get("roles", []),
                     peternak_id=user.get("peternak_id")),
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)):
    return UserOut(id=user["id"], nama=user["nama"], roles=user.get("roles", []),
                   peternak_id=user.get("peternak_id"))


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/ping")
async def admin_ping(user: dict = Depends(require_roles("admin"))):
    return {"ok": True, "as": user["nama"]}


@admin_router.get("/users")
async def list_users(_user: dict = Depends(require_roles("admin"))):
    """Daftar akun (admin only) — untuk memilih petugas saat mendaftarkan nomor WA."""
    rows = await get_db().users.find(
        {}, {"_id": 0, "id": 1, "nama": 1, "username": 1, "roles": 1, "aktif": 1, "peternak_id": 1}
    ).to_list(500)
    return rows


class AkunPeternakIn(BaseModel):
    username: str
    password: str


@admin_router.post("/peternak/{pid}/akun")
async def buat_akun_peternak(
    pid: str, body: AkunPeternakIn, _user: dict = Depends(require_roles("admin"))
):
    """Provision akun login (role 'peternak') dan tautkan ke record peternak `pid`.

    Aman & idempoten-guard: peternak wajib ada, belum punya akun tertaut, dan
    username belum dipakai. Password disimpan sebagai hash (tak pernah plaintext).
    """
    db = get_db()
    username = body.username.strip().lower()
    if not username or len(body.password) < 6:
        raise HTTPException(400, "username wajib & password minimal 6 karakter")

    p = await db.peternak.find_one({"id": pid}, {"_id": 0, "id": 1, "nama": 1})
    if not p:
        raise HTTPException(404, "peternak tidak ditemukan")

    if await db.users.find_one({"peternak_id": pid}):
        raise HTTPException(409, "peternak ini sudah punya akun tertaut")
    if await db.users.find_one({"username": username}):
        raise HTTPException(409, "username sudah dipakai")

    doc = {
        "id": uuid.uuid4().hex,
        "nama": p.get("nama") or username,
        "username": username,
        "password_hash": hash_password(body.password),
        "roles": ["peternak"],
        "peternak_id": pid,
        "aktif": True,
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)
    return {"id": doc["id"], "username": username, "nama": doc["nama"],
            "roles": doc["roles"], "peternak_id": pid}
