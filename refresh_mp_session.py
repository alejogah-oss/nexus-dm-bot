"""
Ejecutar en Terminal:
  cd /Users/macbookpro/nexus-automation && venv/bin/python3 refresh_mp_session.py
"""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_FILE = Path("browser_session/mp_session.json")
PROFILE_DIR  = Path.home() / ".fb_playwright_profile"

async def main():
    print("\n🔑 Abriendo Messenger — inicia sesión con tucarroconalejo@gmail.com")
    print("   El script espera hasta que estés completamente dentro.\n")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.messenger.com/", wait_until="load")

        print("   Esperando login completo (buscando cookie c_user)...")
        for i in range(300):  # hasta 5 minutos
            await asyncio.sleep(1)
            cookies = await ctx.cookies()
            names = {c["name"] for c in cookies}
            # c_user + xs = sesión real de Facebook
            if "c_user" in names and "xs" in names:
                fb_cookies = [c for c in cookies if 'facebook' in c.get('domain','')]
                print(f"   ✅ Login detectado — {len(fb_cookies)} cookies facebook.com")
                break
            if i % 15 == 0 and i > 0:
                print(f"   ... esperando ({i}s) — inicia sesión en el browser")
        else:
            print("   ❌ No se detectó login en 5 minutos.")
            await ctx.close()
            return

        # Esperar que el usuario navegue manualmente a marketplace
        print("   ✅ Login detectado. Ahora navega en el browser a:")
        print("      messenger.com/marketplace")
        print("   El script esperará hasta que esa página cargue...")
        for attempt in range(120):  # hasta 4 minutos esperando
            await asyncio.sleep(2)
            current_url = page.url
            if "marketplace" in current_url and "login" not in current_url:
                print(f"   ✅ Marketplace cargado: {current_url[:80]}")
                break
            if attempt % 10 == 0 and attempt > 0:
                print(f"   ... esperando que navegues a marketplace ({attempt*2}s) — URL actual: {current_url[:60]}")
        else:
            print("   ❌ No se detectó marketplace en 4 minutos.")
            await ctx.close()
            return

        # Guardar solo cookies de facebook.com y messenger.com
        all_cookies = await ctx.cookies(["https://www.facebook.com", "https://www.messenger.com"])
        COOKIES_FILE.parent.mkdir(exist_ok=True)
        COOKIES_FILE.write_text(json.dumps(all_cookies, indent=2))
        c_user = next((c for c in all_cookies if c["name"] == "c_user"), None)
        print(f"   💾 {len(all_cookies)} cookies guardadas — c_user: {c_user['value'][:10] if c_user else 'FALTA'}")
        await ctx.close()

    print("\n✅ Sesión guardada. Reinicia el bot:\n")
    print("   launchctl unload ~/Library/LaunchAgents/com.nexus.marketplace.bot.plist")
    print("   launchctl load  ~/Library/LaunchAgents/com.nexus.marketplace.bot.plist\n")

asyncio.run(main())
