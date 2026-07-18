# VIN Scanner PWA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PWA en el iPhone de Alejo que fotografía VIN + odómetro + fotos/video de un carro y genera copy bilingüe de Marketplace, guardando todo como inventario NEXUS.

**Architecture:** Blueprint Flask nuevo (`scanner_api.py`) registrado en `webhook_server.py` existente; utilidades puras en `vin_utils.py`; prompt de copy en `listing_voice.py`; frontend estático PWA en `static/scanner/`. OCR con Claude Haiku (vision), copy con Claude Sonnet, ficha técnica con NHTSA vPIC (gratis, sin key).

**Tech Stack:** Python/Flask (existente), anthropic SDK (existente, ver `_claude_create` en `dm_bot.py:133`), requests, pytest. Frontend: HTML/JS/CSS vanilla + PWA manifest.

**Ejecutores (optimización de tokens):** cada task indica el subagente NEXUS responsable — **wire** (backend), **ink** (prompt del copy), **shot** (UI, con flujo Magic/ui-ux-pro-max). El coordinador solo despacha y revisa.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-18-vin-scanner-app-design.md`.
- Modelos: OCR → `claude-haiku-4-5-20251001`; copy → `claude-sonnet-5`.
- Copy bilingüe: inglés primero, español después, mismo listing. Título ≤ 100 chars.
- Teléfono en el copy: **(954) 910-6671** (nunca 310-6671).
- Identidad visual: rojo Toyota `#EB0A1E`, fuentes Anton/Bebas Neue/Inter. TODO lo visual lo dirige Shot.
- `listing.json` compatible con `marketplace_poster.py` (claves: `vin, yr, model, trim, color, price`, + extras `mileage, title, description, notes`).
- Auth: header `X-Scanner-Key` == env `SCANNER_KEY` en todos los endpoints `/api/scanner/*`.
- Media en `INVENTORY_DIR` (env, default `inventory/` junto al código; en Railway montar volume y setear `INVENTORY_DIR=/data/inventory`).
- NADA de integración con `marketplace_poster`/bot en v1 (solo formato compatible).
- Commits frecuentes, mensajes `feat:/test:/chore:` + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: vin_utils — validación VIN + decoder NHTSA  · **Ejecutor: wire**

**Files:**
- Create: `vin_utils.py`
- Test: `tests/test_vin_utils.py`

**Interfaces:**
- Produces: `validate_vin(vin: str) -> bool` (largo 17, chars válidos, check digit ISO 3779). `decode_vin(vin: str) -> dict` → `{"yr": str, "make": str, "model": str, "trim": str, "engine": str, "fuel": str, "body": str, "drive": str}` (strings vacíos si NHTSA no trae el campo). `NHTSA_URL` formateable.

- [ ] **Step 1: Test que falla**

```python
# tests/test_vin_utils.py
from unittest.mock import patch, Mock
from vin_utils import validate_vin, decode_vin

def test_validate_vin_ok():
    assert validate_vin("1HGCM82633A004352") is True   # check digit válido conocido

def test_validate_vin_bad_check_digit():
    assert validate_vin("1HGCM82633A004353") is False

def test_validate_vin_bad_length_or_chars():
    assert validate_vin("ABC") is False
    assert validate_vin("1HGCM82633A00435I") is False  # I no es válido en VIN

def test_decode_vin_parses_nhtsa():
    fake = {"Results": [{"ModelYear": "2021", "Make": "TOYOTA", "Model": "Corolla",
                         "Trim": "SE", "DisplacementL": "2.0", "EngineCylinders": "4",
                         "FuelTypePrimary": "Gasoline", "BodyClass": "Sedan",
                         "DriveType": "FWD"}]}
    with patch("vin_utils.requests.get", return_value=Mock(json=lambda: fake, status_code=200)):
        d = decode_vin("1HGCM82633A004352")
    assert d["yr"] == "2021" and d["model"] == "Corolla" and d["trim"] == "SE"
    assert d["engine"] == "2.0L 4cyl"
```

