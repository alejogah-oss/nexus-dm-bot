# Panel Administrador Marketplace — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un panel `/admin` que muestre el estado de publicación de cada carro del scanner, permita editarlos y publicarlos a Facebook Marketplace uno a uno, a discreción de Alejo, desde el Mac Pro.

**Architecture:** El panel es una ruta nueva servida por el mismo `scanner_server.py` que ya corre 24/7 en el Mac Pro. Un blueprint nuevo `admin_api.py` guarda el estado de publicación dentro del `listing.json` de cada carro y expone endpoints para listar, publicar (lanza el bot de Chrome visible como subproceso, con lock de "uno a la vez") y marcar como publicado. `marketplace_poster.py` gana una ruta de publicación separada para carros del scanner (marca/millaje/precio reales) que llena el formulario y se detiene antes del botón Publicar de Facebook.

**Tech Stack:** Python 3.9+, Flask 3.x (blueprints), Playwright async (Chromium visible), pytest, HTML/CSS/JS vanilla (sin build step, patrón del scanner existente).

## Global Constraints

- El bot de Chrome **NUNCA** publica solo ni en lote: llena el formulario y **se detiene antes del botón Publicar de Facebook**; Alejo da Publicar él mismo.
- El panel y el bot corren **SOLO en el Mac Pro** (navegador visible, escritorio real). El MacBook Air NUNCA los corre.
- El panel opera **solo sobre el inventario del scanner** (`INVENTORY_DIR`, carpetas `inventario/<slug>/`). NO toca el inventario del sitio web del dealer.
- Marca, millaje y precio de los carros del scanner se publican con sus **valores reales** — nunca los defaults del stock nuevo (Toyota / "500" / enganche 20%). Color interior por defecto "Black".
- Auth: misma `SCANNER_KEY` fail-closed que el scanner (sin key en env → 401). Header `X-Scanner-Key`; fotos por `?key=`.
- Solo **un** carro publicándose a la vez (lock por PID vivo).
- Teléfono (954) 910-6671 — nunca cambiar (ya vive en el copy generado, no se toca aquí).
- Trabajar en una rama nueva; el repo está en `main`.

---

## File Structure

- `admin_api.py` (crear) — blueprint `admin_bp`: estado de publicación (`read_status`/`set_status`), lock por PID, endpoints `GET /api/admin/inventory`, `POST /api/admin/publish/<slug>`, `POST /api/admin/mark/<slug>`.
- `marketplace_poster.py` (modificar) — `scanner_car_fields()` (lógica pura de campos con datos reales), `post_scanner_car()` (llena el form y se detiene antes de Publicar), `publish_scanner_car()` (lee `inventario/<slug>/`, abre Chrome visible), y CLI `--scanner <slug>`.
- `scanner_api.py` (modificar) — permitir `make` como campo editable en el PUT.
- `static/scanner/app.js` (modificar) — persistir `make` en el payload de guardado.
- `scanner_server.py` (modificar) — registrar `admin_bp` y servir `/admin` + `/static/admin/<file>`.
- `static/admin/index.html`, `static/admin/admin.css`, `static/admin/admin.js` (crear) — el panel.
- `tests/test_admin_api.py` (crear), `tests/test_marketplace_scanner.py` (crear), y casos añadidos a `tests/test_scanner_api.py`.

Preparación (una vez, antes de la Task 1):

```bash
cd /Users/macbookpro/nexus-automation
git checkout -b feature/admin-marketplace-panel
```

---

### Task 1: Persistir la marca (`make`) de punta a punta

Sin esto, publicar usados de cualquier marca es imposible: el scanner captura la marca pero la descarta al guardar. Se persiste en el guardado y se hace editable en el PUT.

**Files:**
- Modify: `static/scanner/app.js:415-420`
- Modify: `scanner_api.py:212`
- Test: `tests/test_scanner_api.py`

**Interfaces:**
- Consumes: endpoint existente `PUT /api/scanner/inventory/<slug>` (`update_inventory_item`).
- Produces: `listing.json` de cada carro incluye la clave `make`; el PUT acepta `make`.

- [ ] **Step 1: Escribir el test que falla (PUT acepta `make`)**

Añadir a `tests/test_scanner_api.py`:

