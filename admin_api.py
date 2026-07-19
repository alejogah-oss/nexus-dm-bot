"""Panel administrador: estado de publicación + lanzar el bot de Marketplace.

Opera SOLO sobre el inventario del scanner (scanner_api.INVENTORY_DIR).
Auth: misma SCANNER_KEY que el scanner (require_key). El bot corre en el Mac Pro.
"""
import json, os, subprocess, sys, time
from pathlib import Path
from flask import Blueprint, jsonify
import scanner_api
from scanner_api import require_key

admin_bp = Blueprint("admin", __name__)

def _inv_dir() -> Path:
    return Path(scanner_api.INVENTORY_DIR)

STATUS_KEYS = ("published", "published_at", "last_error")

def read_status(folder: Path) -> dict:
    try:
        data = json.loads((folder / "listing.json").read_text())
    except Exception:
        return {"published": False, "published_at": None, "last_error": None}
    return {
        "published": bool(data.get("published", False)),
        "published_at": data.get("published_at"),
        "last_error": data.get("last_error"),
    }

def set_status(folder: Path, **fields) -> dict:
    lj = folder / "listing.json"
    data = json.loads(lj.read_text())
    for k in STATUS_KEYS:
        if k in fields:
            data[k] = fields[k]
    lj.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return read_status(folder)
