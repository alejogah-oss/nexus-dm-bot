"""Guarda y carga sesión de Facebook para Playwright usando contexto persistente."""
import json
from pathlib import Path
from playwright.sync_api import BrowserContext, sync_playwright

COOKIES_PATH   = Path.home() / ".fb_cookies.json"
USER_DATA_DIR  = Path.home() / ".fb_playwright_profile"   # contexto persistente completo
MP_SESSION     = Path(__file__).parent / "browser_session/mp_session.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
# --password-store=gnome-libsecret bypasses macOS Keychain so cookies
# are readable from the persistent profile in headless mode
KEYCHAIN_BYPASS = ["--password-store=gnome-libsecret",
                   "--disable-blink-features=AutomationControlled"]


def save_cookies(context: BrowserContext):
    cookies = context.cookies(["https://www.messenger.com", "https://www.facebook.com"])
    valid = [c for c in cookies if c.get("value")]
    COOKIES_PATH.write_text(json.dumps(valid, indent=2))
    print(f"  ✅ {len(valid)} cookies guardadas en {COOKIES_PATH}")


def load_cookies(context: BrowserContext) -> bool:
    if not COOKIES_PATH.exists():
        return False
    cookies = json.loads(COOKIES_PATH.read_text())
    context.add_cookies(cookies)
    print(f"  ✅ Sesión cargada ({len(cookies)} cookies)")
    return True


def refresh_mp_session():
    """
    Extrae cookies ya desencriptadas del perfil persistente y las guarda
    en browser_session/mp_session.json para que marketplace_inbox_bot las use.
    Funciona sin abrir ventana visible y sin necesitar el macOS Keychain.
    """
    print("\n🔄 Extrayendo cookies del perfil guardado...")
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MP_SESSION.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"] + KEYCHAIN_BYPASS,
            ignore_default_args=["--enable-automation"],
            user_agent=UA,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.goto("https://www.messenger.com/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        url = page.url
        if "login" in url:
            print("  ❌ Sesión expirada — necesitas hacer login con login_and_save()")
            ctx.close()
            return False

        page.goto("https://www.messenger.com/marketplace/", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1500)

        cookies = ctx.cookies(["https://www.messenger.com", "https://www.facebook.com"])
        valid = [c for c in cookies if c.get("value")]
        MP_SESSION.write_text(json.dumps(valid, indent=2))
        ctx.close()

    print(f"  ✅ {len(valid)} cookies guardadas en {MP_SESSION}")
    return True


def login_and_save():
    """Abre un browser visible para login manual. Guarda sesión completa."""
    print("\n🔐 Abriendo Facebook para login manual...")
    print(f"   Perfil guardado en: {USER_DATA_DIR}")
    print("   Inicia sesión. Espera a que cargue el inbox de Messenger, luego ENTER.\n")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            slow_mo=100,
            user_agent=UA,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = ctx.new_page()
        page.goto("https://www.messenger.com/")
        input("   [Presiona ENTER cuando veas el inbox de Messenger cargado] ")
        save_cookies(ctx)
        ctx.close()

    # También extraer al mp_session.json
    print("\n  Extrayendo cookies para marketplace_inbox_bot...")
    refresh_mp_session()
    print("  ✅ Listo.")


def create_context(playwright):
    """Retorna un contexto persistente con la sesión guardada."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ctx = playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        slow_mo=200,
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    # Si hay cookies guardadas y el perfil está vacío, las restauramos
    if COOKIES_PATH.exists():
        try:
            cookies = json.loads(COOKIES_PATH.read_text())
            ctx.add_cookies(cookies)
        except Exception:
            pass
    return ctx


def session_exists() -> bool:
    return COOKIES_PATH.exists() or USER_DATA_DIR.exists()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        refresh_mp_session()
    else:
        login_and_save()
