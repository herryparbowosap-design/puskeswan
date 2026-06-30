"""Generator QR — buat PNG QR di server (tanpa panggilan eksternal).

Dipakai admin untuk mencetak QR pendaftaran (umum / per kalurahan).
Butuh login (petugas/admin). Endpoint mengembalikan image/png langsung;
frontend mengambilnya via fetch ber-auth lalu menampilkan/mengunduh.
"""
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from auth import require_roles

router = APIRouter(prefix="/qr", tags=["qr"])

GREEN = (15, 110, 86)


@router.get("")
async def buat_qr(
    data: str = Query(..., min_length=1, max_length=1000),
    box: int = Query(10, ge=4, le=20),
    warna: str = Query("hijau", pattern="^(hijau|hitam)$"),
    _user=Depends(require_roles("petugas", "admin")),
):
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except Exception:
        raise HTTPException(503, "Library QR belum terpasang (qrcode/pillow)")

    fill = GREEN if warna == "hijau" else (0, 0, 0)
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill, back_color="white").get_image().convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})
