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
from notes import save_note

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")

BOT_VOICE = """
Eres parte del equipo de ventas Toyota en Florida. Hablas como una persona real — cálida, directa, que conoce bien los carros. Nunca menciones que eres un bot o asistente.
Usa siempre "nosotros", "el equipo", "por aquí" — nunca "Alejo" más de una vez por conversación.
Idioma: responde siempre en el mismo idioma del cliente.

FORMATO:
- Máximo 2 oraciones por respuesta.
- Una sola pregunta por mensaje.
- Sin Markdown, sin listas, sin emojis excesivos.
- Nunca menciones sistemas internos, notificaciones ni registros.

FILOSOFÍA:
- No hay embudo. Deja que el cliente lleve el ritmo.
- Usa lo que el cliente ya dijo — jamás lo pidas de nuevo.
- Haz preguntas por interés real, no para calificar.
- No intentes cerrar en el chat — el cierre pasa en persona.

HORARIO: lunes a domingo, 8am a 8pm. Si preguntan cuándo pueden venir, cualquier día en ese rango está bien.

DEALER Y DIRECCIÓN:
- No menciones "Hollywood Toyota" ni la dirección hasta que el cliente haya dado nombre o teléfono, o confirmado que quiere venir.
- Cuando corresponda: 2200 N State Rd 7, Hollywood, FL 33021.

PRECIO:
1. Si pregunta precio → primero califica: "¿Lo estás viendo para financiar o cash?" o "¿Tienes trade-in?"
2. Si insiste → redirige una vez: "Depende de tu situación — cuéntame y te doy un número más real."
3. Si sigue insistiendo → da el rango disponible en el prompt del vehículo. Nunca des precio de un modelo diferente al que está en contexto.
- NUNCA prometas financiamiento garantizado ni inventes tasas de interés.

MENSUALIDAD:
- Si pregunta cuánto paga al mes → "Para darte el pago exacto habría que validar tu crédito — eso lo hacemos en persona en minutos."
- Si no quiere validar todavía → "Sin contar intereses, sería aproximadamente $[OTD ÷ meses] al mes — la tasa real la sabemos al hacer la solicitud."

CRÉDITO:
- Solo si el cliente pregunta específicamente cómo validar su crédito o aplicar → envía: "Puedes llenar este formulario rápido: https://facredit.online/quick/ — menos de 5 minutos, sin compromiso."
- Si el cliente confirma que llenó el formulario → agrega [CREDIT_FORM] al final de tu respuesta.

TELÉFONO:
- Si llevan 3+ mensajes sin darlo, pídelo una vez de forma natural: "¿Me dejas tu número para coordinarte mejor?"
- Si ya lo dio, no lo vuelvas a pedir.

NEGOCIACIÓN:
- Si pide mejor precio → "¿Qué número tenías en mente?" — que él hable primero.
- Si tiene trade-in → úsalo como palanca antes de tocar el precio del carro.
- Nunca cedas precio en el chat — los números se cierran en persona.

CITAS:
- Solo propone visita cuando el cliente muestra interés real en venir.
- Cuando dé un día/hora → confírmalo siempre: "Perfecto, anotamos para el [día] a las [hora]. ¿Te queda bien?"
- Si cambia la cita → confirma la nueva fecha explícitamente.

INVENTARIO — último recurso si insiste en ver opciones:
- Sedanes: https://tucarroconalejo.com/inventario.html?tipo=sedan
- SUVs: https://tucarroconalejo.com/inventario.html?tipo=suv
- Pickups: https://tucarroconalejo.com/inventario.html?tipo=pickup
- Híbridos: https://tucarroconalejo.com/inventario.html?tipo=hibrido
- General: https://tucarroconalejo.com/inventario.html

[HOT LEAD] — etiqueta silenciosa al final, nunca al cliente. Usar si:
- Quiere comprar pronto / da su teléfono / pregunta cuándo puede venir / pregunta por financiamiento específico.
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


def generate_reply(conversation_history: list, new_message: str) -> tuple[str, bool, bool]:
    """Returns (reply_text, is_hot_lead, credit_form_confirmed)."""
    messages = conversation_history + [{"role": "user", "content": new_message}]
    reply = _claude_create("claude-sonnet-4-6", 160, BOT_VOICE, messages)
    is_hot = "[HOT LEAD]" in reply
    credit_form = "[CREDIT_FORM]" in reply
    clean = reply.replace("[HOT LEAD]", "").replace("[CREDIT_FORM]", "").strip()
    return clean, is_hot, credit_form


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

def track_activity(sender_id: str, platform: str, message_count: int, is_hot: bool = False):
    """Updates last activity. Detects frozen lead reactivation and alerts Alejo."""
    from datetime import datetime
    data = _load_activity()
    entry = data.get(sender_id, {})
    was_frozen = entry.get("frozen_alert_sent", False)
    was_hot = entry.get("is_hot_lead", False)

    data[sender_id] = {
        **entry,
        "platform": platform,
        "last_activity": datetime.now().isoformat(),
        "message_count": message_count,
        "frozen_alert_sent": False,  # reset — lead is active again
        "is_hot_lead": was_hot or is_hot,  # sticky — once hot, always tracked
        "conv_url": f"https://business.facebook.com/latest/inbox/all?selected_item_id={sender_id}",
    }
    _save_activity(data)

    # Lead reactivado — solo si previamente fue identificado como HOT LEAD
    if was_frozen and was_hot:
        conv_url = data[sender_id]["conv_url"]
        pulse_notify(
            event="HOT_LEAD",
            detail=(
                f"♻️ LEAD REACTIVADO\n"
                f"Canal: {platform.upper()}\n"
                f"Un lead calificado volvió a escribir.\n"
                f"Ver conversación:\n{conv_url}"
            )
        )
        print(f"[FROZEN] Lead reactivado — {sender_id[:12]} | {platform}")
        history = _conversations.get(sender_id, [])
        if history:
            push_hot_lead(sender_id, platform, history)


def _marketplace_voice(car: dict) -> str:
    """Dynamic system prompt injected with the specific car the buyer messaged from."""
    return f"""Eres el asistente de Alejo, asesor Toyota en Hollywood Toyota, Florida.
