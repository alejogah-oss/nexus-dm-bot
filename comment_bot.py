"""
Comment Bot — responde comentarios en posts y anuncios de @tucarroconalejo.
Cubre Facebook (feed) e Instagram (comments).

7 guardas en capas antes de responder (ver docs/superpowers/specs/2026-09-07-*):
  1. kill switch  2. identidad  3. solo top-level  4. dedupe
  5. rate limit   6. intención  7. backstop de Meta (1 private reply / comentario)

Incidente que motivó esto: 6 sep 2026, ~950 comentarios en loop porque no había
guarda de identidad y el bot se respondía a sí mismo.
"""
import json
import os
import time

import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

client            = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID           = os.getenv("META_PAGE_ID", "")
IG_USER_ID        = os.getenv("META_IG_USER_ID", "")
_OWN_IDS          = {i for i in (PAGE_ID, IG_USER_ID) if i}

GRAPH             = "https://graph.facebook.com/v19.0"
HANDLED_STORE     = os.path.join(os.path.dirname(__file__), "comments_handled.json")
PUBLIC_ACK        = "¡Te escribimos al DM! 🙌"
INTENT_ACTIONABLE = {"COMPRA", "PRECIO", "CREDITO"}
MAX_PER_HOUR_GLOBAL = 5
MAX_PER_HOUR_POST   = 3
PRIVATE_REPLY_WINDOW_DAYS = 7


def _enabled() -> bool:
    return os.getenv("COMMENT_BOT_ENABLED", "0") == "1"


def _dry_run() -> bool:
    return os.getenv("COMMENT_BOT_DRY_RUN", "0") == "1"


# ── Store ────────────────────────────────────────────────────────────────────

def _load_handled() -> dict:
    if not os.path.exists(HANDLED_STORE):
        return {}
    try:
        with open(HANDLED_STORE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_handled(store: dict) -> None:
    with open(HANDLED_STORE, "w") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


# ── Guardas puras ────────────────────────────────────────────────────────────

def is_own_author(author_id: str) -> bool:
    """Guarda 2. True si el comentario lo escribió nuestra propia página / cuenta IG."""
    return bool(author_id) and author_id in _OWN_IDS


def is_reply(event: dict) -> bool:
    """Guarda 3. True si el comentario es respuesta a otro comentario (no top-level)."""
    parent = event.get("parent_id") or ""
    post = event.get("post_id") or ""
    return bool(parent) and parent != post


def already_handled(comment_id: str) -> bool:
    """Guarda 4. True si ya evaluamos este comment_id antes."""
    return comment_id in _load_handled()


def rate_limited(post_id: str) -> bool:
    """Guarda 5. True si ya se respondió >= MAX_PER_HOUR_GLOBAL en la última hora,
    o >= MAX_PER_HOUR_POST en este post en la última hora. Solo cuenta entradas
    con una respuesta real enviada (actions no vacío)."""
    cutoff = time.time() - 3600
    store = _load_handled()
    recientes = [
        r for r in store.values()
        if r.get("ts", 0) >= cutoff and r.get("actions")
    ]
    if len(recientes) >= MAX_PER_HOUR_GLOBAL:
        return True
    en_post = [r for r in recientes if r.get("post_id") == post_id]
    return len(en_post) >= MAX_PER_HOUR_POST


_INTENT_LABELS = {"COMPRA", "PRECIO", "CREDITO", "POSITIVO", "NEGATIVO", "SPAM", "OTRO"}

_CLASSIFY_SYSTEM = """Clasifica el comentario de una publicación de un concesionario Toyota.
Responde con UNA sola palabra, exactamente una de estas:

COMPRA   - quiere comprar / cambiar de carro / pregunta disponibilidad de un modelo
PRECIO   - pregunta precio, cuota mensual, enganche
CREDITO  - pregunta por financiamiento, aprobación, mal crédito, sin seguro social
POSITIVO - felicitación, agradecimiento, emoji suelto, "bonito carro"
NEGATIVO - queja, reclamo, insulto, "puras mentiras", troll
SPAM     - publicidad ajena, links, nada que ver
OTRO     - cualquier otra cosa

Solo la palabra. Sin explicación, sin puntuación."""


def classify_intent(text: str) -> str:
    """Guarda 6. Devuelve una etiqueta de _INTENT_LABELS, o "ERROR" si Haiku falla."""
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": text[:500]}],
        )
        label = resp.content[0].text.strip().upper()
        first = label.split()[0].strip(".,!") if label else "OTRO"
        return first if first in _INTENT_LABELS else "OTRO"
    except Exception as e:
        print(f"[COMMENT] classify_intent falló: {e}")
        return "ERROR"


COMMENT_VOICE = """Eres el asistente de Alejo, asesor de ventas en Hollywood Toyota, Florida.
Escribes un mensaje PRIVADO a alguien que comentó en una publicación o anuncio.

TONO:
- Cálido, breve, de persona real — máximo 2 oraciones
- Español natural de Florida/USA
- Nada de sonar a folleto ni a bot corporativo

REGLAS ABSOLUTAS:
- NUNCA des precios, mensualidades ni tasas específicas
- NUNCA prometas crédito garantizado
- El teléfono de Alejo es SIEMPRE (954) 910-6671 — nunca otro número
- El objetivo es que siga la conversación por aquí (DM) o llame al (954) 910-6671

Responde SOLO con el texto del mensaje. Sin comillas, sin explicaciones."""

_PRIVATE_FALLBACK = {
    "COMPRA":  "¡Hola! Con gusto te ayudo con eso — cuéntame qué modelo buscas y lo vemos. También puedes llamar a Alejo al (954) 910-6671 🙌",
    "PRECIO":  "¡Hola! Los mejores números te los da Alejo directo. Escríbeme por aquí o llama al (954) 910-6671 y lo revisamos 👇",
    "CREDITO": "¡Hola! Trabajamos con varias opciones de financiamiento. Cuéntame tu caso por aquí o llama al (954) 910-6671 y te orientamos 💪",
}


def generate_private_reply(text: str, intent: str) -> str:
    """Redacta el DM privado. Si Haiku falla, usa un texto de respaldo fijo."""
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            system=COMMENT_VOICE,
            messages=[{"role": "user", "content": f"Comentario del cliente: \"{text[:400]}\""}],
        )
        out = resp.content[0].text.strip()
        # Red de seguridad: Claude a veces alucina 310-6671 (igual que en dm_bot.py).
        out = out.replace("310-6671", "910-6671")
        if out:
            return out
    except Exception as e:
        print(f"[COMMENT] generate_private_reply falló: {e}")
    return _PRIVATE_FALLBACK.get(intent, _PRIVATE_FALLBACK["COMPRA"])
