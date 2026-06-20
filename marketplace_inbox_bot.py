"""
NEXUS — Marketplace Inbox Bot
Monitorea el inbox de Marketplace del perfil personal (tucarroconalejo@gmail.com)
y responde con la misma IA de dm_bot. Corre en loop localmente.

Uso:
    venv/bin/python3 marketplace_inbox_bot.py
"""
import asyncio
import base64
import json
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

from dm_bot import _claude_create, _marketplace_voice, push_hot_lead, log_event
from marketplace_analytics import track_message, track_hot_lead, track_declined
from pulse import pulse_notify
from appointments import extract_appointment_from_conversation

load_dotenv()

USER_DATA_DIR  = Path.home() / ".fb_playwright_profile"
COOKIES_FILE   = Path(__file__).parent / "browser_session/mp_session.json"
STATE_FILE     = Path(__file__).parent / "marketplace_inbox_state.json"
# En Render no hay perfil persistente — usamos cookies exportadas
USE_COOKIES    = not USER_DATA_DIR.exists()
POLL_SEC       = 60   # intervalo normal
POLL_ACTIVE    = 10   # intervalo cuando hay conversación activa
ACTIVE_WINDOW  = 60   # segundos en modo activo tras responder

_active_until: float = 0.0   # timestamp hasta cuando está en modo activo
MAX_THREADS  = 15        # máximo de threads a revisar por ciclo

# Historial de conversaciones en memoria {thread_id: [messages]}
_conversations: dict[str, list] = {}


# ── Estado persistente ────────────────────────────────────────────────────────

def _load_state() -> dict:
    """Carga {thread_id: last_msg_hash} para no reprocesar mensajes."""
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Helpers de browser ────────────────────────────────────────────────────────

async def _type_and_send(page: Page, text: str):
    """Escribe un mensaje en el cuadro activo y lo envía."""
    box = page.locator('[contenteditable="true"][role="textbox"]').first
    await box.click(force=True)
    await page.wait_for_timeout(400)
    await box.press("Control+a")
    await box.press("Delete")
    await box.type(text, delay=30)
    await page.wait_for_timeout(400)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(1500)


async def _dismiss_pin_modal(page: Page):
    """Cierra el modal de PIN y el modal de confirmación 'Continue without restoring'."""
    try:
        close = page.locator('[aria-label="Close"]').first
        if await close.count() > 0:
            await close.click(force=True)
            await page.wait_for_timeout(800)
    except Exception:
        pass
    try:
        no_restore = page.locator('button:has-text("Don\'t restore messages")')
        if await no_restore.count() > 0:
            await no_restore.click()
            await page.wait_for_timeout(800)
    except Exception:
        pass


async def _extract_messages(page: Page) -> list[dict]:
    """
    Extrae el historial de mensajes del thread abierto en messenger.com.
    Usa aria-label="Message sent TIME by NAME: TEXT" para parsear con precisión.
    """
    messages = []
    try:
        await page.wait_for_timeout(2000)
        await _dismiss_pin_modal(page)
        await page.wait_for_timeout(800)

        els = await page.locator('[aria-label*=" sent "]').all()

        for el in els:
            try:
                label = await el.get_attribute("aria-label") or ""
                # Formato: "Enter, Message sent TIME by NAME: TEXT"
                # o simplemente "Message sent TIME by NAME: TEXT"
                if " sent " not in label:
                    continue

                # Extraer nombre y texto
                # "... by NAME: TEXT" o "... by NAME"
                by_part = label.split(" by ", 1)[-1]  # "NAME: TEXT" o "NAME"
                if ": " in by_part:
                    sender, text = by_part.split(": ", 1)
                else:
                    sender = by_part.strip()
                    text = (await el.inner_text()).strip()

                text = text.strip()
                if not text or len(text) < 1:
                    continue

                # Ignorar mensajes de sistema
                if any(skip in text.lower() for skip in [
                    "started this chat", "to help identify", "reduce scams",
                    "is waiting for your response", "end-to-end"
                ]):
                    continue

                # "You" = nosotros; cualquier otro nombre = cliente
                is_ours = sender.strip().lower() in ["you", "alejandro garcia"]
                role = "assistant" if is_ours else "user"

                if messages and messages[-1]["role"] == role:
                    messages[-1]["content"] += f"\n{text}"
                else:
                    messages.append({"role": role, "content": text})

            except Exception:
                continue

    except Exception as e:
        print(f"  [BOT] Error leyendo mensajes: {e}")

    return messages


async def _get_car_context(page: Page) -> dict | None:
    """
    Intenta extraer el contexto del vehículo desde el header del thread de Marketplace.
    Devuelve un dict básico si lo encuentra, None si no.
    """
    try:
        header = await page.locator('[data-testid="messenger-header"] span').all_inner_texts()
        header_text = " ".join(header)
        # Busca patrón "2026 Toyota RAV4" en el header
        import re
        m = re.search(r"(\d{4})\s+Toyota\s+([\w\s]+?)(?:\s*[-·|]|$)", header_text)
        if m:
            return {
                "yr": int(m.group(1)),
                "model": m.group(2).strip(),
                "trim": "",
                "color": "",
                "down_payment": 0,
                "vin": "",
            }
    except Exception:
        pass
    return None


