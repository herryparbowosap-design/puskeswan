"""
Model data: wilayah (lokasi bertingkat), koordinat, ras, peternak, ternak.

Prinsip:
- Lokasi DUA lapis yang saling melengkapi:
  (1) `wilayah` bertingkat — kapanewon > kalurahan > padukuhan
      (= kecamatan > desa > dusun). Untuk rekap & administrasi; WAJIB cocok
      dengan laporan bulanan. Pohon self-referencing → cascade dropdown.
  (2) `koordinat` (GeoJSON Point) — untuk peta sebaran & navigasi Google Maps.
      Index 2dsphere di MongoDB → bonus: query radius (mis. semua ternak dalam
      radius X km dari titik wabah) untuk pengendalian penyakit, bukan sekadar
      menampilkan titik.
- Peternak SEDERHANA: minimal untuk dibuat = nama + kontak + koordinat.
  Sisanya opsional / terisi otomatis (reverse-geocode dari GPS).
- Semua field "tinggal pilih" didukung combobox dengan search; field pencarian
  (nama, kontak, nik) diberi index agar typeahead cepat dan anti-duplikat.

Pydantic v2.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Wilayah — pohon administratif (nomenklatur DIY)
# ---------------------------------------------------------------------------
class LevelWilayah(str, Enum):
    KAPANEWON = "kapanewon"    # = kecamatan
    KALURAHAN = "kalurahan"    # = desa
    PADUKUHAN = "padukuhan"    # = dusun


class Wilayah(BaseModel):
    """Satu node pohon. Cascade: pilih kapanewon -> filter kalurahan by
    parent_id -> pilih -> filter padukuhan by parent_id."""
    id: str
    nama: str
    level: LevelWilayah
    parent_id: Optional[str] = None    # None hanya untuk kapanewon
    kode: Optional[str] = None         # kode Kemendagri/BPS bila tersedia
    # Index disarankan: (level), (parent_id), text(nama) untuk search.


# ---------------------------------------------------------------------------
# Koordinat — GeoJSON Point (siap index 2dsphere)
# ---------------------------------------------------------------------------
class Koordinat(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: list[float] = Field(
        ..., description="[lng, lat] — PERHATIKAN urutan GeoJSON: bujur dulu"
    )

    @field_validator("coordinates")
    @classmethod
    def _cek_panjang(cls, v: list[float]) -> list[float]:
        if len(v) != 2:
            raise ValueError("coordinates harus [lng, lat]")
        return v

    @classmethod
    def dari_latlng(cls, lat: float, lng: float) -> "Koordinat":
        return cls(coordinates=[lng, lat])

    @property
    def lat(self) -> float:
        return self.coordinates[1]

    @property
    def lng(self) -> float:
        return self.coordinates[0]

    def maps_dir_link(self) -> str:
        """Deep-link navigasi: petugas tap -> Google Maps buka rute."""
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&destination={self.lat},{self.lng}"
        )


# ---------------------------------------------------------------------------
# Ras ternak — master, cascade dari spesies
# ---------------------------------------------------------------------------
class RasTernak(BaseModel):
    """Cascade: pilih spesies -> filter ras by spesies. Sumber awal: kolom
    JENIS_HEWAN pada REFERENSI (mis. Sapi -> PFH/PO/PL/PS/PM/Jersey)."""
    id: str
    spesies: str
    nama: str


# ---------------------------------------------------------------------------
# Peternak — lengkap tapi sederhana (progressive)
# ---------------------------------------------------------------------------
class Peternak(BaseModel):
    id: str
    nama: str                              # WAJIB
    kontak: str                            # WAJIB — nomor WA (kanal layanan)
    nik: Optional[str] = None              # untuk identitas & anti-duplikat

    # Lokasi bertingkat (denormalisasi: simpan ketiganya untuk rekap cepat).
    # Boleh terisi otomatis via reverse-geocode dari koordinat.
    kapanewon_id: Optional[str] = None     # FK -> wilayah (level kapanewon)
    kalurahan_id: Optional[str] = None     # FK -> wilayah (level kalurahan)
    padukuhan_id: Optional[str] = None     # FK -> wilayah (level padukuhan)
    alamat_detail: Optional[str] = None    # RT/RW, patokan jalan

    koordinat: Optional[Koordinat] = None  # peta sebaran + navigasi

    catatan: Optional[str] = None
    dibuat_oleh: str                       # peternak sendiri / petugas (bootstrap)
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Index disarankan: text(nama, kontak, nik) utk search; 2dsphere(koordinat).


# ---------------------------------------------------------------------------
# Ternak — status lifecycle, ras cascade, lapis ganda
# ---------------------------------------------------------------------------
class ModeTernak(str, Enum):
    INDIVIDU = "individu"      # ruminansia besar (eartag)
    POPULASI = "populasi"      # unggas / kelompok


class StatusTernak(str, Enum):
    AKTIF = "aktif"            # satu-satunya status aktif
    MATI = "mati"              # } 
    DIJUAL = "dijual"          # }  ketiganya = NON-AKTIF (terminal)
    DIPOTONG = "dipotong"      # }

    @property
    def aktif(self) -> bool:
        return self is StatusTernak.AKTIF


class Ternak(BaseModel):
    id: str
    peternak_id: str                       # FK -> peternak

    spesies: str                           # dropdown (master/REFERENSI)
    ras_id: Optional[str] = None           # FK -> ras_ternak (cascade dari spesies)
    mode: ModeTernak = ModeTernak.INDIVIDU

    # mode individu
    eartag: Optional[str] = None
    jenis_kelamin: Optional[str] = None
    tgl_lahir: Optional[date] = None

    # mode populasi + lapis ganda (deklarasi peternak vs verifikasi petugas)
    jml_deklarasi: Optional[int] = None
    jml_verifikasi: Optional[int] = None

    # lifecycle — disetir oleh event mutasi_ternak
    status: StatusTernak = StatusTernak.AKTIF
    tgl_status: Optional[date] = None      # kapan menjadi non-aktif

    koordinat: Optional[Koordinat] = None  # opsional; default ikut peternak

    created_at: datetime
    updated_at: Optional[datetime] = None

    @property
    def aktif(self) -> bool:
        return self.status is StatusTernak.AKTIF


# Sinkronisasi status (dipanggil saat mutasi dicatat):
#   mutasi "mati"    -> status=MATI
#   mutasi "jual"    -> status=DIJUAL
#   mutasi "potong"  -> status=DIPOTONG
# Status tidak diedit manual; selalu konsekuensi dari event mutasi_ternak.
_PETA_MUTASI_KE_STATUS = {
    "mati": StatusTernak.MATI,
    "jual": StatusTernak.DIJUAL,
    "potong": StatusTernak.DIPOTONG,
}


def status_dari_mutasi(jenis_mutasi: str) -> Optional[StatusTernak]:
    return _PETA_MUTASI_KE_STATUS.get(jenis_mutasi)
