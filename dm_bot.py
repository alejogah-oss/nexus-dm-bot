"""DM Bot — @tucarroconalejo — responde mensajes de Facebook e Instagram."""
import os
import time
import requests
import anthropic
from dotenv import load_dotenv
from crm_client import push_hot_lead
from pulse import pulse_notify
from assistant import log_event
from appointments import extract_appointment_from_conversation
from marketplace_analytics import track_message, track_hot_lead, track_declined
from notes import save_note, get_note

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")

BOT_VOICE = """
Eres parte del equipo de Hollywood Toyota en Florida. Hablas en nombre del equipo — "nosotros", "por aquí", "te ayudamos". Eres una persona real del equipo, no un robot.

REGLAS DE CONVERSACIÓN — ABSOLUTAS:
- Máximo 2 oraciones por respuesta. Sin excepciones.
- UNA sola pregunta por mensaje. Nunca dos.
- Lee el historial — si el cliente ya dijo algo, úsalo. Jamás lo pidas de nuevo.
- NUNCA menciones que "avisaste", "registraste", "notificaste" ni nada interno. El cliente no sabe que existe un sistema detrás.
- NUNCA expliques lo que estás haciendo internamente.

IDIOMA: detecta el idioma del cliente y responde SIEMPRE en ese mismo idioma. Si escribe en inglés, responde en inglés. Si escribe en español, responde en español.

TONO: persona del equipo que conoce los carros y quiere ayudar. Directo y cálido.

LINKS DE INVENTARIO — solo como último recurso, cuando el cliente insiste en ver opciones y la conversación no avanza. Comparte UNO solo, el que corresponde a lo que pidió:
- Sedanes: https://tucarroconalejo.com/inventario.html?tipo=sedan
- SUVs: https://tucarroconalejo.com/inventario.html?tipo=suv
- Pickups: https://tucarroconalejo.com/inventario.html?tipo=pickup
- Híbridos: https://tucarroconalejo.com/inventario.html?tipo=hibrido
- Si no sabe qué quiere: https://tucarroconalejo.com/inventario.html

REGLAS DE NEGOCIO:
- NUNCA des precios ni mensualidades.
- NUNCA prometas financiamiento sin confirmación.
- Precio → "Los números exactos te los damos directo, ¿me das tu número?"
- Prioriza siempre la conversación sobre mandar links.

TELÉFONO — REGLA IMPORTANTE:
- Si la conversación lleva 3+ mensajes y el cliente NO ha dado su número, intégralo de forma natural en algún momento.
- No lo pidas de golpe — intégralo en el contexto: "¿Me dejas tu número para coordinarte?"
- Si el cliente está frío o cerrando: "Si en algún momento te decides, déjame tu número y te buscamos."
- Si ya lo dio, NO lo pidas de nuevo.

NOMBRE — REGLA IMPORTANTE:
- NUNCA repitas el nombre "Alejo" más de una vez por conversación, y solo si es absolutamente necesario.
- Habla siempre en nombre del equipo: "nosotros", "te contactamos", "por aquí te ayudamos", "el equipo".
- Evita frases como "Alejo te llama", "Alejo te ayuda", "con Alejo" — usa "te contactamos", "te llamamos", "estamos para ayudarte".

FLUJO (un paso por mensaje):
1. Saludo breve + ¿qué modelo te interesa?
2. Una pregunta sobre su situación (primera vez, trade-in, familia, trabajo)
3. Pide nombre y teléfono para coordinar
4. Mantén la conversación hasta que el equipo tome el lead

CITAS — MUY IMPORTANTE:
- Cuando el cliente dé un día u hora, confírmalo SIEMPRE de forma explícita: "Perfecto, anotamos para el [día] a las [hora]. ¿Te queda bien?"
- Si el cliente cambia el día u hora que ya había dado, confirma el nuevo: "Claro, lo cambiamos para el [nuevo día]. ¿Confirmamos a esa hora?"
- Nunca dejes pasar una fecha/hora sin confirmarla en voz alta.

[HOT LEAD] — etiqueta SILENCIOSA, solo al final de tu respuesta, NUNCA la expliques ni la menciones al cliente. Úsala si:
- Quiere comprar pronto / "esta semana" / "tengo el dinero"
- Da su número de teléfono
- Pregunta cuándo puede venir o por financiamiento específico
"""


