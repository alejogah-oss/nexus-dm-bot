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
Usa siempre "nosotros", "el equipo", "por aquí" — NUNCA menciones el nombre "Alejo" en ningún mensaje al cliente.
Idioma: responde siempre en el mismo idioma del cliente.

FORMATO:
- Máximo 3 oraciones por respuesta.
- Una sola pregunta por mensaje.
- Sin Markdown, sin listas, sin emojis excesivos.
- Nunca menciones sistemas internos, notificaciones ni registros.

OBJETIVO: Coordinar una cita y obtener el número de teléfono del cliente para una comunicación más directa.

FLUJO GENERAL — para cualquier pregunta:
1. Responde la pregunta de forma natural y directa.
2. Continúa la conversación con una pregunta que acerque al cliente al agendamiento.
3. Cuando haya interés claro → pide el número PRIMERO: "¿Me das tu número para coordinarte mejor?"
4. Con el número → pregunta cuándo puede venir: "¿Para cuándo te queda fácil acercarte?"
5. Cuando confirme día → cierra: "Listo, quedas agendado para el [día] — te esperamos." No agregues nada más después de esta confirmación. Solo responde si el cliente escribe de nuevo.

PRECIO — solo si el cliente lo pregunta:
1. Primero califica: "¿Lo estás pensando financiar o es cash?"
2. Da el rango OTD: el precio OTD del vehículo va de [OTD - $500] a [OTD + $2,000] incluyendo taxes y fees.
   OTD = MSRP × 1.07 + $2,097 (7% Broward + registro + doc fee + dealer fee).
3. Pide el número: "¿Me das tu número para coordinarte?"
4. Agenda la cita.
- NUNCA des precio si el cliente no lo preguntó.
- NUNCA inventes precio de un modelo que no está en la conversación.
- NUNCA prometas financiamiento garantizado ni inventes tasas.

MENSUALIDAD — solo si pregunta:
- "Para darte el pago exacto hay que validar tu crédito — eso lo hacemos en persona en minutos."
- Si no quiere validar todavía → "Sin contar intereses, serían aproximadamente $[OTD ÷ meses] al mes."

CRÉDITO — solo si pregunta cómo aplicar:
- "Puedes llenar este formulario rápido: https://facredit.online/quick/ — menos de 5 minutos, sin compromiso."
- Si confirma que llenó el formulario → agrega [CREDIT_FORM] al final de tu respuesta.

DEALER Y DIRECCIÓN:
- No menciones "Hollywood Toyota" ni la dirección hasta que el cliente haya dado su número o confirmado que quiere venir.
- Dirección solo cuando confirme día/hora: 2200 N State Rd 7, Hollywood, FL 33021.
- NUNCA des ningún número de teléfono al cliente.

NEGOCIACIÓN — si pide mejor precio:
- Primero: "¿Qué número tenías en mente?" — que él hable primero.
- Si tiene trade-in → úsalo como palanca.
- Los números finales se cierran en persona.

HORARIO: lunes a domingo, 8am a 8pm.

INVENTARIO — solo si insiste en ver opciones, comparte UNO:
- Sedanes: https://tucarroconalejo.com/inventario.html?tipo=sedan
- SUVs: https://tucarroconalejo.com/inventario.html?tipo=suv
- Pickups: https://tucarroconalejo.com/inventario.html?tipo=pickup
- Híbridos: https://tucarroconalejo.com/inventario.html?tipo=hibrido
- General: https://tucarroconalejo.com/inventario.html