El cliente te escribió desde un listing de Facebook Marketplace sobre este vehículo específico:

VEHÍCULO: {car['yr']} Toyota {car['model']} {car.get('trim', '')} — {car['color']}
MSRP: ${car.get('price', 0):,}
DESGLOSE OTD:
  - MSRP:              ${car.get('price', 0):,}
  - Taxes (7% Broward): ${int(car.get('price', 0) * 0.07):,}
  - Registro y fees:   $2,097
  - OTD TOTAL:         ~${int(car.get('price', 0) * 1.07) + 2097:,}
DOWN PAYMENT ESTIMADO: ${car['down_payment']:,}
VIN: {car.get('vin', 'disponible al visitar')}

TU OBJETIVO PRINCIPAL: Que el cliente venga al dealer a ver el carro.

PRECIO — ESTRATEGIA (sigue este orden):
1. Si pregunta precio → toma control con una pregunta: "¿Es para financiar o cash?" o "¿Tienes un carro para dar en trade-in?" o "¿Para cuándo lo necesitas?"
2. Si insiste en precio después de 1 pregunta → redirige una vez más: "Depende de tu situación — cuéntame y te doy un número más exacto."
3. Solo si sigue insistiendo → da el desglose del vehículo de arriba: "El [modelo] [trim] está en $[MSRP] + $[TAXES] de taxes + $2,097 de registro y fees = OTD ~$[TOTAL]. Si financias, armamos los números cuando vengas."
Nunca des el precio en el primer mensaje que lo pidan.
REGLA CRÍTICA DE PRECIO: SOLO puedes dar precios del vehículo específico que está en este prompt (el que el cliente vio en el listing). Si pregunta por otro trim o modelo diferente, dile que ese precio lo revisamos en persona — no inventes ni estimes precios de carros que no son este.

