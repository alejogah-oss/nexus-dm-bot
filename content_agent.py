import os
import random
import requests
from datetime import date
from bs4 import BeautifulSoup
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

INVENTORY_URL = "https://tucarroconalejo.com/"

# Fallback en caso de que el sitio no responda
# Modelos disponibles en Hollywood Toyota, FL (sin Venza ni Mirai)
FALLBACK_MODELS = [
    "RAV4", "Camry", "Corolla", "Corolla Cross", "Highlander",
    "Grand Highlander", "Tacoma", "Tundra", "4Runner", "Sequoia",
    "Sienna", "Crown", "Prius", "bZ4X", "GR Supra", "GR86", "Land Cruiser"
]

def get_current_model_year() -> str:
    """
    Returns the dominant model year in active inventory.
    Source: live CSV feed (most common year across all VINs).
    Fallback: automotive convention — new model year ships in September,
              so month >= 9 → year+1, else current year.
    """
    try:
        import csv as _csv
        resp = requests.get(
            "https://bot.tucarroconalejo.com/feed/vehicles.csv",
            timeout=5, headers={"User-Agent": "Mozilla/5.0"}
        )
        reader = _csv.DictReader(resp.text.splitlines())
        years = [
            row["year"] for row in reader
            if row.get("year", "").strip().isdigit()
        ]
        if years:
            from collections import Counter
            return Counter(years).most_common(1)[0][0]
    except Exception:
        pass
    from datetime import datetime
    now = datetime.now()
    return str(now.year + 1) if now.month >= 9 else str(now.year)


