"""
NEXUS — Marketplace Poster
Publica listings de vehículos en Facebook Marketplace vía browser automation.
Usa sesión guardada de tucarroconalejo@gmail.com.
"""
import asyncio, json, os, re, requests, tempfile, time
from pathlib import Path
from playwright.async_api import async_playwright, Error as PlaywrightError
from dotenv import load_dotenv
from vin_utils import resolve_make

load_dotenv()

SESSION_FILE = Path(__file__).parent / "browser_session/fb_session.json"
LOG_FILE     = Path(__file__).parent / "marketplace_posted.json"
INVENTORY_URL = "https://tucarroconalejo.com/api.php?action=list"
IMAGE_BASE    = "https://bot.tucarroconalejo.com/feed/image"

def load_session_cookies(path=SESSION_FILE) -> list:
    """Devuelve SOLO las cookies de la sesión de Facebook.

    Acepta los dos formatos que hay en browser_session/:
      - storage_state de Playwright  {"cookies": [...], "origins": [...]}
        (lo que escribe refresh_fb_session.py cada vez que Alejo vuelve a entrar)
      - lista pelada de cookies      [...]  (fb_session.py / refresh_mp_session.py)

    Nunca se devuelven los 'origins'. Si se le pasan a
    new_context(storage_state=...), Playwright abre una página y navega a
    https://www.facebook.com para reinyectar el localStorage; Facebook redirige
    sola y el contexto muere con:
        "Error setting storage state: Execution context was destroyed"
    La sesión de FB vive en las cookies (c_user, xs, datr...), no en el
    localStorage — el inbox bot lleva meses corriendo así en Render.
    """
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return []
    return data if isinstance(data, list) else data.get("cookies", [])

# Misma identidad de navegador con la que refresh_fb_session.py inicia sesión.
# Facebook ata la sesión al fingerprint: si el UA o el flag de automatización no
# coinciden con los del login, invalida las cookies y muestra la pantalla de login.
# Los dos perfiles que puede dejar un login por terminal:
#   refresh_fb_session.py  -> ~/.fb_playwright_profile_poster
#   refresh_mp_session.py / marketplace_updater.py -> ~/.fb_playwright_profile
SESSION_PROFILES = [Path.home() / ".fb_playwright_profile_poster",
                    Path.home() / ".fb_playwright_profile"]


def session_profile() -> Path:
    """Perfil de Chrome donde vive (o va a vivir) la sesión de Facebook.

    Siempre el mismo, en orden fijo — no el más reciente: si cambiara de perfil
    entre corridas, el login se guardaría en uno y la siguiente publicada
    abriría el otro, y FB pediría login otra vez. Si no existe ninguno se
    devuelve el del poster igual: Playwright lo crea y ahí queda guardado el
    login que haga Alejo a mano."""
    if SESSION_CHANNEL:
        # Perfil aparte: Chrome y Chromium no comparten formato de perfil sin
        # riesgo, y mezclarlos deja a Alejo logueándose dos veces.
        return Path.home() / f".fb_playwright_profile_{SESSION_CHANNEL}"
    for d in SESSION_PROFILES:
        if d.is_dir():
            return d
    return SESSION_PROFILES[0]
# El Chromium que trae Playwright va por la 148, pero acá declarábamos
# Chrome/120: Facebook compara el UA contra los client hints (Sec-CH-UA), que
# Playwright sigue mandando con la versión real, y esa contradicción es una
# señal de bot justo en el momento del login.
#
# Con FB_BROWSER_CHANNEL=chrome usamos el Google Chrome de verdad instalado en
# la máquina y NO pisamos el UA: todo coherente, que es lo que menos fricción
# le da a Facebook cuando Alejo entra a mano.
SESSION_CHANNEL = os.environ.get("FB_BROWSER_CHANNEL", "").strip()
SESSION_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")
SESSION_ARGS = ["--disable-blink-features=AutomationControlled"]
SESSION_IGNORE_ARGS = ["--enable-automation"]
VIEWPORT = {"width": 1280, "height": 900}


