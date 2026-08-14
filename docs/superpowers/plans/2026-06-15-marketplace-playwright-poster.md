# Marketplace Playwright Poster — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatizar el posting de vehículos en Facebook Marketplace usando Playwright — sin Chrome Claude, sin copy-paste. Un comando publica el carro del día en ~30 segundos.

**Architecture:** `marketplace_poster.py` lee el último listing de `marketplace_daily_log.json`, carga cookies de sesión de Facebook guardadas localmente, navega al formulario de Marketplace, llena todos los campos, sube la foto y captura la URL del listing publicado. El flujo de login manual (headed) solo se corre la primera vez para guardar las cookies.

**Tech Stack:** Playwright 1.60 (Python), Chromium headless, `marketplace_daily_log.json`, `~/Desktop/nexus_listing.jpg`

---

## Archivos

- **Crear:** `marketplace_poster.py` — script principal Playwright
- **Crear:** `fb_session.py` — helper para guardar/cargar cookies de FB
- **Modifica:** `marketplace_daily_log.json` — agrega `listing_url` al entry del día
- **NO subir a git:** `~/.fb_cookies.json` (sesión personal de Facebook)

---

### Task 1: fb_session.py — Guardar y cargar sesión de Facebook

**Archivos:**
- Crear: `fb_session.py`

- [ ] **Step 1: Crear fb_session.py**

```python
"""Guarda y carga cookies de sesión de Facebook para Playwright."""
import json
import os
from pathlib import Path
from playwright.sync_api import BrowserContext, sync_playwright

COOKIES_PATH = Path.home() / ".fb_cookies.json"


def save_cookies(context: BrowserContext):
    cookies = context.cookies()
    COOKIES_PATH.write_text(json.dumps(cookies, indent=2))
    print(f"  ✅ Sesión guardada en {COOKIES_PATH}")


def load_cookies(context: BrowserContext) -> bool:
    if not COOKIES_PATH.exists():
        return False
    cookies = json.loads(COOKIES_PATH.read_text())
    context.add_cookies(cookies)
    print(f"  ✅ Sesión cargada ({len(cookies)} cookies)")
    return True


def login_and_save():
    """Abre un browser visible para que el usuario haga login manualmente."""
    print("\n🔐 Abriendo Facebook para login manual...")
    print("   Inicia sesión en tu cuenta y presiona ENTER aquí cuando estés listo.\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.facebook.com/login")
        input("   [Presiona ENTER después de hacer login en el browser] ")
        save_cookies(context)
        browser.close()
    print("  Listo. La próxima vez no tendrás que hacer login.")


def session_exists() -> bool:
    return COOKIES_PATH.exists()
```

- [ ] **Step 2: Verificar que importa sin errores**

```bash
cd /Users/macbookpro/nexus-automation && source venv/bin/activate && python3 -c "from fb_session import session_exists; print('fb_session OK')"
```
Esperado: `fb_session OK`

- [ ] **Step 3: Commit**

```bash
git add fb_session.py
git commit -m "feat: fb_session helper para cookies de Facebook"
```

---

### Task 2: marketplace_poster.py — Leer datos del listing del día

**Archivos:**
- Crear: `marketplace_poster.py`

- [ ] **Step 1: Crear estructura base con carga de datos**

```python
"""
NEXUS Marketplace Poster — Playwright
Publica automáticamente el carro del día en Facebook Marketplace.
Uso:
  python3 marketplace_poster.py           # publica el último listing del log
  python3 marketplace_poster.py --login   # hace login y guarda cookies (primera vez)
"""
import json
import os
import sys
from pathlib import Path
from datetime import date
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
from fb_session import load_cookies, login_and_save, session_exists

LOG_PATH   = Path(__file__).parent / "marketplace_daily_log.json"
PHOTO_PATH = Path.home() / "Desktop" / "nexus_listing.jpg"
FB_MP_URL  = "https://www.facebook.com/marketplace/create/vehicle"


def load_todays_listing() -> dict:
    log = json.loads(LOG_PATH.read_text())
    listings = log.get("listings", [])
    if not listings:
        raise ValueError("No hay listings en marketplace_daily_log.json — corre marketplace_daily.py primero")
    last = listings[-1]
    last["title"] = f"{last['yr']} Toyota {last['model']} {last.get('trim', '')} — {last['color']}"
    last["down_payment"] = round(last["price"] * 0.20 / 100) * 100
    return last
```