- [ ] **Step 2: Verificar que falla** — Run: `cd ~/nexus-automation && python -m pytest tests/test_vin_utils.py -v` → Expected: FAIL `ModuleNotFoundError: vin_utils`

- [ ] **Step 3: Implementación mínima**

```python
# vin_utils.py
"""VIN: validación check digit ISO 3779 + decode NHTSA vPIC (gratis, sin key)."""
import requests

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"

_TRANSLIT = {**{str(d): d for d in range(10)},
             "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
             "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
             "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

def validate_vin(vin: str) -> bool:
    vin = vin.strip().upper()
    if len(vin) != 17 or any(c not in _TRANSLIT for c in vin):
        return False
    total = sum(_TRANSLIT[c] * w for c, w in zip(vin, _WEIGHTS))
    check = total % 11
    expected = "X" if check == 10 else str(check)
    return vin[8] == expected

def decode_vin(vin: str) -> dict:
    r = requests.get(NHTSA_URL.format(vin=vin.strip().upper()), timeout=15)
    res = (r.json().get("Results") or [{}])[0]
    disp, cyl = res.get("DisplacementL", ""), res.get("EngineCylinders", "")
    engine = f"{float(disp):.1f}L {cyl}cyl" if disp and cyl else (disp or cyl or "")
    return {"yr": res.get("ModelYear", ""), "make": (res.get("Make") or "").title(),
            "model": res.get("Model", ""), "trim": res.get("Trim", ""),
            "engine": engine, "fuel": res.get("FuelTypePrimary", ""),
            "body": res.get("BodyClass", ""), "drive": res.get("DriveType", "")}
```

- [ ] **Step 4: Verificar que pasa** — Run: `python -m pytest tests/test_vin_utils.py -v` → Expected: 4 PASS
- [ ] **Step 5: Commit** — `git add vin_utils.py tests/test_vin_utils.py && git commit -m "feat: vin_utils — check digit + NHTSA decode"`

---

### Task 2: listing_voice — prompt del copy bilingüe  · **Ejecutor: ink**

**Files:**
- Create: `listing_voice.py`
- Test: `tests/test_listing_voice.py`

**Interfaces:**
- Consumes: dict de carro (claves de Task 1 + `mileage: int, price: int, notes: str`).
- Produces: `LISTING_SYSTEM: str` (voz Ink para listings) y `build_listing_prompt(car: dict) -> str` (user prompt). El system exige respuesta SOLO JSON: `{"title": "...", "description": "..."}` con title ≤ 100 chars, descripción EN primero y ES después, teléfono (954) 910-6671, ubicación Hollywood FL, CTA de contacto directo.

- [ ] **Step 1: Test que falla**

```python
# tests/test_listing_voice.py
from listing_voice import LISTING_SYSTEM, build_listing_prompt

CAR = {"yr": "2021", "make": "Toyota", "model": "Corolla", "trim": "SE",
       "engine": "2.0L 4cyl", "fuel": "Gasoline", "body": "Sedan", "drive": "FWD",
       "mileage": 42000, "price": 17500, "notes": "un solo dueño"}

def test_system_rules():
    for must in ["JSON", "100", "(954) 910-6671", "English", "Español"]:
        assert must in LISTING_SYSTEM

def test_prompt_contains_car_data():
    p = build_listing_prompt(CAR)
    for must in ["2021", "Corolla", "SE", "42,000", "$17,500", "un solo dueño"]:
        assert must in p
```

- [ ] **Step 2: Verificar que falla** — `python -m pytest tests/test_listing_voice.py -v` → FAIL ModuleNotFoundError
- [ ] **Step 3: Implementar** — Ink redacta `LISTING_SYSTEM` con su voz (vendedor directo, cercano, sin humo; estructura: hook, bullets ✅ de specs, financiamiento, ubicación 📍 Hollywood FL, CTA 📞) cumpliendo todo lo del bloque Interfaces, y:

