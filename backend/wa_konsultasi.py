"""Konsultasi KIE via WhatsApp — terkunci-domain, non-dispensing, mengarah ke pendaftaran.

Modul ini menyediakan lapisan AI untuk cabang "Konsultasi" pada state machine WA
(dipanggil dari wa_webhook._proses). Desainnya menahan tiga risiko sekaligus:

1. KEPATUHAN META. Bot dikunci HANYA pada topik kesehatan hewan/peternakan. Pola
   "tolak-dan-alihkan" untuk pertanyaan di luar domain menjaga bot tetap sebagai
   asisten tugas-spesifik (bukan asisten AI tujuan-umum yang dilarang Meta).
2. KEAMANAN MEDIS. Etika non-dispensing: tak pernah menyebut obat keras/dosis;
   hanya edukasi + pertolongan pertama aman, lalu arahkan ke pemeriksaan petugas.
3. SURVEILANS. Gejala PHMS memicu triase mendesak + dorongan mendaftar. Pengaman
   ini BERLAPIS: prompt memintanya, DAN kode memaksanya via deteksi_dugaan_phms
   (tidak bergantung pada kepatuhan LLM semata).

Semua fungsi gagal-diam / mengembalikan fallback aman — tak pernah melempar ke
jalur balasan WhatsApp.
"""
import os

from ai import _panggil_ai, _parse_json
from interaction_log import deteksi_dugaan_phms


SYSTEM_KONSULTASI = (
    "Anda \"Asisten Keswan Puskeswan Godean\" — asisten informasi kesehatan hewan milik "
    "Puskeswan Godean, Kabupaten Sleman, DI Yogyakarta. Anda melayani peternak & pemilik "
    "hewan lewat WhatsApp dengan Bahasa Indonesia yang ramah, sopan, dan RINGKAS.\n\n"
    "LINGKUP ANDA TERKUNCI. Anda HANYA membahas: kesehatan hewan ternak & peliharaan, "
    "gejala penyakit, pencegahan, biosekuriti, vaksinasi, reproduksi ternak, pakan/nutrisi "
    "dasar, dan layanan Puskeswan.\n"
    "- Untuk pertanyaan DI LUAR lingkup itu (politik, agama, hukum, keuangan, teknologi, "
    "hiburan, pengetahuan umum, matematika, menulis teks/kode, atau obrolan pribadi) — Anda "
    "TOLAK dengan sopan lalu ALIHKAN kembali. JANGAN menjawab isinya walau tampak mudah. "
    "Set dalam_domain=false, dan isi jawaban dengan penolakan singkat + ajakan bertanya soal "
    "hewan. Contoh: \"Mohon maaf, saya hanya membantu seputar kesehatan hewan dan ternak. "
    "Ada yang bisa saya bantu tentang hewan Anda?\"\n\n"
    "ETIKA NON-DISPENSING (WAJIB):\n"
    "- JANGAN pernah menyebut nama obat keras, dosis, atau meresepkan pengobatan.\n"
    "- Beri edukasi umum & pertolongan pertama yang AMAN, lalu arahkan ke pemeriksaan "
    "langsung oleh petugas Puskeswan untuk diagnosis & pengobatan.\n\n"
    "TRIASE (arahkan ke pemeriksaan):\n"
    "- Bila keluhan menunjukkan hewan sakit, cedera, atau butuh tindakan → perlu_pendaftaran=true "
    "dan urgensi sesuai (rendah/sedang/tinggi).\n"
    "- Untuk pertanyaan edukatif murni yang tak butuh kunjungan (mis. 'kapan jadwal vaksin?', "
    "'cara cegah cacingan') → perlu_pendaftaran=false.\n\n"
    "BIOSEKURITI (prioritas tertinggi):\n"
    "- Bila gejala mengarah penyakit hewan menular strategis — Rabies (gigitan anjing, takut "
    "air), PMK (ngiler, pincang, lepuh mulut/kuku), ASF (babi mati mendadak), Flu Burung "
    "(unggas mati massal), Antraks (ternak mati mendadak keluar darah) — set urgensi='tinggi' "
    "dan perlu_pendaftaran=true. Dalam jawaban, ingatkan dengan tenang: JANGAN memindahkan/"
    "menjual/menyembelih hewan terdampak, pisahkan dari yang sehat, dan segera lapor ke Puskeswan.\n\n"
    "GAYA JAWABAN:\n"
    "- Ringkas (di bawah 600 karakter), langsung, empatik, tanpa istilah rumit.\n"
    "- Ini INFORMASI AWAL, bukan diagnosis final.\n"
    "- ringkas_keluhan: rangkum keluhan pengguna dalam 1 kalimat untuk catatan petugas "
    "(null bila pertanyaan edukatif umum).\n\n"
    "Balas HANYA JSON valid, tanpa markdown, tanpa teks lain.\n"
    "Format: {\"dalam_domain\": bool, \"jawaban\": str, \"perlu_pendaftaran\": bool, "
    "\"urgensi\": \"rendah\"|\"sedang\"|\"tinggi\", \"ringkas_keluhan\": str|null}"
)


