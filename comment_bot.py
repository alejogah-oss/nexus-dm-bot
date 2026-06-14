"""
Comment Bot — responde comentarios en posts y anuncios de @tucarroconalejo.
Cubre Facebook (feed) e Instagram (comments).
"""
import os
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

client            = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
IG_USER_ID        = os.getenv("META_IG_USER_ID")

COMMENT_VOICE = """Eres el asistente público de Alejo, asesor de ventas Toyota en Hollywood Toyota, Florida.
Respondes comentarios en posts y anuncios de @tucarroconalejo en Facebook e Instagram.

TONO:
- Cálido, breve, personal — máximo 2 oraciones
- Hablas español natural de Florida/USA
- Nunca suenas a bot corporativo

REGLAS ABSOLUTAS:
- NUNCA des precios, mensualidades ni tasas específicas
- NUNCA prometas crédito garantizado
- Siempre invita a continuar por DM o llamada

OBJETIVO: Que el comentarista pase al DM o llame a Alejo.

PLANTILLAS según tipo de comentario:
- Interés en comprar → "¡Gracias [nombre si lo sabes]! Escríbenos por DM o llama al (954) 310-6671 — Alejo te atiende personalmente 🙌"
- Pregunta de precio → "Los mejores números te los da Alejo directo — escríbenos al DM y te respondemos enseguida 👇"
- Pregunta de crédito → "¡Aquí encontramos opciones para todos! Cuéntanos más por DM y Alejo te orienta 💪"
- Comentario positivo/felicitación → Responde con calidez y agradecimiento breve
- Negativo/queja → "Lamentamos eso, escríbenos al DM para resolverlo directamente contigo"

Responde SOLO con el texto del comentario. Sin comillas, sin explicaciones."""


def generate_comment_reply(comment_text: str, post_context: str = "") -> str:
    prompt = f"Comentario recibido: \"{comment_text}\""
    if post_context:
        prompt += f"\nContexto del post: {post_context}"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        system=COMMENT_VOICE,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def reply_to_facebook_comment(comment_id: str, reply_text: str) -> dict:
    """Posts a public reply to a Facebook comment."""
    url = f"https://graph.facebook.com/v19.0/{comment_id}/comments"
    resp = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json={"message": reply_text},
        timeout=10,
    )
    return resp.json()


def reply_to_instagram_comment(comment_id: str, reply_text: str) -> dict:
    """Posts a public reply to an Instagram comment."""
    url = f"https://graph.facebook.com/v19.0/{comment_id}/replies"
    resp = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json={"message": reply_text},
        timeout=10,
    )
    return resp.json()


def handle_facebook_comment(comment_id: str, from_name: str, message: str, post_id: str = ""):
    """Full flow: generate reply → post to Facebook."""
    if not message or not comment_id:
        return
    print(f"[FB COMMENT] {from_name}: {message[:60]}...")
    reply = generate_comment_reply(message)
    result = reply_to_facebook_comment(comment_id, reply)
    if result.get("id"):
        print(f"  ✅ Respondido: {reply[:60]}...")
    else:
        print(f"  ⚠️  Error: {result}")


def handle_instagram_comment(comment_id: str, username: str, message: str):
    """Full flow: generate reply → post to Instagram."""
    if not message or not comment_id:
        return
    print(f"[IG COMMENT] @{username}: {message[:60]}...")
    reply = generate_comment_reply(message)
    result = reply_to_instagram_comment(comment_id, reply)
    if result.get("id"):
        print(f"  ✅ Respondido: {reply[:60]}...")
    else:
        print(f"  ⚠️  Error: {result}")
