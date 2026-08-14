"""
NEXUS Marketplace Updater — Actualiza descripciones de listings existentes via Playwright.
Mismo patrón que marketplace_poster.py — sesión guardada, corre solo, headless=False.

Uso:
  python3 marketplace_updater.py           # actualiza los próximos 5
  python3 marketplace_updater.py 10        # actualiza los próximos N
  python3 marketplace_updater.py --status  # muestra progreso sin abrir browser
  python3 marketplace_updater.py --dry     # genera descripciones sin abrir browser
"""

import asyncio
import json
import os
import sys
import random
import anthropic
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

PRICE_OPTIONS = [1000, 2000, 3000]

load_dotenv()

SESSION_FILE = Path(__file__).parent / "browser_session/fb_session.json"
POSTED_LOG   = Path(__file__).parent / "marketplace_posted.json"
UPDATE_LOG   = Path(__file__).parent / "marketplace_update_log.json"
DEFAULT_BATCH = 10

_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_INK_UPDATER = """Eres Ink, copywriter de NEXUS para @tucarroconalejo.
Escribe la descripción de un listing de Facebook Marketplace para este vehículo Toyota.
Tono: vendedor individual, cálido y directo — como Alejo hablando a un amigo, no un dealer corporativo.

PRINCIPIOS DE PSIQUE:
- Emoción PRIMERO, datos después
- El precio se presenta como acceso, nunca como advertencia
- Crédito en construcción amplía audiencia sin prometer nada

FORMATO — reglas absolutas:
- Empieza DIRECTO con el gancho, sin títulos ni etiquetas
- PROHIBIDO: #, *, **, guiones al inicio de línea, markdown de cualquier tipo
- Solo texto limpio, párrafos separados por salto de línea
- Máximo 1 emoji en todo el texto

ESTRUCTURA:
Párrafo 1: Gancho emocional — haz imaginar manejarlo (1-2 oraciones)
Párrafo 2: 2-3 beneficios reales en términos de vida del comprador, no specs técnicos
Párrafo 3: "💳 Precio mostrado = enganche estimado. Financiamiento disponible — crédito en construcción también aplica. Llama al (954) 910-6671 — soy Alejo, te atiendo personalmente."
Párrafo 4: "Estoy en Hollywood, Florida. Escríbeme aquí o agenda tu cita."

LÍMITE: 150 palabras máximo."""

_TRIM_FEATURES = {
    "TRD Off-Road": "suspensión off-road, diferencial trasero bloqueado, modos Multi-Terrain Select",
    "TRD Sport":    "amortiguadores TRD, sport bar, llantas exclusivas TRD",
    "TRD Pro":      "suspensión Fox, skid plates, diferencial trasero bloqueado",
    "Trailhunter":  "suspensión elevada, llantas all-terrain, plataforma off-road lista",
    "Limited":      "cuero premium, sunroof panorámico, JBL audio, llantas 20\"",
    "Platinum":     "cuero premium, sunroof, JBL audio, head-up display, asientos ventilados",
    "1794 Edition": "cuero premium, madera real, llantas 20\", asientos ventilados",
    "SR5":          "ruedas de aleación, Apple CarPlay, Android Auto, Toyota Safety Sense",
    "SR":           "pantalla táctil 8\", cámara de reversa, Toyota Safety Sense 2.0",
    "XSE":          "diseño sport, techo solar, llantas 18\", interior sport",
    "XLE":          "cuero, sunroof, calefacción de asientos, Apple CarPlay",
    "LE":           "Apple CarPlay, Android Auto, cámara trasera, Toyota Safety Sense",
    "Woodland":     "tracción AWD, suspensión elevada, llantas all-terrain",
    "Hybrid":       "motor híbrido, ahorro de combustible excepcional",
    "Plug-in Hybrid": "motor plug-in híbrido, modo eléctrico disponible",
    "3.0 Premium":  "motor inline-6 turbo, tracción trasera, diseño deportivo puro",
}