def _claude_create(model: str, max_tokens: int, system: str, messages: list, retries: int = 3) -> str:
    """Calls Claude API with retry on 529 overload."""
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages
            )
            return response.content[0].text
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"[BOT] Anthropic sobrecargado — reintento en {wait}s")
                time.sleep(wait)
            else:
                raise


def generate_reply(conversation_history: list, new_message: str) -> tuple[str, bool]:
    """Returns (reply_text, is_hot_lead)."""
    messages = conversation_history + [{"role": "user", "content": new_message}]
    reply = _claude_create("claude-sonnet-4-6", 160, BOT_VOICE, messages)
    is_hot = "[HOT LEAD]" in reply
    return reply.replace("[HOT LEAD]", "").strip(), is_hot


def send_facebook_reply(recipient_id: str, text: str):
    """Sends a reply via Facebook Messenger API."""
    url = "https://graph.facebook.com/v19.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    resp = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json=payload,
        timeout=10,
    )
    return resp.json()


def send_instagram_reply(recipient_id: str, text: str):
    """Sends a reply via Instagram Messaging API."""
    ig_user_id = os.getenv("META_IG_USER_ID")
    url = f"https://graph.facebook.com/v19.0/{ig_user_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    resp = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json=payload,
        timeout=10,
    )
    return resp.json()


def notify_alejo_hot_lead(sender_id: str, platform: str, message: str):
    """Notifies Alejo when a hot lead is detected — pushes to CRM (which sends WhatsApp)."""
    print(f"\n🔥 HOT LEAD DETECTADO")
    print(f"   Platform: {platform}")
    print(f"   Sender ID: {sender_id}")
    print(f"   Mensaje: {message}")
    history = _conversations.get(sender_id, [])

    # Guardar nota con resumen + cita detectada
    note = save_note(sender_id, platform, history)
    if note["changed"]:
        pulse_notify(
            event="HOT_LEAD",
            detail=(
                f"⚠️ CAMBIO DE CITA\n"
                f"Cita anterior: {note['prev_appointment']}\n"
                f"Nueva cita: {note['appointment']}\n"
                f"Hora: {note['timestamp']}"
            )
        )
        print(f"   ⚠️ Cambio de cita detectado: {note['prev_appointment']} → {note['appointment']}")

    push_hot_lead(sender_id, platform, history)  # WhatsApp + CRM handled inside
    log_event("HOT_LEAD", f"ID: {sender_id[:12]} | {message[:100]}", platform)


# In-memory conversation stores
_conversations: dict[str, list] = {}
_mp_conversations: dict[str, list] = {}  # Marketplace threads (separate namespace)

# Activity tracker — persisted to disk for frozen lead detection
import json as _json
_ACTIVITY_FILE = os.path.join(os.path.dirname(__file__), "leads_activity.json")

def _load_activity() -> dict:
    try:
        with open(_ACTIVITY_FILE, encoding="utf-8") as f:
            return _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return {}

def _save_activity(data: dict):
    with open(_ACTIVITY_FILE, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)

def track_activity(sender_id: str, platform: str, message_count: int):
    """Updates last activity timestamp for a conversation."""
    from datetime import datetime
    data = _load_activity()
    entry = data.get(sender_id, {})
    data[sender_id] = {
        **entry,
        "platform": platform,
        "last_activity": datetime.now().isoformat(),
        "message_count": message_count,
        "frozen_alert_sent": entry.get("frozen_alert_sent", False),
        "conv_url": f"https://business.facebook.com/latest/inbox/all?selected_item_id={sender_id}",
    }
    _save_activity(data)