```python
def test_put_permite_editar_make(tmp_path):
    slug = _guardar_carro(tmp_path)
    r = c.put(f"/api/scanner/inventory/{slug}", headers=H, json={"make": "Honda"})
    assert r.status_code == 200 and r.json["data"]["make"] == "Honda"
    r2 = c.get(f"/api/scanner/inventory/{slug}", headers=H)
    assert r2.json["data"]["make"] == "Honda"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `venv/bin/python -m pytest tests/test_scanner_api.py::test_put_permite_editar_make -v`
Expected: FAIL — `make` no está entre las claves actualizables, no aparece en `data`.

- [ ] **Step 3: Permitir `make` en el PUT**

En `scanner_api.py`, en `update_inventory_item`, cambiar la tupla de claves actualizables (línea ~212):

```python
    for k in ("title", "description", "price", "mileage", "color", "make", "notes"):
        if k in body:
            data[k] = body[k]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `venv/bin/python -m pytest tests/test_scanner_api.py::test_put_permite_editar_make -v`
Expected: PASS

- [ ] **Step 5: Persistir `make` en el guardado del scanner**

En `static/scanner/app.js`, en el objeto `data` (líneas 415-420), añadir `make`:

```javascript
    const data = {
      vin: session.vin, yr: session.car.yr, make: session.car.make,
      model: session.car.model,
      trim: session.car.trim, color: session.color, price: session.price,
      mileage: session.mileage, title: session.title,
      description: session.description, notes: session.notes,
    };
```

- [ ] **Step 6: Verificar el cambio de payload**

Run: `grep -n "make: session.car.make" static/scanner/app.js`
Expected: una línea coincidente dentro del objeto `data`.

- [ ] **Step 7: Commit**

```bash
git add scanner_api.py static/scanner/app.js tests/test_scanner_api.py
git commit -m "feat: persist and allow editing car make for scanner inventory"
```

---

### Task 2: Estado de publicación por carro (`admin_api` helpers)

Guardar/leer el estado (`published`, `published_at`, `last_error`) dentro del `listing.json` de cada carro, con defaults seguros.

**Files:**
- Create: `admin_api.py`
- Test: `tests/test_admin_api.py`

**Interfaces:**
- Consumes: `scanner_api.INVENTORY_DIR` (leído en cada llamada, para que los tests lo puedan parchear).
- Produces:
  - `read_status(folder: Path) -> dict` → `{"published": bool, "published_at": str|None, "last_error": str|None}`.
  - `set_status(folder: Path, **fields) -> dict` → escribe las claves dadas en `listing.json` y devuelve el estado resultante.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_admin_api.py`:

```python
import json, os
from pathlib import Path
os.environ["SCANNER_KEY"] = "testkey"
import scanner_api, admin_api

def _car(tmp_path, slug="2019-Civic-004352", **extra):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    folder = Path(tmp_path) / slug
    (folder / "photos").mkdir(parents=True)
    data = {"vin": "1HGCM82633A004352", "yr": "2019", "make": "Honda",
            "model": "Civic", "trim": "EX", "color": "Blue", "price": 16500,
            "mileage": 45000, "title": "2019 Honda Civic EX", "description": "d"}
    data.update(extra)
    (folder / "listing.json").write_text(json.dumps(data))
    (folder / "photos" / "01.jpg").write_bytes(b"a")
    return folder

def test_read_status_defaults(tmp_path):
    folder = _car(tmp_path)
    st = admin_api.read_status(folder)
    assert st == {"published": False, "published_at": None, "last_error": None}

def test_set_status_persists(tmp_path):
    folder = _car(tmp_path)
    admin_api.set_status(folder, published=True, published_at="2026-07-19 10:00")
    st = admin_api.read_status(folder)
    assert st["published"] is True and st["published_at"] == "2026-07-19 10:00"
    # no borra los datos originales del carro
    data = json.loads((folder / "listing.json").read_text())
    assert data["make"] == "Honda" and data["price"] == 16500
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv/bin/python -m pytest tests/test_admin_api.py -v`
Expected: FAIL — `admin_api` no existe.

- [ ] **Step 3: Crear `admin_api.py` con los helpers de estado**

```python
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
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv/bin/python -m pytest tests/test_admin_api.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add admin_api.py tests/test_admin_api.py
git commit -m "feat: publish-status helpers for admin panel"
```

---

### Task 3: Endpoints del panel (listar / publicar con lock / marcar)

Exponer el inventario con estado, lanzar el bot como subproceso con lock de "uno a la vez" (por PID vivo), y marcar publicado.

**Files:**
- Modify: `admin_api.py`
- Test: `tests/test_admin_api.py`

**Interfaces:**
- Consumes: `read_status`/`set_status` (Task 2), `scanner_api._folder_for(slug) -> Path|None`, `scanner_api.require_key`.
- Produces:
  - `_launch_publish(slug: str) -> int` (devuelve PID; los tests lo parchean).
  - `GET /api/admin/inventory` → `{"items": [...], "publishing": slug|None}`; cada item lleva `slug, title, make, model, yr, price, mileage, photos, published, published_at, last_error`.
  - `POST /api/admin/publish/<slug>` → 404 si no existe; 409 si ya hay una publicación en curso; si no, lanza el bot, escribe el lock, limpia `last_error`, devuelve `{"ok": True, "slug": slug}`.
  - `POST /api/admin/mark/<slug>` → 404 si no existe; marca `published=True` + `published_at`, borra el lock, devuelve `{"ok": True, ...estado}`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_admin_api.py`:

