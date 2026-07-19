"""
NEXUS — Marketplace Poster
Publica listings de vehículos en Facebook Marketplace vía browser automation.
Usa sesión guardada de tucarroconalejo@gmail.com.
"""
import asyncio, json, os, re, requests, tempfile, time
from pathlib import Path
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

SESSION_FILE = Path(__file__).parent / "browser_session/fb_session.json"
LOG_FILE     = Path(__file__).parent / "marketplace_posted.json"
INVENTORY_URL = "https://tucarroconalejo.com/api.php?action=list"
IMAGE_BASE    = "https://bot.tucarroconalejo.com/feed/image"

def load_posted() -> dict:
    try:
        return json.loads(LOG_FILE.read_text())
    except Exception:
        return {}

def save_posted(log: dict):
    LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False))

_COLOR_PRIORITY = [
    "red", "supersonic", "blue", "heritage", "cavalry", "blueprint",
    "white", "ice cap", "wind chill", "silver", "sky",
    "black", "midnight", "underground", "gray", "magnetic",
]

def _color_score(color: str) -> int:
    c = color.lower()
    for i, kw in enumerate(_COLOR_PRIORITY):
        if kw in c:
            return i
    return 99

_COLOR_CODE_RE = __import__("re").compile(r"^[0-9][A-Z0-9]{3}$")

def _is_real_color(color: str) -> bool:
    return not _COLOR_CODE_RE.match(color.strip())

def _resolve_fb_color(color: str) -> str:
    vc = color.lower()
    return next((fb for name, fb in COLOR_MAP.items() if name in vc), "Black")

def fetch_unique_inventory() -> list:
    """Un listing por trim — varía colores dentro del mismo modelo sin repetir categoría FB."""
    r = requests.get(INVENTORY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    vehicles = r.json()["vehicles"]

    # Agrupar: model → trim → [vehículos con color real]
    model_groups: dict = {}
    for v in vehicles:
        if not v.get("vin") or not _is_real_color(v.get("color", "")):
            continue
        model_groups.setdefault(v["model"], {}).setdefault(v.get("trim", ""), []).append(v)

    unique = []
    for model, trims in sorted(model_groups.items()):
        used_fb: set = set()  # colores FB ya usados en este modelo
        for trim, group in sorted(trims.items()):
            # Ordenar por atractivo del color
            by_priority = sorted(group, key=lambda v: _color_score(v["color"]))
            # Intentar color no repetido en el modelo
            chosen = next(
                (v for v in by_priority if _resolve_fb_color(v["color"]) not in used_fb),
                by_priority[0]  # fallback: mejor color aunque repita
            )
            used_fb.add(_resolve_fb_color(chosen["color"]))
            unique.append(chosen)

    return unique

def download_image(vin: str) -> str | None:
    try:
        r = requests.get(f"{IMAGE_BASE}/{vin}", timeout=20)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(r.content)
            tmp.close()
            return tmp.name
    except Exception as e:
        print(f"    ⚠️  Image: {e}")
    return None

_TRIM_FEATURES = {
    "TRD Off-Road": "suspensión off-road, diferencial trasero bloqueado, modos de terreno Multi-Terrain Select",
    "TRD Sport": "amortiguadores TRD, sport bar, llantas exclusivas TRD",
    "TRD Pro": "suspensión Fox, skid plates, diferencial trasero bloqueado, color exclusivo",
    "Limited": "cuero premium, sunroof panorámico, JBL audio, llantas 20\"",
    "Platinum": "cuero premium, sunroof, JBL audio, head-up display, asientos ventilados",
    "SR5": "ruedas de aleación, Apple CarPlay, Android Auto, Toyota Safety Sense",
    "SR": "pantalla táctil 8\", cámara de reversa, Toyota Safety Sense 2.0",
    "XSE": "diseño sport, techo solar, llantas 18\", interior sport",
    "XLE": "cuero, sunroof, calefacción de asientos, Apple CarPlay",
    "LE": "Apple CarPlay, Android Auto, cámara trasera, Toyota Safety Sense",
    "Hybrid": "motor híbrido, ahorro de combustible excepcional, tecnología Toyota",
    "Plug-in Hybrid": "motor plug-in híbrido, modo eléctrico disponible",
}

def build_description(v: dict) -> str:
    model  = v["model"]
    trim   = v.get("trim", "")
    color  = v["color"]
    yr     = v["yr"]
    # Find trim feature blurb
    features = next(
        (feat for key, feat in _TRIM_FEATURES.items() if key.lower() in trim.lower()),
        "Apple CarPlay, Android Auto, Toyota Safety Sense, cámara de reversa"
    )

    return (
        f"{yr} Toyota {model} {trim} — {color}\n\n"
        f"✅ Vehículo nuevo — 0 km de fábrica\n"
        f"✅ Transmisión automática\n"
        f"✅ {features}\n\n"
        f"💳 Precio mostrado = enganche estimado.\n"
        f"Financiamiento disponible — crédito en construcción también aplica.\n\n"
        f"📍 Hollywood, Florida\n"
        f"👤 Soy Alejo, te atiendo personalmente.\n\n"
        f"Escríbeme aquí o llámame directo:\n"
        f"📞 (954) 910-6671"
    )

async def select_combobox_option(page, label_text: str, option_text: str) -> bool:
    """Clicks a LABEL[role=combobox] by its visible text, then picks an option."""
    try:
        combo = page.get_by_role("combobox").filter(has_text=label_text)
        await combo.first.click(timeout=5000)
        await asyncio.sleep(1.5)
    except Exception as e:
        print(f"    ⚠️  Abrir '{label_text}': {e}")
        return False

    # Option appears as role=option, listitem, or option element
    for selector in [
        f'[role="option"]:has-text("{option_text}")',
        f'li:has-text("{option_text}")',
        f'[role="listitem"]:has-text("{option_text}")',
    ]:
        try:
            opt = page.locator(selector).first
            if await opt.is_visible(timeout=2000):
                await opt.click()
                await asyncio.sleep(1)
                return True
        except Exception:
            pass

    # get_by_role fallback
    for role in ["option", "menuitem"]:
        try:
            opt = page.get_by_role(role, name=option_text)
            if await opt.first.is_visible(timeout=1500):
                await opt.first.click()
                await asyncio.sleep(1)
                return True
        except Exception:
            pass

    # Último intento: reabrir y escribir para filtrar
    try:
        combo = page.get_by_role("combobox").filter(has_text=label_text)
        await combo.first.click(timeout=3000)
        await asyncio.sleep(1)
        await page.keyboard.type(option_text, delay=80)
        await asyncio.sleep(1)
        opt = page.locator(f'[role="option"]:has-text("{option_text}")').first
        if await opt.is_visible(timeout=2000):
            await opt.click()
            await asyncio.sleep(1)
            return True
    except Exception:
        pass

    print(f"    ⚠️  Opción '{option_text}' no encontrada en '{label_text}'")
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)
    return False

