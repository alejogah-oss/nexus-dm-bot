"""Endpoints del VIN Scanner PWA. Auth: X-Scanner-Key == env SCANNER_KEY."""
import base64, functools, json, os, re
from pathlib import Path
from flask import Blueprint, jsonify, request
from vin_utils import validate_vin, decode_vin
from listing_voice import LISTING_SYSTEM, build_listing_prompt
from dm_bot import _claude_create
import anthropic

bp = Blueprint("scanner", __name__)
INVENTORY_DIR = os.environ.get("INVENTORY_DIR", str(Path(__file__).parent / "inventory"))
OCR_MODEL, COPY_MODEL = "claude-haiku-4-5-20251001", "claude-sonnet-5"
_client = anthropic.Anthropic()

# Claves que marketplace_poster necesita en listing.json (notes es opcional)
REQUIRED_LISTING_KEYS = ("vin", "yr", "model", "trim", "color", "price", "mileage", "title", "description")

def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code

def require_key(f):
    @functools.wraps(f)
    def wrap(*a, **k):
        if request.headers.get("X-Scanner-Key") != os.environ.get("SCANNER_KEY"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*a, **k)
    return wrap

def _ocr(photo, instruction: str) -> str:
    """Claude Haiku vision: devuelve solo el texto pedido."""
    b64 = base64.standard_b64encode(photo.read()).decode()
    media = photo.mimetype if photo.mimetype in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
    r = _client.messages.create(model=OCR_MODEL, max_tokens=50, messages=[{
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
        raw = _ocr(photo, "Lee el VIN (17 caracteres) de esta foto. Responde SOLO el VIN, sin texto extra.")
    except Exception:
        return _bad("no se pudo leer la foto — reintenta", 502)
    vin = re.sub(r"[^A-HJ-NPR-Z0-9]", "", raw.upper())[:17]
    valid = validate_vin(vin)
    try:
        car = decode_vin(vin) if valid else {}
    except Exception:
        car = {}  # NHTSA caído — la PWA deja llenar la ficha a mano
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
    try:
        text = _claude_create(COPY_MODEL, 1500, LISTING_SYSTEM,
                              [{"role": "user", "content": build_listing_prompt(car)}])
        m = re.search(r"\{.*\}", text, re.DOTALL)
        out = json.loads(m.group()) if m else {"title": "", "description": text}
    except Exception:
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