# ── Helpers de datos ────────────────────────────────────────────────────────

def load_posted() -> dict:
    try:
        return json.loads(POSTED_LOG.read_text())
    except Exception:
        return {}

def load_update_log() -> dict:
    try:
        return json.loads(UPDATE_LOG.read_text())
    except Exception:
        return {"updated": [], "last_run": None}

def save_update_log(log: dict):
    UPDATE_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False))

def parse_vehicle(key: str, data: dict) -> dict:
    parts = key.split("|", 2)
    yr    = parts[0] if len(parts) > 0 else "2026"
    model = parts[1] if len(parts) > 1 else ""
    trim  = parts[2] if len(parts) > 2 else ""
    title = data.get("title", "")
    color = title.split(" — ", 1)[1].strip() if " — " in title else ""
    return {"yr": yr, "model": model, "trim": trim, "color": color,
            "down": data.get("down", 0), "title": title, "key": key}

def get_features(trim: str) -> str:
    for key, feat in _TRIM_FEATURES.items():
        if key.lower() in trim.lower():
            return feat
    return "Apple CarPlay, Android Auto, Toyota Safety Sense, cámara de reversa"

def generate_description(v: dict) -> str:
    features = get_features(v["trim"])
    prompt = (
        f"Vehículo: {v['yr']} Toyota {v['model']} {v['trim']}\n"
        f"Color: {v['color']}\n"
        f"Down payment desde: ${v['down']:,}\n"
        f"Features: {features}\n"
        f"Condición: Nuevo — 0 km de fábrica"
    )
    resp = _claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=350,
        system=_INK_UPDATER,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()

def pick_pending(posted: dict, update_log: dict, batch: int) -> list:
    updated = set(update_log.get("updated", []))
    pending = []
    for key, data in posted.items():
        if key not in updated:
            pending.append(parse_vehicle(key, data))
        if len(pending) >= batch:
            break
    return pending

def show_status(posted: dict, update_log: dict):
    updated = set(update_log.get("updated", []))
    total, done = len(posted), len(updated)
    print(f"\n── Updater Status ({done}/{total} actualizados) ──────────────────")
    for key, data in posted.items():
        icon = "✅" if key in updated else "  "
        print(f"  {icon} {data.get('title', key)[:70]}")
    print(f"\n  Pendientes: {total - done}")
    print("──────────────────────────────────────────────\n")


# ── Playwright ──────────────────────────────────────────────────────────────

async def scroll_load_all_listings(page) -> list[str]:
    """Hace scroll en la página de seller para cargar todos los listings.
    Retorna lista deduplicada de aria-labels tipo 'More options for [nombre]'."""
    known: set[str] = set()
    prev_count = 0
    for _ in range(25):
        labels: list[str] = await page.evaluate('''() => {
            const els = document.querySelectorAll("[aria-label]");
            return [...els]
                .map(e => e.getAttribute("aria-label"))
                .filter(a => a && a.startsWith("More options for"));
        }''')
        for lbl in labels:
            known.add(lbl)
        if len(known) == prev_count:
            break
        prev_count = len(known)
        await page.keyboard.press("End")
        await asyncio.sleep(2)
    return list(known)


