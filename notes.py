"""
NEXUS Notes — Resúmenes de conversación con timestamp por cliente.
- Guarda resumen + cita detectada al ocurrir HOT LEAD
- Detecta cambios de cita en clientes que regresan
- Alerta via pulse cuando hay un cambio
"""
import json
import os
import anthropic
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

NOTES_FILE = os.path.join(os.path.dirname(__file__), "conversation_notes.json")
_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _load() -> dict:
    try:
        with open(NOTES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _extract_appointment(conversation_history: list) -> str:
    """Uses Claude Haiku to extract appointment date/time from conversation."""
    if not conversation_history:
        return ""
    transcript = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in conversation_history[-16:]
    )
    try:
        resp = _claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{
                "role": "user",
                "content": (
                    "De esta conversación, extrae SOLO la cita o día/hora mencionados. "
                    "Si no hay cita confirmada, responde: ninguna. "
                    "Responde en 1 línea máximo, ejemplo: 'martes a las 3pm' o 'sábado por la mañana'.\n\n"
                    f"{transcript}"
                )
            }]
        )
        result = resp.content[0].text.strip().lower()
        return "" if "ninguna" in result or "no hay" in result else result
    except Exception:
        return ""


def _generate_summary(conversation_history: list, platform: str, name: str) -> str:
    """Uses Claude Haiku to generate a short conversation summary."""
    if not conversation_history:
        return f"Contacto desde {platform.upper()}. Sin historial."
    transcript = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in conversation_history[-16:]
    )
    try:
        resp = _claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{
                "role": "user",
                "content": (
                    "Resume esta conversación de venta de autos en 2-3 oraciones. "
                    "Incluye: modelo de interés, situación del cliente, intención de compra, cita si hay. "
                    "Directo, sin introducción.\n\n"
                    f"Cliente: {name}\n{transcript}"
                )
            }]
        )
        return resp.content[0].text.strip()
    except Exception:
        return f"Contacto desde {platform.upper()}."


def analyze_buyer(conversation_history: list) -> dict:
    """
    Analyzes buyer psychology: profile type, buying state, and negotiation insights.
    Returns dict with: perfil, estado, approach, señales.
    """
    if not conversation_history:
        return {}
    transcript = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in conversation_history[-20:]
    )
    try:
        resp = _claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            messages=[{
                "role": "user",
                "content": (
                    "Analiza este chat de venta de autos desde perspectiva psicológica. "
                    "Responde SOLO con JSON válido:\n\n"
                    "{\n"
                    '  "perfil": "Analítico|Emocional|Desconfiado|Impulsivo|Negociador",\n'
                    '  "estado": "Explorando|Interesado|Considerando|Decidido|Urgente",\n'
                    '  "señales": "2 señales clave observadas en el chat",\n'
                    '  "approach": "1-2 oraciones: cómo debe abordarlo Alejo en la negociación"\n'
                    "}\n\n"
                    f"CONVERSACIÓN:\n{transcript}"
                )
            }]
        )
        text = resp.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0].replace("json", "").strip()
        return json.loads(text)
    except Exception:
        return {}


def save_note(sender_id: str, platform: str, conversation_history: list, name: str = "Sin nombre") -> dict:
    """
    Genera resumen + extrae cita y guarda nota con timestamp.
    Retorna dict con: summary, appointment, changed (bool), prev_appointment.
    """
    data = _load()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    summary = _generate_summary(conversation_history, platform, name)
    appointment = _extract_appointment(conversation_history)
    buyer = analyze_buyer(conversation_history)

    entry = data.get(sender_id, {})
    prev_appointment = entry.get("appointment", "")
    changed = bool(prev_appointment and appointment and prev_appointment != appointment)

    data[sender_id] = {
        "name": name,
        "platform": platform,
        "last_updated": now,
        "summary": summary,
        "appointment": appointment or prev_appointment,
        "buyer_profile": buyer,
        "history": entry.get("history", []) + [{
            "timestamp": now,
            "summary": summary,
            "appointment": appointment,
            "buyer_profile": buyer,
        }],
    }
    data[sender_id]["history"] = data[sender_id]["history"][-10:]
    _save(data)

    print(f"[NOTES] {now} | {name} | Cita: {appointment or 'ninguna'} | Perfil: {buyer.get('perfil','?')} | Estado: {buyer.get('estado','?')}")
    return {
        "summary": summary,
        "appointment": appointment,
        "prev_appointment": prev_appointment,
        "changed": changed,
        "timestamp": now,
        "buyer": buyer,
    }


def get_note(sender_id: str) -> dict:
    """Returns saved note for a sender_id."""
    return _load().get(sender_id, {})