- [ ] **Step 2: Verificar carga de datos**

```bash
cd /Users/macbookpro/nexus-automation && source venv/bin/activate && python3 -c "
from marketplace_poster import load_todays_listing
v = load_todays_listing()
print(v['title'], '| Price:', v['price'], '| Down:', v['down_payment'])
"
```
Esperado: `2026 Toyota 4Runner TRD Off-Road Premium  — Black | Price: 67158 | Down: 13400`

---

### Task 3: marketplace_poster.py — Llenar el formulario de Marketplace

**Archivos:**
- Modifica: `marketplace_poster.py` — agrega `fill_marketplace_form()`

- [ ] **Step 1: Agregar función fill_marketplace_form al archivo**

```python
def _select_option_by_text(page: Page, label: str, value: str, timeout: int = 8000):
    """Hace click en un combobox por su label y selecciona la opción que contiene el texto."""
    page.get_by_role("combobox", name=label).click(timeout=timeout)
    page.get_by_role("option", name=value, exact=False).first.click(timeout=timeout)


def _fill_text_field(page: Page, label: str, value: str, timeout: int = 8000):
    field = page.get_by_role("textbox", name=label)
    field.click(timeout=timeout)
    field.fill(str(value), timeout=timeout)


def fill_marketplace_form(page: Page, v: dict):
    print("  Navegando al formulario...")
    page.goto(FB_MP_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)  # Facebook necesita unos segundos para hidratar React

    print("  Llenando: Año, Marca, Modelo...")
    _fill_text_field(page, "Year", str(v["yr"]))
    page.wait_for_timeout(500)
    _fill_text_field(page, "Make", "Toyota")
    page.wait_for_timeout(500)
    _fill_text_field(page, "Model", v["model"])
    page.wait_for_timeout(500)

    print("  Llenando: Millaje, Condición...")
    _fill_text_field(page, "Mileage", "0")
    page.wait_for_timeout(500)
    try:
        _select_option_by_text(page, "Condition", "New")
    except PWTimeout:
        print("  ⚠️  Campo Condition no encontrado — skipping")

    print("  Llenando: Color, Precio...")
    try:
        _fill_text_field(page, "Exterior Color", v["color"])
        page.wait_for_timeout(500)
    except PWTimeout:
        print("  ⚠️  Color field no encontrado — skipping")

    _fill_text_field(page, "Price", str(v["price"]))
    page.wait_for_timeout(500)

    print("  Llenando: Descripción...")
    desc_field = page.get_by_role("textbox", name="Description")
    desc_field.click()
    desc_field.fill(v.get("description", ""))
    page.wait_for_timeout(500)

    print("  Llenando: Ubicación...")
    try:
        loc_field = page.get_by_role("textbox", name="Location")
        loc_field.click()
        loc_field.fill("Hollywood, FL")
        page.wait_for_timeout(1000)
        page.get_by_role("option").first.click(timeout=5000)
    except PWTimeout:
        print("  ⚠️  Location no encontrado — skipping")
```

- [ ] **Step 2: Commit progreso**

```bash
git add marketplace_poster.py
git commit -m "feat: marketplace_poster form filler (Playwright)"
```

---

### Task 4: marketplace_poster.py — Subir foto y publicar

**Archivos:**
- Modifica: `marketplace_poster.py` — agrega `upload_photo()`, `publish()`, `update_log()`

- [ ] **Step 1: Agregar upload_photo, publish y update_log**

