"""Utilitas teks WhatsApp — normalisasi markdown & pemecahan pesan (chunking).

Dua masalah nyata yang ditangani modul ini:

1. NORMALISASI MARKDOWN. Model bahasa sering membalas dengan markdown gaya-web
   (`**tebal**`, `# Judul`, `- butir`, `[teks](url)`). WhatsApp TIDAK me-render
   itu — `**tebal**` muncul mentah dengan tanda bintang ganda. WhatsApp punya
   sintaks sendiri: `*tebal*` (bintang tunggal), `_miring_`, `~coret~`. Fungsi
   `normalisasi_wa_markdown` mengonversi markdown → format WhatsApp yang benar.

2. CHUNKING. Batas panjang satu pesan WhatsApp Cloud API ~4096 karakter. Kode
   pengirim lama memotong dengan `teks[:4000]` — balasan panjang HILANG diam-diam.
   `potong_pesan` memecah teks jadi beberapa bagian di batas alami (paragraf →
   baris → kalimat), menambahkan penanda (n/total) bila lebih dari satu bagian.

Modul murni (tanpa I/O, tanpa dependensi) sehingga mudah diuji.
"""
import re

# Ambang aman di bawah batas keras WhatsApp (4096). Sisakan ruang untuk penanda
# "(n/total)" dan variasi encoding.
BATAS_AMAN = 3900


def normalisasi_wa_markdown(teks: str) -> str:
    """Ubah markdown gaya-web menjadi format teks WhatsApp yang benar.

    - `**x**` / `__x__`        → `*x*`  (tebal WhatsApp)
    - `# Judul` ... `###### `   → `*Judul*` (baris judul dijadikan tebal)
    - `- x` / `* x` / `+ x`     → `• x`   (butir di awal baris)
    - `[teks](url)`             → `teks (url)`
    - `` `kode` ``              → `kode`  (backtick tunggal dibuang)
    - 3+ baris kosong           → 2 baris
    Sisa `*tebal*` asli WhatsApp dari pesan sistem tetap utuh.
    """
    if not teks:
        return ""

    baris_out = []
    for baris in teks.split("\n"):
        b = baris

        # Judul markdown (#..###### ) di awal baris → jadikan tebal WhatsApp.
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", b)
        if m:
            isi = m.group(2).strip().rstrip("#").strip()
            b = f"*{isi}*" if isi else ""
            baris_out.append(b)
            continue

        # Butir daftar di awal baris (-, *, +) diikuti spasi → bullet •.
        # Ditangani SEBELUM konversi bold agar `* ` butir tak dikira bintang tebal.
        m = re.match(r"^(\s*)([-*+])\s+(.*)$", b)
        if m:
            indent, _, isi = m.groups()
            b = f"{indent}• {isi}"

        baris_out.append(b)

    t = "\n".join(baris_out)

    # Tebal ganda markdown → tebal tunggal WhatsApp. `**x**` dan `__x__`.
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t, flags=re.S)
    t = re.sub(r"__(.+?)__", r"*\1*", t, flags=re.S)

    # Tautan markdown [teks](url) → teks (url).
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", t)

    # Backtick tunggal (kode inline) → buang tanda, sisakan isi.
    t = re.sub(r"`([^`]+)`", r"\1", t)

    # Rapikan: maksimal dua baris kosong beruntun, buang spasi ekor.
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    return t.strip()


def _pecah_paragraf_panjang(paragraf: str, batas: int) -> list[str]:
    """Pecah satu paragraf yang melebihi batas: coba per kalimat, lalu keras."""
    hasil = []
    # Pisah per kalimat sambil mempertahankan tanda baca akhir.
    kalimat = re.split(r"(?<=[.!?])\s+", paragraf)
    buf = ""
    for kal in kalimat:
        if len(kal) > batas:
            # Kalimat tunggal pun terlalu panjang → potong keras per batas.
            if buf:
                hasil.append(buf)
                buf = ""
            for i in range(0, len(kal), batas):
                hasil.append(kal[i:i + batas])
            continue
        tambah = kal if not buf else buf + " " + kal
        if len(tambah) <= batas:
            buf = tambah
        else:
            hasil.append(buf)
            buf = kal
    if buf:
        hasil.append(buf)
    return hasil


def potong_pesan(teks: str, batas: int = BATAS_AMAN, beri_penanda: bool = True) -> list[str]:
    """Pecah teks jadi daftar bagian, masing-masing <= batas karakter.

    Pemecahan mengikuti batas alami: paragraf (baris kosong) → baris → kalimat →
    (terakhir) potong keras. Bila hasilnya lebih dari satu bagian dan
    `beri_penanda` True, tiap bagian diberi awalan "(n/total)".
    Selalu mengembalikan minimal satu bagian (bisa string kosong bila input kosong).
    """
    teks = (teks or "").strip()
    if not teks:
        return [""]
    if len(teks) <= batas:
        return [teks]

    # Cadangkan ruang untuk penanda "(nn/nn)\n" ~ 9 karakter.
    batas_efektif = batas - 9 if beri_penanda else batas

    bagian = []
    buf = ""

    def dorong():
        nonlocal buf
        if buf.strip():
            bagian.append(buf.strip())
        buf = ""

    for paragraf in teks.split("\n\n"):
        # Paragraf sendiri melebihi batas → pecah lebih halus.
        if len(paragraf) > batas_efektif:
            dorong()
            for potongan in _pecah_paragraf_panjang(paragraf, batas_efektif):
                if bagian and len(bagian[-1]) + len(potongan) + 2 <= batas_efektif:
                    bagian[-1] = bagian[-1] + "\n\n" + potongan
                else:
                    bagian.append(potongan)
            continue

        calon = paragraf if not buf else buf + "\n\n" + paragraf
        if len(calon) <= batas_efektif:
            buf = calon
        else:
            dorong()
            buf = paragraf
    dorong()

    if not bagian:
        bagian = [teks[:batas_efektif]]

    if beri_penanda and len(bagian) > 1:
        total = len(bagian)
        bagian = [f"({i}/{total})\n{b}" for i, b in enumerate(bagian, 1)]
    return bagian


def siapkan_untuk_wa(teks: str, batas: int = BATAS_AMAN) -> list[str]:
    """Pipeline lengkap: normalisasi markdown lalu pecah jadi bagian siap-kirim."""
    return potong_pesan(normalisasi_wa_markdown(teks), batas=batas)