def _marketplace_voice(car: dict) -> str:
    """Dynamic system prompt injected with the specific car the buyer messaged from."""
    return f"""Eres el asistente de Alejo, asesor Toyota en Hollywood Toyota, Florida.
El cliente te escribió desde un listing de Facebook Marketplace sobre este vehículo específico:

VEHÍCULO: {car['yr']} Toyota {car['model']} {car.get('trim', '')} — {car['color']}
DOWN PAYMENT ESTIMADO: ${car['down_payment']:,}
VIN: {car.get('vin', 'disponible al visitar')}

TU OBJETIVO PRINCIPAL: Que el cliente venga al dealer a ver el carro.
Estamos en Hollywood, Florida — la dirección exacta se la das cuando confirmen que vienen.

FLUJO:
Msg 1 → Confirma el carro que vio + invita a verlo en persona en Hollywood, FL
Msg 2 → Si duda, maneja la objeción con calidez + vuelve a invitar
Msg 3 → Si confirma que viene → pregunta: "¿Cuándo te viene bien? ¿Mañana, el fin de semana?" + da la dirección: 2200 N State Rd 7, Hollywood, FL 33021
Msg 4 → Cuando diga el día/hora → confirma: "Perfecto, te esperamos el [día] a las [hora]. Alejo estará pendiente."
Msg 3 (si sigue dudando) → ofrece que el equipo lo llame: "¿Me dejas tu número para coordinarte?"

AGENDAMIENTO — MUY IMPORTANTE:
- Cuando el cliente diga que viene (HOT LEAD), SIEMPRE pregunta qué día y hora le viene bien
- Si ya dijo el día/hora, confírmalo y agrega [HOT LEAD] al final
- Ejemplos de confirmación: "el sábado", "mañana por la mañana", "esta semana", "el martes a las 3"

CONTADOR DE RECHAZOS — MUY IMPORTANTE:
- Rechazo 1: maneja la objeción con calidez, ofrece alternativa (llamada, otro día)
- Rechazo 2: si no ha dado su número, pídelo de forma natural antes de despedirte ("Por si cambias de opinión, ¿me dejas un número?"). Luego despídete y agrega [SHOWROOM_DECLINED] al final
- Cuentan como rechazo: "no puedo", "queda lejos", "no tengo tiempo", "lo voy a pensar",
  "no sé", "tal vez después", "estoy ocupado" — cualquier evasiva es un rechazo
- NO sigas insistiendo después del 2do rechazo — acepta y cierra con gracia

SEÑALES DE HOT LEAD (agrega [HOT LEAD] al final de tu respuesta):
- Dice "voy", "esta semana", "mañana", "cuándo puedo ir", "me interesa"
- Da su número de teléfono
- Pregunta por financiamiento específico o cuánto de inicial

IDIOMA: detecta el idioma del cliente y responde SIEMPRE en ese mismo idioma.

REGLAS ABSOLUTAS:
- NUNCA des precio total ni mensualidades
- NUNCA prometas crédito garantizado
- Nunca compartas el número de Alejo — si el cliente quiere contacto directo, dile que Alejo lo busca: pide el número del cliente
- Máximo 3 oraciones por respuesta — breve y cálido
- Sin Markdown
- Las banderas [HOT LEAD] y [SHOWROOM_DECLINED] van al final, nunca en medio del texto"""


WELCOME_MESSAGE = (
    "¡Hola! Bienvenido a Tu Carro con Alejo 🙌\n\n"
    "Soy el asistente de Alejo — asesor de ventas Toyota en Hollywood, Florida.\n\n"
    "Cuéntame, ¿qué modelo Toyota te interesa? O si tienes preguntas sobre crédito, "
    "trade-in o disponibilidad, aquí estamos 👇"
)


def handle_get_started(sender_id: str, platform: str = "facebook"):
    """Sends welcome message when user taps Get Started button."""
    if platform == "instagram":
        send_instagram_reply(sender_id, WELCOME_MESSAGE)
    else:
        send_facebook_reply(sender_id, WELCOME_MESSAGE)
    _conversations[sender_id] = []
    print(f"[{platform.upper()}] {sender_id[:10]}... → GET_STARTED bienvenida enviada")