```python
def upload_photo(page: Page):
    if not PHOTO_PATH.exists():
        print("  ⚠️  No hay foto en ~/Desktop/nexus_listing.jpg — skipping")
        return
    print(f"  Subiendo foto desde {PHOTO_PATH}...")
    # Facebook tiene un input[type=file] oculto — lo activamos via JS
    file_input = page.locator("input[type='file']").first
    file_input.set_input_files(str(PHOTO_PATH))
    page.wait_for_timeout(3000)  # esperar upload
    print("  ✅ Foto subida")


def publish(page: Page) -> str | None:
    """Hace click en Next y luego Publish. Retorna la URL del listing o None."""
    print("  Haciendo click en Next...")
    try:
        page.get_by_role("button", name="Next").click(timeout=8000)
        page.wait_for_timeout(2000)
    except PWTimeout:
        print("  ⚠️  Botón Next no encontrado — intentando Publish directo")

    print("  Publicando...")
    page.get_by_role("button", name="Publish").click(timeout=10000)
    
    # Esperar que la URL cambie a marketplace/item/
    try:
        page.wait_for_url("**/marketplace/item/**", timeout=15000)
        url = page.url
        print(f"  ✅ Publicado: {url}")
        return url
    except PWTimeout:
        print("  ⚠️  No se detectó URL del listing — el post puede haber funcionado igual")
        print(f"  URL actual: {page.url}")
        return page.url if "marketplace" in page.url else None


def update_log(listing_url: str):
    log = json.loads(LOG_PATH.read_text())
    if log["listings"]:
        log["listings"][-1]["listing_url"] = listing_url
        LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False))
        print(f"  ✅ URL guardada en log")
```

- [ ] **Step 2: Agregar función run() y __main__**

```python
def run():
    if "--login" in sys.argv:
        login_and_save()
        return

    if not session_exists():
        print("❌ No hay sesión de Facebook guardada.")
        print("   Corre primero: python3 marketplace_poster.py --login")
        return

    print("\n── NEXUS Marketplace Poster ────────────────────")
    v = load_todays_listing()
    print(f"🚗 Posting: {v['title']}")
    print(f"   Precio: ${v['price']:,} | Down: ${v['down_payment']:,}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headed para ver el proceso
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        load_cookies(context)
        page = context.new_page()

        # Verificar que la sesión es válida
        page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)
        if "login" in page.url.lower():
            browser.close()
            print("❌ La sesión expiró. Corre: python3 marketplace_poster.py --login")
            return

        fill_marketplace_form(page, v)
        upload_photo(page)
        url = publish(page)

        if url:
            update_log(url)
            print(f"\n✅ Listing publicado: {url}")
        else:
            print("\n⚠️  Post completado pero no se capturó la URL")

        input("\n[Presiona ENTER para cerrar el browser] ")
        browser.close()
    print("──────────────────────────────────────────────\n")


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Commit**

```bash
git add marketplace_poster.py fb_session.py
git commit -m "feat: marketplace_poster Playwright — post automático FB Marketplace"
```

---

### Task 5: Login inicial y prueba end-to-end

- [ ] **Step 1: Hacer login y guardar cookies (solo la primera vez)**

```bash
cd /Users/macbookpro/nexus-automation && source venv/bin/activate && python3 marketplace_poster.py --login
```
→ Se abre un browser. Alejo hace login en Facebook, presiona ENTER.
Esperado: `✅ Sesión guardada en ~/.fb_cookies.json`

- [ ] **Step 2: Correr el poster**

```bash
python3 marketplace_poster.py
```
Esperado:
```
── NEXUS Marketplace Poster ────────────────────
🚗 Posting: 2026 Toyota 4Runner TRD Off-Road Premium  — Black
   Precio: $67,158 | Down: $13,400
  ✅ Sesión cargada (N cookies)
  Navegando al formulario...
  Llenando: Año, Marca, Modelo...
  ...
  ✅ Publicado: https://www.facebook.com/marketplace/item/...
✅ Listing publicado
```

- [ ] **Step 3: Confirmar que el listing aparece en tu perfil de Marketplace**

Navegar a: `facebook.com/marketplace/you/selling`

- [ ] **Step 4: Si algo falla — debug mode**

```bash
# Correr con PWDEBUG=1 para ver el inspector de Playwright
PWDEBUG=1 python3 marketplace_poster.py
```

---

## Notas de implementación

**Por qué headed (no headless):**
Facebook detecta headless browsers y bloquea el login. Con `headless=False` el proceso es visible pero más confiable.

**Si Facebook cambia el UI:**
Los selectores usan `get_by_role` con labels de texto — más resilientes que CSS selectors o XPaths con clases dinámicas. Si un campo falla, revisar el label exacto con el inspector de Playwright (`PWDEBUG=1`).

**Descripción en el form:**
El log guarda `description` solo si se agrega. Necesitamos pasarla desde `marketplace_daily.py` al log, o generarla de nuevo en `marketplace_poster.py` si no está en el log.
