"""
CRM Client — NEXUS → crm.tucarroconalejo.com
Envía leads al CRM cuando el bot detecta HOT LEAD o captura datos de contacto.
"""
import os
import re
import json
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

CRM_WEBHOOK_URL = os.getenv("CRM_WEBHOOK_URL", "https://crm.tucarroconalejo.com/api/webhook/tucarro")
CRM_WEBHOOK_KEY = os.getenv("CRM_WEBHOOK_KEY", "crm-wh-k3y-2025-AutoXz9pLm")
CRM_AGENT_CODE  = os.getenv("CRM_AGENT_CODE", "alejo")
PAGE_ID         = os.getenv("META_PAGE_ID", "765862069934682")
IG_USER_ID      = os.getenv("META_IG_USER_ID", "17841476248130016")


def conversation_url(sender_id: str, platform: str) -> str:
    """Returns direct link to the conversation in Meta Business Suite.
    El chat del sitio web no vive en Meta — no hay link directo, solo la nota
    con el resumen generado por _build_crm_brief."""
    if platform == "web":
        return "Chat del sitio web (sin link directo — ver nota)"
    # Marketplace sale del perfil personal, no de la Página: su chat no está en
    # la bandeja de Business Suite. Es el mismo link que usan las alertas del
    # bot de Marketplace (marketplace_inbox_bot.py).
    if platform in ("marketplace_personal", "marketplace"):
        return f"https://www.messenger.com/marketplace/t/{sender_id}"
    asset_id = IG_USER_ID if platform == "instagram" else PAGE_ID
    return f"https://business.facebook.com/latest/inbox/all?asset_id={asset_id}&selected_item_id={sender_id}"


# Teléfono = disparador determinista del lead (decisión de Alejo, ago 2026). El
# patrón exige 10 dígitos agrupados 3-3-4 (US), así que horarios ("8:00 to 8:30")
# y fechas ("02 and September 4th" / "2026-08-24") NO se leen como teléfono.
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)")


def _detect_phone(text: str) -> str | None:
    """Devuelve el teléfono US normalizado (10 dígitos) si el texto contiene uno,
    o None. No depende de la IA — se usa como disparador y como respaldo cuando
    la extracción con Haiku no capturó el número que el cliente sí escribió."""
    if not text:
        return None
    m = _PHONE_RE.search(text)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None

_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def fetch_user_profile(sender_id: str, platform: str) -> dict:
    """Fetch public name and profile pic from Meta Graph API using sender_id."""
    token = os.getenv("META_PAGE_ACCESS_TOKEN")
    if not token or not sender_id:
        return {}
    try:
        # Facebook Messenger: sender_id is a PSID — can fetch name via Graph API
        if platform == "facebook":
            r = requests.get(
                f"https://graph.facebook.com/v19.0/{sender_id}",
                params={"fields": "first_name,last_name,profile_pic", "access_token": token},
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "first_name":   data.get("first_name"),
                    "last_name":    data.get("last_name"),
                    "profile_pic":  data.get("profile_pic"),
                }
        # Instagram: sender_id is an IGSID — name not always available
        elif platform == "instagram":
            r = requests.get(
                f"https://graph.facebook.com/v19.0/{sender_id}",
                params={"fields": "name,username", "access_token": token},
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json()
                name_parts = (data.get("name") or "").split(" ", 1)
                return {
                    "first_name": name_parts[0] if name_parts else None,
                    "last_name":  name_parts[1] if len(name_parts) > 1 else None,
                    "ig_username": data.get("username"),
                }
    except Exception as e:
        print(f"  ⚠️  CRM — profile fetch falló: {e}")
    return {}


def extract_lead_data(conversation_history: list, platform: str = "facebook") -> dict:
    """
    Uses Claude to extract structured lead data from the conversation history.
    Returns dict with whatever fields are detectable.
    """
    if not conversation_history:
        return {}

    convo_text = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in conversation_history[-20:]
    )

    response = _claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                f"Extrae datos de este chat de venta de carros. Alejo es asesor Toyota pero "
                f"también atiende trade-ins usados de otras marcas (Lexus, Mercedes, Nissan, etc.) — "
                f"usa 'vehicle_make' SOLO si el cliente mencionó una marca específica, si no déjalo null. "
                f"Responde SOLO con JSON válido, campos vacíos como null:\n\n"
                f"{convo_text}\n\n"
                f"Formato exacto:\n"
                f'{{"first_name":null,"last_name":null,"phone":null,"email":null,'
                f'"vehicle_make":null,"vehicle_model":null,"vehicle_year":null}}'
            )
        }]
    )

    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].split("```")[0].replace("json", "").strip()

    try:
        data = json.loads(text)
        data["source_platform"] = platform
        return {k: v for k, v in data.items() if v is not None}
    except Exception:
        return {"source_platform": platform}


