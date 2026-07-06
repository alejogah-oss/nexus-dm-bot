"""
NEXUS — Marketplace Inbox Bot
Monitorea el inbox de Marketplace del perfil personal (tucarroconalejo@gmail.com)
y responde con la misma IA de dm_bot. Corre en loop localmente.

Uso:
    venv/bin/python3 marketplace_inbox_bot.py
"""
import sys, os
print(f"[MIB] STARTED pid={os.getpid()} python={sys.executable}", flush=True)

import asyncio
import base64
import json
import time
from pathlib import Path

print("[MIB] stdlib ok", flush=True)

from playwright.async_api import async_playwright, Page
print("[MIB] playwright imported", flush=True)

from dotenv import load_dotenv

from dm_bot import _claude_create, _marketplace_voice, push_hot_lead, log_event
print("[MIB] dm_bot imported", flush=True)
from marketplace_analytics import track_message, track_hot_lead, track_declined
print("[MIB] marketplace_analytics imported", flush=True)
from pulse import pulse_notify
print("[MIB] pulse imported", flush=True)
from appointments import extract_appointment_from_conversation
print("[MIB] appointments imported", flush=True)

load_dotenv()

USER_DATA_DIR  = Path.home() / ".fb_playwright_profile"
COOKIES_FILE   = Path(__file__).parent / "browser_session/mp_session.json"
STATE_FILE     = Path(__file__).parent / "marketplace_inbox_state.json"
# Siempre usar cookies (mp_session.json) — el perfil persistente falla en headless
USE_COOKIES    = True
POLL_SEC       = 60    # intervalo normal
POLL_ACTIVE    = 10    # intervalo cuando hay conversación activa
ACTIVE_WINDOW  = 300   # segundos en modo activo tras responder (5 min)