```python
def build_listing_prompt(car: dict) -> str:
    return (
        f"Genera el listing para este carro:\n"
        f"{car['yr']} {car['make']} {car['model']} {car['trim']}\n"
        f"Motor: {car['engine']} | {car['fuel']} | {car['body']} | {car['drive']}\n"
        f"Millaje: {car['mileage']:,} millas\nPrecio: ${car['price']:,}\n"
        f"Notas del vendedor: {car.get('notes') or 'ninguna'}"
    )
```

- [ ] **Step 4: Verificar que pasa** — `python -m pytest tests/test_listing_voice.py -v` → 2 PASS
- [ ] **Step 5: Commit** — `git add listing_voice.py tests/test_listing_voice.py && git commit -m "feat: listing_voice — prompt bilingüe voz Ink"`

---

### Task 3: scanner_api — blueprint con los 4 endpoints  · **Ejecutor: wire**

**Files:**
- Create: `scanner_api.py`
- Modify: `webhook_server.py` (registrar blueprint, 3 líneas al final de los imports/registros)
- Test: `tests/test_scanner_api.py`

**Interfaces:**
- Consumes: `validate_vin/decode_vin` (Task 1), `LISTING_SYSTEM/build_listing_prompt` (Task 2), `_claude_create` importado de `dm_bot` (firma en `dm_bot.py:133`: `_claude_create(model, max_tokens, system, messages) -> str`).
- Produces (todo JSON, auth `X-Scanner-Key`):
  - `POST /api/scanner/vin` (multipart `photo`) → `{"vin": str, "valid": bool, "car": {…decode_vin}}`
  - `POST /api/scanner/odometer` (multipart `photo`) → `{"mileage": int}`
  - `POST /api/scanner/listing` (JSON car dict) → `{"title": str, "description": str}`
  - `POST /api/scanner/inventory` (multipart: `data` JSON + `photos[]` + `video` opcional) → `{"folder": str}`

- [ ] **Step 1: Tests que fallan**

```python
# tests/test_scanner_api.py
import io, json, os
from unittest.mock import patch
os.environ["SCANNER_KEY"] = "testkey"
import scanner_api
from flask import Flask

app = Flask(__name__); app.register_blueprint(scanner_api.bp)
c = app.test_client()
H = {"X-Scanner-Key": "testkey"}

def test_auth_required():
    assert c.post("/api/scanner/vin").status_code == 401

def test_vin_endpoint():
    with patch.object(scanner_api, "_ocr", return_value="1HGCM82633A004352"), \
         patch.object(scanner_api, "decode_vin", return_value={"yr": "2003", "model": "Accord"}):
        r = c.post("/api/scanner/vin", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "vin.jpg")})
    assert r.status_code == 200 and r.json["valid"] is True and r.json["car"]["yr"] == "2003"

def test_odometer_endpoint():
    with patch.object(scanner_api, "_ocr", return_value="42,350"):
        r = c.post("/api/scanner/odometer", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "odo.jpg")})
    assert r.json["mileage"] == 42350

def test_listing_endpoint():
    fake = json.dumps({"title": "2021 Toyota Corolla SE", "description": "desc"})
    with patch.object(scanner_api, "_claude_create", return_value=fake):
        r = c.post("/api/scanner/listing", headers=H,
                   json={"yr": "2021", "make": "Toyota", "model": "Corolla", "trim": "SE",
                         "engine": "", "fuel": "", "body": "", "drive": "",
                         "mileage": 42000, "price": 17500, "notes": ""})
    assert r.json["title"].startswith("2021")

def test_inventory_saves(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    data = {"vin": "1HGCM82633A004352", "yr": "2021", "model": "Corolla", "trim": "SE",
            "color": "Blanco", "price": 17500, "mileage": 42000,
            "title": "t", "description": "d", "notes": ""}
    r = c.post("/api/scanner/inventory", headers=H, data={
        "data": json.dumps(data),
        "photos": [(io.BytesIO(b"a"), "1.jpg"), (io.BytesIO(b"b"), "2.jpg")],
        "video": (io.BytesIO(b"v"), "walk.mp4")})
    folder = tmp_path / r.json["folder"].split("/")[-1]
    assert (folder / "listing.json").exists() and (folder / "photos" / "01.jpg").exists() \
        and (folder / "video.mp4").exists() and (folder / "copy.md").exists()
```

