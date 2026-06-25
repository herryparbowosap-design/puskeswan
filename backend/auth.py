"""Autentikasi + RBAC. Semua route di bawah /api (prefix ditambah di server)."""
import os
from datetime import datetime, timedelta, timezone

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
        user=UserOut(id=user["id"], nama=user["nama"], roles=user.get("roles", [])),
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(current_user)):
    return UserOut(id=user["id"], nama=user["nama"], roles=user.get("roles", []))


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/ping")
async def admin_ping(user: dict = Depends(require_roles("admin"))):
    return {"ok": True, "as": user["nama"]}
