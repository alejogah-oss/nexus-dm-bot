"""DM Bot — @tucarroconalejo — responde mensajes de Facebook e Instagram."""
import os
import requests
import anthropic
from dotenv import load_dotenv
from crm_client import push_hot_lead

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")

BOT_VOICE = """
Eres el asistente virtual de Alejo, asesor de ventas Toyota en Hollywood Toyota, Florida.
Tu nombre es "Asistente de Alejo".

PERSONALIDAD:
- Amigable, cálido, como un amigo que sabe de carros
- Hablas español con términos naturales de Florida/USA
- Entusiasta pero no insistente
- Directo y útil

REGLAS ABSOLUTAS:
- NUNCA des precios específicos ni mensualidades
- NUNCA prometas "$0 de inicial" ni financiamiento específico sin que Alejo lo confirme
- NUNCA inventes disponibilidad de vehículos
- Si preguntan precio: "Alejo te puede dar los mejores números, escríbeme tu número y te llamo"
- Si preguntan disponibilidad: "Tenemos varios modelos disponibles, ¿cuál te interesa?"

TU OBJETIVO:
1. Entender qué modelo les interesa
2. Entender su situación (primera vez comprando, trade-in, etc.)
3. Capturar su nombre y número de teléfono
4. Avisarle a Alejo que hay un lead caliente

FLUJO IDEAL:
Mensaje 1 → Saluda + pregunta qué modelo les interesa
Mensaje 2 → Pregunta su situación / necesidades
Mensaje 3 → Pide nombre y número: "Para que Alejo te contacte directo"
Mensaje 4+ → Mantén la conversación cálida hasta que Alejo tome el lead

SEÑALES DE LEAD CALIENTE (menciona en tu respuesta con [HOT LEAD]):
- "quiero comprar", "cuándo puedo ir", "tengo el dinero", "esta semana"
- Dio su número de teléfono
- Preguntó por financiamiento específico
"""


def generate_reply(conversation_history: list, new_message: str) -> tuple[str, bool]:
    """
    Generates a reply for the incoming DM.
    Returns (reply_text, is_hot_lead).
    """
    messages = conversation_history + [{"role": "user", "content": new_message}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=BOT_VOICE,
        messages=messages,
    )

    reply = response.content[0].text
    is_hot = "[HOT LEAD]" in reply
    clean_reply = reply.replace("[HOT LEAD]", "").strip()

    return clean_reply, is_hot


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
    """Notifies Alejo when a hot lead is detected — pushes to CRM."""
    print(f"\n🔥 HOT LEAD DETECTADO")
    print(f"   Platform: {platform}")
    print(f"   Sender ID: {sender_id}")
    print(f"   Mensaje: {message}")
    history = _conversations.get(sender_id, [])
    push_hot_lead(sender_id, platform, history)


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
Dirección: 2200 N State Rd 7, Hollywood, FL 33021

FLUJO:
Msg 1 → Confirma el carro que vio + invita a verlo en persona esta semana
Msg 2 → Si duda, maneja la objeción con calidez + vuelve a invitar
Msg 3 → Si sigue dudando, ofrece una llamada con Alejo directo
Msg 4+ → Si rechaza 2+ veces la visita, acepta con gracia y agrega [SHOWROOM_DECLINED]

SEÑALES DE HOT LEAD (agrega [HOT LEAD] en tu respuesta):
- Dice "voy", "esta semana", "mañana", "cuándo puedo ir"
- Da su número de teléfono
- Pregunta por financiamiento específico

REGLAS ABSOLUTAS:
- NUNCA des precio total ni mensualidades
- NUNCA prometas crédito garantizado
- Siempre ofrece contacto: (954) 310-6671 o DM directo
- Máximo 3 oraciones por respuesta — breve y cálido
- Sin Markdown"""


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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=_marketplace_voice(car),
        messages=history + [{"role": "user", "content": text}],
    )

    reply = response.content[0].text
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

    if is_hot:
        print(f"\n🔥 MARKETPLACE HOT LEAD — {platform.upper()} | {sender_id[:12]}...")
        push_hot_lead(sender_id, platform, history)

    if is_declined:
        print(f"\n📋 SHOWROOM DECLINED — {platform.upper()} | {sender_id[:12]}...")
        print(f"   Carro: {car['yr']} Toyota {car['model']} {car.get('trim','')} {car['color']}")
        print(f"   Alejo debe contactar personalmente al (954) 310-6671")
        push_hot_lead(sender_id, platform, history)

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