- [ ] **Step 2: Verificar que fallan** — `python -m pytest tests/test_scanner_api.py -v` → FAIL ModuleNotFoundError

- [ ] **Step 3: Implementar**

```python
# scanner_api.py
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
    raw = _ocr(request.files["photo"],
               "Lee el VIN (17 caracteres) de esta foto. Responde SOLO el VIN, sin texto extra.")
    vin = re.sub(r"[^A-HJ-NPR-Z0-9]", "", raw.upper())[:17]
    valid = validate_vin(vin)
    car = decode_vin(vin) if valid else {}
    return jsonify({"vin": vin, "valid": valid, "car": car})

@bp.route("/api/scanner/odometer", methods=["POST"])
@require_key
def scan_odometer():
    raw = _ocr(request.files["photo"],
               "Lee el millaje (odómetro) en esta foto de tablero. Responde SOLO el número.")
    digits = re.sub(r"[^0-9]", "", raw)
    return jsonify({"mileage": int(digits) if digits else 0})

@bp.route("/api/scanner/listing", methods=["POST"])
@require_key
def gen_listing():
    car = request.get_json(force=True)
    text = _claude_create(COPY_MODEL, 1500, LISTING_SYSTEM,
                          [{"role": "user", "content": build_listing_prompt(car)}])
    m = re.search(r"\{.*\}", text, re.DOTALL)
    out = json.loads(m.group()) if m else {"title": "", "description": text}
    out["title"] = out.get("title", "")[:100]
    return jsonify(out)

@bp.route("/api/scanner/inventory", methods=["POST"])
@require_key
def save_inventory():
    data = json.loads(request.form["data"])
    slug = re.sub(r"[^A-Za-z0-9-]", "", f"{data['yr']}-{data['model']}-{data['vin'][-6:]}")
    folder = Path(INVENTORY_DIR) / slug
    (folder / "photos").mkdir(parents=True, exist_ok=True)
    for i, ph in enumerate(request.files.getlist("photos"), 1):
        ph.save(folder / "photos" / f"{i:02d}.jpg")
    if "video" in request.files:
        request.files["video"].save(folder / "video.mp4")
    (folder / "listing.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    (folder / "copy.md").write_text(f"# {data['title']}\n\n{data['description']}\n")
    return jsonify({"folder": str(folder)})
```

En `webhook_server.py`, junto a los otros registros/imports de la app:

```python
from scanner_api import bp as scanner_bp
app.register_blueprint(scanner_bp)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # video walkaround
```

- [ ] **Step 4: Verificar** — `python -m pytest tests/test_scanner_api.py -v` → 5 PASS; y `python -c "import webhook_server"` sin error.
- [ ] **Step 5: Commit** — `git add scanner_api.py tests/test_scanner_api.py webhook_server.py && git commit -m "feat: scanner_api — endpoints VIN/odometer/listing/inventory"`

---

### Task 4: PWA frontend — flujo 4 pasos  · **Ejecutor: shot** (dirige lo visual; usa flujo Magic/ui-ux-pro-max)

**Files:**
- Create: `static/scanner/index.html`, `static/scanner/app.js`, `static/scanner/styles.css`, `static/scanner/manifest.json`, `static/scanner/icon-512.png`
- Modify: `webhook_server.py` (ruta `GET /scanner` que sirve `static/scanner/index.html`)

**Interfaces:**
- Consumes: los 4 endpoints de Task 3 (contratos exactos arriba). La key se pide una vez (prompt) y se guarda en `localStorage.scannerKey`; se envía como header `X-Scanner-Key` en cada fetch.
- Produces: PWA instalable en `https://<host>/scanner`.