```python
from flask import Flask
from unittest.mock import patch

app = Flask(__name__); app.register_blueprint(admin_api.admin_bp)
cl = app.test_client()
H = {"X-Scanner-Key": "testkey"}

def test_inventory_lista_con_estado(tmp_path):
    _car(tmp_path)
    r = cl.get("/api/admin/inventory", headers=H)
    assert r.status_code == 200
    it = r.json["items"][0]
    assert it["make"] == "Honda" and it["published"] is False and it["photos"] == 1
    assert r.json["publishing"] is None

def test_inventory_auth_401(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    assert cl.get("/api/admin/inventory").status_code == 401

def test_publish_lanza_y_bloquea(tmp_path):
    _car(tmp_path)
    admin_api._lock_file().unlink(missing_ok=True)
    with patch.object(admin_api, "_launch_publish", return_value=os.getpid()) as lp:
        r = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r.status_code == 200 and r.json["ok"] is True
        lp.assert_called_once_with("2019-Civic-004352")
        # segundo intento mientras el PID sigue vivo → 409
        r2 = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r2.status_code == 409
    admin_api._lock_file().unlink(missing_ok=True)

def test_publish_slug_inexistente_404(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    admin_api._lock_file().unlink(missing_ok=True)
    assert cl.post("/api/admin/publish/noexiste", headers=H).status_code == 404

def test_lock_muerto_se_limpia(tmp_path):
    _car(tmp_path)
    with patch.object(admin_api, "_launch_publish", return_value=2147480000):  # PID muerto
        r = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r.status_code == 200
        r2 = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r2.status_code == 200  # el lock anterior estaba muerto → se reintenta
    admin_api._lock_file().unlink(missing_ok=True)

def test_mark_publicado(tmp_path):
    folder = _car(tmp_path)
    r = cl.post("/api/admin/mark/2019-Civic-004352", headers=H)
    assert r.status_code == 200 and r.json["published"] is True and r.json["published_at"]
    assert admin_api.read_status(folder)["published"] is True
    assert not admin_api._lock_file().exists()
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv/bin/python -m pytest tests/test_admin_api.py -v`
Expected: FAIL — `_lock_file`, `_launch_publish` y los endpoints no existen.

- [ ] **Step 3: Añadir lock, launcher y endpoints a `admin_api.py`**

Añadir a `admin_api.py`:

```python
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
```

- [ ] **Step 4: Correr toda la suite del panel y verificar que pasa**

Run: `venv/bin/python -m pytest tests/test_admin_api.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add admin_api.py tests/test_admin_api.py
git commit -m "feat: admin panel endpoints (list/publish-lock/mark)"
```

---

### Task 4: Publicación de carros del scanner en `marketplace_poster.py`

Lógica pura de campos con datos reales (`scanner_car_fields`) + el flujo de Chrome que llena el formulario y **se detiene antes de Publicar** (`post_scanner_car`), más el entrypoint que lee el inventario y el CLI `--scanner`.

**Files:**
- Modify: `marketplace_poster.py`
- Test: `tests/test_marketplace_scanner.py`