async def edit_one_listing(page, aria_label: str, new_desc: str, price: int = 0) -> bool:
    """Abre el menú ··· del listing y actualiza la descripción."""
    safe = aria_label.replace(" ", "_")[:50]

    # Clic en el ··· del listing — scroll para hacerlo visible si está fuera del viewport
    try:
        btn = page.locator(f'[aria-label="{aria_label}"]').first
        await btn.scroll_into_view_if_needed(timeout=5000)
        await asyncio.sleep(0.5)
        await btn.click()
        await asyncio.sleep(1.5)
    except Exception as e:
        print(f"    ⚠️  Click ···: {e}")
        return False

    # Clic en "Edit listing" del menú
    clicked = False
    for txt in ["Edit listing", "Editar anuncio", "Edit", "Editar"]:
        try:
            opt = page.get_by_role("menuitem", name=txt).first
            if await opt.is_visible(timeout=2000):
                await opt.click()
                await asyncio.sleep(4)
                clicked = True
                break
        except Exception:
            pass
    if not clicked:
        print(f"    ⚠️  'Edit listing' no encontrado en menú")
        await page.keyboard.press("Escape")
        return False

    print(f"    ✏️  Formulario abierto")

    # Actualizar el precio si se especificó
    if price:
        for price_label in ["Price", "Precio"]:
            try:
                pf = page.get_by_label(price_label).first
                if await pf.is_visible(timeout=3000):
                    await pf.click()
                    await page.keyboard.press("Control+a")
                    await pf.fill(str(price))
                    await asyncio.sleep(0.5)
                    print(f"    💰 Precio → ${price:,}")
                    break
            except Exception:
                pass

    # Actualizar el campo Description
    updated = False
    for label in ["Description", "Descripción"]:
        try:
            field = page.get_by_label(label).first
            if await field.is_visible(timeout=3000):
                await field.click()
                await asyncio.sleep(0.5)
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.3)
                await field.fill(new_desc)
                await asyncio.sleep(1)
                updated = True
                print(f"    ✅ Descripción actualizada")
                break
        except Exception:
            pass

    if not updated:
        try:
            ta = page.locator("textarea").first
            if await ta.is_visible(timeout=2000):
                await ta.click()
                await page.keyboard.press("Control+a")
                await ta.fill(new_desc)
                await asyncio.sleep(1)
                updated = True
                print(f"    ✅ Descripción actualizada (textarea)")
        except Exception:
            pass

    if not updated:
        print(f"    ⚠️  Campo Description no encontrado")
        await page.screenshot(path=f"/tmp/mp_nodesc_{safe}.png")
        return False

    # Guardar — el formulario de edición usa "Update" (no Next + Publish)
    for save_txt in ["Update", "Save", "Guardar", "Publish", "Publicar", "Save changes", "Guardar cambios"]:
        try:
            btn = page.get_by_role("button", name=save_txt).first
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                await asyncio.sleep(5)
                print(f"    ✅ ¡Guardado con '{save_txt}'!")
                return True
        except Exception:
            pass

    print(f"    ⚠️  Botón Update/Save no encontrado")
    await page.screenshot(path=f"/tmp/mp_nosave_{safe}.png")
    return False


BATCH_PAUSE = 120  # segundos entre grupos de 10


def match_posted_entry(label_name: str, posted: dict) -> dict | None:
    """Busca la entrada en posted.json más cercana al nombre del listing en Facebook."""
    name_lower = label_name.lower()
    for key, data in posted.items():
        parts = key.split("|")
        model = parts[1].lower() if len(parts) > 1 else ""
        if model and model in name_lower:
            return parse_vehicle(key, data)
    return None


def pick_price() -> int:
    return random.choice(PRICE_OPTIONS)


def build_desc_for_label(name: str, posted: dict, price: int) -> str:
    """Genera descripción vía Claude para el nombre del listing, con el precio dado."""
    v = match_posted_entry(name, posted)
    if v:
        v["down"] = price
        return generate_description(v)
    return (
        f"Imagínate manejando este {name} nuevo, cero kilómetros, directo de fábrica.\n\n"
        f"Comodidad, tecnología y la confiabilidad que solo Toyota te da.\n\n"
        f"💳 ${price:,} = enganche estimado. Financiamiento disponible "
        f"— crédito en construcción también aplica. "
        f"Llama al (954) 910-6671 — soy Alejo, te atiendo personalmente.\n\n"
        f"Estoy en Hollywood, Florida. Escríbeme aquí o agenda tu cita."
    )


