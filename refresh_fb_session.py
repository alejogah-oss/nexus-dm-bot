"""
Refresca la sesión de Facebook para el Marketplace Updater.
Abre el browser — inicia sesión con tucarroconalejo@gmail.com
El script detecta el login automáticamente, no hay que presionar nada.

Uso: venv/bin/python3 refresh_fb_session.py
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

USER_DATA_DIR = str(Path.home() / ".fb_playwright_profile_poster")
SESSION_FILE  = Path("browser_session/fb_session.json")


async def main():
    print("\n🔐 Abriendo Facebook — inicia sesión con tucarroconalejo@gmail.com")
    print("   El script detecta el login solo, no necesitas presionar nada.\n")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            slow_mo=100,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

        print("   Esperando que inicies sesión (hasta 5 minutos)...")

        # Esperar hasta detectar la cookie c_user (= sesión activa)
        for i in range(300):
            await asyncio.sleep(1)
            cookies = await ctx.cookies()
            names = {c["name"] for c in cookies}
            if "c_user" in names and "xs" in names:
                fb_cookies = [c for c in cookies if "facebook" in c.get("domain", "")]
                print(f"   ✅ Login detectado — {len(fb_cookies)} cookies guardadas")
                break
            if i % 20 == 0 and i > 0:
                print(f"   ... esperando ({i}s)")
        else:
            print("   ❌ No se detectó login en 5 minutos. Cierra e intenta de nuevo.")
            await ctx.close()
            return

        # Navegar a marketplace para asegurar cookies de esa sección
        await page.goto("https://www.facebook.com/marketplace/you/selling",
                        wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Guardar storage state (cookies + localStorage) en fb_session.json
        SESSION_FILE.parent.mkdir(exist_ok=True)
        await ctx.storage_state(path=str(SESSION_FILE))
        print(f"   💾 Sesión guardada en {SESSION_FILE}")

        await ctx.close()

    print("\n✅ Sesión lista. Corriendo el updater...\n")


asyncio.run(main())
