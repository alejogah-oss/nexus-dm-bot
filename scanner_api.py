"""Endpoints del VIN Scanner PWA. Auth: X-Scanner-Key == env SCANNER_KEY."""
import base64, functools, json, os, re, traceback
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file
from vin_utils import validate_vin, decode_vin, clean_vin, repair_vin
from listing_voice import LISTING_SYSTEM, build_listing_prompt
import anthropic

bp = Blueprint("scanner", __name__)
INVENTORY_DIR = os.environ.get("INVENTORY_DIR", str(Path(__file__).parent / "inventory"))
OCR_MODEL, COPY_MODEL = "claude-haiku-4-5-20251001", "claude-sonnet-5"
_client = anthropic.Anthropic()

# Claves que marketplace_poster necesita en listing.json (notes es opcional)
REQUIRED_LISTING_KEYS = ("vin", "yr", "model", "trim", "color", "price", "mileage", "title", "description")

def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code

def _copy_call(prompt: str) -> str:
    """Genera el copy con Sonnet 5. Thinking desactivado (vía extra_body para
    compatibilidad con SDKs viejos) y extracción del bloque de TEXTO — en
    Sonnet 5 content[0] puede ser un bloque thinking, nunca leer por índice."""
    r = _client.messages.create(
        model=COPY_MODEL, max_tokens=3000, system=LISTING_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"thinking": {"type": "disabled"}},
    )
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")

def require_key(f):
    @functools.wraps(f)
    def wrap(*a, **k):
        expected = os.environ.get("SCANNER_KEY")
        if not expected or request.headers.get("X-Scanner-Key") != expected:
            return jsonify({"error": "unauthorized"}), 401
        return f(*a, **k)
    return wrap

VIN_OCR_PROMPT = (
    "Esta foto muestra el VIN de un vehículo (placa del parabrisas, etiqueta del "
    "marco de la puerta o documento). Un VIN tiene EXACTAMENTE 17 caracteres, solo "
    "mayúsculas y dígitos, y NUNCA contiene las letras I, O ni Q. Transcríbelo con "
    "máximo cuidado carácter por carácter; confusiones típicas que debes evitar: "
    "S vs 5, B vs 8, Z vs 2, G vs 6, D vs 0. Si hay varios textos en la imagen, el "
    "VIN es la cadena de 17 caracteres. Responde SOLO los 17 caracteres, sin "
    "espacios, guiones ni texto adicional."
)

def _ocr(photo, instruction: str, model: str = OCR_MODEL) -> str:
    """Claude vision: devuelve solo el texto pedido."""
    photo.seek(0)
    b64 = base64.standard_b64encode(photo.read()).decode()
    media = photo.mimetype if photo.mimetype in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
    r = _client.messages.create(model=model, max_tokens=100, messages=[{
        "role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
            {"type": "text", "text": instruction}]}])
    return r.content[0].text.strip()

@bp.route("/api/scanner/vin", methods=["POST"])
@require_key
def scan_vin():
    photo = request.files.get("photo")
    if not photo:
        return _bad("falta el archivo 'photo'")
    try:
        vin = repair_vin(clean_vin(_ocr(photo, VIN_OCR_PROMPT)))
        if not validate_vin(vin):
            # Haiku no logró un VIN válido — segundo intento con Sonnet (mejor visión)
            vin = repair_vin(clean_vin(_ocr(photo, VIN_OCR_PROMPT, model=COPY_MODEL)))
    except Exception:
        return _bad("no se pudo leer la foto — reintenta", 502)
    valid = validate_vin(vin)
    try:
        car = decode_vin(vin) if valid else {}
    except Exception:
        car = {}  # NHTSA caído — la PWA deja llenar la ficha a mano
    return jsonify({"vin": vin, "valid": valid, "car": car})