def send_to_crm(lead_data: dict, conversation_summary: str = "") -> dict:
    """
    POSTs lead to crm.tucarroconalejo.com via webhook.
    Returns CRM response dict.
    """
    payload = {
        "agent_code":    CRM_AGENT_CODE,
        "vehicle_make":  "Toyota",
        **lead_data,
    }
    if conversation_summary:
        payload["notes"] = conversation_summary[:2000]

    try:
        resp = requests.post(
            CRM_WEBHOOK_URL,
            json=payload,
            headers={
                "X-Api-Key":    CRM_WEBHOOK_KEY,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        result = resp.json()
        if result.get("success"):
            print(f"  📋 CRM — Lead creado. ID: {result.get('lead_id')}")
        else:
            print(f"  ⚠️  CRM — Error: {result}")
        return result
    except Exception as e:
        print(f"  ⚠️  CRM — No se pudo enviar: {e}")
        return {"error": str(e)}


# Canal que el CRM muestra por fuera en cada tarjeta (ver lead_intake.php).
CRM_CHANNELS = {
    "marketplace_personal": "marketplace", "marketplace": "marketplace",
    "facebook": "facebook", "instagram": "instagram", "web": "web",
}
BUYER_PROFILES = ("Analítico", "Emocional", "Desconfiado", "Impulsivo", "Negociador")
BUYER_STATES   = ("Explorando", "Interesado", "Considerando", "Decidido", "Urgente")
# Con menos mensajes del cliente que esto, un perfil es adivinar: la IA tiene
# que escoger uno aunque el chat sea "hola / ¿precio? / mi número es…", y un
# "Desconfiado" inventado predispone al asesor. Mejor no mostrar nada.
MIN_CLIENT_MSGS_FOR_PROFILE = 4


def _build_crm_brief(conversation_history: list, platform: str, name: str,
                     make: str, model: str, trim: str, ref: str | None = None) -> dict:
    """Nota corta para el asesor + perfil y estado del comprador, en UNA llamada.

    La nota tiene siempre la misma forma — Quiere / Situación / Cómo abrirle —
    para que el asesor la lea de un vistazo. El canal, el perfil y el link al
    chat NO van en la nota: el CRM los muestra por fuera de la tarjeta.
    Devuelve {"note", "buyer_profile", "buyer_state"} (los dos últimos o None).
    """
    carro = " ".join(x for x in (make, model, trim) if x and x != "no especificado").strip()
    fallback = {"note": f"Quiere: {carro or 'no lo dijo'}", "buyer_profile": None, "buyer_state": None}
    head = f"Llegó por el anuncio: {ref}\n" if ref else ""
    if not conversation_history:
        fallback["note"] = head + fallback["note"]
        return fallback

    transcript = "".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}\n"
        for m in conversation_history[-16:]
    )
    prompt = (
        "Eres asistente de un equipo de ventas Toyota. Lee este chat y prepara al asesor "
        "que va a llamar al cliente. Responde SOLO con JSON válido:\n"
        "{\n"
        '  "quiere": "modelo que le interesa y precio o presupuesto hablado (enganche si lo dijo)",\n'
        '  "situacion": "primera vez, trade-in, crédito, familia, trabajo — lo que se sepa, corto",\n'
        '  "como_abrirle": "1 oración: con qué empezar la llamada según lo que mostró en el chat",\n'
        '  "perfil": "Analítico|Emocional|Desconfiado|Impulsivo|Negociador, o null si el chat no da para saberlo",\n'
        '  "estado": "Explorando|Interesado|Considerando|Decidido|Urgente, o null si no se sabe"\n'
        "}\n"
        "Cada campo en una línea corta, en español, sin introducciones. Si algo no se sabe, "
        "escribe \"no lo dijo\" — no inventes.\n\n"
        f"CLIENTE: {name}\nCARRO DEL ANUNCIO: {carro or 'ninguno'}\n"
        f"CONVERSACIÓN:\n{transcript}"
    )
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0].replace("json", "").strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"la IA no devolvió un objeto JSON: {type(data).__name__}")
    except Exception as e:
        print(f"  ⚠️  CRM — no se pudo armar la nota con IA: {e}")
        fallback["note"] = head + fallback["note"]
        return fallback

    def campo(k, vacio):
        v = data.get(k)
        return str(v).strip() if isinstance(v, (str, int, float)) and str(v).strip() else vacio

    note = head + (
        f"Quiere: {campo('quiere', 'no lo dijo')}\n"
        f"Situación: {campo('situacion', 'no lo dijo')}\n"
        f"Cómo abrirle: {campo('como_abrirle', '—')}"
    )
    client_msgs = sum(1 for m in conversation_history if m.get("role") == "user")
    enough = client_msgs >= MIN_CLIENT_MSGS_FOR_PROFILE
    profile = data.get("perfil") if enough and data.get("perfil") in BUYER_PROFILES else None
    state = data.get("estado") if enough and data.get("estado") in BUYER_STATES else None
    return {"note": note, "buyer_profile": profile, "buyer_state": state}


