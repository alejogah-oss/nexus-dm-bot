"""Sincroniza un carro del scanner a la base de datos de tucarroconalejo.com,
SIEMPRE como pendiente de aprobar (active=0).

Reusa api.php?action=save (el mismo endpoint que usa admin.html para altas
manuales) — no publica nada por sí solo. La aprobación (activar el carro para
que se vea en el sitio) es exclusiva del panel /admin del propio sitio
(tucarroconalejo.com/admin.html, pestaña "Pendientes"), NO de este panel del
scanner — el Mac Pro es solo para Marketplace, son dos cosas separadas.
Esta función solo mantiene sincronizados los datos (precio, fotos, millaje)
del borrador; nunca toca el campo 'active' en un re-sync, para no revertir
una aprobación ya hecha desde admin.html.
"""
import base64
import io
import json
import os
import time
from pathlib import Path

import requests
from PIL import Image

SITE_API_URL = os.environ.get("SITE_API_URL", "https://tucarroconalejo.com/api.php")
SITE_ADMIN_PASSWORD = os.environ.get("SITE_ADMIN_PASSWORD", "")

MAX_PHOTOS = 12
MAX_DIM = 1600
JPEG_QUALITY = 78


def _photo_data_uri(path: Path) -> str:
    img = Image.open(path).convert("RGB")
    img.thumbnail((MAX_DIM, MAX_DIM))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _photo_paths(folder: Path) -> list[Path]:
    photos_dir = folder / "photos"
    if not photos_dir.exists():
        return []
    files = sorted(photos_dir.glob("*.jpg"), key=lambda p: p.stem)
    return files[:MAX_PHOTOS]


def _infer_type(mileage) -> str:
    """Mismo criterio que usa inventario.html para el filtro Nuevo/Usado
    (basado en millaje, no en un campo de 'condición' aparte): 0 o vacío = nuevo."""
    digits = "".join(ch for ch in str(mileage or "") if ch.isdigit())
    return "new" if not digits or int(digits) == 0 else "used"


def build_payload(data: dict, folder: Path) -> dict:
    vin = str(data.get("vin", ""))
    mileage = data.get("mileage", "")
    payload = {
        "yr": int(data.get("yr") or 2020),
        "make": data.get("make") or "Toyota",
        "model": data.get("model", ""),
        "trim": data.get("trim", ""),
        "color": data.get("color", ""),
        "hp": int(data.get("hp") or 0),
        "drive": data.get("drive") or "FWD",
        "trans": data.get("trans") or "Auto",
        "price": float(data.get("price") or 0),
        "msrp": float(data.get("msrp") or 0),
        "mileage": str(mileage),
        "vin": vin,
        "stock": data.get("stock") or vin[-6:],
        "body_style": data.get("body_style") or data.get("body") or "",
        "fuel_type": data.get("fuel_type") or "",
        "type": data.get("type") or _infer_type(mileage),
        "badges": data.get("badges") or [],
        "dots": data.get("dots") or [],
        "source": "scanner",  # protege este carro del refresco por CSV (nuevo o usado)
    }
    data_uris = [_photo_data_uri(p) for p in _photo_paths(folder)]
    if data_uris:
        payload["img"] = data_uris[0]
        payload["imgs"] = data_uris[1:]
    site_id = data.get("site_id")
    if site_id:
        payload["id"] = int(site_id)  # presencia de 'id' -> UPDATE (no toca 'active')
    else:
        payload["active"] = 0  # primer envío: siempre pendiente de aprobar
    return payload


def push_scanner_car_to_site(folder: Path) -> dict:
    """Crea (pendiente) o resincroniza datos del vehículo en tucarroconalejo.com.
    Siempre deja listing.json con el resultado (site_synced / site_error), incluso si falla."""
    lj = folder / "listing.json"
    data = json.loads(lj.read_text())
    try:
        if not SITE_ADMIN_PASSWORD:
            raise RuntimeError("falta SITE_ADMIN_PASSWORD en el entorno")
        payload = build_payload(data, folder)
        resp = requests.post(
            f"{SITE_API_URL}?action=save",
            json=payload,
            headers={"X-Admin-Password": SITE_ADMIN_PASSWORD},
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "respuesta sin 'ok'")
        data["site_id"] = result["id"]
        data["site_synced"] = True
        data["site_synced_at"] = time.strftime("%Y-%m-%d %H:%M")
        data["site_error"] = None
        lj.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return {"ok": True, "site_id": result["id"], "site_synced_at": data["site_synced_at"]}
    except Exception as e:
        data["site_error"] = str(e)
        lj.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return {"ok": False, "error": str(e)}