# ── Procesamiento de thread ───────────────────────────────────────────────────

async def process_thread(page: Page, state: dict, thread_url: str, sender_name: str):
    """Abre un thread, lee mensajes y responde si hay uno nuevo sin responder."""

    thread_id = thread_url.split("/t/")[-1].split("/")[0].split("?")[0]

    print(f"  [BOT] Revisando: {sender_name} ({thread_id})")

    try:
        await page.goto(f"https://www.facebook.com/messages/t/{thread_id}",
                        wait_until="load", timeout=25000)
        await page.wait_for_timeout(2500)
    except Exception as e:
        print(f"  [BOT] Error cargando thread: {e}")
        return

    messages = await _extract_messages(page)

    if not messages:
        print(f"  [BOT] Sin mensajes legibles en {thread_id}")
        return

    # Solo responde si el último mensaje es del cliente
    if messages[-1]["role"] != "user":
        return

    last_msg = messages[-1]["content"]
    msg_hash = hash(last_msg.strip())

    if state.get(thread_id) == msg_hash:
        return  # Ya respondimos a este mensaje

    print(f"  [BOT] Nuevo mensaje de {sender_name}: \"{last_msg[:70]}\"")

    # Obtener contexto del carro desde el nombre del thread (ej: "Benito · 2026 Toyota rav4 plug-in hybrid")
    car = await _get_car_context(page)
    # Fallback: parsear desde sender_name si header falla
    if not car:
        import re
        m = re.search(r"(\d{4})\s+Toyota\s+([\w\s\-]+)", sender_name)
        if m:
            car = {"yr": int(m.group(1)), "model": m.group(2).strip(),
                   "trim": "", "color": "", "down_payment": 0, "vin": ""}

    history = _conversations.get(thread_id, messages[:-1])

    # Intro en primer contacto (igual que handle_marketplace_message en dm_bot)
    if not history and car:
        intro = (
            f"¡Hola! Vi que te interesa el {car['yr']} Toyota {car['model']} "
            f"{car.get('trim', '')} 🙌 "
            f"Es un carro increíble — ¿cuándo puedes venir a verlo en persona? "
            f"Estamos en Hollywood Toyota, 2200 N State Rd 7."
        ).strip()
        try:
            await _type_and_send(page, intro)
            history = [{"role": "assistant", "content": intro}]
        except Exception:
            pass

    # Generar respuesta
    system = _marketplace_voice(car) if car else _marketplace_voice(
        {"yr": "2026", "model": "Toyota", "trim": "", "color": "", "down_payment": 0, "vin": ""}
    )
    try:
        raw_reply = _claude_create(
            "claude-sonnet-4-6", 200, system,
            history + [{"role": "user", "content": last_msg}]
        )
    except Exception as e:
        print(f"  [BOT] Error generando respuesta: {e}")
        return

    is_hot      = "[HOT LEAD]" in raw_reply
    is_declined = "[SHOWROOM_DECLINED]" in raw_reply
    reply       = raw_reply.replace("[HOT LEAD]", "").replace("[SHOWROOM_DECLINED]", "").strip()

    # Enviar respuesta
    try:
        await _type_and_send(page, reply)
        print(f"  [BOT] ✅ Respondido a {sender_name}")
        # Activar modo rápido: revisar cada 10s durante 60s
        global _active_until
        _active_until = time.time() + ACTIVE_WINDOW
    except Exception as e:
        print(f"  [BOT] Error enviando respuesta: {e}")
        return

    # Actualizar historial (16 mensajes = 8 exchanges, igual que dm_bot)
    _conversations[thread_id] = (history + [
        {"role": "user",      "content": last_msg},
        {"role": "assistant", "content": reply},
    ])[-16:]

    state[thread_id] = msg_hash

    full_history = _conversations[thread_id]

    # HOT LEAD — igual que dm_bot.handle_marketplace_message
    if is_hot:
        print(f"  [BOT] 🔥 HOT LEAD — {sender_name}")
        try:
            push_hot_lead(thread_id, "marketplace_personal", full_history, car=car)
        except Exception as e:
            print(f"  [BOT] Error CRM HOT LEAD: {e}")
        log_event("HOT_LEAD", f"Marketplace personal | {sender_name} | {last_msg[:80]}", "marketplace")
        if car:
            track_hot_lead(car)
            extract_appointment_from_conversation(full_history, car, thread_id, "marketplace")

    # SHOWROOM_DECLINED — igual que dm_bot.handle_marketplace_message
    if is_declined:
        print(f"  [BOT] ❌ DECLINED — {sender_name}")
        try:
            push_hot_lead(thread_id, "marketplace_personal", full_history, car=car)
        except Exception as e:
            print(f"  [BOT] Error CRM DECLINED: {e}")
        pulse_notify(
            event="SHOWROOM_DECLINED",
            detail=f"Marketplace personal | {sender_name} | {car['yr']} Toyota {car['model'] if car else ''}"
        )
        log_event("SHOWROOM_DECLINED", f"Marketplace personal | {sender_name}", "marketplace")
        if car:
            track_declined(car)

    if car:
        track_message(car)