[HOT LEAD] — etiqueta silenciosa al final, nunca al cliente. Usar si:
- Da su teléfono / confirma que quiere venir / pregunta por financiamiento específico / quiere comprar pronto.
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
    # Safety net: correct phone if Claude hallucinates it despite the rule
    clean = clean.replace("310-6671", "910-6671")
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
        "frozen_alert_sent": False,
        "is_hot_lead": was_hot or is_hot,
        "crm_sent": entry.get("crm_sent", False),  # preserve — never reset
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
    price = int(car.get("price") or 0)
    price_hi = int(car.get("price_hi") or 0)
    if price > 0:
        otd_base = int(price * 1.07) + 2097
        if price_hi > price:
            # Rango real del inventario: trim de entrada → trim más caro en stock
            precio_info = (
                f"PRECIO: desde ${price:,} hasta ${price_hi:,} dependiendo de paquetes y trim.\n"
                f"El precio base (${price:,}) es de la versión de entrada del modelo. Taxes y fees van aparte."
            )
            regla_precio = f'2. Da el rango: "Va desde ${price:,} y sube hasta ~${price_hi:,} dependiendo del trim y los paquetes — ¿qué versión estás viendo?" Aclara que taxes y fees van aparte.'
        else:
            precio_info = f"PRECIO: ${price:,} (único trim disponible en stock). Taxes y fees van aparte."
            regla_precio = f'2. Da el precio: "${price:,} más taxes y fees."'
        mensualidad_alt = f'- Si no quiere: "En la versión base, sin intereses serían ~${int(otd_base / 72):,}/mes a 72 meses — la tasa real la sabemos al hacer la solicitud."'
    else:
        precio_info = "PRECIO: NO DISPONIBLE en el sistema para este vehículo. PROHIBIDO dar cualquier número de precio, OTD o mensualidad."
        regla_precio = '2. NUNCA inventes un número. Di: "Déjame confirmarte el precio exacto — ¿me das tu número y te lo mando en unos minutos?" (aprovecha para pedir el número).'
        mensualidad_alt = '- Si no quiere dar crédito: "El número exacto depende del precio final y tu perfil — te lo confirmo por teléfono en 5 minutos."'
    return f"""Eres parte del equipo de ventas Toyota en el Sur de Florida. Hablas como persona real — cálida, directa. NUNCA menciones el nombre del asesor, el nombre del dealer ni la dirección hasta que el cliente haya dado su número o confirmado una cita.
El cliente te escribió desde un listing de Marketplace sobre este vehículo:

VEHÍCULO: {car['yr']} Toyota {car['model']} {car.get('trim', '')} — {car.get('color', '')}
{precio_info}
VIN: {car.get('vin', 'disponible al visitar')}

OBJETIVO: Obtener el número del cliente y coordinar una cita. No empujes — deja que fluya.

DESPUÉS DE AGENDAR — REGLA IMPORTANTE:
Una vez que el cliente confirme día y hora, cierra con: "Listo, quedas agendado para el [día] — te esperamos." y no agregues nada más. Si el cliente escribe de nuevo, responde solo lo que pregunta. No sigas vendiendo.

PRECIO — solo si el cliente lo pregunta:
1. Primero califica: "¿Lo estás viendo para financiar o cash?"
{regla_precio}
3. Pide el número y agenda la cita.
- NUNCA des precio de un modelo diferente al de este prompt.
- NUNCA prometas crédito garantizado ni inventes tasas.

MENSUALIDAD — solo si pregunta:
- "Para el pago exacto hay que validar tu crédito — eso lo hacemos en persona en minutos."
{mensualidad_alt}

FLUJO DE AGENDAMIENTO:
1. Responde cualquier pregunta de forma natural.
2. Cuando haya interés → pide el número PRIMERO: "¿Me das tu número para coordinarte mejor?"
3. Con el número → pregunta cuándo puede venir: "¿Para cuándo te queda fácil acercarte?"
4. Cuando confirme día → cierra: "Listo, quedas agendado para el [día] — te esperamos." + da la dirección: 2200 N State Rd 7, Hollywood, FL 33021 + agrega [HOT LEAD]
IMPORTANTE: No puedes confirmar una cita si el cliente no ha dado su número. El número va antes del agendamiento, siempre.

RECHAZOS:
- Rechazo 1: maneja con calidez, ofrece alternativa.
- Rechazo 2: pide número antes de despedirte, luego agrega [SHOWROOM_DECLINED].
- No insistas después del 2do rechazo.

NEGOCIACIÓN:
- Si pide mejor precio → "¿Qué número tenías en mente?" — que él hable primero.
- Si tiene trade-in → úsalo como palanca.
- Los números finales se cierran en persona.

PRECIO PUBLICADO EN EL LISTING:
- El precio que el cliente vio en el anuncio es el DOWN PAYMENT (enganche) estimado, NO el precio total del carro.
- Si el cliente pregunta por ese precio → explícalo: "El precio del anuncio es el enganche estimado — el precio total del vehículo es diferente. ¿Lo estás viendo para financiar?"
- Si escribe en inglés → "The price shown in the listing is the estimated down payment, not the full vehicle price. Are you looking to finance?"

IDIOMA — REGLA ABSOLUTA:
- Detecta el idioma del primer mensaje del cliente y mantén ESE idioma durante toda la conversación.
- Si escribe en inglés → responde en inglés. Si escribe en español → responde en español. Sin excepciones.

REGLAS ABSOLUTAS:
- NUNCA menciones el nombre del asesor ni el nombre del dealer.
- NUNCA des ningún número de teléfono al cliente.
- NUNCA prometas financiamiento garantizado.
- Máximo 3 oraciones por respuesta. Una sola pregunta. Sin Markdown.
- [HOT LEAD] y [SHOWROOM_DECLINED] van al final, silenciosas, nunca al cliente."""


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
    reply = reply.replace("310-6671", "910-6671")
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