**Requisitos funcionales (no negociables):**
1. Wizard de 4 pasos con barra de progreso: **VIN → Odómetro/Precio → Fotos/Video → Copy**.
2. Paso VIN: `<input type="file" accept="image/*" capture="environment">` → POST `/api/scanner/vin` → mostrar ficha (`yr make model trim engine`) editable + campo VIN manual si `valid:false`.
3. Paso Odómetro: igual captura → `/api/scanner/odometer` → millaje en input editable; campos precio (numérico, requerido) y notas (texto libre); campo color (texto, requerido — `listing.json` lo necesita).
4. Paso Fotos/Video: `<input multiple accept="image/*" capture>` con miniaturas y botón eliminar por foto; `<input accept="video/*" capture>` opcional (1 video).
5. Paso Copy: POST `/api/scanner/listing`; mostrar título + descripción; botón **Copiar** (`navigator.clipboard.writeText(title + "\n\n" + description)`); botón **Guardar en NEXUS** → POST multipart `/api/scanner/inventory`; mostrar carpeta guardada.
6. Estado en memoria JS (objeto `session`); si un POST falla (sin señal en el lote), mostrar botón **Reintentar** sin perder fotos; `beforeunload` advierte si hay sesión sin guardar.
7. Manifest PWA: `display: standalone`, `theme_color: "#EB0A1E"`, nombre "NEXUS Scanner", ícono 512px (Shot lo genera).
8. Visual: fondo oscuro, rojo Toyota `#EB0A1E` en CTAs/progreso, títulos Anton/Bebas Neue, cuerpo Inter, botones grandes usables con una mano a pleno sol.

- [ ] **Step 1:** Construir `index.html + app.js + styles.css` cumpliendo los 8 requisitos.
- [ ] **Step 2:** Agregar en `webhook_server.py`: `@app.route("/scanner")` → `send_file("static/scanner/index.html")` (mismo patrón de `send_file` que la línea 717).
- [ ] **Step 3: Verificar local** — `python webhook_server.py` (o `flask run`), abrir `http://localhost:<puerto>/scanner`, recorrer los 4 pasos con imágenes de prueba y confirmar cada fetch en la pestaña Network.
- [ ] **Step 4: Commit** — `git add static/scanner webhook_server.py && git commit -m "feat: PWA VIN Scanner — wizard 4 pasos"`

---

### Task 5: Deploy + E2E real  · **Ejecutor: coordinador con Alejo**

**Files:** ninguno nuevo (config de entorno).

- [ ] **Step 1:** Setear en el hosting (donde corre `webhook_server`): `SCANNER_KEY` (generar: `python -c "import secrets; print(secrets.token_urlsafe(16))"`) y `INVENTORY_DIR` apuntando al volume persistente.
- [ ] **Step 2:** Deploy (mismo flujo git push del servicio actual). Verificar: `curl -s -o /dev/null -w "%{http_code}" https://<host>/scanner` → `200`, y `curl -X POST https://<host>/api/scanner/vin` → `401`.
- [ ] **Step 3:** Alejo en el lote: abrir `/scanner` en Safari iPhone → Compartir → **Agregar a pantalla de inicio**. Probar con un carro real: VIN real leído y decodificado, millaje real, copy generado, Copiar → pegar en Marketplace, Guardar en NEXUS → confirmar carpeta con fotos/video/`listing.json`.
- [ ] **Step 4:** Registrar resultado del E2E en `docs/superpowers/specs/2026-07-18-vin-scanner-app-design.md` (sección Testing) y commit final.

---

## Self-review (hecho)

- Cobertura del spec: 4 endpoints ✔, wizard 4 pasos ✔, bilingüe/teléfono/identidad en constraints ✔, retención offline (req. 6 Task 4) ✔, sin integración bot ✔, VIN inválido → manual (req. 2 Task 4) ✔, NHTSA sin datos → ficha editable (req. 2) ✔.
- Sin placeholders; código completo en cada step de backend; frontend con requisitos exactos por ser dominio de Shot.
- Tipos consistentes entre tasks (contratos en bloques Interfaces).
