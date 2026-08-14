import openai
import os
import random
import base64
import time
import requests
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── MuAPI ──────────────────────────────────────────────────────────────────
MUAPI_KEY  = os.getenv("MUAPI_KEY")
MUAPI_BASE = "https://api.muapi.ai/api/v1"

def _muapi_generate(endpoint: str, payload: dict, timeout_s: int = 120) -> str:
    headers = {"Content-Type": "application/json", "x-api-key": MUAPI_KEY}
    r = requests.post(f"{MUAPI_BASE}/{endpoint}", json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    request_id = data.get("request_id") or data.get("id")
    if not request_id:
        url = (data.get("outputs") or [None])[0] or data.get("url")
        if url:
            return _muapi_download(url, endpoint)
        raise ValueError(f"MuAPI: sin request_id ni URL: {data}")

    poll_url = f"{MUAPI_BASE}/predictions/{request_id}/result"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(5)
        res = requests.get(poll_url, headers=headers, timeout=15)
        res.raise_for_status()
        raw = res.json()
        # MuAPI wraps result under "detail" key
        result = raw.get("detail", raw)
        status = result.get("status", "").lower()
        if status in ("completed", "succeeded", "success"):
            url = (result.get("outputs") or [None])[0] or result.get("url")
            if url:
                return _muapi_download(url, endpoint)
        elif status in ("failed", "error"):
            raise RuntimeError(f"MuAPI falló: {result.get('error', 'desconocido')}")
    raise TimeoutError(f"MuAPI: timeout tras {timeout_s}s")

def _upload_for_muapi(local_path: str) -> str | None:
    """Sube imagen a un CDN accesible por MuAPI. Usa catbox.moe (sin rate-limit)."""
    from io import BytesIO
    try:
        img = Image.open(local_path).convert("RGB")
        img.thumbnail((1024, 1024))
        buf = BytesIO()
        img.save(buf, "JPEG", quality=88)
        buf.seek(0)
        r = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": ("car.jpg", buf, "image/jpeg")},
            timeout=30,
        )
        url = r.text.strip()
        if url.startswith("https://"):
            return url
        # Fallback: Imgur
        buf.seek(0)
        r2 = requests.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": "Client-ID 546c25a59c58ad7"},
            files={"image": ("car.jpg", buf, "image/jpeg")},
            timeout=30,
        )
        return r2.json().get("data", {}).get("link")
    except Exception as e:
        print(f"  Upload error: {e}")
        return None


def _upload_to_imgur(local_path: str) -> str | None:
    return _upload_for_muapi(local_path)


def _muapi_download(url: str, label: str) -> str:
    safe = label.replace("/", "_").replace(".", "_")[:30]
    path = f"/tmp/nexus_ai_{safe}_{int(time.time())}.jpg"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    # Convert to JPEG regardless of source format (AVIF, WebP, PNG, etc.)
    from io import BytesIO
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(path, "JPEG", quality=95)
    return path

_PRESSROOM_SLUGS = {
    "camry": "camry", "corolla": "corolla", "rav4": "rav4", "rav4 hybrid": "rav4-hybrid",
    "highlander": "highlander", "tacoma": "tacoma", "tundra": "tundra", "sequoia": "sequoia",
    "4runner": "4runner", "sienna": "sienna", "crown": "crown", "venza": "venza",
    "prius": "prius", "land cruiser": "land-cruiser", "gr supra": "gr-supra", "gr86": "gr86",
    "corolla cross": "corolla-cross", "bz4x": "bz4x", "grand highlander": "grand-highlander",
    "tundra hybrid": "tundra", "highlander hybrid": "highlander-hybrid",
}

_PRESSROOM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

