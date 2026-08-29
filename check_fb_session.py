"""¿La sesión de Facebook del poster está viva?

Abre Chrome igual que lo hace el botón Publicar del panel y carga el formulario
de Marketplace, sin publicar nada. Si Facebook pide login, esperá y entrá a mano
en esa ventana: queda guardado en el perfil y el botón Publicar ya no lo pide.

Uso:  venv/bin/python3 check_fb_session.py
"""
import asyncio
from playwright.async_api import async_playwright

from marketplace_poster import (open_session_context, session_page,
                                hay_muro_de_login, ensure_logged_in,
                                session_profile, load_session_cookies)


async def main():
    perfil = session_profile()
    print(f"\n  perfil: {perfil or 'ninguno'}")
    print(f"  cookies en fb_session.json: {len(load_session_cookies())}")

    async with async_playwright() as p:
        ctx, cerrar = await open_session_context(p)
        page = await session_page(ctx)
        await page.goto("https://www.facebook.com/marketplace/create/vehicle",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        if not await hay_muro_de_login(page):
            print(f"\n  ✅ Sesión viva — {page.url}")
        else:
            print("\n  ❌ Facebook pidió login.")
            try:
                await ensure_logged_in(page)
                print("  ✅ Listo — el login quedó guardado en el perfil.")
            except RuntimeError as e:
                print(f"  ⚠️  {e}")
        await asyncio.sleep(3)
        await cerrar()


asyncio.run(main())