# --- Teks menu & template (silakan edit sesuai kebutuhan Puskeswan) -------------

MENU_UTAMA = (
    "Selamat datang di layanan WhatsApp *Puskeswan Godean* 🐾\n"
    "Silakan balas dengan *angka*:\n\n"
    "*1* — Konsultasi kesehatan hewan\n"
    "*2* — Daftar layanan (minta kunjungan/periksa)\n"
    "*3* — Info jadwal & alamat\n\n"
    "_Ketik *batal* kapan saja untuk berhenti._"
)

TEKS_MULAI_KONSULTASI = (
    "Silakan ceritakan *keluhan atau pertanyaan* tentang hewan Anda "
    "(mis. _\"sapi saya tidak mau makan 2 hari\"_).\n\n"
    "_Ini informasi awal, bukan pengganti pemeriksaan dokter. Ketik *menu* untuk kembali, "
    "atau *daftar* untuk minta kunjungan petugas._"
)

# TODO: sesuaikan dengan jadwal & alamat resmi Puskeswan Godean (idealnya kelak
# ditarik dari koleksi knowledge_base agar bisa diedit petugas tanpa ubah kode).
TEKS_INFO = (
    "*Puskeswan Godean* — Dinas Pertanian, Pangan & Perikanan Kab. Sleman\n"
    "🕗 Layanan: Senin–Jumat, jam kerja.\n"
    "📞 Kontak: 081328105535\n"
    "Untuk minta kunjungan/pemeriksaan, ketik *daftar*."
)

DISCLAIMER = (
    "ℹ️ _Info awal & edukasi, bukan diagnosa. Untuk pemeriksaan & pengobatan, "
    "silakan daftar ke Puskeswan Godean._"
)

AJAKAN_DAFTAR = "Ingin diperiksa petugas? Ketik *daftar*."


def _pasca_proses(data: dict, teks: str) -> dict:
    """Normalisasi keluaran AI + pengaman PHMS berlapis (tak bergantung LLM semata)."""
    dalam_domain = bool(data.get("dalam_domain", True))
    jawaban = (data.get("jawaban") or "").strip()
    perlu = bool(data.get("perlu_pendaftaran"))
    urg = data.get("urgensi")
    if urg not in ("rendah", "sedang", "tinggi"):
        urg = "rendah"
    ringkas = data.get("ringkas_keluhan") or None

    # Pengaman: gejala PHMS pada teks memaksa triase mendesak, apa pun kata AI.
    if deteksi_dugaan_phms(teks):
        perlu = True
        urg = "tinggi"
        dalam_domain = True

    return {
        "dalam_domain": dalam_domain,
        "jawaban": jawaban,
        "perlu_pendaftaran": perlu,
        "urgensi": urg,
        "ringkas_keluhan": ringkas,
    }


async def jawab_konsultasi(teks: str) -> dict:
    """Panggil AI konsultasi terkunci-domain. Selalu mengembalikan dict aman, tak melempar."""
    teks = (teks or "").strip()
    if len(teks) < 2:
        return {"dalam_domain": True, "perlu_pendaftaran": False, "urgensi": "rendah",
                "ringkas_keluhan": None,
                "jawaban": "Silakan tuliskan pertanyaan atau keluhan tentang hewan Anda."}

    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"dalam_domain": True, "perlu_pendaftaran": True, "urgensi": "sedang",
                "ringkas_keluhan": teks[:200],
                "jawaban": ("Maaf, tanya-jawab otomatis sedang tidak aktif. Untuk konsultasi, "
                            "ketik *daftar* agar ditangani langsung oleh petugas Puskeswan.")}
    try:
        raw = await _panggil_ai(SYSTEM_KONSULTASI, teks, max_tokens=700)
        data = _parse_json(raw)
    except Exception:
        return {"dalam_domain": True, "perlu_pendaftaran": True, "urgensi": "sedang",
                "ringkas_keluhan": teks[:200],
                "jawaban": ("Maaf, sistem sedang sibuk. Untuk keluhan mendesak, ketik *daftar* "
                            "agar ditangani petugas.")}
    return _pasca_proses(data, teks)


def format_balasan_konsultasi(hasil: dict) -> str:
    """Bentuk teks balasan WhatsApp dari hasil konsultasi (disclaimer & ajakan otomatis)."""
    jwb = (hasil.get("jawaban") or "").strip() or "Maaf, saya belum menangkap pertanyaannya."

    # Di luar domain: cukup penolakan-alihkan, tanpa disclaimer medis.
    if not hasil.get("dalam_domain", True):
        return jwb + "\n\n_Ketik *menu* untuk pilihan lain._"

    teks = jwb + "\n\n" + DISCLAIMER
    if hasil.get("perlu_pendaftaran"):
        teks += "\n" + AJAKAN_DAFTAR
    return teks