**Interfaces:**
- Consumes: helpers existentes `select_combobox_option`, `fill_label_input`, `COLOR_MAP`, `BODY_STYLE_MAP`, `FUEL_MAP`.
- Produces:
  - `scanner_car_fields(car: dict) -> dict` con claves `make, model, year, mileage, price, body_style, exterior_color, interior_color, fuel, condition, title, description` (todas `str`).
  - `async def post_scanner_car(page, fields: dict, photo_paths: list[str]) -> bool` — llena el form, sube fotos, se detiene antes de Publicar; devuelve True si llenó, False si no encontró el formulario.
  - `async def publish_scanner_car(slug: str) -> None` — lee `INVENTORY_DIR/<slug>/`, abre Chrome visible, llama a `post_scanner_car`, deja el navegador abierto.
  - CLI: `python marketplace_poster.py --scanner <slug>`.

- [ ] **Step 1: Escribir el test que falla (campos reales)**

Crear `tests/test_marketplace_scanner.py`:

```python
import marketplace_poster

def test_scanner_car_fields_usa_datos_reales():
    car = {"make": "Honda", "model": "Civic", "yr": "2019",
           "mileage": 45000, "price": 16500, "color": "Blue",
           "title": "2019 Honda Civic EX", "description": "buen carro"}
    f = marketplace_poster.scanner_car_fields(car)
    assert f["make"] == "Honda"        # marca real, NO "Toyota"
    assert f["mileage"] == "45000"     # millaje real, NO "500"
    assert f["price"] == "16500"       # precio completo, NO enganche (20%)
    assert f["interior_color"] == "Black"
    assert f["exterior_color"] == "Blue"
    assert f["condition"] == "Excellent"
    assert f["title"] == "2019 Honda Civic EX"

def test_scanner_car_fields_make_fallback():
    # Si el scanner no trae marca, cae a Toyota (dealer Toyota) sin romper
    f = marketplace_poster.scanner_car_fields({"model": "Corolla", "yr": "2020",
                                               "mileage": 10, "price": 20000, "color": "White"})
    assert f["make"] == "Toyota" and f["exterior_color"] == "White"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `venv/bin/python -m pytest tests/test_marketplace_scanner.py -v`
Expected: FAIL — `scanner_car_fields` no existe.

- [ ] **Step 3: Implementar `scanner_car_fields`**

Añadir a `marketplace_poster.py` (después de `FUEL_MAP`):

```python
def scanner_car_fields(car: dict) -> dict:
    """Campos de Marketplace para un carro del SCANNER (usado, cualquier marca).
    A diferencia del stock nuevo del dealer: marca/millaje/precio son los REALES."""
    model = str(car.get("model", ""))
    color = str(car.get("color", ""))
    vc = color.lower()
    body_style = next((bs for k, bs in BODY_STYLE_MAP.items() if k.lower() in model.lower()), "SUV")
    fb_color = next((fb for name, fb in COLOR_MAP.items() if name in vc), "Black")
    ml = model.lower()
    fuel = next((f for k, f in FUEL_MAP.items() if k in ml), "Gasoline")
    return {
        "make": str(car.get("make") or "Toyota"),
        "model": model,
        "year": str(car.get("yr", "")),
        "mileage": str(car.get("mileage", "")),
        "price": str(car.get("price", "")),
        "body_style": body_style,
        "exterior_color": fb_color,
        "interior_color": "Black",
        "fuel": fuel,
        "condition": "Excellent",
        "title": str(car.get("title", "")),
        "description": str(car.get("description", "")),
    }
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `venv/bin/python -m pytest tests/test_marketplace_scanner.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Implementar el flujo de Chrome que se detiene antes de Publicar**

Añadir a `marketplace_poster.py`:

```python
async def post_scanner_car(page, fields: dict, photo_paths: list) -> bool:
    """Llena el formulario de Marketplace con los datos reales del carro y SE DETIENE
    antes del botón Publicar de Facebook. Alejo revisa y publica manualmente."""
    await page.goto("https://www.facebook.com/marketplace/create/vehicle",
                    wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    await select_combobox_option(page, "Vehicle type", "Car/Truck")
    await asyncio.sleep(2)

    if photo_paths:
        try:
            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(photo_paths)
            await asyncio.sleep(4)
            print(f"    📷 {len(photo_paths)} fotos subidas")
        except Exception as e:
            print(f"    ⚠️  Fotos: {e}")

    await select_combobox_option(page, "Year", fields["year"]); await asyncio.sleep(2)
    await select_combobox_option(page, "Make", fields["make"]); await asyncio.sleep(2)
    await fill_label_input(page, "Model", fields["model"]); await asyncio.sleep(1)
    await fill_label_input(page, "Mileage", fields["mileage"]); await asyncio.sleep(0.5)
    await select_combobox_option(page, "Body style", fields["body_style"]); await asyncio.sleep(1)
    await select_combobox_option(page, "Exterior color", fields["exterior_color"]); await asyncio.sleep(1)
    await select_combobox_option(page, "Interior color", fields["interior_color"]); await asyncio.sleep(1)
    try:
        chk = page.locator('input[type="checkbox"][aria-label*="clean title"]')
        if not await chk.is_checked(timeout=2000):
            await chk.check()
    except Exception:
        pass
    await select_combobox_option(page, "Vehicle condition", fields["condition"]); await asyncio.sleep(1)
    await select_combobox_option(page, "Fuel type", fields["fuel"]); await asyncio.sleep(1)
    await fill_label_input(page, "Price", fields["price"]); await asyncio.sleep(0.5)
    await fill_label_input(page, "Description", fields["description"]); await asyncio.sleep(1)

    safe = re.sub(r"[^A-Za-z0-9_-]", "_", fields.get("title", "car"))[:60]
    await page.screenshot(path=f"/tmp/mp_scanner_{safe}.png")
    print("    ⏸️  Formulario lleno. Revisa y dale PUBLICAR tú mismo en Facebook.")
    return True


async def publish_scanner_car(slug: str) -> None:
    """Lee inventario/<slug>/ y abre Chrome VISIBLE con el formulario lleno.
    Deja el navegador abierto para que Alejo revise y publique manualmente."""
    inv = os.environ.get("INVENTORY_DIR", str(Path(__file__).parent / "inventory"))
    folder = Path(inv) / slug
    car = json.loads((folder / "listing.json").read_text())
    fields = scanner_car_fields(car)
    photos_dir = folder / "photos"
    photo_paths = [str(p) for p in sorted(photos_dir.glob("*.jpg"))] if photos_dir.exists() else []

    with open(SESSION_FILE) as f:
        storage = json.load(f)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900},
                                        storage_state=storage)
        page = await ctx.new_page()
        print(f"\n  📦 {fields['year']} {fields['make']} {fields['model']} — "
              f"{fields['mileage']} mi — ${fields['price']}")
        await post_scanner_car(page, fields, photo_paths)
        # NO cerramos el browser: Alejo revisa y da Publicar. Se cierra al terminar él.
        await asyncio.sleep(3600)