def _get_toyota_pressroom_image(car_model: str) -> str | None:
    """Descarga foto oficial Toyota Pressroom, la redimensiona y la sube a Imgur."""
    import re
    slug = _PRESSROOM_SLUGS.get(car_model.lower()) or car_model.lower().replace(" ", "-")
    url = f"https://pressroom.toyota.com/vehicle/2026-toyota-{slug}/"
    try:
        r = requests.get(url, headers=_PRESSROOM_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        imgs = re.findall(r'https://toyota-cms-media\.s3\.amazonaws\.com[^"\']+\.jpg', r.text)
        # Preferir imágenes sin -scaled ni dimensiones (peso manejable)
        clean = [i for i in imgs if "-scaled" not in i and not re.search(r'-\d+x\d+\.jpg$', i)]
        s3_url = clean[0] if clean else (imgs[0] if imgs else None)
        if not s3_url:
            return None
        # Descargar con Referer del pressroom
        img_r = requests.get(s3_url, headers={**_PRESSROOM_HEADERS, "Referer": "https://pressroom.toyota.com/"}, timeout=20)
        img_r.raise_for_status()
        # Redimensionar a máx 1024px (ai-product-shot falla con imágenes grandes)
        from io import BytesIO
        img = Image.open(BytesIO(img_r.content)).convert("RGB")
        img.thumbnail((1024, 1024))
        buf = BytesIO()
        img.save(buf, "JPEG", quality=88)
        buf.seek(0)
        # Subir a Imgur (anónimo, URL pública accesible por MuAPI)
        up = requests.post("https://api.imgur.com/3/image",
            headers={"Authorization": "Client-ID 546c25a59c58ad7"},
            files={"image": ("car.jpg", buf, "image/jpeg")}, timeout=30)
        imgur_url = up.json().get("data", {}).get("link")
        return imgur_url
    except Exception as e:
        print(f"  Pressroom error: {e}")
        return None

def generate_lifestyle_inventory_photo(car_model: str, year: str = "2026") -> str | None:
    """
    Foto lifestyle GARANTIZADA con el carro real (regla jul 14 2026):
    los píxeles del carro NUNCA pasan por la IA — Kontext/i2i redibuja
    generaciones viejas aunque se le prohíba (verificado con Camry 2026).

    1. PNG oficial del modelo actual (car_library/{model}.png — render 2026 con alpha)
    2. IA genera SOLO el fondo (calle South Florida sin carros)
    3. Composición PIL: carro real + sombra sobre el fondo
    Returns: path local o None (el caller decide fallback).
    """
    import time as _time
    from PIL import ImageFilter

    slug = car_model.lower().replace(" ", "_")
    candidates = [f"car_library/{slug}.png", f"car_library/{slug}_0.png"]
    base = os.path.dirname(os.path.abspath(__file__))
    car_path = next(
        (os.path.join(base, c) for c in candidates
         if os.path.exists(os.path.join(base, c))),
        None,
    )
    if not car_path:
        print(f"  Shot · sin PNG oficial para {car_model} — no se genera lifestyle")
        return None

    try:
        bg_prompt = (
            "empty scenic palm-lined avenue in South Florida at golden hour, smooth empty "
            "asphalt road in the foreground, tall palm trees on both sides, warm sunset light, "
            "soft golden haze, clean editorial photography, wide open completely empty road, "
            "absolutely no cars, no vehicles, no people, no text, no watermarks"
        )
        bg_path = _muapi_generate("flux-dev-image", {"prompt": bg_prompt, "aspect_ratio": "1:1"},
                                  timeout_s=180)

        bg = Image.open(bg_path).convert("RGB").resize((1080, 1080))
        car = Image.open(car_path).convert("RGBA")
        bbox = car.getbbox()
        if bbox:
            car = car.crop(bbox)

        # Carro real: 88% del ancho, asentado en el tercio inferior
        cw = 950
        ch = int(car.height * cw / car.width)
        car = car.resize((cw, ch), Image.LANCZOS)
        cx = (1080 - cw) // 2
        cy = 760 - ch  # llanta al nivel ~760px — deja aire para el texto del template

        # Sombra suave bajo el carro
        shadow = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
        sh = Image.new("RGBA", (int(cw * 0.94), int(ch * 0.20)), (0, 0, 0, 0))
        from PIL import ImageDraw as _ImageDraw
        _ImageDraw.Draw(sh).ellipse([0, 0, sh.width - 1, sh.height - 1], fill=(0, 0, 0, 150))
        shadow.paste(sh, (cx + int(cw * 0.03), cy + ch - int(sh.height * 0.55)), sh)
        shadow = shadow.filter(ImageFilter.GaussianBlur(16))

        out = Image.alpha_composite(bg.convert("RGBA"), shadow)
        out.paste(car, (cx, cy), car)

        out_path = f"/tmp/nexus_lifestyle_{slug}_{int(_time.time())}.jpg"
        out.convert("RGB").save(out_path, "JPEG", quality=93)
        print(f"  Shot · lifestyle compuesto (carro real intacto): {out_path}")
        return out_path
    except Exception as e:
        print(f"  Shot · lifestyle inventory falló: {e}")
        return None


def generate_ai_promo_image(car_model: str, promo: str, year: str = "2026") -> str:
    """Imagen AI para post de promo mensual — foto oficial Drive + brand frame NEXUS."""
    from datetime import datetime as _dt
    from templates import template_ai_promo
    from html_renderer import render_to_image

    weekday = _dt.now().weekday()

    scene = (
        "at Hollywood Toyota dealership exterior, bright South Florida midday sun, "
        "clear blue sky with a few white clouds, vivid natural daylight on the car's paint, "
        "palm trees and clean dealership lot, Toyota signage softly visible in background"
    )
    if weekday == 1:
        scene = (
            "at Hollywood Toyota dealership exterior, bright warm afternoon sun, "
            "wide blue South Florida sky, sharp natural light, palm trees casting soft shadows, "
            "clean dealership lot, energetic sunny South Florida atmosphere"
        )
    elif weekday == 3:
        scene = (
            "inside Hollywood Toyota showroom, large floor-to-ceiling windows with bright natural daylight, "
            "clean white epoxy showroom floor with subtle reflection, modern dealership interior, "
            "Toyota branding visible in background, bright airy premium atmosphere"
        )

    from templates import template_ai_promo, template_ai_promo_s2, template_ai_promo_s3

    kontext_prompt = (
        f"Keep this exact Toyota {car_model} car completely unchanged — same color, "
        f"same body, same details. Only change the environment: place it {scene}. "
        f"Professional automotive photography, cinematic lighting, "
        f"shallow depth of field f/2.8, car magazine editorial quality, 8K. "
        f"No people, no text, no watermarks. Car must remain pixel-perfect identical."
    )

    def _get_public_url(local_path: str) -> str | None:
        """Sube foto a Facebook CDN (infraestructura existente) → URL pública para MuAPI."""
        try:
            from meta_publisher import upload_image_to_facebook
            url = upload_image_to_facebook(local_path)
            if url and url.startswith("http"):
                print(f"  Shot · FB CDN: {url[:70]}...")
                return url
        except Exception as e:
            print(f"  Shot · FB CDN error: {e}")
        return None

    def _enhance_with_kontext(local_path: str) -> str | None:
        """Drive photo → FB CDN → Kontext i2i → dramatic scene. Returns local path."""
        print(f"  Shot · Kontext i2i — transformando escena...")
        public_url = _get_public_url(local_path)
        if not public_url:
            return None
        try:
            enhanced = _muapi_generate(
                "flux-kontext-pro-i2i",
                {"images_list": [public_url], "prompt": kontext_prompt}
            )
            print(f"  Shot · escena generada: {enhanced}")
            return enhanced
        except Exception as e:
            print(f"  Shot · Kontext falló ({e}) — usando foto original")
            return None

    def _make_slides(hero_path: str) -> list[str]:
        slug = car_model.lower().replace(" ", "_")
        s1 = render_to_image(template_ai_promo(car_model, year, hero_path, promo),
                             f"/tmp/nexus_aipromo_{slug}_s1.jpg", height=1350)
        s2 = render_to_image(template_ai_promo_s2(car_model, year, promo),
                             f"/tmp/nexus_aipromo_{slug}_s2.jpg", height=1350)
        s3 = render_to_image(template_ai_promo_s3(car_model, promo),
                             f"/tmp/nexus_aipromo_{slug}_s3.jpg", height=1350)
        return [s1, s2, s3]

    slug = car_model.lower().replace(" ", "_")

    # 1. Drive photo → Kontext i2i → frame
    from drive_reader import get_promo_photo
    local_photo = get_promo_photo(car_model)
    if local_photo:
        enhanced = _enhance_with_kontext(local_photo)
        hero = enhanced if enhanced else local_photo
        print(f"  Shot → carousel 3 slides — {car_model}")
        return _make_slides(hero)

    # 2. Fallback: Pressroom → Kontext i2i → frame
    pressroom_url = _get_toyota_pressroom_image(car_model)
    if pressroom_url:
        import tempfile, io as _io
        r = requests.get(pressroom_url, timeout=20)
        try:
            img = Image.open(_io.BytesIO(r.content)).convert("RGB")
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            img.save(tmp.name, "JPEG", quality=90)
            enhanced = _enhance_with_kontext(tmp.name)
            hero = enhanced if enhanced else tmp.name
        except Exception:
            hero = None
        if hero:
            print(f"  Shot → carousel (Pressroom+Kontext) — {car_model}")
            return _make_slides(hero)

    # 3. Fallback final: Flux Dev text-to-image + slides 2/3
    t2i_prompt = (
        f"New Toyota {car_model} {year} {scene}. "
        f"Professional automotive photography, cinematic color grade, "
        f"8K photorealistic, car magazine editorial quality. "
        f"No text, no people, no watermarks."
    )
    print(f"  Shot → Flux Dev text-to-image — {car_model}")
    s1_path = _muapi_generate("flux-dev-image", {"prompt": t2i_prompt, "aspect_ratio": "1:1"})
    s2 = render_to_image(template_ai_promo_s2(car_model, year, promo),
                         f"/tmp/nexus_aipromo_{slug}_s2.jpg", height=1350)
    s3 = render_to_image(template_ai_promo_s3(car_model, promo),
                         f"/tmp/nexus_aipromo_{slug}_s3.jpg", height=1350)
    return [s1_path, s2, s3]

def generate_celebration_post(photo_path: str, post_type: str = "entrega",
                              subtitle: str = "", model: str = "", year: str = "2026") -> str:
    """
    Flujo IA para entrega / new_car_day:
    1. Sube foto cliente a Facebook CDN
    2. Kontext i2i → agrega atmósfera festiva (bokeh dorado, luces cálidas)
    3. Render HTML text overlay encima del resultado AI
    Devuelve ruta local del JPEG final.
    """
    from templates import template_entrega_especial, template_new_car_day
    from html_renderer import render_to_image
    from meta_publisher import upload_image_to_facebook

    slug = post_type.replace(" ", "_")
    out_path = f"/tmp/nexus_{slug}_{int(time.time())}.jpg"

    # ── Prompt festivo según tipo ──────────────────────────────────────
    # Clave: MUY sutil — el objetivo es que la foto real se vea nítida y clara,
    # no cubrirla con bokeh/glow dorado (eso tapaba caras y detalles del carro).
    if post_type == "entrega":
        mood = ("only a very subtle touch of warmth to the lighting, keep the photo "
                "sharp, crisp and naturally lit — do NOT add glow, haze, bokeh or "
                "light leaks that obscure faces or the car, keep ALL people and the "
                "car perfectly crisp and clearly visible, a few small confetti pieces "
                "are fine but must never cover faces, do NOT darken the image")
    else:
        mood = ("only a very subtle touch of warmth to the lighting, keep the photo "
                "sharp, crisp and naturally lit — do NOT add glow, haze, bokeh or "
                "light leaks that obscure faces or the car, keep ALL people and the "
                "car perfectly crisp and clearly visible, festive New Car Day feel "
                "without covering the image in light effects, do NOT darken the image")

    kontext_prompt = (
        f"Keep every person and the Toyota car in this photo completely unchanged — "
        f"same faces, same poses, same car color and details. "
        f"Only enhance the atmosphere: add {mood}. "
        f"Photorealistic, 4K quality, no text, no watermarks."
    )

    # ── Step 1: subir foto a CDN público para MuAPI ────────────────────
    enhanced_path = None
    try:
        print(f"  Celebration · subiendo foto a Facebook CDN...")
        public_url = upload_image_to_facebook(photo_path)
        if public_url and public_url.startswith("http"):
            print(f"  Celebration · Kontext i2i festivo...")
            enhanced_path = _muapi_generate(
                "flux-kontext-pro-i2i",
                {"images_list": [public_url], "prompt": kontext_prompt}
            )
            print(f"  Celebration · foto festiva generada: {enhanced_path}")
    except Exception as e:
        print(f"  Celebration · Kontext falló ({e}), usando foto original")

    hero = enhanced_path or photo_path

    # ── Step 2: overlay HTML con texto ────────────────────────────────
    if post_type == "entrega":
        html = template_entrega_especial(model, year, subtitle or "Especial", hero)
    else:
        html = template_new_car_day(model, year, subtitle or model, hero)

    render_to_image(html, out_path, height=1350)
    return out_path


# Paleta de marca Tucarro con Alejo
COLORS = {
    "bg":      (10, 10, 10),       # Negro profundo
    "red":     (204, 0, 0),        # Rojo Toyota
    "gold":    (255, 215, 0),      # Dorado/estrellas
    "white":   (255, 255, 255),
    "gray":    (160, 160, 160),
    "dark_red": (140, 0, 0),
}

TOYOTA_MODELS = [
    "Camry", "Corolla", "RAV4", "Highlander", "Tacoma",
    "Tundra", "4Runner", "Sienna", "Venza", "Crown",
    "bZ4X", "Prius", "C-HR", "Sequoia", "Land Cruiser"
]

def get_fonts():
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    font_path = next((p for p in paths if os.path.exists(p)), None)
    if font_path:
        return {
            "xl":   ImageFont.truetype(font_path, 72),
            "lg":   ImageFont.truetype(font_path, 54),
            "md":   ImageFont.truetype(font_path, 38),
            "sm":   ImageFont.truetype(font_path, 28),
            "xs":   ImageFont.truetype(font_path, 22),
        }
    default = ImageFont.load_default()
    return {k: default for k in ["xl", "lg", "md", "sm", "xs"]}

def add_brand_footer(draw, img_width, img_height, fonts):
    """Barra de marca inferior consistente en todas las plantillas."""
    draw.rectangle([0, img_height - 70, img_width, img_height], fill=COLORS["red"])
    draw.text((img_width // 2, img_height - 35),
              "@tucarroconalejo  •  Hollywood Toyota",
              font=fonts["sm"], fill=COLORS["white"], anchor="mm")

def add_stars(draw, x, y, count=5):
    """Estrellas doradas decorativas."""
    for i in range(count):
        draw.text((x + i * 28, y), "★", fill=COLORS["gold"])

def template_new_car_day(model: str, year: str = "2025", trim: str = "LE") -> str:
    """Plantilla celebración de entrega — NEW CAR DAY."""
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), COLORS["bg"])
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    # Fondo con textura sutil
    for i in range(0, H, 4):
        alpha = 12 + (i / H) * 18
        draw.line([(0, i), (W, i)], fill=(int(alpha), int(alpha), int(alpha)))

    # Barra superior roja
    draw.rectangle([0, 0, W, 10], fill=COLORS["red"])

    # Estrellas decorativas arriba
    add_stars(draw, 80, 50, 6)

    # Emoji lazo
    draw.text((W // 2, 180), "🎀", font=fonts["xl"], fill=COLORS["white"], anchor="mm")

    # NEW CAR DAY
    draw.text((W // 2, 290), "NEW CAR DAY!", font=fonts["xl"],
              fill=COLORS["white"], anchor="mm")

    # Línea roja divisoria
    draw.rectangle([80, 370, W - 80, 376], fill=COLORS["red"])

    # Modelo del carro
    draw.text((W // 2, 450), f"TOYOTA {model.upper()}", font=fonts["lg"],
              fill=COLORS["red"], anchor="mm")
    draw.text((W // 2, 530), f"{year}  •  {trim}", font=fonts["md"],
              fill=COLORS["gray"], anchor="mm")

    # Mensaje emocional
    draw.text((W // 2, 650), "¡Felicitaciones a la familia!", font=fonts["md"],
              fill=COLORS["white"], anchor="mm")
    draw.text((W // 2, 710), "Un sueño hecho realidad 🙌", font=fonts["sm"],
              fill=COLORS["gold"], anchor="mm")

    # Estrellas abajo
    add_stars(draw, 80, 800, 6)

    # Footer de marca
    add_brand_footer(draw, W, H, fonts)

    path = f"/tmp/nexus_newcarday_{model.lower()}.jpg"
    img.save(path, "JPEG", quality=95)
    return path

def template_tips(title: str, points: list) -> str:
    """Plantilla de tips y consejos."""
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), COLORS["bg"])
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    # Barra superior roja
    draw.rectangle([0, 0, W, 10], fill=COLORS["red"])

    # Franja lateral izquierda
    draw.rectangle([0, 0, 12, H], fill=COLORS["red"])

    # Título de sección
    draw.text((60, 70), "TUCARRO", font=fonts["lg"], fill=COLORS["red"])
    draw.text((60, 135), "CON ALEJO", font=fonts["lg"], fill=COLORS["white"])
    draw.rectangle([60, 200, 400, 206], fill=COLORS["red"])

    # Título del post
    y = 250
    words = title.upper().split()
    line, lines = "", []
    for word in words:
        test = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=fonts["md"])
        if bbox[2] > W - 120:
            lines.append(line)
            line = word
        else:
            line = test
    lines.append(line)
    for l in lines[:3]:
        draw.text((60, y), l, font=fonts["md"], fill=COLORS["white"])
        y += 52

    y += 30

    # Puntos
    for i, point in enumerate(points[:5]):
        num = f"0{i+1}"
        draw.text((60, y), num, font=fonts["md"], fill=COLORS["red"])
        text = point[:52] + "..." if len(point) > 52 else point
        draw.text((140, y + 4), text, font=fonts["sm"], fill=COLORS["white"])
        draw.line([(60, y + 52), (W - 60, y + 53)], fill=(40, 40, 40), width=1)
        y += 70

    # Footer
    add_brand_footer(draw, W, H, fonts)

    path = f"/tmp/nexus_tips_{title[:20].replace(' ', '_')}.jpg"
    img.save(path, "JPEG", quality=95)
    return path

def template_offer(model: str, price: str, feature: str) -> str:
    """Plantilla de oferta/promoción."""
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), COLORS["bg"])
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    # Barra superior
    draw.rectangle([0, 0, W, 10], fill=COLORS["red"])

    # Pregunta principal
    draw.text((W // 2, 160), "¿BUSCAS TU", font=fonts["lg"],
              fill=COLORS["white"], anchor="mm")
    draw.text((W // 2, 240), "PRÓXIMO TOYOTA?", font=fonts["lg"],
              fill=COLORS["red"], anchor="mm")

    # Emoji carro
    draw.text((W // 2, 360), "🚗", font=fonts["xl"], fill=COLORS["white"], anchor="mm")

    # Modelo destacado
    draw.rectangle([80, 460, W - 80, 466], fill=COLORS["red"])
    draw.text((W // 2, 510), f"TOYOTA {model.upper()}", font=fonts["xl"],
              fill=COLORS["white"], anchor="mm")
    draw.rectangle([80, 570, W - 80, 576], fill=COLORS["red"])

    # Precio
    draw.text((W // 2, 640), f"Desde ${price}/mes", font=fonts["lg"],
              fill=COLORS["gold"], anchor="mm")

    # Feature
    draw.text((W // 2, 720), feature, font=fonts["sm"],
              fill=COLORS["gray"], anchor="mm")

    # CTA
    draw.text((W // 2, 820), "📲 Escríbeme hoy", font=fonts["md"],
              fill=COLORS["white"], anchor="mm")
    draw.text((W // 2, 875), "Te ayudo a manejar tu Toyota esta semana",
              font=fonts["xs"], fill=COLORS["gray"], anchor="mm")

    # Footer
    add_brand_footer(draw, W, H, fonts)

    path = f"/tmp/nexus_offer_{model.lower()}.jpg"
    img.save(path, "JPEG", quality=95)
    return path

def get_car_jelly_url(model: str) -> str | None:
    """Returns a local path to a random color-variant jelly PNG for the model."""
    import json as _json
    lib = os.path.join(os.path.dirname(__file__), "car_library")
    index_path = os.path.join(lib, "index.json")
    try:
        with open(index_path, encoding="utf-8") as f:
            index = _json.load(f)
        variants = [p for p in index.get(model, []) if os.path.exists(p) and os.path.getsize(p) > 1000]
        if variants:
            return f"file://{random.choice(variants)}"
    except Exception:
        pass
    # Fallback: single PNG saved from toyota.com
    slug = model.lower().replace(" ", "_").replace("/", "")
    local = os.path.join(lib, f"{slug}.png")
    return f"file://{local}" if os.path.exists(local) else None


def generate_car_photo(topic: str, model: str = None) -> str:
    """Genera foto realista de Toyota con gpt-image-2."""
    car = model or random.choice(TOYOTA_MODELS)
    prompt = f"""Professional automotive photography.
    Toyota {car} at a modern dealership showroom.
    Dramatic studio lighting, cinematic quality.
    Context: {topic}
    Style: car magazine, clean background, photorealistic.
    No text, no watermarks."""

    response = client.images.generate(
        model="gpt-image-2",
        prompt=prompt,
        size="1024x1024",
        quality="medium",
        n=1
    )
    image_bytes = base64.b64decode(response.data[0].b64_json)
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in topic[:15].replace(" ", "_"))
    path = f"/tmp/nexus_photo_{car.lower()}_{safe}.jpg"
    with open(path, "wb") as f:
        f.write(image_bytes)
    print(f"Foto Toyota generada: {path}")
    return path

def generate_image_for_post(topic: str, post_type: str = "auto",
                             model: str = None, points: list = None) -> dict:
    """Genera la imagen correcta según el tipo de post."""
    if post_type == "auto":
        post_type = random.choice(["photo", "tips", "offer"])

    if post_type == "photo":
        path = generate_car_photo(topic, model)
        return {"type": "photo", "local_path": path}

    elif post_type == "new_car_day":
        car = model or random.choice(TOYOTA_MODELS)
        path = template_new_car_day(car)
        return {"type": "new_car_day", "local_path": path}

    elif post_type == "tips":
        pts = points or [
            "Tip 1 sobre el tema",
            "Tip 2 sobre el tema",
            "Tip 3 sobre el tema",
            "Tip 4 sobre el tema",
            "Tip 5 sobre el tema",
        ]
        path = template_tips(topic, pts)
        return {"type": "tips", "local_path": path}

    elif post_type == "offer":
        car = model or random.choice(TOYOTA_MODELS)
        path = template_offer(car, "399", "0% APR por 60 meses disponible")
        return {"type": "offer", "local_path": path}

    return {"type": "tips", "local_path": template_tips(topic, [])}

if __name__ == "__main__":
    print("Generando plantillas de prueba...")

    path1 = template_new_car_day("RAV4", "2025", "XLE Premium")
    print(f"New Car Day: {path1}")

    path2 = template_tips("5 razones para elegir Toyota", [
        "Mayor valor de reventa del mercado",
        "Confiabilidad comprobada por décadas",
        "Tecnología híbrida líder",
        "Red de servicio en todo USA",
        "Financiamiento flexible y accesible",
    ])
    print(f"Tips: {path2}")

    path3 = template_offer("Camry", "329", "0% APR por 60 meses disponible")
    print(f"Oferta: {path3}")

    import subprocess
    subprocess.run(["open", path1, path2, path3])
