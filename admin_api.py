"""Panel administrador: estado de publicación + lanzar el bot de Marketplace.

Opera SOLO sobre el inventario del scanner (scanner_api.INVENTORY_DIR).
Auth: misma SCANNER_KEY que el scanner (require_key). El bot corre en el Mac Pro.
"""
import json, os, re, subprocess, sys, threading, time
from pathlib import Path
import requests
from flask import Blueprint, jsonify, request
import scanner_api
import site_publisher
from scanner_api import require_key
from vin_utils import decode_vin

admin_bp = Blueprint("admin", __name__)

# Serializa la sección crítica de admin_publish (check-del-lock + launch +
# escritura del lock). app.run() en Flask 3.x es threaded=True por defecto
# (necesario para las subidas grandes de video del scanner), así que dos
# requests casi simultáneos (doble-clic) podían pasar ambos el check y
# lanzar dos Chrome. Ver .superpowers/sdd/task-6-report.md.
_PUBLISH_MUTEX = threading.Lock()

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

def is_inactive(folder: Path) -> bool:
    try:
        return bool(json.loads((folder / "listing.json").read_text()).get("inactive"))
    except Exception:
        return False

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
    if pid <= 0:
        return False
    # El subproceso de publicación es hijo directo de este proceso Flask.
    # Si ya terminó pero nadie hizo wait(), queda <defunct> (zombie): kill(pid, 0)
    # sigue viendo el PID como "vivo" para siempre. waitpid con WNOHANG lo reapea
    # si ya terminó, sin bloquear si sigue corriendo.
    try:
        reaped_pid, _status = os.waitpid(pid, os.WNOHANG)
        if reaped_pid == pid:
            return False
    except ChildProcessError:
        return False
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
        pid = int(info.get("pid", -1))
    except Exception:
        lf.unlink(missing_ok=True)
        return None
    if not _pid_alive(pid):
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
                "vin": data.get("vin", ""),
                "make": data.get("make", ""), "model": data.get("model", ""),
                "yr": data.get("yr", ""), "price": data.get("price"),
                "mileage": data.get("mileage"),
                "internal_price": data.get("internal_price") or 0,
                "alt_price_low": data.get("alt_price_low") or 0,
                "alt_price_high": data.get("alt_price_high") or 0,
                "updated_at": time.strftime("%d/%m %H:%M", time.localtime(lj.stat().st_mtime)),
                "photos": len(list(photos_dir.glob("*.jpg"))) if photos_dir.exists() else 0,
                "inactive": bool(data.get("inactive")),
                "inactive_at": data.get("inactive_at"),
                "on_site": bool(data.get("site_id")),
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
    if is_inactive(folder):
        return jsonify({"error": "el carro está inactivo — reactívalo antes de publicar"}), 409
    with _PUBLISH_MUTEX:
        lock = _current_lock()
        if lock:
            return jsonify({"error": "ya hay una publicación en curso", "slug": lock.get("slug")}), 409
        pid = _launch_publish(slug)
        _lock_file().write_text(json.dumps({"slug": slug, "pid": pid}))
        set_status(folder, last_error=None)
    return jsonify({"ok": True, "slug": slug})

@admin_bp.route("/api/admin/regenerate/<slug>", methods=["POST"])
@require_key
def admin_regenerate(slug):
    folder = scanner_api._folder_for(slug)
    if not folder:
        return jsonify({"error": "no existe"}), 404
    if read_status(folder)["published"]:
        return jsonify({"error": "ya está publicado — no se puede regenerar el copy"}), 409
    data = json.loads((folder / "listing.json").read_text())
    try:
        decoded = decode_vin(data["vin"])
    except Exception:
        decoded = {}
    notes = (data.get("notes") or "").strip()
    if data.get("color"):
        notes = (notes + f" | Color: {data['color']}").strip(" |")
    car = {
        "yr": data.get("yr") or decoded.get("yr", ""),
        "make": decoded.get("make", ""),
        "model": data.get("model") or decoded.get("model", ""),
        "trim": data.get("trim") or decoded.get("trim", ""),
        "engine": decoded.get("engine", ""),
        "fuel": decoded.get("fuel", ""),
        "body": decoded.get("body", ""),
        "drive": decoded.get("drive", ""),
        "mileage": data.get("mileage", 0),
        "price": data.get("price", 0),
        "notes": notes,
    }
    try:
        out = scanner_api.generate_copy(car)
    except Exception:
        return jsonify({"error": "no se pudo generar el copy — reintenta"}), 502
    return jsonify(out)

@admin_bp.route("/api/admin/mark/<slug>", methods=["POST"])
@require_key
def admin_mark(slug):
    folder = scanner_api._folder_for(slug)
    if not folder:
        return jsonify({"error": "no existe"}), 404
    st = set_status(folder, published=True,
                    published_at=time.strftime("%Y-%m-%d %H:%M"), last_error=None)
    lock = _current_lock()
    if lock and lock.get("slug") == slug:
        _lock_file().unlink(missing_ok=True)
    return jsonify({"ok": True, **st})

# ── Inactivar / reactivar ────────────────────────────────────────────
# Un carro que ya no está en el lote. Facebook lo marca Alejo a mano (decisión
# del 2 oct 2026: nada de automatizar Marketplace para no arriesgar la cuenta).
# Acá solo: se borra de tucarroconalejo.com — de donde leen el inventario el bot
# de Marketplace y el DM bot, así que dejan de ofrecerlo — y queda marcado
# inactivo en listing.json. Se BORRA del sitio en vez de poner active=0 porque
# active=0 es "Pendiente de aprobar" en admin.html y alguien lo re-aprobaría.