async def fill_label_input(page, label_text: str, value: str) -> bool:
    """Fills an input associated with a LABEL element."""
    try:
        field = page.get_by_label(label_text)
        await field.first.click(timeout=5000)
        await field.first.fill(value)
        await asyncio.sleep(0.5)
        return True
    except Exception as e:
        print(f"    ⚠️  Fill '{label_text}': {e}")
    return False

COLOR_MAP = {
    "black": "Black", "white": "White", "silver": "Silver",
    "gray": "Gray", "grey": "Gray", "red": "Red", "blue": "Blue",
    "green": "Green", "brown": "Brown", "gold": "Gold",
    "orange": "Orange", "yellow": "Yellow", "purple": "Purple",
    "beige": "Beige", "magnetic": "Gray", "midnight": "Black",
    "wind chill": "White", "supersonic": "Red", "cavalry": "Blue",
    "solar": "Yellow", "blueprint": "Blue", "cavalry blue": "Blue",
    "silver sky": "Silver", "ice cap": "White", "army green": "Green",
}

BODY_STYLE_MAP = {
    "4Runner": "SUV", "RAV4": "SUV", "Highlander": "SUV",
    "Grand Highlander": "SUV", "Sequoia": "SUV", "Corolla Cross": "SUV",
    "bZ4X": "SUV", "C-HR": "SUV", "Land Cruiser": "SUV",
    "Camry": "Sedan", "Corolla": "Sedan", "Crown": "Sedan",
    "Tacoma": "Truck", "Tundra": "Truck",
    "Sienna": "Minivan", "GR Supra": "Coupe", "GR86": "Coupe",
    "Prius": "Hatchback",
}

FUEL_MAP = {
    "bz": "Electric", "electric": "Electric",
    "plug-in hybrid": "Plug-in hybrid", "hybrid": "Hybrid",
}

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


