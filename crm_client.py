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

_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


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


def push_hot_lead(sender_id: str, platform: str, conversation_history: list) -> dict:
    """
    Full flow: extract data from conversation → send to CRM.
    Called automatically when bot detects HOT LEAD signal.
    """
    print(f"\n  📋 NEXUS → CRM: extrayendo datos del lead...")
    lead_data = extract_lead_data(conversation_history, platform)

    name = " ".join(filter(None, [lead_data.get("first_name"), lead_data.get("last_name")])) or "Sin nombre"
    phone = lead_data.get("phone", "no capturado")
    model = lead_data.get("vehicle_model", "no especificado")
    print(f"  Nombre: {name} | Tel: {phone} | Modelo: {model}")

    summary = f"Lead desde {platform.upper()} — ID: {sender_id[:12]}. Modelo de interés: {model}."
    return send_to_crm(lead_data, summary)
