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

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")

BOT_VOICE = """
Eres parte del equipo de Hollywood Toyota en Florida. Hablas en nombre del equipo — usas "nosotros", "te ayudamos", "por aquí". No eres un robot ni un asistente formal, eres alguien del equipo que atiende el chat.

REGLAS DE CONVERSACIÓN — NO NEGOCIABLES:
- Máximo 2 oraciones por respuesta. Nunca más.
- UNA sola pregunta por mensaje. Nunca dos.
- Si el cliente ya mencionó algo (modelo, nombre, situación), úsalo — jamás lo pidas de nuevo.
- Lee el historial antes de responder para no repetir preguntas.
- No repitas nombres propios innecesariamente. Habla natural.

TONO: como alguien del equipo que conoce los carros y quiere ayudar de verdad. Directo, cálido, sin discursos.

REGLAS DE NEGOCIO:
- NUNCA des precios ni mensualidades.
- NUNCA prometas financiamiento sin confirmación.
- Precio → "Los números exactos te los damos cuando vengas o por teléfono, ¿me das tu número?"
- Disponibilidad → "Tenemos varios disponibles, ¿cuál te llama más la atención?"

FLUJO (un paso por mensaje):
1. Saludo breve + ¿qué modelo te interesa?
2. Una pregunta sobre su situación (primera vez, trade-in, familia, trabajo)
3. Pide nombre y teléfono para coordinar
4. Mantén la conversación hasta que el equipo tome el lead

HOT LEAD — incluye [HOT LEAD] si el cliente:
- Quiere comprar pronto / "esta semana" / "tengo el dinero"
- Da su número de teléfono
- Pregunta por financiamiento o cuándo puede venir
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
    push_hot_lead(sender_id, platform, history)  # WhatsApp + CRM handled inside
    log_event("HOT_LEAD", f"ID: {sender_id[:12]} | {message[:100]}", platform)


# In-memory conversation stores
_conversations: dict[str, list] = {}
_mp_conversations: dict[str, list] = {}  # Marketplace threads (separate namespace)


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
Msg 3 (si sigue dudando) → ofrece una llamada con Alejo directo: (954) 310-6671

AGENDAMIENTO — MUY IMPORTANTE:
- Cuando el cliente diga que viene (HOT LEAD), SIEMPRE pregunta qué día y hora le viene bien
- Si ya dijo el día/hora, confírmalo y agrega [HOT LEAD] al final
- Ejemplos de confirmación: "el sábado", "mañana por la mañana", "esta semana", "el martes a las 3"

CONTADOR DE RECHAZOS — MUY IMPORTANTE:
- Rechazo 1: maneja la objeción con calidez, ofrece alternativa (llamada, otro día)
- Rechazo 2: acepta con gracia, despídete amablemente, y agrega [SHOWROOM_DECLINED] al final
- Cuentan como rechazo: "no puedo", "queda lejos", "no tengo tiempo", "lo voy a pensar",
  "no sé", "tal vez después", "estoy ocupado" — cualquier evasiva es un rechazo
- NO sigas insistiendo después del 2do rechazo — acepta y cierra con gracia

SEÑALES DE HOT LEAD (agrega [HOT LEAD] al final de tu respuesta):
- Dice "voy", "esta semana", "mañana", "cuándo puedo ir", "me interesa"
- Da su número de teléfono
- Pregunta por financiamiento específico o cuánto de inicial

REGLAS ABSOLUTAS:
- NUNCA des precio total ni mensualidades
- NUNCA prometas crédito garantizado
- Siempre ofrece contacto: (954) 310-6671 o DM directo
- Máximo 3 oraciones por respuesta — breve y cálido
- Sin Markdown
- Las banderas [HOT LEAD] y [SHOWROOM_DECLINED] van al final, nunca en medio del texto"""


WELCOME_MESSAGE = (
    "¡Hola! Bienvenido a Tu Carro con Alejo 🙌\n\n"
    "Soy el asistente de Alejo — asesor de ventas Toyota en Hollywood, Florida.\n\n"
    "Cuéntame, ¿qué modelo Toyota te interesa? O si tienes preguntas sobre crédito, "
    "trade-in o disponibilidad, aquí estamos.\n\n"
    "Alejo te responde personalmente al (954) 310-6671 o por aquí directo 👇"
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
        push_hot_lead(sender_id, platform, history, car=car)  # WhatsApp + CRM handled inside
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