def fetch_available_models() -> list[str]:
    """Consulta tucarroconalejo.com y retorna lista de modelos disponibles (sin precios)."""
    try:
        resp = requests.get(INVENTORY_URL, timeout=8,
                            headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        known_models = [
            "4Runner", "Camry", "Corolla Cross", "Corolla", "Crown",
            "GR Supra", "GR86", "Grand Highlander", "Highlander",
            "Land Cruiser", "Prius", "RAV4", "Sequoia",
            "Sienna", "Tacoma", "Tundra", "bZ4X"
        ]
        found = [m for m in known_models if m.lower() in text.lower()]
        return found if found else FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS


def pick_model_for_post() -> str:
    """Selecciona modelo aleatorio del inventario que tenga imagen jelly disponible."""
    import json as _json
    models = fetch_available_models()
    lib = os.path.join(os.path.dirname(__file__), "car_library")

    def _has_image(model: str) -> bool:
        try:
            with open(os.path.join(lib, "index.json")) as f:
                idx = _json.load(f)
            if any(os.path.exists(p) and os.path.getsize(p) > 1000
                   for p in idx.get(model, [])):
                return True
        except Exception:
            pass
        slug = model.lower().replace(" ", "_").replace("/", "")
        return os.path.exists(os.path.join(lib, f"{slug}.png"))

    with_image = [m for m in models if _has_image(m)]
    if with_image:
        return random.choice(with_image)
    # Ningún modelo escaneado tiene imagen (p.ej. pressroom devolvió un modelo
    # nuevo sin PNG en car_library) — usar FALLBACK_MODELS filtrado en vez de
    # elegir a ciegas (eso producía posts con solo el fondo, sin el carro).
    fallback_with_image = [m for m in FALLBACK_MODELS if _has_image(m)]
    return random.choice(fallback_with_image) if fallback_with_image else random.choice(models)


def get_promo_for_model(model: str) -> str | None:
    """Retorna el texto de UNA promoción válida para el modelo, o None."""
    result = get_promo_context(model)
    return result[0] if result else None


def get_promo_context(model: str) -> tuple[str, str] | None:
    """Retorna (promo_text, copy_restriction) para el modelo, o None."""
    try:
        promo_path = os.path.join(os.path.dirname(__file__), "promotions.json")
        with open(promo_path) as f:
            import json
            data = json.load(f)
        today = date.today().isoformat()
        eligible = [
            p for p in data["promotions"]
            if ("all" in p["models"] or model in p["models"])
            and p.get("valid_until", "9999-12-31") >= today
        ]
        if not eligible:
            return None
        # Prioridad: modelo específico > priority flag > genérico aleatorio
        model_specific = [p for p in eligible if model in p.get("models", [])]
        if model_specific:
            chosen = model_specific[0]
        else:
            priority_promos = [p for p in eligible if p.get("priority")]
            chosen = priority_promos[0] if priority_promos else random.choice(eligible)
        return (chosen["text"], chosen.get("copy_restriction", ""))
    except Exception:
        return None

def _load_lex_bank() -> str:
    """Loads Alejo's phrase bank and returns a formatted block for the copy prompt."""
    try:
        import json as _json
        path = os.path.join(os.path.dirname(__file__), "lex_bank.json")
        with open(path, encoding="utf-8") as f:
            bank = _json.load(f)
        samples = []
        for category, phrases in bank.get("phrases", {}).items():
            if phrases:
                samples.append(f"- {phrases[0]}")
        return "\nFRASES AUTÉNTICAS DE ALEJO (úsalas como referencia de su voz):\n" + "\n".join(samples[:8]) + "\n"
    except Exception:
        return ""


BRAND_CONTEXT = """
Eres el copywriter de "Tu Carro con Alejo" — página de Facebook e Instagram de Alejo,
asesor de ventas de Toyota en Hollywood Toyota, Florida.

VOZ DE ALEJO: Cálido, directo, como un amigo de confianza de la comunidad latina.
No es un vendedor — es alguien que genuinamente quiere ayudarte a conseguir tu carro.
Usa "yo" con naturalidad. Varía el tono: a veces emocionante, a veces reflexivo, a veces gracioso.
Nunca suenes a anuncio corporativo. Suena a persona real.

IDIOMA: Español natural del sur de Florida. Mezcla términos en inglés cuando es orgánico
(ej: "el dealership", "el down payment", "el trade-in") pero no lo fuerces.

AUDIENCIA: Comunidad latina en South Florida — primera compra, cambio de carro, familias,
jóvenes profesionales. Muchos tienen crédito en construcción. Todos merecen un Toyota.

CONTACTO DE ALEJO:
- Teléfono/WhatsApp: (954) 910-6671
- Instagram/Facebook DM: @tucarroconalejo
- Siempre ofrecer AMBAS opciones de contacto al final.

REGLAS ABSOLUTAS — NUNCA VIOLAR:
- JAMÁS mencionar precios específicos, mensualidades ni cifras de financiamiento ($).
- JAMÁS hacer promesas de aprobación de crédito garantizada.
- JAMÁS repetir datos técnicos literalmente si ya van en la imagen — transfórmalos en emoción.
- JAMÁS sonar a copy corporativo o de anuncio de periódico.

PERMITIDO Y RECOMENDADO:
- Celebrar entregas y clientes felices con emoción genuina.
- Destacar lo que el modelo hace sentir, no solo sus especificaciones.
- Contenido educativo conversacional ("¿sabías que...?", "te cuento algo...").
- Promos del mes mencionadas UNA vez, de forma natural, no como titular.
- CTA siempre con teléfono Y DM: "(954) 910-6671 o escríbeme directo".
"""

def _promo_block(promo: str | None, restriction: str = "") -> str:
    if not promo:
        return ""
    base = f"\nPROMOCIÓN DEL MES (menciónala UNA vez de forma natural, antes del CTA, nunca como titular): {promo}\n"
    base += ("OBLIGATORIO: toda promo va acompañada de 'aplican condiciones' o "
             "'sujeto a aprobación de crédito' — corto y natural, puede ir al final del copy. "
             "NUNCA prometer aprobación garantizada.\n")
    if restriction:
        base += f"RESTRICCIÓN DE ESTA PROMO (respétala en el copy): {restriction}\n"
    return base


def _specs_block(specs: str | None) -> str:
    if not specs:
        return ""
    return (
        f"\nCONTEXTO TÉCNICO DEL MODELO (úsalo como INSPIRACIÓN EMOCIONAL — "
        f"no lo repitas literalmente, transfórmalo en sensación o deseo): {specs}\n"
    )


def generate_facebook_post(topic: str, promo: str | None = None, specs: str | None = None, restriction: str = "") -> str:
    lex = _load_lex_bank()
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""{BRAND_CONTEXT}
{lex}{_promo_block(promo, restriction)}{_specs_block(specs)}
Crea un post para Facebook sobre: {topic}

Requisitos:
- Entre 100 y 200 palabras
- Voz de Alejo: personal, cercana, nunca corporativa
- 2-3 emojis para dar ritmo visual (no excesivos)
- 1 pregunta al final que invite a comentar o compartir
- CTA al final con teléfono Y DM: "(954) 910-6671 o escríbeme directo"
- Si hay promoción, menciónala una vez de forma orgánica
- 3-5 hashtags al final
- IMPORTANTE: NO uses Markdown. Sin asteriscos, guiones bajos ni almohadillas.

Solo devuelve el texto del post, sin explicaciones."""
        }]
    )
    return message.content[0].text


def generate_instagram_caption(topic: str, promo: str | None = None, specs: str | None = None, restriction: str = "") -> str:
    lex = _load_lex_bank()
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""{BRAND_CONTEXT}
{lex}{_promo_block(promo, restriction)}{_specs_block(specs)}
Crea un caption para Instagram sobre: {topic}

Requisitos:
- Máximo 150 palabras
- Primera línea que detenga el scroll — no empieces con el nombre del carro
- 3-5 emojis estratégicos (no decorativos)
- CTA con teléfono Y DM: "(954) 910-6671 o escríbeme directo 👇"
- Si hay promoción, menciónala brevemente antes del CTA
- 10-15 hashtags mezclados español/inglés al final
- IMPORTANTE: NO uses Markdown. Sin asteriscos ni guiones bajos.

Solo devuelve el caption, sin explicaciones."""
        }]
    )
    return message.content[0].text