async def open_session_context(p):
    """Abre Chrome con la sesión de Facebook ya iniciada. Devuelve (ctx, cerrar).

    Preferimos el perfil persistente que deja refresh_fb_session.py cuando Alejo
    entra por el terminal: ahí vive la sesión completa y Facebook la refresca
    sola en cada visita, así que no vuelve a pedir login. Exportar cookies a un
    Chromium limpio es el plan B — funciona hasta que FB nota que el navegador
    no es el mismo que inició sesión.
    """
    perfil = session_profile()
    perfil.mkdir(parents=True, exist_ok=True)
    opciones = dict(headless=False, slow_mo=300, viewport=VIEWPORT,
                    args=SESSION_ARGS, ignore_default_args=SESSION_IGNORE_ARGS)
    if SESSION_CHANNEL:
        opciones["channel"] = SESSION_CHANNEL      # UA propio y coherente
        print(f"  🔑 Navegador: {SESSION_CHANNEL} | perfil: {perfil.name}")
    else:
        opciones["user_agent"] = SESSION_UA
        print(f"  🔑 Perfil de sesión: {perfil.name}")
    ctx = await p.chromium.launch_persistent_context(str(perfil), **opciones)
    # A propósito NO sembramos las cookies de browser_session/: traen c_user y
    # xs aunque estén muertas, y eso hacía que diéramos el login por bueno
    # cuando Facebook seguía mostrando la pantalla de entrar. El perfil es la
    # única fuente de verdad de la sesión.
    return ctx, ctx.close


async def session_page(ctx):
    return ctx.pages[0] if ctx.pages else await ctx.new_page()


async def hay_muro_de_login(page) -> bool:
    """¿Facebook mandó al login en vez de al formulario?"""
    if "/login" in page.url or "/checkpoint" in page.url:
        return True
    try:
        return await page.locator('input[name="pass"]').first.is_visible(timeout=2000)
    except PlaywrightError:
        return False


