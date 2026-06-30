"""Notifikasi WhatsApp — outbound, provider-agnostic, feature-flagged.

Provider dipilih via env WA_PROVIDER:
  - "cloud"  : Meta WhatsApp Cloud API (resmi). Pakai TEMPLATE yang sudah disetujui
               (pesan bisnis-inisiasi di luar jendela 24 jam wajib template).
  - "fonnte" : layanan tidak resmi (teks bebas). Disediakan untuk fleksibilitas.
  - "none"   : nonaktif (default). Tidak mengirim apa pun.

Aman: jika kredensial kosong atau gagal kirim, fungsi MENGEMBALIKAN status (dict),
TIDAK melempar exception — sehingga alur konfirmasi/tolak tak pernah terblokir.

Kredensial diisi via env (Emergent UI), JANGAN di kode:
  WA_PROVIDER=cloud
  WA_CLOUD_TOKEN=...            (access token sistem-user)
  WA_CLOUD_PHONE_ID=...         (phone number id WABA)
  WA_CLOUD_TEMPLATE_KONFIRMASI=pendaftaran_terverifikasi   (nama template utility, {{1}}=nama)
  WA_CLOUD_TEMPLATE_TOLAK=pendaftaran_ditolak
  WA_CLOUD_LANG=id             (kode bahasa template; default id)
  WA_API_VERSION=v21.0         (opsional)
  # untuk fonnte: WA_FONNTE_TOKEN=...
"""
import os
import json
import asyncio
import urllib.parse
import urllib.request
import urllib.error


def normalisasi_no(no) -> str | None:
    """08xx / 62xx / +62 → 62xxxxxxxxxx (hanya digit)."""
    if not no:
        return None
    d = "".join(ch for ch in str(no) if ch.isdigit())
    if not d:
        return None
    if d.startswith("620"):
        d = "62" + d[3:]
    elif d.startswith("62"):
        pass
    elif d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    return d if len(d) >= 9 else None


def _pesan_default(nama, jenis) -> str:
    nama = nama or "Bapak/Ibu"
    if jenis == "konfirmasi":
        return (f"Halo {nama}, pendaftaran Anda di Puskeswan Godean telah DIVERIFIKASI. "
                f"Petugas akan menindaklanjuti sesuai jadwal layanan. Terima kasih.")
    return (f"Halo {nama}, mohon maaf, pendaftaran Anda di Puskeswan Godean belum dapat "
            f"diproses. Silakan hubungi 081328105535 untuk informasi lebih lanjut.")


def _post_json(url, headers, payload, timeout=10):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def _post_form(url, headers, fields, timeout=10):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def _bangun_payload_cloud(no, nama, jenis):
    """Susun payload Cloud API (template utility, {{1}}=nama). Dipisah agar bisa diuji."""
    tpl = os.getenv("WA_CLOUD_TEMPLATE_KONFIRMASI" if jenis == "konfirmasi" else "WA_CLOUD_TEMPLATE_TOLAK")
    if not tpl:
        return None
    lang = os.getenv("WA_CLOUD_LANG", "id")
    return {
        "messaging_product": "whatsapp",
        "to": no,
        "type": "template",
        "template": {
            "name": tpl,
            "language": {"code": lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": nama or "Bapak/Ibu"}]}
            ],
        },
    }


async def _kirim_cloud(no, nama, jenis):
    token = os.getenv("WA_CLOUD_TOKEN")
    phone_id = os.getenv("WA_CLOUD_PHONE_ID")
    if not token or not phone_id:
        return {"status": "skip", "alasan": "kredensial cloud kosong"}
    payload = _bangun_payload_cloud(no, nama, jenis)
    if payload is None:
        return {"status": "skip", "alasan": "nama template belum diatur"}
    ver = os.getenv("WA_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{ver}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        status, body = await asyncio.to_thread(_post_json, url, headers, payload)
        ok = 200 <= status < 300
        return {"status": "terkirim" if ok else "gagal", "http": status, "resp": body[:300]}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = str(e)
        return {"status": "gagal", "http": getattr(e, "code", None), "resp": detail}
    except Exception as e:
        return {"status": "gagal", "error": str(e)[:200]}


async def _kirim_fonnte(no, nama, jenis):
    token = os.getenv("WA_FONNTE_TOKEN")
    if not token:
        return {"status": "skip", "alasan": "token fonnte kosong"}
    headers = {"Authorization": token, "Content-Type": "application/x-www-form-urlencoded"}
    fields = {"target": no, "message": _pesan_default(nama, jenis)}
    try:
        status, body = await asyncio.to_thread(_post_form, "https://api.fonnte.com/send", headers, fields)
        ok = 200 <= status < 300
        return {"status": "terkirim" if ok else "gagal", "http": status, "resp": body[:300]}
    except Exception as e:
        return {"status": "gagal", "error": str(e)[:200]}


async def kirim_teks_wa(no, teks):
    """Kirim teks BEBAS via Cloud API (hanya valid dalam jendela 24 jam — untuk
    balasan alur inbound, di mana pengguna sudah chat duluan, jadi GRATIS).
    Mengembalikan dict status, tak melempar."""
    provider = (os.getenv("WA_PROVIDER") or "none").lower()
    if provider == "none":
        return {"status": "off"}
    no = normalisasi_no(no)
    if not no:
        return {"status": "skip", "alasan": "no HP tidak valid"}
    if provider == "fonnte":
        token = os.getenv("WA_FONNTE_TOKEN")
        if not token:
            return {"status": "skip", "alasan": "token fonnte kosong"}
        try:
            status, body = await asyncio.to_thread(
                _post_form, "https://api.fonnte.com/send",
                {"Authorization": token, "Content-Type": "application/x-www-form-urlencoded"},
                {"target": no, "message": teks})
            return {"status": "terkirim" if 200 <= status < 300 else "gagal", "http": status}
        except Exception as e:
            return {"status": "gagal", "error": str(e)[:200]}
    # cloud
    token = os.getenv("WA_CLOUD_TOKEN")
    phone_id = os.getenv("WA_CLOUD_PHONE_ID")
    if not token or not phone_id:
        return {"status": "skip", "alasan": "kredensial cloud kosong"}
    ver = os.getenv("WA_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{ver}/{phone_id}/messages"
    payload = {"messaging_product": "whatsapp", "to": no, "type": "text", "text": {"body": teks[:4000]}}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        status, body = await asyncio.to_thread(_post_json, url, headers, payload)
        return {"status": "terkirim" if 200 <= status < 300 else "gagal", "http": status, "resp": body[:300]}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = str(e)
        return {"status": "gagal", "http": getattr(e, "code", None), "resp": detail}
    except Exception as e:
        return {"status": "gagal", "error": str(e)[:200]}

    """jenis: 'konfirmasi' | 'tolak'. Selalu mengembalikan dict status, tak melempar."""
    provider = (os.getenv("WA_PROVIDER") or "none").lower()
    if provider == "none":
        return {"status": "off"}
    no = normalisasi_no(kontak)
    if not no:
        return {"status": "skip", "alasan": "no HP tidak valid"}
    try:
        if provider == "cloud":
            return await _kirim_cloud(no, nama, jenis)
        if provider == "fonnte":
            return await _kirim_fonnte(no, nama, jenis)
        return {"status": "skip", "alasan": f"provider tak dikenal: {provider}"}
    except Exception as e:
        return {"status": "gagal", "error": str(e)[:200]}
