# puskeswan

SIM Puskeswan — administrasi keswan & layanan peternak.

Stack: FastAPI + React + MongoDB (deploy via Emergent). App saudara dari SAPgrup.

## Struktur
```
backend/
  server.py        FastAPI: /health, CORS, router foto, ensure_indexes
  db.py            Koneksi MongoDB (motor)
  storage_s3.py    Upload foto pola presigned URL (S3/R2)
  models_pelayanan.py
  models_lokasi_peternak_ternak.py
  seed_loader.py   Muat master ke Mongo dari seed JSON
  seed-master-puskeswan.json
  requirements.txt
  .env.example
frontend/
  src/App.jsx      Shell — ping /health (bukti pipeline)
  ...
```

## Jalankan lokal
Backend:
```
cd backend
pip install -r requirements.txt
cp .env.example .env        # isi MONGO_URL dll
uvicorn server:app --reload --port 8000
```
Frontend:
```
cd frontend
cp .env.example .env
npm install && npm run dev
```
Cek http://localhost:8000/health → status backend & mongo.

## Deploy (Emergent)
1. Set env di Emergent: MONGO_URL, DB_NAME, CORS_ORIGINS, dan (untuk foto) S3_*.
2. Deploy. Pastikan /health hidup.
3. Seed master sekali: `python seed_loader.py` (penyakit, ras, referensi, crosswalk iSIKHNAS).

> Catatan: samakan tata letak folder & entry point dengan repo SAPgrup yang
> sudah jalan di Emergent — itu acuan konvensi Emergent yang sudah terbukti.

## Peta jalan
Fase 0 (ini): pondasi + deploy skeleton.
Fase 1: data inti (peternak/ternak/pelayanan) + auth/RBAC + CRUD + UI.
Fase 2: rekap laporan bulanan. Fase 3: lapis AI. Fase 4: WhatsApp.