```

Y añadir `import re` arriba si no está, y extender el `__main__`:

```python
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--scanner":
        asyncio.run(publish_scanner_car(sys.argv[2]))
    else:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
        asyncio.run(main(limit=limit))
```

- [ ] **Step 6: Verificar que el módulo importa y no rompe la suite**

Run: `venv/bin/python -c "import marketplace_poster; print('ok')" && venv/bin/python -m pytest tests/test_marketplace_scanner.py -v`
Expected: `ok` y PASS (2 passed). (El flujo de Chrome se verifica manualmente en el Mac Pro; no toca Facebook en los tests.)

- [ ] **Step 7: Commit**

```bash
git add marketplace_poster.py tests/test_marketplace_scanner.py
git commit -m "feat: publish scanner cars with real make/mileage/price, stop before FB publish"
```

---

### Task 5: Panel `/admin` (frontend)

Página que lista los carros del scanner con badge de estado, permite editar los no publicados y disparar la publicación de uno a la vez. Reusa el patrón visual y de auth del scanner (rojo Toyota `#EB0A1E`, clave en `localStorage`).

**Files:**
- Create: `static/admin/index.html`
- Create: `static/admin/admin.css`
- Create: `static/admin/admin.js`

**Interfaces:**
- Consumes: `GET /api/admin/inventory`, `POST /api/admin/publish/<slug>`, `POST /api/admin/mark/<slug>`, `PUT /api/scanner/inventory/<slug>` (editar), `GET /api/scanner/inventory/<slug>/photo/1?key=<KEY>` (foto). Todos con header `X-Scanner-Key` salvo la foto (query `?key=`).

- [ ] **Step 1: Crear `static/admin/index.html`**

