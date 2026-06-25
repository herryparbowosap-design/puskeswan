# SIM Puskeswan — PRD

## Problem Statement (Phase: skeleton bring-up)
Existing scaffold: FastAPI (backend/), React+Vite (frontend/). Bring skeleton to life only.
Targets: backend up via `uvicorn server:app`, MongoDB connected (DB_NAME=puskeswan),
CORS set to frontend domain, Vite up with VITE_API_URL, GET /health => status ok & mongo true,
seed master data via `python backend/seed_loader.py`. No new features.

## Architecture
- Backend: FastAPI + Motor (async MongoDB), supervisor runs uvicorn on :8001.
- Frontend: React 18 + Vite 5, supervisor runs `yarn start` (vite) on :3000.
- DB: local MongoDB, db `puskeswan`.

## Done (2026-06-25)
- Created backend/.env (MONGO_URL, DB_NAME=puskeswan, CORS_ORIGINS=preview domain, S3 placeholders).
- Created frontend/.env (VITE_API_URL=preview domain).
- Added `start` script to package.json; configured vite.config.js (host 0.0.0.0, port 3000, allowedHosts true).
- Added load_dotenv to db.py / server.py / seed_loader.py so .env is honored.
- Fixed dependency: pinned pymongo==4.9.2 (motor 3.6.0 needs >=4.9,<4.10); added to requirements.txt.
- Verified GET /health => {"status":"ok","service":"puskeswan","mongo":true}.
- Seeded master: penyakit 394, ras_ternak 22, referensi 14, crosswalk_isikhnas 188.

## Notes / Known limitation
- Backend health route is `/health` (not `/api`-prefixed). Platform ingress only routes `/api/*`
  to backend externally, so the frontend status card (fetch VITE_API_URL/health) won't resolve
  via the public domain. Backend itself is verified healthy via curl on :8001.

## Backlog (next phases)
- Fase 1: login + shell peran (peternak / petugas / admin).
- Domain CRUD: lokasi/peternak/ternak, pelayanan, penyakit.