def check_monthly_promo_reminder() -> bool:
    """Retorna True el día 1 de cada mes para recordar actualizar promociones."""
    from datetime import date
    import json
    today = date.today()
    if today.day != 1:
        return False
    promo_path = os.path.join(os.path.dirname(__file__), "promotions.json")
    try:
        with open(promo_path) as f:
            data = json.load(f)
        current_month = today.strftime("%B %Y")
        return data.get("month", "") != current_month
    except Exception:
        return True


def generate_content(topic: str, model: str | None = None, specs: str | None = None) -> dict:
    print(f"Generando contenido para: {topic}")
    promo, restriction = None, ""
    if model:
        ctx = get_promo_context(model)
        if ctx:
            promo, restriction = ctx
    if promo:
        print(f"Promoción del mes aplicada: {promo}")
    fb_post = generate_facebook_post(topic, promo, specs, restriction)
    ig_caption = generate_instagram_caption(topic, promo, specs, restriction)
    return {
        "topic": topic,
        "model": model,
        "promo_used": promo,
        "facebook": fb_post,
        "instagram": ig_caption
    }

def generate_tips_points(topic: str) -> list[str]:
    """Returns 5 short tips for the given topic, for use in the tips image template."""
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Dame exactamente 5 tips cortos (máximo 8 palabras cada uno) sobre: {topic}\n"
                "Responde SOLO con los 5 tips, uno por línea, sin números ni viñetas."
            )
        }]
    )
    lines = [l.strip().lstrip("0123456789.-) ").strip()
             for l in message.content[0].text.strip().split("\n")
             if l.strip()]
    return lines[:5]


if __name__ == "__main__":
    content = generate_content("5 tips para mantener tu carro en perfecto estado")
    print("\n--- FACEBOOK ---")
    print(content["facebook"])
    print("\n--- INSTAGRAM ---")
    print(content["instagram"])