async def ensure_logged_in(page, segundos: int = 240) -> None:
    """Si Facebook pide login, esperar a que Alejo entre a mano en esa misma
    ventana — UNA vez.

    Como el navegador corre sobre un perfil persistente, ese login queda
    guardado en disco y las publicadas siguientes ya no lo piden. Antes se
    abría un Chromium limpio: Alejo entraba, se publicaba, se cerraba la
    ventana y el login se perdía — por eso lo pedía en cada publicada.
    """
    if not await hay_muro_de_login(page):
        return

    print("\n  🔐 Facebook pidió login. Entrá en la ventana que se abrió.")
    print("     Es la última vez: queda guardado en el perfil.\n", flush=True)

    avisado_2fa = False
    for i in range(segundos):
        await asyncio.sleep(1)
        try:
            names = {c["name"] for c in await page.context.cookies()}
            url = page.url
        except PlaywrightError:
            continue  # la ventana está navegando justo ahora

        # Que exista la cookie c_user NO significa que la sesión sirva: puede
        # estar vencida. La señal buena es que Facebook deje de mostrar el muro.
        if not await hay_muro_de_login(page) and "c_user" in names:
            print("  ✅ Login detectado — sigo publicando", flush=True)
            await asyncio.sleep(2)
            return

        # Facebook manda a un checkpoint (código por SMS/app, "¿fuiste vos?").
        # Hasta que no lo pases NO entrega la cookie xs, así que no es que el
        # script esté colgado: está esperando que termines ese paso.
        if "/checkpoint" in url or "two_step" in url or "/authenticate" in url:
            if not avisado_2fa:
                print("  🔒 Facebook pidió verificación en dos pasos — completala "
                      "en la ventana y sigo solo.", flush=True)
                avisado_2fa = True

        if i and i % 15 == 0:
            faltan = [n for n in ("c_user", "xs") if n not in names]
            print(f"     ... esperando ({i}s) | página: {url[:90]}", flush=True)
            print(f"         cookies que faltan: {', '.join(faltan)}", flush=True)

    raise RuntimeError(
        f"no se completó el login en {segundos}s. Última página: {page.url[:120]}")

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
    try:
        mileage = int(car.get("mileage") or 0)
    except (TypeError, ValueError):
        mileage = 0
    # Marketplace no acepta 0 millas — un carro nuevo se publica igual con 500 (mínimo aceptado).
    if mileage <= 0:
        mileage = 500
    return {
        "make": str(resolve_make(car)),
        "model": model,
        "year": str(car.get("yr", "")),
        "mileage": str(mileage),
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
        # exact=True: evita chocar con "View next image" del carrusel de fotos
        next_btn = page.get_by_role("button", name="Next", exact=True)
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
    posted = load_posted()
    vehicles = fetch_unique_inventory()
    pending  = [v for v in vehicles
                if f"{v['yr']}|{v['model']}|{v.get('trim','')}" not in posted]

    print(f"Inventario: {len(vehicles)} | Ya publicados: {len(posted)} | Pendientes: {len(pending)}")
    print(f"Publicando {min(limit, len(pending))} en esta corrida...\n")

    async with async_playwright() as p:
        ctx, cerrar = await open_session_context(p)
        page = await session_page(ctx)

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
        await cerrar()

async def post_scanner_car(page, fields: dict, photo_paths: list, video_path: str | None = None) -> bool:
    """Llena el formulario de Marketplace con los datos reales del carro,
    selecciona todos los grupos disponibles y publica automáticamente."""
    await page.goto("https://www.facebook.com/marketplace/create/vehicle",
                    wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    await ensure_logged_in(page)
    if "marketplace/create/vehicle" not in page.url:
        # Después del login FB manda al inicio: hay que volver al formulario.
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

    if video_path:
        try:
            # Casilla aparte para video, junto a la de fotos (no es el mismo input)
            video_input = page.locator('input[type="file"][accept*="video"]').first
            if await video_input.count() == 0:
                video_input = page.locator('input[type="file"]').nth(1)
            await video_input.set_input_files(video_path)
            # El video pesa ~150MB y tarda mucho más en subir/procesar que las fotos
            await asyncio.sleep(75)
            print("    🎥 Video subido")
        except Exception as e:
            print(f"    ⚠️  Video: {e}")

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
    await page.screenshot(path=f"/tmp/mp_scanner_step1_{safe}.png")

    # --- Next: pasa a la página 2 (donde vive "Promote listing after publish") ---
    try:
        # exact=True: evita chocar con "View next image" del carrusel de fotos
        next_btn = page.get_by_role("button", name="Next", exact=True)
        await next_btn.click(force=True, timeout=5000)
        await asyncio.sleep(4)
    except Exception as e:
        print(f"    ⚠️  Next: {e}")
        await page.screenshot(path=f"/tmp/mp_scanner_next_fail_{safe}.png")
        return False

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

    # --- Apagar "Promote listing after publish" (viene activado por defecto) ---
    try:
        promote = page.locator(
            '[aria-label*="Promote listing after publish"], '
            'input[type="checkbox"][aria-label*="Promote listing"]'
        ).first
        if await promote.count() > 0:
            checked = await promote.get_attribute("aria-checked")
            is_on = (checked == "true") if checked is not None else await promote.is_checked()
            if is_on:
                await promote.click()
                await asyncio.sleep(0.5)
                print("    🔕 Promote listing after publish: apagado")
    except Exception as e:
        print(f"    ⚠️  Promote toggle: {e}")

    # --- Seleccionar todos los grupos disponibles (a petición de Alejo, jul 21 2026) ---
    try:
        checks = page.locator('div[role="checkbox"], input[type="checkbox"]')
        count = await checks.count()
        for i in range(count):
            item = checks.nth(i)
            try:
                label = (await item.get_attribute("aria-label")) or ""
                if "promote" in label.lower() or "clean title" in label.lower():
                    continue
                checked = await item.get_attribute("aria-checked")
                is_checked = (checked == "true") if checked is not None else await item.is_checked()
                if not is_checked:
                    await item.click()
                    await asyncio.sleep(0.3)
            except Exception:
                continue
        print(f"    👥 Grupos revisados: {count}")
    except Exception as e:
        print(f"    ⚠️  Grupos: {e}")

    await page.screenshot(path=f"/tmp/mp_scanner_prepublish_{safe}.png")

    # --- Publicar ---
    for pub_text in ["Publish", "Publicar", "Post", "Submit"]:
        try:
            btn = page.get_by_role("button", name=pub_text)
            if await btn.first.is_visible(timeout=3000):
                await btn.first.click()
                # Verificar que FB realmente salió del flujo de creación antes de
                # asumir éxito — un click que no navega (validación silenciosa,
                # error, rate limit) no significa que el listing quedó publicado.
                try:
                    await page.wait_for_url(lambda u: "/marketplace/create/" not in u, timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                await page.screenshot(path=f"/tmp/mp_scanner_postpublish_{safe}.png")
                if "/marketplace/create/" in page.url:
                    print(f"    ⚠️  Click en \"{pub_text}\" pero la URL sigue en create/ — no se publicó de verdad")
                    return False
                print("    ✅ ¡Publicado!")
                return True
        except Exception:
            pass

    await page.screenshot(path=f"/tmp/mp_scanner_no_publish_{safe}.png")
    print("    ⚠️  Publish no encontrado — screenshot guardado")
    return False


def record_publish_error(slug: str, msg: str) -> None:
    """Escribe last_error en el listing.json del carro del scanner (para el badge 🔴)."""
    inv = os.environ.get("INVENTORY_DIR", str(Path(__file__).parent / "inventory"))
    lj = Path(inv) / slug / "listing.json"
    try:
        data = json.loads(lj.read_text())
    except Exception:
        return
    data["last_error"] = str(msg)[:300]
    lj.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def record_publish_success(slug: str) -> None:
    """Marca published=true + published_at en el listing.json (badge 🟢 del panel)."""
    inv = os.environ.get("INVENTORY_DIR", str(Path(__file__).parent / "inventory"))
    lj = Path(inv) / slug / "listing.json"
    try:
        data = json.loads(lj.read_text())
    except Exception:
        return
    data["published"] = True
    data["published_at"] = time.strftime("%Y-%m-%d %H:%M")
    data["last_error"] = None
    lj.write_text(json.dumps(data, indent=2, ensure_ascii=False))


async def publish_scanner_car(slug: str) -> None:
    """Lee inventario/<slug>/ y abre Chrome VISIBLE con el formulario lleno.
    Selecciona todos los grupos disponibles y publica automáticamente
    (a petición de Alejo, jul 21 2026 — ya no se detiene antes de Publicar).
    Si falla (sesión FB expirada, cambio de DOM), corre como subproceso
    desacoplado, así que nadie más se entera — por eso escribimos last_error
    en el listing.json para que el badge 🔴 del panel se dispare."""
    try:
        inv = os.environ.get("INVENTORY_DIR", str(Path(__file__).parent / "inventory"))
        folder = Path(inv) / slug
        car = json.loads((folder / "listing.json").read_text())
        fields = scanner_car_fields(car)
        photos_dir = folder / "photos"
        photo_paths = [str(p) for p in sorted(photos_dir.glob("*.jpg"))] if photos_dir.exists() else []
        video_file = folder / "video.mp4"
        video_path = str(video_file) if video_file.exists() else None

        async with async_playwright() as p:
            ctx, cerrar = await open_session_context(p)
            page = await session_page(ctx)
            print(f"\n  📦 {fields['year']} {fields['make']} {fields['model']} — "
                  f"{fields['mileage']} mi — ${fields['price']}")
            ok = await post_scanner_car(page, fields, photo_paths, video_path)
            if ok:
                record_publish_success(slug)
            else:
                record_publish_error(slug, "no se encontró el formulario o el botón Publicar")
            await cerrar()
    except Exception as e:
        record_publish_error(slug, str(e))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--scanner":
        asyncio.run(publish_scanner_car(sys.argv[2]))
    else:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
        asyncio.run(main(limit=limit))