def handle_marketplace_message(sender_id: str, text: str, car: dict, platform: str = "facebook") -> str:
    """
    Handles DMs from Marketplace listings. Knows the specific car,
    pushes for showroom visit, detects HOT LEAD and SHOWROOM_DECLINED.
    """
    history = _mp_conversations.get(sender_id, [])

    if not history:
        intro = (
            f"¡Hola! Vi que te interesa el {car['yr']} Toyota {car['model']} "
            f"{car.get('trim', '')} en {car['color']} 🙌 "
            f"Es un carro increíble — ¿cuándo puedes venir a verlo en persona? "
            f"Estamos en Hollywood Toyota, 2200 N State Rd 7."
        )
        if platform == "instagram":
            send_instagram_reply(sender_id, intro)
        else:
            send_facebook_reply(sender_id, intro)
        history.append({"role": "assistant", "content": intro})

    reply = _claude_create(
        "claude-sonnet-4-6", 200,
        _marketplace_voice(car),
        history + [{"role": "user", "content": text}],
    )
    is_hot = "[HOT LEAD]" in reply
    is_declined = "[SHOWROOM_DECLINED]" in reply
    clean_reply = reply.replace("[HOT LEAD]", "").replace("[SHOWROOM_DECLINED]", "").strip()

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": clean_reply})
    _mp_conversations[sender_id] = history[-16:]

    if platform == "instagram":
        send_instagram_reply(sender_id, clean_reply)
    else:
        send_facebook_reply(sender_id, clean_reply)

    # Registrar mensaje en analytics (siempre, para todo listing)
    track_message(car)

    if is_hot:
        print(f"\n🔥 MARKETPLACE HOT LEAD — {platform.upper()} | {sender_id[:12]}...")
        note = save_note(sender_id, platform, history)
        if note["changed"]:
            pulse_notify(
                event="HOT_LEAD",
                detail=(
                    f"⚠️ CAMBIO DE CITA — Marketplace\n"
                    f"Cita anterior: {note['prev_appointment']}\n"
                    f"Nueva cita: {note['appointment']}\n"
                    f"Hora: {note['timestamp']}"
                )
            )
        push_hot_lead(sender_id, platform, history, car=car)
        log_event("HOT_LEAD", f"Marketplace {car['yr']} {car['model']} {car.get('trim','')} | {text[:80]}", platform)
        track_hot_lead(car)
        extract_appointment_from_conversation(history, car, sender_id, platform)

    if is_declined:
        print(f"\n📋 SHOWROOM DECLINED — {platform.upper()} | {sender_id[:12]}...")
        print(f"   Carro: {car['yr']} Toyota {car['model']} {car.get('trim','')} {car['color']}")
        push_hot_lead(sender_id, platform, history, car=car)
        pulse_notify(
            event="SHOWROOM_DECLINED",
            detail=f"Carro: {car['yr']} Toyota {car['model']} {car.get('trim','')} {car['color']} | Platform: {platform.upper()}"
        )
        log_event("SHOWROOM_DECLINED", f"Marketplace {car['yr']} {car['model']} {car.get('trim','')} {car['color']}", platform)
        track_declined(car)

    print(f"[MP-{platform.upper()}] {sender_id[:10]}... → replied | hot={is_hot} | declined={is_declined}")
    return clean_reply


def handle_message(sender_id: str, message_text: str, platform: str = "facebook") -> str:
    """Main handler — processes incoming DM and sends reply."""
    history = _conversations.get(sender_id, [])

    # First message from this user — send welcome before AI reply
    if not history:
        if platform == "instagram":
            send_instagram_reply(sender_id, WELCOME_MESSAGE)
        else:
            send_facebook_reply(sender_id, WELCOME_MESSAGE)

    reply, is_hot = generate_reply(history, message_text)

    # Update conversation history
    history.append({"role": "user", "content": message_text})
    history.append({"role": "assistant", "content": reply})
    _conversations[sender_id] = history[-20:]  # keep last 10 exchanges

    # Track activity for frozen lead detection
    track_activity(sender_id, platform, len(history))

    # Send reply
    if platform == "instagram":
        send_instagram_reply(sender_id, reply)
    else:
        send_facebook_reply(sender_id, reply)

    # Alert for hot leads
    if is_hot:
        notify_alejo_hot_lead(sender_id, platform, message_text)

    print(f"[{platform.upper()}] {sender_id[:10]}... → replied ({len(reply)} chars) | hot={is_hot}")
    return reply
