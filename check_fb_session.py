"""¿La sesión de Facebook del poster está viva?

Abre Chrome igual que lo hace el botón Publicar del panel y carga el formulario
de Marketplace, sin publicar nada. Sirve para saber si hay que renovar la sesión
antes de darle Publicar a un carro.

Uso:  venv/bin/python3 check_fb_session.py
"""
import asyncio
from playwright.async_api import async_playwright

from marketplace_poster import (open_session_context, session_page,
                                assert_logged_in, session_profile,
                                load_session_cookies)


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
        try:
            await assert_logged_in(page)
            print(f"\n  ✅ Sesión viva — {page.url}")
        except RuntimeError as e:
            print(f"\n  ❌ {e}")
        await asyncio.sleep(3)
        await cerrar()


asyncio.run(main())
