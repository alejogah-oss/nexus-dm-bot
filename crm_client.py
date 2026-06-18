"""
CRM Client — NEXUS → crm.tucarroconalejo.com
Envía leads al CRM cuando el bot detecta HOT LEAD o captura datos de contacto.
"""
import os
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
    """Returns direct link to the conversation in Meta Business Suite."""
    asset_id = IG_USER_ID if platform == "instagram" else PAGE_ID
    return f"https://business.facebook.com/latest/inbox/all?asset_id={asset_id}&selected_item_id={sender_id}"

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
                f"Extrae datos de este chat de venta de carros. "
                f"Responde SOLO con JSON válido, campos vacíos como null:\n\n"
                f"{convo_text}\n\n"
                f"Formato exacto:\n"
                f'{{"first_name":null,"last_name":null,"phone":null,"email":null,'
                f'"vehicle_make":"Toyota","vehicle_model":null,"vehicle_year":null}}'
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
        payload["notes"] = conversation_summary[:500]

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


def push_hot_lead(sender_id: str, platform: str, conversation_history: list,
                  car: dict | None = None) -> dict:
    """
    Full flow: extract data from conversation → send to CRM.
    car: optional Marketplace listing dict (yr, model, trim, color, vin, down_payment).
    Called automatically when bot detects HOT LEAD signal.
    """
    print(f"\n  📋 NEXUS → CRM: extrayendo datos del lead...")
    # 1. Fetch public profile from Meta (name, pic) — fast, no AI needed
    profile = fetch_user_profile(sender_id, platform)
    # 2. Extract remaining fields from conversation with AI
    lead_data = extract_lead_data(conversation_history, platform)
    # 3. Profile data takes priority over AI extraction (more reliable)
    lead_data = {**lead_data, **{k: v for k, v in profile.items() if v}}

    # If we know the exact car (Marketplace), override AI-extracted vehicle fields
    if car:
        lead_data["vehicle_model"] = car.get("model", lead_data.get("vehicle_model"))
        lead_data["vehicle_year"]  = str(car.get("yr", lead_data.get("vehicle_year", "")))
        lead_data["vehicle_trim"]  = car.get("trim", "")
        lead_data["vehicle_color"] = car.get("color", "")
        lead_data["vehicle_vin"]   = car.get("vin", "")
        lead_data["down_payment"]  = car.get("down_payment", "")

    name  = " ".join(filter(None, [lead_data.get("first_name"), lead_data.get("last_name")])) or "Sin nombre"
    phone = lead_data.get("phone", "no capturado")
    model = lead_data.get("vehicle_model", "no especificado")
    trim  = lead_data.get("vehicle_trim", "")
    conv_url = conversation_url(sender_id, platform)
    print(f"  Nombre: {name} | Tel: {phone} | Carro: {lead_data.get('vehicle_year','')} Toyota {model} {trim}")
    print(f"  Conversación: {conv_url}")

    # WhatsApp notification includes direct link
    from pulse import pulse_notify
    pulse_notify(
        event="HOT_LEAD",
        detail=(
            f"Cliente: {name}\n"
            f"Tel: {phone}\n"
            f"Carro: {lead_data.get('vehicle_year','')} Toyota {model} {trim}\n"
            f"Canal: {platform.upper()}\n"
            f"Chat: {conv_url}"
        )
    )

    lead_data["link"]             = conv_url
    lead_data["source_url"]       = conv_url
    lead_data["conversation_link"] = conv_url

    summary = (
        f"Lead desde {platform.upper()}. "
        f"Carro: {lead_data.get('vehicle_year','')} Toyota {model} {trim}. "
        f"Chat: {conv_url}"
    )
    return send_to_crm(lead_data, summary)