async def goto_selling(page):
    await page.goto("https://www.facebook.com/marketplace/you/selling",
                    wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)
    # Scroll rápido para que Facebook cargue todos los listings en el DOM
    for _ in range(8):
        await page.keyboard.press("End")
        await asyncio.sleep(0.8)
    await page.keyboard.press("Home")
    await asyncio.sleep(0.5)


async def run_all(posted: dict, update_log: dict, batch_size: int, dry_run: bool = False):
    """Detecta listings activos, pre-genera descripciones, luego edita en grupos."""

    print(f"\n── NEXUS Marketplace Updater ───────────────────")
    print("  📋 Detectando listings (abriendo browser)...")

    user_data_dir = str(Path.home() / ".fb_playwright_profile")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            slow_mo=300,
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

        await goto_selling(page)
        print("  🔄 Cargando todos los listings...")
        aria_labels = await scroll_load_all_listings(page)

        already_updated = set(update_log.get("updated", []))
        pending_labels  = [l for l in aria_labels if l not in already_updated]
        print(f"  ✅ {len(aria_labels)} en página | {len(pending_labels)} pendientes\n")

        if not pending_labels:
            print("  ✅ Todos actualizados.")
            await ctx.close()
            return

        # Pre-generar TODAS las descripciones y asignar precios aleatorios
        print("  ✍️  Generando descripciones con Claude (sin tocar el browser)...")
        desc_map: dict[str, str] = {}
        price_map: dict[str, int] = {}
        for lbl in pending_labels:
            name = lbl.replace("More options for ", "")
            price = pick_price()
            price_map[lbl] = price
            desc_map[lbl] = build_desc_for_label(name, posted, price)
            print(f"    ✓ {name[:55]}  → ${price:,}")
        print(f"  ✅ {len(desc_map)} descripciones listas\n")

        if dry_run:
            print("[DRY RUN — no se edita nada]")
            await ctx.close()
            return

        total_ok  = 0
        total_pnd = len(pending_labels)
        total_batches = (total_pnd + batch_size - 1) // batch_size

        for batch_num, start in enumerate(range(0, total_pnd, batch_size), 1):
            batch_labels = pending_labels[start : start + batch_size]

            print(f"\n{'─'*55}")
            print(f"  Grupo {batch_num}/{total_batches}")

            # Volver a la página de seller al inicio de cada batch
            await goto_selling(page)
            await asyncio.sleep(1)

            batch_ok = 0
            for aria_label in batch_labels:
                name = aria_label.replace("More options for ", "")
                print(f"\n  🚗 {name}")
                try:
                    ok = await edit_one_listing(page, aria_label, desc_map[aria_label], price_map[aria_label])
                    if ok:
                        batch_ok += 1
                        total_ok += 1
                        update_log["updated"].append(aria_label)
                        update_log["last_run"] = datetime.now().isoformat()
                        save_update_log(update_log)
                    # Volver a selling page para el próximo listing del mismo grupo
                    await goto_selling(page)
                except Exception as e:
                    print(f"    ❌ Error: {e}")
                    await goto_selling(page)

            print(f"\n  ✅ Grupo {batch_num} completo: {batch_ok}/{len(batch_labels)}")
            print(f"  Total acumulado: {total_ok}/{total_pnd}")

            if start + batch_size < total_pnd:
                print(f"\n  ⏳ Pausa {BATCH_PAUSE}s antes del siguiente grupo...")
                await asyncio.sleep(BATCH_PAUSE)

        print(f"\n{'═'*55}")
        print(f"  ✅ Corrida completa: {total_ok}/{total_pnd} actualizados")
        await asyncio.sleep(5)
        await ctx.close()


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    dry    = "--dry"    in sys.argv
    status = "--status" in sys.argv
    batch  = DEFAULT_BATCH
    for arg in sys.argv[1:]:
        if arg.isdigit():
            batch = int(arg)

    posted     = load_posted()
    update_log = load_update_log()

    if status:
        show_status(posted, update_log)
        return

    asyncio.run(run_all(posted, update_log, batch_size=batch, dry_run=dry))


if __name__ == "__main__":
    main()