# ── Loop principal ────────────────────────────────────────────────────────────

async def _ensure_messenger_logged_in(page: Page):
    """Verifica login en facebook.com antes de navegar al inbox."""
    await page.goto("https://www.facebook.com/", wait_until="load", timeout=30000)
    await page.wait_for_timeout(3000)
    print(f"[BOT] FB URL: {page.url} | Título: {await page.title()}")

    # Si redirigió a login, las cookies no son válidas
    if "login" in page.url.lower():
        print("[BOT] ⚠️ Sesión expirada — cookies inválidas desde esta IP")
        return False

    print("[BOT] ✅ Sesión válida en facebook.com")
    return True


async def check_inbox(page: Page, state: dict):
    """Escanea el inbox de Marketplace en Messenger y procesa threads nuevos."""
    print(f"\n[BOT] Revisando inbox Marketplace — {time.strftime('%H:%M:%S')}")

    try:
        logged_in = await _ensure_messenger_logged_in(page)
        if not logged_in:
            print("[BOT] ❌ Sin sesión válida — saltando ciclo")
            return
        # Navegar al inbox via facebook.com (más estable que messenger.com desde IPs externas)
        await page.goto("https://www.facebook.com/messages/t/", wait_until="load", timeout=30000)
        await page.wait_for_timeout(5000)
        print(f"[BOT] URL actual: {page.url}")
        print(f"[BOT] Título: {await page.title()}")
    except Exception as e:
        print(f"[BOT] Error cargando inbox: {e}")
        return

    # Recolectar links de threads (facebook.com usa /messages/t/)
    try:
        links = await page.locator('a[href*="/messages/t/"]').all()
        print(f"[BOT] Links /messages/t/: {len(links)}")
        if not links:
            links = await page.locator('a[href*="/t/"]').all()
            print(f"[BOT] Links /t/ (fallback): {len(links)}")
    except Exception:
        print("[BOT] No se encontraron threads")
        return

    seen_ids = set()
    threads  = []

    for link in links[:MAX_THREADS]:
        try:
            href = await link.get_attribute("href")
            if not href or "/t/" not in href:
                continue

            thread_id = href.split("/t/")[-1].split("/")[0].split("?")[0]
            if thread_id in seen_ids:
                continue
            seen_ids.add(thread_id)

            # Nombre del remitente
            try:
                name = (await link.locator('[dir="auto"]').first.inner_text()).strip().split("\n")[0]
            except Exception:
                name = thread_id

            threads.append((href, name))
        except Exception:
            continue

    print(f"[BOT] {len(threads)} threads encontrados")

    for href, name in threads:
        await process_thread(page, state, href, name)
        # Volver al inbox entre threads
        try:
            await page.goto("https://www.facebook.com/messages/marketplace/",
                            wait_until="load", timeout=20000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass

    print(f"[BOT] Ciclo completo — próximo en {POLL_SEC}s")


async def run():
    state = _load_state()

    LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                   "--disable-blink-features=AutomationControlled"]
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    async with async_playwright() as p:
        if USE_COOKIES:
            # Render / sin perfil local — usa cookies desde env var o archivo
            browser = await p.chromium.launch(headless=True, args=LAUNCH_ARGS)
            ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
            raw_b64 = os.getenv("FB_COOKIES_B64", "")
            if raw_b64:
                cookies = json.loads(base64.b64decode(raw_b64).decode())
            else:
                cookies = json.loads(COOKIES_FILE.read_text())
            await ctx.add_cookies(cookies)
        else:
            # Mac local — perfil persistente completo
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                headless=True,
                args=LAUNCH_ARGS,
                ignore_default_args=["--enable-automation"],
                user_agent=UA,
                viewport={"width": 1280, "height": 900},
            )
        page = await ctx.new_page()

        print("=" * 50)
        print("  NEXUS — Marketplace Inbox Bot")
        print(f"  Cuenta: tucarroconalejo@gmail.com")
        print(f"  Intervalo: {POLL_SEC}s")
        print("=" * 50)

        while True:
            try:
                await check_inbox(page, state)
                _save_state(state)
            except Exception as e:
                print(f"[BOT] Error general: {e}")
                try:
                    await page.reload(timeout=15000)
                    await page.wait_for_timeout(5000)
                except Exception:
                    pass

            # Modo activo: 10s si hubo respuesta reciente, 60s si no
            sleep = POLL_ACTIVE if time.time() < _active_until else POLL_SEC
            if sleep == POLL_ACTIVE:
                print(f"[BOT] Modo activo — próximo en {sleep}s ({int(_active_until - time.time())}s restantes)")
            await asyncio.sleep(sleep)


if __name__ == "__main__":
    asyncio.run(run())