Estructura mínima: overlay de clave (igual patrón que el scanner, guarda en `localStorage` bajo `nexus_scanner_key`), header "ADMINISTRADOR — Tu Carro con Alejo", contenedor `#cars` para las tarjetas, y un modal `#editModal` con campos `título, descripción, precio, millaje, color, marca` + botón Guardar. Incluir `<link rel="stylesheet" href="/static/admin/admin.css">` y `<script src="/static/admin/admin.js"></script>`.

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Administrador — Tu Carro con Alejo</title>
<meta name="theme-color" content="#EB0A1E">
<link rel="stylesheet" href="/static/admin/admin.css">
</head>
<body>
<div id="keyOverlay" class="overlay hidden">
  <div class="card">
    <h2>Administrador</h2>
    <p>Ingresa la clave para continuar.</p>
    <input type="text" id="keyInput" autocomplete="off" placeholder="Clave">
    <button id="keySaveBtn">Entrar</button>
  </div>
</div>
<header>
  <h1>ADMINISTRADOR <span>Tu Carro con Alejo</span></h1>
  <p id="publishingBanner" class="banner hidden"></p>
</header>
<main id="cars"><p class="hint">Cargando…</p></main>

<div id="editModal" class="overlay hidden">
  <div class="card">
    <h2>Editar carro</h2>
    <label>Título <input id="eTitle" maxlength="100"></label>
    <label>Descripción <textarea id="eDesc" rows="8"></textarea></label>
    <label>Marca <input id="eMake"></label>
    <label>Precio <input id="ePrice" type="number" inputmode="numeric"></label>
    <label>Millaje <input id="eMileage" type="number" inputmode="numeric"></label>
    <label>Color <input id="eColor"></label>
    <button id="eSaveBtn">Guardar cambios</button>
    <button id="eCancelBtn" class="ghost">Cancelar</button>
  </div>
</div>
<script src="/static/admin/admin.js"></script>
</body>
</html>
```

- [ ] **Step 2: Crear `static/admin/admin.css`**

Estilo oscuro NEXUS (fondo `#0A0A0A`, acentos `#EB0A1E`, fuente `Inter`/system). Tarjeta por carro con foto a la izquierda, datos a la derecha, badge de estado arriba a la derecha. Clases: `.car-card`, `.badge.pending` (amarillo), `.badge.published` (verde), `.badge.failed` (rojo), `.overlay`, `.hidden`, `.hint`, `.banner`. Botones `.btn-primary` (rojo), `.ghost`. Diseño responsive (una columna en móvil). Que el `.overlay` centre su `.card` y `#cars` sea un grid/flex de tarjetas apiladas.

- [ ] **Step 3: Crear `static/admin/admin.js`**

Lógica:
- Al cargar: leer `localStorage.nexus_scanner_key`; si no hay, mostrar `#keyOverlay`; al guardar, ocultar y cargar.
- `api(path, opts)`: fetch con header `X-Scanner-Key`; si 401, limpiar clave y volver a pedirla.
- `load()`: `GET /api/admin/inventory`; renderizar una tarjeta por item. Foto: `/api/scanner/inventory/${slug}/photo/1?key=${KEY}`. Badge según estado: `published` → 🟢 "Publicado {published_at}"; `last_error` → 🔴 "Falló: {last_error}"; si no → 🟡 "Sin publicar". Mostrar `year make model`, precio, millaje.
- Si el item NO está publicado: botones **Editar** y **Publicar este carro**. Si está publicado: sin botones de acción.
- Si `resp.publishing` no es null: mostrar `#publishingBanner` ("Publicando {slug} — termina en el Mac Pro y marca como publicado") y deshabilitar todos los botones "Publicar".
- **Editar**: abrir `#editModal`, precargar con `GET /api/scanner/inventory/<slug>`; Guardar → `PUT /api/scanner/inventory/<slug>` con `{title, description, make, price, mileage, color}` (números con `Number(...)`); cerrar y `load()`.
- **Publicar**: `POST /api/admin/publish/<slug>`; si 200, alert "Chrome se abrió en el Mac Pro. Revisa el formulario y dale Publicar. Luego vuelve y marca como publicado." y añadir a esa tarjeta un botón **Marcar publicado**; si 409, alert "Ya hay una publicación en curso." Recargar.
- **Marcar publicado**: `POST /api/admin/mark/<slug>` → `load()`.

- [ ] **Step 4: Verificar sintaxis JS/HTML**

Run: `node --check static/admin/admin.js`
Expected: sin salida (sintaxis válida). Si `node` no está: `venv/bin/python -c "import pathlib; pathlib.Path('static/admin/admin.js').read_text(); print('leido ok')"`.

- [ ] **Step 5: Commit**

```bash
git add static/admin/
git commit -m "feat: admin panel UI (status badges, edit, one-at-a-time publish)"
```