def _clean_sender_name(sender_name: str) -> str:
    """El nombre real de Marketplace viene como 'Kimonia · 2025 Nissan Altima'
    (nombre + separador + año/marca/modelo del listing) — nos quedamos solo
    con el nombre. Si el sidebar dio un ID numérico en vez del nombre (pasa
    a veces, ver _get_car_context), lo descartamos en vez de guardar basura."""
    if not sender_name:
        return ""
    name = sender_name.split("·")[0].strip()
    return "" if not name or name.isdigit() else name


def _missing_required(name: str, phone: str) -> list[str]:
    """Qué falta para poder crear el lead en el CRM.

    El mínimo es el TELÉFONO y SOLO el teléfono (decisión de Alejo, ago 2026):
    es el único dato que hace al lead accionable. El nombre NO bloquea — la
    tabla `leads` lo acepta nulo y el Kanban muestra "Sin nombre", que es un
    problema de cosmética, no de negocio.

    Antes exigía ambos y eso contradecía la decisión escrita dos líneas más
    abajo: en sep 2026 se perdieron 7 leads CON teléfono real porque el bot no
    tenía el nombre a mano (ver `_resolve_sender_name` en marketplace_inbox_bot).
    """
    return [] if phone else ["teléfono"]


def push_hot_lead(sender_id: str, platform: str, conversation_history: list,
                  car: dict | None = None, ref: str | None = None,
                  sender_name: str = "") -> dict:
    """
    Full flow: extract data from conversation → send to CRM.
    First HOT_LEAD: crea la entrada en el CRM y avisa por WhatsApp UNA vez.
    Siguientes veces: no vuelve a avisar por WhatsApp (pedido explícito de
    Alejo, ago 2026 — el criterio de [HOT LEAD] en el prompt es amplio
    (teléfono, financiamiento, "quiere venir") y sin este guard cada mensaje
    de una conversación normal disparaba un WhatsApp nuevo, aunque no hubiera
    pasado nada realmente nuevo). Una cita CONFIRMADA sigue avisando aparte,
    vía appointments.create_appointment() — ese es el evento que sí importa
    después del primer contacto.
    """
    import json as _json, os as _os
    _activity_file = _os.path.join(_os.path.dirname(__file__), "leads_activity.json")
    try:
        with open(_activity_file, encoding="utf-8") as f:
            _activity = _json.load(f)
    except Exception:
        _activity = {}

    already_sent = _activity.get(sender_id, {}).get("crm_sent", False)

    if already_sent:
        print(f"  📋 CRM — Lead ya existe, sin notificación nueva (ya avisado una vez).")
        return {"ok": True, "skipped": True}

    print(f"\n  📋 NEXUS → CRM: extrayendo datos del lead...")
    # 1. Fetch public profile from Meta (name, pic) — fast, no AI needed
    profile = fetch_user_profile(sender_id, platform)
    # 2. Extract remaining fields from conversation with AI
    lead_data = extract_lead_data(conversation_history, platform)
    # 3. Profile data takes priority over AI extraction (more reliable)
    lead_data = {**lead_data, **{k: v for k, v in profile.items() if v}}

    # If we know the exact car (Marketplace), override AI-extracted vehicle fields
    if car:
        # Marca real del listing (Alejo también atiende trade-ins usados de otras
        # marcas: Lexus, Mercedes, Nissan). Sin esto el lead decía "Toyota" siempre.
        if car.get("make"):
            lead_data["vehicle_make"] = car["make"]
        lead_data["vehicle_model"] = car.get("model", lead_data.get("vehicle_model"))
        lead_data["vehicle_year"]  = str(car.get("yr", lead_data.get("vehicle_year", "")))
        lead_data["vehicle_trim"]  = car.get("trim", "")
        lead_data["vehicle_color"] = car.get("color", "")
        lead_data["vehicle_vin"]   = car.get("vin", "")
        lead_data["down_payment"]  = car.get("down_payment", "")

    name  = " ".join(filter(None, [lead_data.get("first_name"), lead_data.get("last_name")])).strip()
    # Respaldo confiable cuando el perfil de Meta no aplica (Marketplace,
    # platform="marketplace_personal") y la IA no encontró nombre en el
    # texto: el nombre real de Facebook que el bot ya leyó del sidebar.
    if not name:
        name = _clean_sender_name(sender_name)
    phone = (lead_data.get("phone") or "").strip()
    # Respaldo determinista: si Haiku no extrajo el teléfono pero el cliente sí
    # lo escribió en algún mensaje, recuperarlo con regex. El teléfono es el
    # mínimo que habilita crear el lead (ver guard abajo), así que no puede
    # depender solo de la IA (bug: cliente da su número y el lead nunca se crea).
    if not phone:
        for _m in conversation_history:
            if _m.get("role") == "user":
                _p = _detect_phone(_m.get("content", ""))
                if _p:
                    phone = _p
                    break
    # `name` y `phone` se calcularon arriba combinando perfil de Meta, extracción
    # con IA, el nombre del sidebar de Facebook y el regex de teléfono. Hasta aquí
    # solo alimentaban el guard de datos mínimos, el WhatsApp de Pulse y la nota —
    # nunca volvían al payload, así que el CRM recibía el lead sin first_name (y
    # sin phone cuando lo había recuperado el regex) y el Kanban mostraba
    # "Sin nombre" aunque el bot lo tuviera. Se sincronizan antes de enviar.
    if name and not lead_data.get("first_name"):
        _first, _, _last = name.partition(" ")
        lead_data["first_name"] = _first
        if _last.strip():
            lead_data["last_name"] = _last.strip()
    if phone:
        lead_data["phone"] = phone

    make  = lead_data.get("vehicle_make") or "Toyota"
    model = lead_data.get("vehicle_model", "no especificado")
    trim  = lead_data.get("vehicle_trim", "")
    conv_url = conversation_url(sender_id, platform)

    # Mínimo para CRM: TELÉFONO real (decisión de Alejo, ago 2026). El bot marca
    # [HOT LEAD] con señales amplias (confirma visita, pregunta financiamiento,
    # emoji, etc.) y el nombre casi siempre está disponible vía perfil de Meta o
    # el nombre de Facebook del sidebar — así que exigir solo nombre creaba un
    # lead por casi cualquier conversación, sin dato accionable de contacto
    # (bug real: "monta leads sin los mínimos"). Un lead sin teléfono no es
    # accionable; se avisa a Alejo una vez por WhatsApp y se espera al teléfono.
    # (Las citas confirmadas — el otro camino válido — ahora también exigen
    # teléfono, así que ese flujo entra por aquí con teléfono presente.)
    missing = _missing_required(name, phone)
    if not name:
        # El nombre NO bloquea. Un lead sin nombre se arregla en 10 segundos
        # mirando el chat; uno que nunca entró al CRM se pierde entero.
        print("  📋 CRM — Lead sin nombre, se crea igual (el mínimo es el teléfono).")
    if missing:
        # Sin teléfono el lead NUNCA llega a crearse en CRM, así que
        # crm_sent nunca queda True — sin este guard, cada [HOT LEAD] repetido
        # en la misma conversación volvía a mandar WhatsApp para siempre. Se
        # avisa una sola vez por sender_id, con su propio flag.
        if _activity.get(sender_id, {}).get("incomplete_alert_sent", False):
            print(f"  📋 CRM — Lead incompleto (falta {', '.join(missing)}), ya avisado antes, sin notificación nueva.")
            return {"ok": True, "skipped": True, "reason": "incomplete_data", "missing": missing}
        print(f"  ⚠️  CRM — Lead incompleto (falta {', '.join(missing)}) — NO se crea en CRM aún")
        from pulse import pulse_notify
        pulse_notify(
            event="HOT_LEAD",
            detail=(
                f"🔥 Señal de interés — falta {', '.join(missing)} para registrar en CRM\n"
                f"Nombre: {name or '—'} | Tel: {phone or '—'}\n"
                f"Canal: {platform.upper()}\n"
                f"Chat: {conv_url}"
            )
        )
        try:
            _activity[sender_id] = {**_activity.get(sender_id, {}), "incomplete_alert_sent": True}
            with open(_activity_file, "w", encoding="utf-8") as f:
                _json.dump(_activity, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  ⚠️  CRM — No se pudo marcar incomplete_alert_sent: {e}")
        return {"ok": True, "skipped": True, "reason": "incomplete_data", "missing": missing}

    print(f"  Nombre: {name or '—'} | Tel: {phone} | Carro: {lead_data.get('vehicle_year','')} {make} {model} {trim}")
    print(f"  Conversación: {conv_url}")

    # WhatsApp notification includes direct link
    from pulse import pulse_notify
    pulse_notify(
        event="HOT_LEAD",
        detail=(
            f"Cliente: {name}\n"
            f"Tel: {phone}\n"
            f"Carro: {lead_data.get('vehicle_year','')} {make} {model} {trim}\n"
            f"Canal: {platform.upper()}\n"
            f"Chat: {conv_url}"
        )
    )

    lead_data["link"]             = conv_url
    lead_data["source_url"]       = conv_url

    brief = _build_crm_brief(conversation_history, platform, name, make, model, trim, ref)
    lead_data["channel"] = CRM_CHANNELS.get(platform)
    lead_data["buyer_profile"] = brief["buyer_profile"]
    lead_data["buyer_state"] = brief["buyer_state"]
    if conv_url.startswith("https://"):
        lead_data["conversation_link"] = conv_url

    result = send_to_crm(lead_data, brief["note"])

    # Mark as sent so future HOT_LEAD signals don't create duplicate CRM entries
    if result.get("success") or result.get("ok"):
        try:
            _activity[sender_id] = {**_activity.get(sender_id, {}), "crm_sent": True}
            with open(_activity_file, "w", encoding="utf-8") as f:
                _json.dump(_activity, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  ⚠️  CRM — No se pudo marcar crm_sent: {e}")

    return result
