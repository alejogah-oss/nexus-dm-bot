"""
Ejecutar en Terminal:
  cd /Users/macbookpro/nexus-automation && venv/bin/python3 refresh_mp_session.py

Abre un browser. Inicia sesión con tucarroconalejo@gmail.com.
Cuando el script diga "Sesión lista", el bot empieza automáticamente en el mismo browser.
"""
import asyncio, json, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_FILE = Path("browser_session/mp_session.json")
PROFILE_DIR  = Path.home() / ".fb_playwright_profile"
STATE_FILE   = Path("marketplace_inbox_state.json")
LOCAL_ARGS   = ["--no-sandbox", "--disable-blink-features=AutomationControlled",
                "--no-first-run", "--no-default-browser-check"]

POLL_SEC = 60


async def main():
    # Importar el bot aquí para que corra en el mismo proceso
    sys.path.insert(0, str(Path(__file__).parent))
    from marketplace_inbox_bot import check_inbox, _load_state, _save_state

    print("\n🔑 Abriendo Messenger — inicia sesión con tucarroconalejo@gmail.com")
    print("   El script espera hasta que estés completamente dentro.\n")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            args=LOCAL_ARGS,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.messenger.com/", wait_until="load")

        # Esperar login
        print("   Esperando login completo (buscando cookie c_user)...")
        for i in range(300):
            await asyncio.sleep(1)
            cookies = await ctx.cookies()
            names = {c["name"] for c in cookies}
            if "c_user" in names and "xs" in names:
                fb_cookies = [c for c in cookies if 'facebook' in c.get('domain', '')]
                print(f"   ✅ Login detectado — {len(fb_cookies)} cookies facebook.com")
                break
            if i % 15 == 0 and i > 0:
                print(f"   ... esperando ({i}s) — inicia sesión en el browser")
        else:
            print("   ❌ No se detectó login en 5 minutos.")
            await ctx.close()
            return

        # Guardar cookies al mp_session.json
        all_cookies = await ctx.cookies(["https://www.facebook.com", "https://www.messenger.com"])
        COOKIES_FILE.parent.mkdir(exist_ok=True)
        COOKIES_FILE.write_text(json.dumps(all_cookies, indent=2))
        c_user = next((c for c in all_cookies if c["name"] == "c_user"), None)
        print(f"   💾 {len(all_cookies)} cookies guardadas — c_user: {c_user['value'][:10] if c_user else 'FALTA'}")

        print("\n✅ Sesión lista — el bot arranca AHORA en este mismo browser.")
        print("   Puedes minimizar el browser. Ctrl+C para detener.\n")

        # Activar LOCAL_MODE en el módulo ya importado para que check_inbox
        # vaya directo a messenger.com/marketplace/ (el perfil sí puede acceder)
        import marketplace_inbox_bot as _mib
        _mib.LOCAL_MODE = True

        # Arrancar el bot en el mismo contexto (sesión nunca expira)
        state = _load_state()
        cycle = 0
        while True:
            cycle += 1
            print(f"\n[MIB] === CICLO {cycle} === {time.strftime('%H:%M:%S')}", flush=True)
            try:
                await check_inbox(page, state, quick=False)
                _save_state(state)
            except Exception as e:
                print(f"[MIB] Ciclo {cycle} error: {e}", flush=True)
                try:
                    page = await ctx.new_page()
                except Exception:
                    print("[MIB] No se pudo abrir nueva página — reinicia el script", flush=True)
                    break
            print(f"[MIB] Durmiendo {POLL_SEC}s...", flush=True)
            await asyncio.sleep(POLL_SEC)


asyncio.run(main())
