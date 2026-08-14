"""
NEXUS Agency — pre-publication review pipeline.
Growth-Leo (content strategy) + Frame (design) review every post before it goes live.
Nothing publishes without agency approval.
"""
import os
import base64
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

REVIEW_SYSTEM = """Eres el equipo de revisión de NEXUS Agency para @tucarroconalejo — Toyota Hollywood, FL.

Revisas CADA post antes de publicar. Dos roles simultáneos:

GROWTH-LEO — estrategia de contenido:
- ¿Imagen y copy son congruentes? (un quote sobre "entrega" sin foto de entrega = FALLA)
- ¿El copy suena a Alejo (personal, latino, cálido) o a corporativo/genérico?
- ¿Hay CTA con teléfono (954) 910-6671 o @tucarroconalejo?
- ¿La promo está integrada naturalmente si aplica?
- ¿El tipo de post es el correcto para el contenido?

FRAME — consistencia visual:
- ¿La imagen tiene identidad de marca @tucarroconalejo?
- ¿El template es el correcto para este tipo de post?
- ¿Imagen y texto son legibles y congruentes?

CAUSAS DE RECHAZO AUTOMÁTICO (solo estas — no inventar otras):
- Quote de texto puro con tema de entrega/celebración sin foto de entrega → RECHAZAR
- Copy con PRECIO DEL VEHÍCULO específico (ej: "$35,000", "desde $299/mes") → RECHAZAR
- Copy que GARANTIZA aprobación de crédito (ej: "aprobado 100%", "crédito garantizado") → RECHAZAR
- Post sin ninguna forma de contactar a Alejo (ni teléfono ni @) → RECHAZAR
- Copy que suena a anuncio corporativo de Toyota, no a Alejo → RECHAZAR
- El post promociona un modelo específico (inventory/ai_promo) pero el carro NO aparece
  visible en la imagen, o el carro visible no corresponde al modelo/año mencionado en el
  copy (color, carrocería o forma distinta) → RECHAZAR

PERMITIDO (NO son causa de rechazo):
- Bonos promocionales con monto: "bono de $500", "$1,000 extra si ya tienes Toyota" — son promos oficiales del dealer
- Mencionar que trabajan con crédito bajo/en construcción sin garantizar aprobación
- Hashtags relacionados a crédito o financiamiento
- Número (954) 910-6671 — este es el único número correcto de Alejo

Responde ÚNICAMENTE con JSON válido, sin texto adicional antes ni después."""


def review_post(post_type: str, model: str, image_path: str,
                fb_text: str, ig_caption: str) -> dict:
    """
    Growth-Leo + Frame review before publishing.
    Returns dict with 'approved' bool and details.
    """
    print("\n── NEXUS Agency Review ──────────────────────")

    content_parts = []

    if image_path and os.path.exists(image_path) and os.path.getsize(image_path) > 1000:
        with open(image_path, "rb") as f:
            img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
        content_parts.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}
        })

    content_parts.append({
        "type": "text",
        "text": f"""Revisa este post antes de publicar.

TIPO: {post_type}
MODELO: {model}

COPY FACEBOOK:
{fb_text[:1500]}

COPY INSTAGRAM:
{ig_caption[:1200]}

Responde con este JSON exacto:
{{
  "approved": true,
  "growth_leo": "observación de una línea",
  "frame": "observación de una línea",
  "issues": [],
  "fix": ""
}}

Si hay problemas:
{{
  "approved": false,
  "growth_leo": "observación de una línea",
  "frame": "observación de una línea",
  "issues": ["problema específico"],
  "fix": "qué cambiar exactamente"
}}"""
    })

    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=400,
            system=REVIEW_SYSTEM,
            messages=[{"role": "user", "content": content_parts}]
        )
        text = response.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json.loads(text)
    except Exception as e:
        print(f"  ⚠️  Review error: {e} — aprobando por defecto")
        return {"approved": True, "issues": [], "growth_leo": "error", "frame": "error"}

    if result.get("approved"):
        print(f"  ✅ Growth-Leo: {result.get('growth_leo', '—')}")
        print(f"  ✅ Frame:      {result.get('frame', '—')}")
    else:
        print(f"  🔴 Growth-Leo: {result.get('growth_leo', '—')}")
        print(f"  🔴 Frame:      {result.get('frame', '—')}")
        for issue in result.get("issues", []):
            print(f"     → {issue}")
        if result.get("fix"):
            print(f"  💡 Fix sugerido: {result.get('fix')}")

    print("─────────────────────────────────────────────")
    return result