@bp.route("/api/scanner/vin-decode", methods=["POST"])
@require_key
def vin_decode():
    """VIN ya leído (escáner en vivo del navegador) → validar + ficha NHTSA."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body.get("vin"):
        return _bad("falta el campo 'vin'")
    vin = repair_vin(clean_vin(str(body["vin"])))
    valid = validate_vin(vin)
    try:
        car = decode_vin(vin) if valid else {}
    except Exception:
        car = {}
    return jsonify({"vin": vin, "valid": valid, "car": car})

@bp.route("/api/scanner/odometer", methods=["POST"])
@require_key
def scan_odometer():
    photo = request.files.get("photo")
    if not photo:
        return _bad("falta el archivo 'photo'")
    try:
        raw = _ocr(photo, "Lee el millaje (odómetro) en esta foto de tablero. Responde SOLO el número.")
    except Exception:
        return _bad("no se pudo leer la foto — reintenta", 502)
    digits = re.sub(r"[^0-9]", "", raw)
    return jsonify({"mileage": int(digits) if digits else 0})

@bp.route("/api/scanner/listing", methods=["POST"])
@require_key
def gen_listing():
    car = request.get_json(silent=True)
    if not isinstance(car, dict):
        return _bad("body JSON inválido")
    missing = [k for k in ("yr", "make", "model", "mileage", "price") if car.get(k) in ("", None)]
    if missing:
        return _bad("faltan campos: " + ", ".join(missing))
    try:
        text = _copy_call(build_listing_prompt(car))
        m = re.search(r"\{.*\}", text, re.DOTALL)
        out = json.loads(m.group()) if m else {"title": "", "description": text}
    except Exception:
        print("[SCANNER] /listing falló:", flush=True)
        traceback.print_exc()
        return _bad("no se pudo generar el copy — reintenta", 502)
    out["title"] = out.get("title", "")[:100]
    return jsonify(out)

@bp.route("/api/scanner/inventory", methods=["POST"])
@require_key
def save_inventory():
    try:
        data = json.loads(request.form["data"])
    except (KeyError, ValueError):
        return _bad("campo 'data' ausente o JSON inválido")
    if not isinstance(data, dict):
        return _bad("campo 'data' debe ser un objeto JSON")
    missing = [k for k in REQUIRED_LISTING_KEYS if data.get(k) in ("", None)]
    if missing:
        return _bad("faltan campos: " + ", ".join(missing))
    if not request.files.getlist("photos"):
        return _bad("agrega al menos una foto")
    slug = re.sub(r"[^A-Za-z0-9-]", "", f"{data['yr']}-{data['model']}-{data['vin'][-6:]}") or str(data["vin"])[-6:]
    folder = Path(INVENTORY_DIR) / slug
    (folder / "photos").mkdir(parents=True, exist_ok=True)
    for i, ph in enumerate(request.files.getlist("photos"), 1):
        ph.save(folder / "photos" / f"{i:02d}.jpg")
    if "video" in request.files:
        request.files["video"].save(folder / "video.mp4")
    (folder / "listing.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    (folder / "copy.md").write_text(f"# {data['title']}\n\n{data['description']}\n")
    return jsonify({"folder": str(folder)})

# ── Pendientes por subir: listar, ver, editar ───────────────────────

_SLUG_RE = re.compile(r"^[A-Za-z0-9-]+$")

def _folder_for(slug: str):
    """Carpeta de inventario validada (sin path traversal)."""
    if not _SLUG_RE.match(slug or ""):
        return None
    folder = Path(INVENTORY_DIR) / slug
    return folder if (folder / "listing.json").exists() else None

@bp.route("/api/scanner/inventory", methods=["GET"])
@require_key
def list_inventory():
    items = []
    root = Path(INVENTORY_DIR)
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
                "yr": data.get("yr", ""), "model": data.get("model", ""),
                "trim": data.get("trim", ""), "price": data.get("price"),
                "mileage": data.get("mileage"),
                "photos": len(list(photos_dir.glob("*.jpg"))) if photos_dir.exists() else 0,
                "video": (d / "video.mp4").exists(),
            })
    return jsonify({"items": items})

@bp.route("/api/scanner/inventory/<slug>", methods=["GET"])
@require_key
def get_inventory_item(slug):
    folder = _folder_for(slug)
    if not folder:
        return _bad("no existe", 404)
    data = json.loads((folder / "listing.json").read_text())
    photos_dir = folder / "photos"
    return jsonify({"slug": slug, "data": data,
                    "photos": len(list(photos_dir.glob("*.jpg"))) if photos_dir.exists() else 0,
                    "video": (folder / "video.mp4").exists()})

@bp.route("/api/scanner/inventory/<slug>", methods=["PUT"])
@require_key
def update_inventory_item(slug):
    folder = _folder_for(slug)
    if not folder:
        return _bad("no existe", 404)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _bad("body JSON inválido")
    data = json.loads((folder / "listing.json").read_text())
    for k in ("title", "description", "price", "mileage", "color", "notes"):
        if k in body:
            data[k] = body[k]
    data["title"] = str(data.get("title", ""))[:100]
    (folder / "listing.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    (folder / "copy.md").write_text(f"# {data['title']}\n\n{data['description']}\n")
    return jsonify({"ok": True, "data": data})

@bp.route("/api/scanner/inventory/<slug>/photo/<int:n>", methods=["GET"])
def inventory_photo(slug, n):
    # Los <img> no mandan headers: auth por query param ?key=
    expected = os.environ.get("SCANNER_KEY")
    if not expected or request.args.get("key") != expected:
        return jsonify({"error": "unauthorized"}), 401
    folder = _folder_for(slug)
    if not folder:
        return _bad("no existe", 404)
    p = folder / "photos" / f"{n:02d}.jpg"
    if not p.is_file():
        return _bad("no existe", 404)
    return send_file(p, mimetype="image/jpeg")
