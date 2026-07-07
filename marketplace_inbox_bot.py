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

USER_DATA_DIR    = Path.home() / ".fb_playwright_profile"
COOKIES_FILE     = Path(__file__).parent / "browser_session/mp_session.json"
STATE_FILE       = Path(__file__).parent / "marketplace_inbox_state.json"
TWO_FA_CODE_FILE    = Path(__file__).parent / "browser_session/2fa_code.txt"
TWO_FA_PENDING_FILE = Path(__file__).parent / "browser_session/2fa_pending.txt"
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

async def _wait_for_2fa_code(timeout: int = 300) -> str | None:
    """Espera hasta `timeout` segundos a que se ingrese el código 2FA via endpoint."""
    TWO_FA_PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    TWO_FA_PENDING_FILE.write_text("waiting")
    print(
        "[BOT] ⏳ Ingresa el código 2FA en:\n"
        "       https://bot.tucarroconalejo.com/marketplace/enter-2fa?code=XXXXXX",
        flush=True,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if TWO_FA_CODE_FILE.exists():
            code = TWO_FA_CODE_FILE.read_text().strip()
            TWO_FA_CODE_FILE.unlink(missing_ok=True)
            if code:
                print(f"[BOT] Código 2FA recibido: {code}", flush=True)
                TWO_FA_PENDING_FILE.unlink(missing_ok=True)
                return code
        await asyncio.sleep(5)
    TWO_FA_PENDING_FILE.unlink(missing_ok=True)
    print("[BOT] ❌ 2FA timeout — saltando ciclo", flush=True)
    return None


async def _trigger_2fa_sms(page: Page):
    """
    Navega las pantallas intermedias del 2FA de Facebook para llegar al campo de código.
    Selecciona el teléfono terminado en 71 y dispara el envío del SMS.
    Usa JS directo para evitar checks de visibilidad de Playwright.
    """
    # Esperar a que la red se estabilice (SPA termina de cargar)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await page.wait_for_timeout(2000)

    # Screenshot de la página 2FA para diagnóstico visual
    try:
        shot_path = Path(__file__).parent / "browser_session/2fa_screenshot.png"
        shot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(shot_path), full_page=True)
        print(f"[BOT] 2FA screenshot guardado — ver en /marketplace/screenshot", flush=True)
    except Exception as e:
        print(f"[BOT] 2FA screenshot error: {e}", flush=True)

    # Dump de diagnóstico vía JS (sin checks de visibilidad)
    try:
        pg_title = await page.title()
        pg_text  = await page.evaluate("document.body ? document.body.innerText.substring(0, 800) : 'NO BODY'")
        pg_html  = await page.evaluate("document.body ? document.body.innerHTML.substring(0, 400) : 'NO HTML'")
        print(f"[BOT] 2FA TITLE: {pg_title}", flush=True)
        print(f"[BOT] 2FA TEXT: {pg_text}", flush=True)
        print(f"[BOT] 2FA HTML: {pg_html}", flush=True)
    except Exception as e:
        print(f"[BOT] 2FA dump error: {e}", flush=True)

    # Función JS para buscar y hacer clic en botón/link que contenga texto
    async def _js_click_text(texts: list[str]) -> bool:
        for txt in texts:
            try:
                clicked = await page.evaluate(f"""
                    (txt) => {{
                        const els = document.querySelectorAll('a, button, div[role="button"], span[role="button"]');
                        for (const el of els) {{
                            if (el.textContent && el.textContent.trim().toLowerCase().includes(txt.toLowerCase())) {{
                                el.click();
                                return el.textContent.trim();
                            }}
                        }}
                        return null;
                    }}
                """, txt)
                if clicked:
                    print(f"[BOT] 2FA JS click: '{clicked[:60]}'", flush=True)
                    await page.wait_for_timeout(2500)
                    return True
            except Exception:
                pass
        return False

    # 1. Navegar desde pantalla "Aprueba desde la app" a otro método
    await _js_click_text(["Try Another Way", "Try a different method", "Use a different method",
                          "Another way", "different method"])

    # 2. Seleccionar SMS/Text si hay selección de método
    await _js_click_text(["Text message", "SMS", "Text (SMS)"])

    # 3. Seleccionar teléfono terminado en 71
    try:
        clicked_phone = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('a, button, div[role="button"], label, li, span[role="button"]');
                for (const el of els) {
                    const txt = el.textContent ? el.textContent.trim() : '';
                    if (txt.includes('71') && txt.length < 60) {
                        el.click();
                        return txt;
                    }
                }
                return null;
            }
        """)
        if clicked_phone:
            print(f"[BOT] 2FA: teléfono seleccionado: '{clicked_phone[:50]}'", flush=True)
            await page.wait_for_timeout(1500)
    except Exception as e:
        print(f"[BOT] 2FA phone select error: {e}", flush=True)

    # 4. Confirmar envío (Continue / Send code)
    await _js_click_text(["Continue", "Send code", "Send SMS", "Next", "Submit"])


async def _submit_2fa_code(page: Page, code: str) -> bool:
    """Rellena el campo de código 2FA y lo envía. _trigger_2fa_sms ya navegó a esta pantalla."""
    try:
        CODE_SELECTOR = (
            '#approvals_code, [name="approvals_code"], input[name="code"], '
            'input[type="tel"], input[autocomplete="one-time-code"], '
            'input[aria-label*="code" i], input[placeholder*="code" i], '
            'input[aria-label*="código" i], input[placeholder*="código" i]'
        )

        try:
            await page.wait_for_selector(CODE_SELECTOR, timeout=15000)
        except Exception:
            try:
                pg_text = (await page.inner_text("body"))[:600]
                print(f"[BOT] 2FA — input no encontrado. Página:\n{pg_text}\n---", flush=True)
            except Exception:
                pass
            print("[BOT] ❌ No se encontró campo de código 2FA", flush=True)
            return False

        await page.fill(CODE_SELECTOR, code)
        await page.wait_for_timeout(500)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(6000)
        print(f"[BOT] Post-2FA url={page.url[:80]}", flush=True)

        # Facebook puede preguntar "Save this browser?" — guardar para no pedir 2FA de nuevo
        try:
            save_btn = page.locator(
                'button[name="submit[Save Browser]"], button:has-text("Save Browser"), '
                'button:has-text("Save"), button:has-text("Remember Browser")'
            )
            if await save_btn.count() > 0:
                await save_btn.first.click()
                await page.wait_for_timeout(4000)
                print("[BOT] ✅ Browser guardado — futuras sesiones no necesitarán 2FA", flush=True)
        except Exception:
            pass

        still_2fa = "two_step" in page.url or "checkpoint" in page.url
        if still_2fa:
            print("[BOT] ❌ 2FA code no aceptado (sigue en checkpoint)", flush=True)
            return False
        return True
    except Exception as e:
        print(f"[BOT] Error enviando código 2FA: {e}", flush=True)
        return False


async def _fb_login(page: Page) -> bool:
    """Intenta login con FB_EMAIL + FB_PASSWORD. Retorna True si exitoso."""
    email = os.getenv("FB_EMAIL", "tucarroconalejo@gmail.com")
    password = os.getenv("FB_PASSWORD", "")
    if not password:
        print("[BOT] ⚠️  FB_PASSWORD no configurado — no se puede re-autenticar", flush=True)
        return False

    print("[BOT] Limpiando cookies viejas e iniciando sesión...", flush=True)
    try:
        # Limpiar cookies — las viejas redirigen al home en vez de mostrar el login
        await page.context.clear_cookies()
        print("[BOT] Cookies limpiadas", flush=True)

        await page.goto("https://www.facebook.com/login/", wait_until="domcontentloaded", timeout=45000)
        print(f"[BOT] Login page url={page.url[:80]}", flush=True)
        await page.wait_for_timeout(3000)

        # Esperar que aparezca el campo email
        try:
            await page.wait_for_selector('[name="email"], #email, input[type="email"]', timeout=15000)
        except Exception:
            print(f"[BOT] No se encontró campo email — url={page.url[:80]}", flush=True)
            # Último intento: versión móvil
            await page.goto("https://m.facebook.com/login/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            try:
                await page.wait_for_selector('[name="email"], #email', timeout=10000)
            except Exception:
                print(f"[BOT] Login form no encontrado en móvil tampoco — url={page.url[:80]}", flush=True)
                return False

        await page.fill('[name="email"]', email)
        await page.wait_for_timeout(500)
        await page.fill('[name="pass"]', password)
        await page.wait_for_timeout(500)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(8000)
        final_url = page.url
        print(f"[BOT] Post-login url={final_url[:80]}", flush=True)

        if "checkpoint" in final_url or "two_step" in final_url:
            # Diagnosticar qué tipo de verificación pide Facebook
            try:
                await page.wait_for_timeout(2000)
                page_title = await page.title()
                page_text  = (await page.inner_text("body"))[:800]
                has_code   = await page.locator(
                    '#approvals_code,[name="approvals_code"],input[name="code"],'
                    'input[type="tel"],input[autocomplete="one-time-code"]'
                ).count()
                has_approve = await page.locator(
                    'button:has-text("Approve"),button:has-text("It Was Me"),'
                    'input[value="Approve"],a:has-text("Approve")'
                ).count()
                print(f"[BOT] 2FA TITLE: {page_title}", flush=True)
                print(f"[BOT] 2FA HAS_CODE_INPUT: {has_code}  HAS_APPROVE_BTN: {has_approve}", flush=True)
                print(f"[BOT] 2FA PAGE TEXT:\n{page_text}\n---", flush=True)
            except Exception as _diag_e:
                print(f"[BOT] 2FA diag error: {_diag_e}", flush=True)
            # Navegar pantallas intermedias Y disparar SMS al teléfono terminado en 71
            await _trigger_2fa_sms(page)
            print("[BOT] ⚠️  2FA requerido — esperando código (hasta 5 min)...", flush=True)
            code = await _wait_for_2fa_code(timeout=300)
            if not code:
                return False
            ok = await _submit_2fa_code(page, code)
            if not ok:
                return False
            # Si llegó aquí, login exitoso con 2FA

        elif "login" in final_url and "facebook" in final_url:
            print("[BOT] ⚠️  Login rechazado (contraseña incorrecta o bloqueo)", flush=True)
            return False

        print("[BOT] ✅ Login Facebook exitoso", flush=True)
        await page.goto("https://www.messenger.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        logged_in = "login" not in page.url
        if logged_in:
            await _save_session_cookies(page)
        return logged_in
    except Exception as e:
        print(f"[BOT] Error en login: {e}", flush=True)
        return False


async def _save_session_cookies(page: Page):
    """Guarda las cookies activas a mp_session.json para reusar en próximos reinicios."""
    try:
        ctx = page.context
        cookies = await ctx.cookies(["https://www.messenger.com", "https://www.facebook.com"])
        valid = [c for c in cookies if c.get("value")]
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_FILE.write_text(json.dumps(valid, indent=2))
        b64 = base64.b64encode(json.dumps(valid).encode()).decode()
        print(f"[BOT] ✅ Cookies guardadas ({len(valid)} cookies) en {COOKIES_FILE}", flush=True)
        print(f"[BOT] FB_COOKIES_B64={b64[:60]}...", flush=True)
    except Exception as e:
        print(f"[BOT] Error guardando cookies: {e}", flush=True)


async def _ensure_messenger_logged_in(page: Page) -> bool:
    """Navega a messenger.com. Si la sesión no es válida intenta re-login. Retorna True si OK."""
    print("[BOT] goto messenger.com...", flush=True)
    try:
        await page.goto("https://www.messenger.com/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[BOT] Timeout/error navigating to messenger.com: {e}", flush=True)
        return False
    print(f"[BOT] messenger loaded — url={page.url[:80]}", flush=True)
    await page.wait_for_timeout(3000)

    # Si redirigió al login, intentar re-autenticación
    if "login" in page.url or "facebook.com" in page.url:
        print("[BOT] Sesión expirada — intentando re-login...", flush=True)
        ok = await _fb_login(page)
        if not ok:
            return False
        await page.wait_for_timeout(3000)

    # Completar login si aparece "Continue as" — esperar hasta 8s para que el SPA renderice
    for _ in range(8):
        clicked = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('button, div[role="button"]');
                for (const el of els) {
                    if (el.textContent && el.textContent.includes('Continue as')) {
                        el.click();
                        return el.textContent.trim();
                    }
                }
                return null;
            }
        """)
        if clicked:
            print(f"[BOT] Messenger: clic 'Continue as' → '{clicked[:40]}'", flush=True)
            await page.wait_for_timeout(4000)
            break
        await page.wait_for_timeout(1000)

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
            print("[BOT] Sesión inválida en marketplace — intentando re-login...", flush=True)
            ok = await _fb_login(page)
            if not ok:
                print("[BOT] Login fallido — saltando ciclo", flush=True)
                return
            await page.goto("https://www.messenger.com/marketplace/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            print(f"[BOT] Post-login URL: {page.url[:80]}", flush=True)
            if "login" in page.url:
                print("[BOT] Sigue sin sesión válida — saltando", flush=True)
                return
    except Exception as e:
        print(f"[BOT] Error cargando inbox: {e}", flush=True)
        return

    # Sesión válida — activar bloqueador para reducir RAM en el scraping del inbox
    async def _block_heavy(route):
        if route.request.resource_type in ("image", "stylesheet", "font", "media", "other"):
            await route.abort()
        else:
            await route.continue_()
    try:
        await page.route("**/*", _block_heavy)
    except Exception:
        pass

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


LAUNCH_ARGS = [
    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
    "--disable-extensions", "--disable-plugins",
    "--no-first-run", "--no-default-browser-check",
]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


async def run():
    print("[MIB] run() entered", flush=True)
    state = _load_state()
    print("[MIB] state loaded", flush=True)

    print("=" * 50)
    print("  NEXUS — Marketplace Inbox Bot")
    print(f"  Cuenta: tucarroconalejo@gmail.com")
    print(f"  Ciclos: cada {POLL_SEC}s, browser cierra/abre por ciclo")
    print("=" * 50)

    # Mantener el driver Playwright vivo — solo cerrar el browser entre ciclos
    async with async_playwright() as p:
        print("[MIB] playwright driver listo", flush=True)
        cycle = 0
        while True:
            cycle += 1
            print(f"\n[MIB] === CICLO {cycle} === {time.strftime('%H:%M:%S')}", flush=True)
            browser = None
            try:
                browser = await p.chromium.launch(headless=True, args=LAUNCH_ARGS)
                print(f"[MIB] chromium up v{browser.version}", flush=True)
                ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})

                # Preferir cookies guardadas (login desde Render) sobre env var stale
                if COOKIES_FILE.exists():
                    cookies = json.loads(COOKIES_FILE.read_text())
                else:
                    raw_b64 = os.getenv("FB_COOKIES_B64", "")
                    cookies = json.loads(base64.b64decode(raw_b64).decode()) if raw_b64 else []
                if cookies:
                    await ctx.add_cookies(cookies)

                page = await ctx.new_page()
                # El bloqueador se aplica DESPUÉS del login en check_inbox
                # para que la página 2FA cargue completa (SPA necesita todos los recursos)
                await check_inbox(page, state, quick=False)
                _save_state(state)
            except Exception as e:
                print(f"[MIB] Ciclo {cycle} error: {e}", flush=True)
            finally:
                if browser:
                    try:
                        await browser.close()
                        print("[MIB] chromium cerrado", flush=True)
                    except Exception:
                        pass

            print(f"[MIB] Durmiendo {POLL_SEC}s...", flush=True)
            await asyncio.sleep(POLL_SEC)


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