_active_until: float = 0.0              # timestamp hasta cuando está en modo activo
_active_threads: dict[str, float] = {}  # {thread_id: expires_at}
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
        await page.wait_for_timeout(800)
        await _dismiss_pin_modal(page)
        await page.wait_for_timeout(400)

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
        await page.goto(f"https://www.messenger.com/t/{thread_id}",
                        wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1200)
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

    # Intro en primer contacto
    if not history and car:
        intro = (
            f"¡Hola! Vi que te interesa el {car['yr']} Toyota {car['model']} "
            f"{car.get('trim', '')}. "
            f"¿Tienes alguna pregunta sobre el carro?"
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
        # Activar modo rápido: revisar este thread cada 10s durante 5 min
        global _active_until, _active_threads
        _active_until = time.time() + ACTIVE_WINDOW
        _active_threads[thread_id] = time.time() + ACTIVE_WINDOW
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

async def _fb_login(page: Page) -> bool:
    """Intenta login con FB_EMAIL + FB_PASSWORD. Retorna True si exitoso."""
    email = os.getenv("FB_EMAIL", "tucarroconalejo@gmail.com")
    password = os.getenv("FB_PASSWORD", "")
    if not password:
        print("[BOT] ⚠️  FB_PASSWORD no configurado — no se puede re-autenticar", flush=True)
        return False

    print("[BOT] Iniciando sesión en Facebook...", flush=True)
    try:
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        await page.fill('[name="email"]', email)
        await page.fill('[name="pass"]', password)
        await page.click('[name="login"]')
        await page.wait_for_timeout(6000)
        final_url = page.url
        print(f"[BOT] Post-login url={final_url[:80]}", flush=True)

        if "checkpoint" in final_url or "two_step" in final_url or "login" in final_url:
            print("[BOT] ⚠️  Login bloqueado / 2FA requerido — url=" + final_url[:80], flush=True)
            return False

        print("[BOT] ✅ Login Facebook exitoso", flush=True)
        # Navegar a messenger.com para que las cookies queden activas
        await page.goto("https://www.messenger.com/", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        return "login" not in page.url
    except Exception as e:
        print(f"[BOT] Error en login: {e}", flush=True)
        return False


async def _ensure_messenger_logged_in(page: Page) -> bool:
    """Navega a messenger.com. Si la sesión no es válida intenta re-login. Retorna True si OK."""
    print("[BOT] goto messenger.com...", flush=True)
    try:
        await page.goto("https://www.messenger.com/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[BOT] Timeout/error navigating to messenger.com: {e}", flush=True)
        return False
    print(f"[BOT] messenger loaded — url={page.url[:80]}", flush=True)
    await page.wait_for_timeout(2000)

    # Si redirigió al login, intentar re-autenticación
    if "login" in page.url or "facebook.com" in page.url:
        print("[BOT] Sesión expirada — intentando re-login...", flush=True)
        ok = await _fb_login(page)
        if not ok:
            return False
        await page.wait_for_timeout(2000)

    # Completar login si aparece "Continue as"
    btn = page.locator('button:has-text("Continue as")')
    if await btn.count() > 0:
        print("[BOT] Completando login en Messenger...", flush=True)
        await btn.first.click()
        await page.wait_for_timeout(5000)

    # Cerrar modal de PIN de cifrado si aparece
    close_btn = page.locator('[aria-label="Close"]').first
    if await close_btn.count() > 0:
        print("[BOT] Cerrando modal de PIN...", flush=True)
        await close_btn.click(force=True)
        await page.wait_for_timeout(1000)

    # Confirmar "Continue without restoring?" si aparece
    no_restore = page.locator('button:has-text("Don\'t restore messages")')
    if await no_restore.count() > 0:
        print("[BOT] Confirmando sin restaurar mensajes...", flush=True)
        await no_restore.click()
        await page.wait_for_timeout(1000)

    return True


async def check_inbox(page: Page, state: dict, quick: bool = False):
    """Escanea el inbox de Marketplace. quick=True solo revisa threads activos."""
    now = time.time()

    # Modo rápido: solo los threads con conversación activa
    if quick:
        active = {tid: exp for tid, exp in _active_threads.items() if exp > now}
        if not active:
            return
        print(f"\n[BOT] Modo activo — revisando {len(active)} thread(s) — {time.strftime('%H:%M:%S')}")
        for thread_id, _ in active.items():
            href = f"https://www.messenger.com/marketplace/t/{thread_id}"
            await process_thread(page, state, href, "")
        return

    print(f"\n[BOT] Revisando inbox Marketplace — {time.strftime('%H:%M:%S')}")

    try:
        logged_in = await _ensure_messenger_logged_in(page)
        if not logged_in:
            print("[BOT] Sesión no válida — saltando ciclo", flush=True)
            return
        await page.goto("https://www.messenger.com/marketplace/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"[BOT] URL: {page.url[:80]}", flush=True)
        if "login" in page.url:
            print("[BOT] Redirigido a login en marketplace — sesión inválida", flush=True)
            return
    except Exception as e:
        print(f"[BOT] Error cargando inbox: {e}", flush=True)
        return

    try:
        links = await page.locator('a[href*="/marketplace/t/"]').all()
        if not links:
            links = await page.locator('a[href*="/t/"]').all()
    except Exception:
        print("[BOT] No se encontraron threads")
        return

    seen_ids  = set()
    threads   = []
    # Recolectar threads con preview de último mensaje para saltar los sin cambios
    for link in links[:MAX_THREADS]:
        try:
            href = await link.get_attribute("href")
            if not href or "/t/" not in href:
                continue
            thread_id = href.split("/t/")[-1].split("/")[0].split("?")[0]
            if thread_id in seen_ids:
                continue
            seen_ids.add(thread_id)
            try:
                name = (await link.locator('[dir="auto"]').first.inner_text()).strip().split("\n")[0]
            except Exception:
                name = thread_id
            # Preview del último mensaje visible en el inbox
            try:
                preview = (await link.locator('[dir="auto"]').nth(1).inner_text()).strip()
            except Exception:
                preview = ""
            threads.append((href, name, thread_id, preview))
        except Exception:
            continue

    # Filtrar: solo abrir threads donde el preview cambió respecto al último hash
    to_process = []
    for href, name, thread_id, preview in threads:
        preview_hash = hash(preview) if preview else None
        # Si no hay preview o el hash cambió, hay que revisar
        if not preview or preview_hash != state.get(f"preview_{thread_id}"):
            to_process.append((href, name, thread_id, preview_hash))

    skipped = len(threads) - len(to_process)
    print(f"[BOT] {len(threads)} threads — {len(to_process)} con cambios, {skipped} sin cambios")

    for href, name, thread_id, preview_hash in to_process:
        await process_thread(page, state, href, name)
        # Guardar preview hash para evitar recargar en próximo ciclo
        if preview_hash:
            state[f"preview_{thread_id}"] = preview_hash
        if to_process.index((href, name, thread_id, preview_hash)) < len(to_process) - 1:
            try:
                await page.goto("https://www.messenger.com/marketplace/",
                                wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(600)
            except Exception:
                pass

    print(f"[BOT] Ciclo completo — próximo en {POLL_SEC}s")


async def run():
    print("[MIB] run() entered", flush=True)
    state = _load_state()
    print("[MIB] state loaded", flush=True)

    LAUNCH_ARGS = [
        "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-extensions", "--disable-plugins", "--disable-translate",
        "--disable-background-networking", "--disable-sync",
        "--disable-default-apps", "--no-first-run", "--no-default-browser-check",
        "--js-flags=--max-old-space-size=256",
        "--memory-pressure-off",
    ]
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    print("[MIB] launching playwright...", flush=True)
    async with async_playwright() as p:
        print("[MIB] playwright ctx ok", flush=True)
        if USE_COOKIES:
            print("[MIB] launching chromium...", flush=True)
            # Render / sin perfil local — usa cookies desde env var o archivo
            browser = await p.chromium.launch(headless=True, args=LAUNCH_ARGS)
            print(f"[MIB] chromium up version={browser.version}", flush=True)
            ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
            print("[MIB] context created", flush=True)
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
            in_active = time.time() < _active_until
            try:
                await check_inbox(page, state, quick=in_active)
                _save_state(state)
            except Exception as e:
                print(f"[BOT] Error general: {e}")
                try:
                    await page.reload(timeout=15000)
                    await page.wait_for_timeout(5000)
                except Exception:
                    pass

            sleep = POLL_ACTIVE if time.time() < _active_until else POLL_SEC
            await asyncio.sleep(sleep)


if __name__ == "__main__":
    print("[MIB] __main__ reached — calling asyncio.run(run())", flush=True)
    try:
        asyncio.run(run())
    except BaseException as e:
        import traceback
        print(f"[MIB] FATAL {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        code = e.code if isinstance(e, SystemExit) else 1
        sys.exit(code)
    print("[MIB] asyncio.run() returned — loop exited (unexpected)", flush=True)