---

### Task 6: Montar `/admin` en `scanner_server.py`

Registrar el blueprint y servir la página del panel y sus estáticos desde el servidor que ya corre en el Mac Pro.

**Files:**
- Modify: `scanner_server.py`
- Test: `tests/test_scanner_server_admin.py`

**Interfaces:**
- Consumes: `admin_api.admin_bp`, archivos `static/admin/*` (Task 5).

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_scanner_server_admin.py`:

```python
import os
os.environ["SCANNER_KEY"] = "testkey"
import scanner_server

c = scanner_server.app.test_client()

def test_admin_page_sirve():
    r = c.get("/admin")
    assert r.status_code == 200 and b"ADMINISTRADOR" in r.data

def test_admin_static_sirve():
    assert c.get("/static/admin/admin.js").status_code == 200

def test_admin_api_registrado_y_protegido():
    # blueprint montado: sin clave → 401 (no 404)
    assert c.get("/api/admin/inventory").status_code == 401
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv/bin/python -m pytest tests/test_scanner_server_admin.py -v`
Expected: FAIL — `/admin` y `/api/admin/inventory` dan 404 (blueprint/rutas no registrados).

- [ ] **Step 3: Registrar el blueprint y las rutas en `scanner_server.py`**

Tras `from scanner_api import bp as scanner_bp` añadir:

```python
from admin_api import admin_bp
```

Tras `app.register_blueprint(scanner_bp)` añadir:

```python
app.register_blueprint(admin_bp)
```

Y junto a las rutas del scanner añadir:

```python
@app.get("/admin")
def admin_panel():
    return send_file(_HERE / "static/admin/index.html")


@app.get("/static/admin/<path:filename>")
def admin_static(filename):
    return send_file(_HERE / "static/admin" / filename)
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv/bin/python -m pytest tests/test_scanner_server_admin.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Correr toda la suite**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: todos los tests pasan (scanner + admin + marketplace).

- [ ] **Step 6: Commit**

```bash
git add scanner_server.py tests/test_scanner_server_admin.py
git commit -m "feat: mount /admin panel and admin_bp in scanner_server"
```

---

## Despliegue (manual, tras aprobar la rama — NO parte de la ejecución automática)

Solo en el Mac Pro (nunca en el Air). Sincronizar los archivos nuevos/cambiados y reiniciar el LaunchAgent del scanner:

```bash
# desde el Air, rsync al Pro (ejemplo — ajustar host/llave):
rsync -av admin_api.py marketplace_poster.py scanner_server.py scanner_api.py \
  static/admin/ static/scanner/app.js \
  macbookpro@macbook-pro-de-macbook.local:~/nexus-automation/
# en el Pro: reiniciar el servicio del scanner
launchctl kickstart -k gui/$(id -u)/com.nexus.scanner
```

Panel accesible en: `https://macbook-pro-de-macbook.tail99ec84.ts.net:8443/admin` (clave `nexus-d98064ac`). Requiere que la sesión de Facebook (`browser_session/fb_session.json`) esté vigente en el Mac Pro; si expiró, renovarla con login humano cuidadoso (la cuenta tuvo checkpoint en julio).

---

## Self-Review

**Spec coverage:**
- Estado persistente por carro (`published`/`published_at`/`last_error`) → Task 2 + 3. ✅
- Panel con badges 🟡/🟢/🔴, editar no publicados → Task 5 (usa PUT de Task 1). ✅
- Publicación separada con marca/millaje/precio reales, se detiene antes de Publicar → Task 4. ✅
- Uno a la vez (lock por PID) → Task 3. ✅
- Solo Mac Pro, navegador visible → Task 4 (`headless=False`) + despliegue. ✅
- Auth fail-closed, slug 404 → Task 3 (reusa `require_key`/`_folder_for`). ✅
- Inventarios separados → el panel solo lee `INVENTORY_DIR` del scanner. ✅
- Marca real (gap detectado: el scanner no la guardaba) → Task 1. ✅

**Placeholder scan:** sin TBD/TODO; todo el código está completo en cada step.

**Type consistency:** `scanner_car_fields` devuelve las claves que consume `post_scanner_car` (`year, make, model, mileage, body_style, exterior_color, interior_color, condition, fuel, price, description`). `read_status`/`set_status` usan las mismas 3 claves de estado en todos lados. Endpoints devuelven `slug` y estado consistentes con lo que consume `admin.js`.
