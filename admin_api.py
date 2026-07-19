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

def _lock_file() -> Path:
    return _inv_dir() / ".publish.lock"

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False

def _current_lock() -> dict | None:
    lf = _lock_file()
    if not lf.exists():
        return None
    try:
        info = json.loads(lf.read_text())
    except Exception:
        lf.unlink(missing_ok=True)
        return None
    if not _pid_alive(int(info.get("pid", -1))):
        lf.unlink(missing_ok=True)  # lock viejo de un proceso muerto
        return None
    return info

def _launch_publish(slug: str) -> int:
    """Lanza el bot en el Mac Pro (Chrome visible) como subproceso. Devuelve el PID."""
    here = Path(__file__).parent
    proc = subprocess.Popen(
        [sys.executable, str(here / "marketplace_poster.py"), "--scanner", slug],
        cwd=str(here),
    )
    return proc.pid

@admin_bp.route("/api/admin/inventory", methods=["GET"])
@require_key
def admin_inventory():
    items = []
    root = _inv_dir()
    if root.exists():
        for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            lj = d / "listing.json"
            if not lj.is_file():
                continue
            try:
                data = json.loads(lj.read_text())
            except ValueError:
                continue
            photos_dir = d / "photos"
            items.append({
                "slug": d.name, "title": data.get("title", ""),
                "make": data.get("make", ""), "model": data.get("model", ""),
                "yr": data.get("yr", ""), "price": data.get("price"),
                "mileage": data.get("mileage"),
                "photos": len(list(photos_dir.glob("*.jpg"))) if photos_dir.exists() else 0,
                **read_status(d),
            })
    lock = _current_lock()
    return jsonify({"items": items, "publishing": lock.get("slug") if lock else None})

@admin_bp.route("/api/admin/publish/<slug>", methods=["POST"])
@require_key
def admin_publish(slug):
    folder = scanner_api._folder_for(slug)
    if not folder:
        return jsonify({"error": "no existe"}), 404
    lock = _current_lock()
    if lock:
        return jsonify({"error": "ya hay una publicación en curso", "slug": lock.get("slug")}), 409
    pid = _launch_publish(slug)
    _lock_file().write_text(json.dumps({"slug": slug, "pid": pid}))
    set_status(folder, last_error=None)
    return jsonify({"ok": True, "slug": slug})

@admin_bp.route("/api/admin/mark/<slug>", methods=["POST"])
@require_key
def admin_mark(slug):
    folder = scanner_api._folder_for(slug)
    if not folder:
        return jsonify({"error": "no existe"}), 404
    st = set_status(folder, published=True,
                    published_at=time.strftime("%Y-%m-%d %H:%M"), last_error=None)
    _lock_file().unlink(missing_ok=True)
    return jsonify({"ok": True, **st})
