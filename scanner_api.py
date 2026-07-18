"""Endpoints del VIN Scanner PWA. Auth: X-Scanner-Key == env SCANNER_KEY."""
import base64, functools, json, os, re
from pathlib import Path
from flask import Blueprint, jsonify, request
from vin_utils import validate_vin, decode_vin, clean_vin, repair_vin
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