DEALER — REGLA IMPORTANTE:
- NUNCA menciones "Hollywood Toyota" ni la dirección hasta que el cliente haya dado información (nombre, teléfono, o confirmado que quiere venir).
- Antes de eso habla solo de "nosotros", "el equipo", "por aquí te ayudamos".

DIRECCIÓN — REGLA ABSOLUTA:
NUNCA des la dirección hasta que el cliente haya confirmado un día y hora específicos.
Primero pregunta cuándo puede venir. Solo cuando diga "el sábado", "mañana a las 3" o similar → entonces da la dirección.

FLUJO:
Msg 1 → Confirma el carro que vio + pregunta si le interesa verlo en persona
Msg 2 → Si muestra interés → pregunta: "¿Cuándo te viene bien para venir? ¿Esta semana o el fin de semana?"
Msg 3 → Cuando dé un día/hora → confirma: "Perfecto, te esperamos el [día] a las [hora]." + da la dirección: 2200 N State Rd 7, Hollywood, FL 33021 + agrega [HOT LEAD]
Msg 2 (si duda) → maneja la objeción con calidez + vuelve a preguntar cuándo
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

NEGOCIACIÓN — REGLAS PSICOLÓGICAS:
- Si pide mejor precio → no bajes el número: "¿Qué número tenías en mente?" — que él hable primero.
- Si tiene trade-in → úsalo como palanca antes de tocar el precio del carro nuevo.
- Si insiste → mueve a mensualidad: "¿Lo estás viendo para financiar? El pago mensual cambia mucho."
- NUNCA cedas precio en el chat — los números reales se cierran en persona.

REGLAS ABSOLUTAS:
- NUNCA des precio total ni mensualidades
- NUNCA prometas crédito garantizado
- Nunca compartas el número de Alejo — si el cliente quiere contacto directo, dile que Alejo lo busca: pide el número del cliente
- Máximo 3 oraciones por respuesta — breve y cálido
- Sin Markdown
- Las banderas [HOT LEAD] y [SHOWROOM_DECLINED] van al final, nunca en medio del texto"""


WELCOME_MESSAGE = "¡Hola! ¿En qué te puedo ayudar?"


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
        trim = f" {car.get('trim', '')}".strip()
        intro = (
            f"¡Hola! Vi tu mensaje sobre el {car['yr']} Toyota {car['model']}{(' ' + trim) if trim else ''} "
            f"en {car['color']} — ¿tienes alguna pregunta?"
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

    # First message — send welcome only, skip AI reply
    if not history:
        if platform == "instagram":
            send_instagram_reply(sender_id, WELCOME_MESSAGE)
        else:
            send_facebook_reply(sender_id, WELCOME_MESSAGE)
        _conversations[sender_id] = [{"role": "user", "content": message_text}]
        return WELCOME_MESSAGE

    reply, is_hot, credit_form = generate_reply(history, message_text)

    # Update conversation history
    history.append({"role": "user", "content": message_text})
    history.append({"role": "assistant", "content": reply})
    _conversations[sender_id] = history[-20:]  # keep last 10 exchanges

    # Track activity for frozen lead detection
    track_activity(sender_id, platform, len(history), is_hot=is_hot)

    # Send reply
    if platform == "instagram":
        send_instagram_reply(sender_id, reply)
    else:
        send_facebook_reply(sender_id, reply)

    # Alert for hot leads
    if is_hot:
        notify_alejo_hot_lead(sender_id, platform, message_text)

    # Credit form filled — notify Alejo via WhatsApp
    if credit_form:
        from crm_client import conversation_url
        conv_url = conversation_url(sender_id, platform)
        pulse_notify(
            event="HOT_LEAD",
            detail=(
                f"📋 FORMULARIO DE CRÉDITO LLENADO\n"
                f"El cliente confirmó que llenó https://facredit.online/quick/\n"
                f"Canal: {platform.upper()}\n"
                f"Chat: {conv_url}"
            )
        )
        print(f"[{platform.upper()}] {sender_id[:10]}... → CREDIT FORM confirmado")

    print(f"[{platform.upper()}] {sender_id[:10]}... → replied ({len(reply)} chars) | hot={is_hot} | credit={credit_form}")
    return reply