def _delete_from_site(site_id: int) -> None:
    if not site_publisher.SITE_ADMIN_PASSWORD:
        raise RuntimeError("falta SITE_ADMIN_PASSWORD en el entorno")
    resp = requests.post(
        f"{site_publisher.SITE_API_URL}?action=delete",
        json={"id": int(site_id)},
        headers={"X-Admin-Password": site_publisher.SITE_ADMIN_PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    if not resp.json().get("ok"):
        raise RuntimeError(resp.json().get("error") or "respuesta sin 'ok'")

@admin_bp.route("/api/admin/inactivate/<slug>", methods=["POST"])
@require_key
def admin_inactivate(slug):
    folder = scanner_api._folder_for(slug)
    if not folder:
        return jsonify({"error": "no existe"}), 404
    lock = _current_lock()
    if lock and lock.get("slug") == slug:
        return jsonify({"error": "se está publicando ahora mismo — espera a que termine"}), 409
    lj = folder / "listing.json"
    data = json.loads(lj.read_text())
    if data.get("inactive"):
        return jsonify({"ok": True, "inactive": True, "inactive_at": data.get("inactive_at")})
    site_id = data.get("site_id")
    if site_id:
        # Si el sitio falla, NO se marca inactivo: seguiría a la venta en la web
        # y el bot lo seguiría ofreciendo. Mejor que Alejo vea el error y reintente.
        try:
            _delete_from_site(site_id)
        except Exception as e:
            return jsonify({"error": f"no se pudo quitar de la web: {e}"}), 502
    data["inactive"] = True
    data["inactive_at"] = time.strftime("%Y-%m-%d %H:%M")
    data["site_id_removed"] = site_id
    for k in ("site_id", "site_synced", "site_synced_at", "site_error"):
        data.pop(k, None)
    lj.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return jsonify({"ok": True, "inactive": True, "inactive_at": data["inactive_at"],
                    "removed_from_site": bool(site_id)})

@admin_bp.route("/api/admin/reactivate/<slug>", methods=["POST"])
@require_key
def admin_reactivate(slug):
    folder = scanner_api._folder_for(slug)
    if not folder:
        return jsonify({"error": "no existe"}), 404
    lj = folder / "listing.json"
    data = json.loads(lj.read_text())
    for k in ("inactive", "inactive_at", "site_id_removed"):
        data.pop(k, None)
    lj.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    # Sin site_id, el sync lo crea de nuevo como PENDIENTE (active=0): vuelve a
    # la web solo cuando Alejo lo aprueba en admin.html, igual que un carro nuevo.
    scanner_api._sync_to_site_bg(folder)
    return jsonify({"ok": True, "inactive": False})

# ── Cuadrar contra el lote ───────────────────────────────────────────
# Alejo pega los VINs que SÍ tiene hoy (completos o los últimos 6). Devuelve
# los carros activos del inventario que no aparecen. Solo lee: inactivar
# es un paso aparte, carro por carro, que Alejo aprueba en el panel.

_VIN_TOKEN = re.compile(r"[A-HJ-NPR-Z0-9]{6,17}")

def parse_vins(text: str) -> tuple[set, set]:
    full, tails = set(), set()
    for tok in _VIN_TOKEN.findall((text or "").upper()):
        if not any(c.isdigit() for c in tok):
            continue  # "TUNDRA", "SIENNA": palabras, no VINs
        (full if len(tok) == 17 else tails).add(tok)
    return full, tails

def _in_lot(vin: str, full: set, tails: set) -> bool:
    vin = (vin or "").upper()
    return vin in full or any(vin.endswith(t) for t in tails)

@admin_bp.route("/api/admin/reconcile", methods=["POST"])
@require_key
def admin_reconcile():
    body = request.get_json(silent=True) or {}
    full, tails = parse_vins(body.get("vins", ""))
    if not full and not tails:
        return jsonify({"error": "no encontré ningún VIN en el texto (mínimo los últimos 6)"}), 400
    root = _inv_dir()
    missing, back_in_lot, matched_vins = [], [], set()
    if root.exists():
        for d in sorted(root.iterdir()):
            lj = d / "listing.json"
            if not lj.is_file():
                continue
            try:
                data = json.loads(lj.read_text())
            except ValueError:
                continue
            vin = str(data.get("vin", "")).upper()
            title = " ".join(str(x) for x in (data.get("yr"), data.get("make"), data.get("model")) if x)
            if _in_lot(vin, full, tails):
                matched_vins.add(vin)
                if data.get("inactive"):
                    back_in_lot.append({"slug": d.name, "vin": vin, "title": title})
            elif not data.get("inactive"):
                missing.append({
                    "slug": d.name, "vin": vin,
                    "title": title,
                    "on_site": bool(data.get("site_id")),
                })
    # VINs pegados que no corresponden a ningún carro escaneado (para que Alejo
    # sepa que hay carros en el lote que nunca pasaron por el scanner).
    not_scanned = sorted(
        [v for v in full if v not in matched_vins] +
        [t for t in tails if not any(v.endswith(t) for v in matched_vins)]
    )
    return jsonify({"missing": missing, "not_scanned": not_scanned, "back_in_lot": back_in_lot,
                    "pasted": len(full) + len(tails), "matched": len(matched_vins)})