async def post_vehicle(page, v: dict, posted: dict) -> bool:
    vin   = v.get("vin", "")
    key   = f"{v['yr']}|{v['model']}|{v.get('trim','')}"
    down  = round(v["price"] * 0.20 / 100) * 100
    model = v["model"]
    trim  = v.get("trim", "")
    safe_key = key.replace("|", "_").replace("/", "-").replace(" ", "_")[:60]

    # Resolve body style
    body_style = next((bs for k, bs in BODY_STYLE_MAP.items() if k.lower() in model.lower()), "SUV")
    # Resolve exterior color — default Black si no hay match
    vc = v["color"].lower()
    fb_color = next((fb for name, fb in COLOR_MAP.items() if name in vc), "Black")
    # Resolve fuel type
    ml = model.lower()
    fuel = next((f for k, f in FUEL_MAP.items() if k in ml), "Gasoline")

    print(f"\n  📦 {v['yr']} Toyota {model} {trim} — {v['color']} (${down:,} down)")

    await page.goto("https://www.facebook.com/marketplace/create/vehicle",
                   wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # --- Vehicle type ---
    await select_combobox_option(page, "Vehicle type", "Car/Truck")
    await asyncio.sleep(2)

    # --- Upload photo ---
    img_path = download_image(vin)
    if img_path:
        try:
            # Inject directly into the hidden file input — more reliable than file chooser
            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(img_path)
            await asyncio.sleep(4)
            if os.path.exists(img_path):
                os.unlink(img_path)
            print("    📷 Foto subida")
        except Exception as e:
            print(f"    ⚠️  Foto: {e}")

    # --- Year ---
    await select_combobox_option(page, "Year", str(v["yr"]))
    await asyncio.sleep(2)

    # --- Make ---
    await select_combobox_option(page, "Make", "Toyota")
    await asyncio.sleep(2)

    # --- Model (text input, appears after Make) ---
    await fill_label_input(page, "Model", model)
    await asyncio.sleep(1)

    # --- Mileage ---
    await fill_label_input(page, "Mileage", "500")
    await asyncio.sleep(0.5)

    # --- Body style ---
    await select_combobox_option(page, "Body style", body_style)
    await asyncio.sleep(1)

    # --- Exterior color ---
    if fb_color:
        await select_combobox_option(page, "Exterior color", fb_color)
        await asyncio.sleep(1)

    # --- Interior color (requerido) ---
    await select_combobox_option(page, "Interior color", "Black")
    await asyncio.sleep(1)

    # --- Clean title checkbox ---
    try:
        chk = page.locator('input[type="checkbox"][aria-label*="clean title"]')
        if not await chk.is_checked(timeout=2000):
            await chk.check()
    except Exception:
        pass

    # --- Vehicle condition ---
    await select_combobox_option(page, "Vehicle condition", "Excellent")
    await asyncio.sleep(1)

    # --- Fuel type ---
    await select_combobox_option(page, "Fuel type", fuel)
    await asyncio.sleep(1)

    # --- Price ---
    await fill_label_input(page, "Price", str(down))
    await asyncio.sleep(0.5)

    # --- Description ---
    await fill_label_input(page, "Description", build_description(v))
    await asyncio.sleep(1)

    await page.screenshot(path=f"/tmp/mp_step1_{safe_key}.png")

    # --- Next ---
    try:
        next_btn = page.get_by_role("button", name="Next")
        # Force=True bypasses aria-disabled check — FB validates server-side
        await next_btn.click(force=True, timeout=5000)
        await asyncio.sleep(5)
        await page.screenshot(path=f"/tmp/mp_step2_{safe_key}.png")
        print("    ➡️  Paso 2")
    except Exception as e:
        print(f"    ⚠️  Next: {e}")
        await page.screenshot(path=f"/tmp/mp_next_fail_{safe_key}.png")
        return False

    # === PAGE 2: Publish ===
    await asyncio.sleep(3)

    # Cerrar popup "Query Error" que aparece al cargar grupos
    for _ in range(3):
        try:
            btn = page.get_by_role("button", name="Close").first
            if await btn.is_visible(timeout=1500):
                await btn.click()
                await asyncio.sleep(1)
                break
        except Exception:
            pass
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except Exception:
            pass

    await page.screenshot(path=f"/tmp/mp_step2_{safe_key}.png")

    for pub_text in ["Publish", "Publicar", "Post", "Submit"]:
        try:
            btn = page.get_by_role("button", name=pub_text)
            if await btn.first.is_visible(timeout=3000):
                await btn.first.click()
                await asyncio.sleep(6)
                print(f"    ✅ ¡Publicado!")
                posted[key] = {
                    "vin": vin,
                    "title": f"{v['yr']} Toyota {model} {trim} — {v['color']}",
                    "down": down,
                    "posted_at": time.strftime("%Y-%m-%d %H:%M"),
                }
                return True
        except Exception:
            pass

    await page.screenshot(path=f"/tmp/mp_no_publish_{safe_key}.png")
    print("    ⚠️  Publish no encontrado — screenshot guardado")
    return False


async def main(limit: int = 5):
    """
    limit: cuántos vehículos publicar en esta corrida.
           Usar 137 para publicar todos.
    """
    with open(SESSION_FILE) as f:
        storage = json.load(f)

    posted = load_posted()
    vehicles = fetch_unique_inventory()
    pending  = [v for v in vehicles
                if f"{v['yr']}|{v['model']}|{v.get('trim','')}" not in posted]

    print(f"Inventario: {len(vehicles)} | Ya publicados: {len(posted)} | Pendientes: {len(pending)}")
    print(f"Publicando {min(limit, len(pending))} en esta corrida...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            storage_state=storage
        )
        page = await ctx.new_page()

        count = 0
        for v in pending[:limit]:
            try:
                ok = await post_vehicle(page, v, posted)
                if ok:
                    count += 1
                    save_posted(posted)
                await asyncio.sleep(10)
            except Exception as e:
                print(f"    ❌ Error: {e}")
                await asyncio.sleep(5)

        print(f"\n✅ Corrida completa: {count} publicados.")
        print(f"   Total acumulado: {len(posted)} de {len(vehicles)}.")
        await asyncio.sleep(15)
        await browser.close()

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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--scanner":
        asyncio.run(publish_scanner_car(sys.argv[2]))
    else:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
        asyncio.run(main(limit=limit))
