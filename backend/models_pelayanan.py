"""
Model data koleksi `pelayanan` — SIM Puskeswan.

Satu koleksi untuk 10 jenis aktivitas pelayanan, dibedakan `kategori`.
Tulang punggung sama; field khas tiap jenis disimpan di `detail`
(discriminated union pada field `kategori`).

Prinsip desain (hasil pemetaan dari Template Laporan Bulanan):
- Registry ternak OPSIONAL di titik input: `peternak`/`hewan` bisa menunjuk
  record terdaftar (via *_id) atau memuat snapshot bebas. Laporan tetap
  bisa keluar walau ternak belum terdaftar.
- iSIKHNAS first-class: `isikhnas_id` + `penyakit_id` (kode iSIKHNAS).
- Audit wajib: created_by/created_at + jejak konfirmasi draft AI.

Catatan: KEMATIAN bukan kategori pelayanan — itu event `mutasi_ternak`
(jenis="mati") yang membawa penyakit_id. Lihat MutasiTernak di bawah.

Pydantic v2.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enum — sumber nilai: sheet REFERENSI pada template laporan
# ---------------------------------------------------------------------------
class KategoriPelayanan(str, Enum):
    KESWAN = "KESWAN"          # sheet: pelayanan keswan
    GANGREP = "GANGREP"        # sheet: data Gangrep -> Gangrep
    PKB = "PKB"                # sheet: PKB
    VAKSINASI = "VAKSINASI"    # sheet: data vaksinasi -> vaksinasi
    LAB = "LAB"                # sheet: data lab -> pem.lab / rekap data lab
    YANDUWAN = "YANDUWAN"      # sheet: yanduwan
    PEMBINAAN = "PEMBINAAN"    # sheet: pembinaan
    DESINFEKSI = "DESINFEKSI"  # sheet: desinfeksi -> brantas penyakit
    KONSULTASI = "KONSULTASI"  # sheet: Layanan Konsultasi
    ADUAN = "ADUAN"            # sheet: Layanan Aduan


class Prognosa(str, Enum):            # REFERENSI.PROGNOSA
    FAUSTA = "Fausta"
    DUBIUS = "Dubius"
    INFAUSTA = "Infausta"


class MetodeLayanan(str, Enum):       # REFERENSI.METODE_LAYANAN
    LANGSUNG = "Langsung"
    TIDAK_LANGSUNG = "Tidak Langsung"
    TELEPON_WA = "Telepon/WA"
    KUNJUNGAN_LAPANGAN = "Kunjungan Lapangan"


class HasilPKB(str, Enum):            # REFERENSI.DIAGNOSA_PKB
    BUNTING = "Bunting"
    TIDAK_BUNTING = "Tidak Bunting"
    BIRAHI = "Birahi"
    BELUM_BIRAHI = "Belum Birahi"


class SumberInput(str, Enum):
    MANUAL = "manual"
    AI_DRAFT = "ai_draft"     # distrukturkan AI, lalu dikonfirmasi petugas


# ---------------------------------------------------------------------------
# Snapshot — registry opsional
# ---------------------------------------------------------------------------
class PeternakSnapshot(BaseModel):
    """Menunjuk peternak terdaftar (peternak_id) ATAU snapshot bebas."""
    peternak_id: Optional[str] = None        # FK -> peternak (jika terdaftar)
    nama: str                                # kolom: Nama Peternak
    wilayah_id: Optional[str] = None         # FK -> wilayah (kalurahan)
    alamat: Optional[str] = None             # kolom: Alamat (dusun, desa, kec)


class HewanSnapshot(BaseModel):
    """Objek hewan; ternak_id diisi bila sudah ada di registry."""
    ternak_id: Optional[str] = None          # FK -> ternak (jika terdaftar)
    jenis_hewan: str                         # REFERENSI.JENIS_HEWAN (mis. "Sapi PFH")
    kelamin: Optional[str] = None            # REFERENSI.KELAMIN
    umur: Optional[str] = None               # bebas: "3 th", "5 bln"
    jumlah: int = 1                          # kolom: Jumlah


# ---------------------------------------------------------------------------
# Detail per kategori (discriminated union pada `kategori`)
# ---------------------------------------------------------------------------
class DetailKeswan(BaseModel):
    kategori: Literal["KESWAN"] = "KESWAN"
    # diagnosa/tindakan/prognosa ada di tulang punggung Pelayanan


class DetailGangrep(BaseModel):
    kategori: Literal["GANGREP"] = "GANGREP"
    # diagnosa dibatasi subset GANGREP; pengobatan -> Pelayanan.tindakan


class DetailPKB(BaseModel):
    kategori: Literal["PKB"] = "PKB"
    hasil: HasilPKB                          # kolom: Diagnosa PKB
    usia_kebuntingan_bln: Optional[float] = None  # kolom: usia kebuntingan


class DetailVaksinasi(BaseModel):
    kategori: Literal["VAKSINASI"] = "VAKSINASI"
    jenis_vaksin: str                        # REFERENSI.JENIS_VAKSIN / Nama Vaksin
    no_batch: Optional[str] = None           # kolom: No. Batch (telusur)
    dosis: Optional[float] = None            # kolom: Hitungan Dosis
    jumlah_divaksin: int                     # kolom: Jumlah divaksin
    # NB: catat pemakaian vaksin sebagai KunjunganObat (stok keluar)


class DetailLab(BaseModel):
    kategori: Literal["LAB"] = "LAB"
    specimen: str                            # REFERENSI.SPECIMEN
    hasil_lab: str                           # REFERENSI.DIAGNOSA_LAB


class YanduwanRincian(BaseModel):
    jenis_ternak: str                        # REFERENSI.JENIS_TERNAK
    populasi: int                            # kolom: Populasi
    perlakuan: int                           # kolom: Perlakuan


class DetailYanduwan(BaseModel):
    kategori: Literal["YANDUWAN"] = "YANDUWAN"
    nama_kelompok: str                       # kolom: Nama dan Alamat Kelompok
    rincian: list[YanduwanRincian]           # per jenis ternak


class DetailPembinaan(BaseModel):
    kategori: Literal["PEMBINAAN"] = "PEMBINAAN"
    nama_kelompok: str                       # kolom: Nama dan Alamat Kelompok
    materi: str                              # kolom: Materi
    jumlah_peserta: int                      # kolom: Jumlah Peserta


class DetailDesinfeksi(BaseModel):
    kategori: Literal["DESINFEKSI"] = "DESINFEKSI"
    jenis_desinfektan: str                   # REFERENSI.DESINFEKTAN
    jumlah_ml: Optional[float] = None        # kolom: Jumlah Desinfektan (ml)
    jumlah_tab: Optional[float] = None       # kolom: Jumlah Desinfektan (tab)
    # NB: catat pemakaian desinfektan sebagai KunjunganObat (sarana, stok keluar)


class DetailKonsultasi(BaseModel):
    kategori: Literal["KONSULTASI"] = "KONSULTASI"
    uraian: str                              # kolom: Uraian Konsultasi


class DetailAduan(BaseModel):
    kategori: Literal["ADUAN"] = "ADUAN"
    uraian: str                              # kolom: Uraian Aduan
    tindak_lanjut: Optional[str] = None      # kolom: Informasi Tindak Lanjut/Solusi
    # NB: aduan dapat berasal dari permintaan_layanan (kanal WA)


PelayananDetail = Annotated[
    Union[
        DetailKeswan, DetailGangrep, DetailPKB, DetailVaksinasi, DetailLab,
        DetailYanduwan, DetailPembinaan, DetailDesinfeksi, DetailKonsultasi,
        DetailAduan,
    ],
    Field(discriminator="kategori"),
]


# ---------------------------------------------------------------------------
# Koleksi utama: pelayanan
# ---------------------------------------------------------------------------
class Pelayanan(BaseModel):
    id: str
    kategori: KategoriPelayanan
    tgl: date                                # kolom: TGL / Tanggal

    petugas_id: str                          # FK -> petugas
    peternak: PeternakSnapshot
    hewan: Optional[HewanSnapshot] = None    # None utk PEMBINAAN/KONSULTASI/ADUAN non-hewan

    # Diagnosa terstandar + iSIKHNAS
    penyakit_id: Optional[str] = None        # FK -> penyakit (kode iSIKHNAS)
    diagnosa_teks: Optional[str] = None      # label sesuai input (kolom: Diagnosa)
    isikhnas_id: Optional[str] = None        # kolom: Isikhnas / ID Kasus

    tindakan: Optional[str] = None           # kolom: Tindakan / Pengobatan
    prognosa: Optional[Prognosa] = None      # kolom: Prognosa
    metode_layanan: Optional[MetodeLayanan] = None
    keterangan: Optional[str] = None         # kolom: Keterangan

    detail: PelayananDetail

    # Audit & jejak AI
    sumber_input: SumberInput = SumberInput.MANUAL
    dikonfirmasi_oleh: Optional[str] = None  # petugas yang verifikasi draft AI
    created_by: str
    created_at: datetime

    @model_validator(mode="after")
    def _kategori_konsisten(self) -> "Pelayanan":
        if self.detail.kategori != self.kategori.value:
            raise ValueError(
                f"kategori ({self.kategori.value}) != detail.kategori "
                f"({self.detail.kategori})"
            )
        return self


# ---------------------------------------------------------------------------
# Event terkait: mutasi_ternak (menampung KEMATIAN untuk rekap kematian)
# ---------------------------------------------------------------------------
class JenisMutasi(str, Enum):
    LAHIR = "lahir"
    MATI = "mati"
    JUAL = "jual"
    BELI = "beli"
    POTONG = "potong"


class MutasiTernak(BaseModel):
    id: str
    ternak_id: Optional[str] = None          # FK -> ternak (bila terdaftar)
    jenis: JenisMutasi
    jumlah: int
    tgl: date
    # khusus jenis="mati": isi diagnosa untuk rekap kematian/unggas/AI/ND
    penyakit_id: Optional[str] = None        # FK -> penyakit
    diagnosa_teks: Optional[str] = None
    # snapshot bila ternak belum terdaftar (laporan event-centric)
    peternak: Optional[PeternakSnapshot] = None
    hewan: Optional[HewanSnapshot] = None
    dicatat_oleh: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Event terkait: kunjungan_obat (stok keluar — vaksin/obat/sarana)
# ---------------------------------------------------------------------------
class KunjunganObat(BaseModel):
    id: str
    pelayanan_id: str                        # FK -> pelayanan
    obat_id: str                             # FK -> obat
    jumlah: float                            # mengurangi stok (lihat ledger)
    no_batch: Optional[str] = None
