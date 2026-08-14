"""HTML templates for @tucarroconalejo — Creative Direction: Premium Automotive.
Comparable to: Toyota Gazoo Racing, Porsche, Audi Sport, BMW M, Mercedes AMG.
"""
import base64
import os
import random

# ── Brand tokens ──────────────────────────────────────────────────────────────
_RED   = "#EB0028"   # Toyota red (235,0,40) — master prompt spec
_BG    = "#141414"   # Toyota Dark (20,20,20)
_BG2   = "#0F0F0F"   # Secondary black
_WHITE = "#FFFFFF"   # Pure white
_GRAY  = "#A0A0A0"   # Secondary info / specs

# Warm palette — entrega / celebración (master prompt — colores saturados del feed real)
_GOLD  = "#FFB300"   # Naranja-dorado brillante — título línea 1
_SKY   = "#4FC3F7"   # Azul cielo brillante — título línea 2
_ROSE  = "#FF4081"   # Rosa hot pink — título línea 3

# Fonts: Anton + Bebas Neue + Fredoka One + Dancing Script (quote cursive) + Inter
_FONTS = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Anton&family=Bebas+Neue&family=Fredoka+One'
    '&family=Dancing+Script:wght@700'
    '&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">'
)

# Toyota three-oval SVG logo
_TOYOTA = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 72" fill="none">'
    '<ellipse cx="50" cy="36" rx="48" ry="34" stroke="white" stroke-width="2.5"/>'
    '<ellipse cx="50" cy="36" rx="27" ry="14" stroke="white" stroke-width="2.5"/>'
    '<ellipse cx="50" cy="36" rx="14" ry="34" stroke="white" stroke-width="2.5"/>'
    '</svg>'
)

# Inline SVG icons for stats bar (engine · hybrid · mpg)
_IC_ENGINE = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" width="20" height="20">'
    '<rect x="2" y="8" width="12" height="8" rx="2"/>'
    '<path d="M14 11h3l2-2v6l-2-2h-3"/><path d="M5 8V6M9 8V6"/></svg>'
)
_IC_LEAF = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" width="20" height="20">'
    '<path d="M6 20c0-6 4-12 14-12-4 0-8 2-10 6"/>'
    '<path d="M4 20C4 14 9 8 20 8"/></svg>'
)
_IC_SPEED = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" width="20" height="20">'
    '<path d="M4 17A9 9 0 0120 17"/><path d="M12 8v3"/>'
    '<path d="M7.5 9.5l2 2"/><path d="M16.5 9.5l-2 2"/>'
    '<circle cx="12" cy="17" r="1.5" fill="currentColor"/>'
    '<line x1="12" y1="15.5" x2="10" y2="13.5"/></svg>'
)
_IC_CAL = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" width="20" height="20">'
    '<rect x="3" y="4" width="18" height="18" rx="2"/>'
    '<path d="M16 2v4M8 2v4M3 10h18"/></svg>'
)
_IC_PIN = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" width="20" height="20">'
    '<path d="M12 2a7 7 0 010 14C7 16 5 12 5 9a7 7 0 0114 0c0 3-2 7-7 9z"/>'
    '<circle cx="12" cy="9" r="2.5" fill="currentColor"/></svg>'
)
_IC_CAR = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"'
    ' stroke-linecap="round" width="20" height="20">'
    '<path d="M5 17H3v-5l2-5h14l2 5v5h-2"/>'
    '<circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>'
    '<path d="M5 12h14"/></svg>'
)

# Grain — 3% (spec)
_grain_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.72" numOctaves="4" stitchTiles="stitch"/></filter><rect width="200" height="200" filter="url(#n)"/></svg>'
_GRAIN_URI = "data:image/svg+xml;base64," + base64.b64encode(_grain_svg).decode()
_GRAIN_CSS = (
    f'body::after {{content:"";position:absolute;inset:0;z-index:98;pointer-events:none;'
    f'opacity:0.03;background:url("{_GRAIN_URI}") repeat;background-size:200px 200px;}}'
)

# Vignette — 15% at edges
_VIGNETTE = (
    '<div style="position:absolute;inset:0;z-index:9;pointer-events:none;'
    'background:radial-gradient(ellipse at 50% 50%,transparent 38%,rgba(0,0,0,0.15) 100%);"></div>'
)

# Structured specs: (stat1, stat2, stat3)
MODEL_SPECS_3 = {
    "GR Supra":        ("382 HP", "TURBO 3.0L", "0-60 EN 3.9S"),
    "GR86":            ("228 HP", "BOXER 2.4L", "6 VELOCIDADES"),
    "Camry":           ("203 HP", "2.5L 4 CIL.", "HÍBRIDO"),
    "RAV4":            ("203 HP", "AWD", "HYBRID DISPONIBLE"),
    "Tacoma":          ("326 HP", "TURBO 2.4L", "4WD"),
    "Tundra":          ("389 HP", "TWIN TURBO", "HYBRID"),
    "4Runner":         ("278 HP", "V6 4.0L", "4WD"),
    "Highlander":      ("265 HP", "V6 3.5L", "8 VELOCIDADES"),
    "Grand Highlander": ("362 HP", "TURBO", "AWD"),
    "Corolla":         ("169 HP", "2.0L", "CVT"),
    "Corolla Cross":   ("169 HP", "AWD", "5 PASAJEROS"),
    "Crown":           ("340 HP", "HYBRID", "AWD"),
    "Prius":           ("220 HP", "PLUG-IN HYBRID", "AWD"),
    "Sequoia":         ("437 HP", "TWIN TURBO", "HYBRID"),
    "Sienna":          ("245 HP", "HYBRID", "7-8 PASAJEROS"),
    "bZ4X":            ("201 HP", "100% ELÉCTRICO", "AWD"),
    "Land Cruiser":    ("326 HP", "TWIN TURBO", "4WD"),
}

# Flat string version (backward compat for other modules)
MODEL_SPECS = {k: " · ".join(v) for k, v in MODEL_SPECS_3.items()}


def _warm_particles_svg(seed: int = 42, w: int = 1080, h: int = 1350) -> str:
    """Bokeh dorado: círculos con blur + destellos ✦ + corazones ♥."""
    rng = random.Random(seed)
    filters, circles, overlay = [], [], []

    for i in range(22):
        x   = rng.randint(-20, w + 20)
        y   = rng.randint(-20, h + 20)
        r   = rng.randint(20, 60)
        op  = round(rng.uniform(0.06, 0.22), 2)
        clr = rng.choice(["#FFB300", "#FFD54F", "#FFFFFF", "#FFE082", "#FF8A65"])
        sd  = rng.randint(10, 26)
        fid = f"bk{i}"
        filters.append(f'<filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%">'
                        f'<feGaussianBlur stdDeviation="{sd}"/></filter>')
        circles.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{clr}" '
                        f'opacity="{op}" filter="url(#{fid})"/>')

    for _ in range(16):
        x  = rng.randint(30, w - 30)
        y  = rng.randint(30, h - 30)
        op = round(rng.uniform(0.22, 0.55), 2)
        sz = rng.randint(11, 22)
        clr = rng.choice(["#FFB300", "#FFFFFF"])
        overlay.append(f'<text x="{x}" y="{y}" font-family="serif" font-size="{sz}" '
                        f'fill="{clr}" opacity="{op}" text-anchor="middle">✦</text>')

    for _ in range(9):
        x  = rng.randint(40, w - 40)
        y  = rng.randint(40, h - 40)
        op = round(rng.uniform(0.28, 0.55), 2)
        sz = rng.randint(16, 30)
        overlay.append(f'<text x="{x}" y="{y}" font-family="serif" font-size="{sz}" '
                        f'fill="#FF4081" opacity="{op}" text-anchor="middle">♥</text>')

    defs = "<defs>" + "".join(filters) + "</defs>"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'style="position:absolute;inset:0;width:100%;height:100%;z-index:16;pointer-events:none">'
        + defs + "".join(circles) + "".join(overlay) + "</svg>"
    )


def _spec_icon_svg(spec_text: str, size: int = 32) -> str:
    """Retorna SVG inline que referencia semánticamente el texto de la spec."""
    t = spec_text.upper()
    if any(x in t for x in ("HÍBRIDO", "HYBRID", "ELÉCTRICO", "ELECTRIC", "PLUG-IN")):
        inner = (
            '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 '
            '0 5.5-4.78 10-10 10z"/>'
            '<path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>'
        )
    elif any(x in t for x in ("AWD", "4WD", "4X4")):
        inner = (
            '<circle cx="6" cy="16" r="2.5"/><circle cx="18" cy="16" r="2.5"/>'
            '<circle cx="6" cy="8" r="2.5"/><circle cx="18" cy="8" r="2.5"/>'
            '<path d="M6 10.5v3M18 10.5v3M8.5 8h7M8.5 16h7"/>'
        )
    elif any(x in t for x in ("HP", "CV")):
        inner = (
            '<rect x="2" y="8" width="12" height="8" rx="2"/>'
            '<path d="M14 11h3l2-2v6l-2-2h-3"/><path d="M5 8V6M9 8V6"/>'
        )
    elif "TURBO" in t:
        inner = (
            '<circle cx="12" cy="12" r="3.5"/>'
            '<path d="M12 2v3M12 19v3M2 12h3M19 12h3'
            'M5.22 5.22l2.12 2.12M16.66 16.66l2.12 2.12'
            'M5.22 18.78l2.12-2.12M16.66 7.34l2.12-2.12"/>'
        )
    elif any(x in t for x in ("0-60", "KMH", "0-6")):
        inner = (
            '<path d="M4 17A9 9 0 0 1 20 17"/>'
            '<path d="M12 17l-2.5-4.5"/>'
            '<circle cx="12" cy="17" r="1.2" fill="currentColor"/>'
        )
    elif any(x in t for x in ("PASAJEROS", "SEATS")):
        inner = (
            '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
            '<circle cx="9" cy="7" r="4"/>'
            '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
            '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
        )
    elif any(x in t for x in ("CVT", "VELOCIDADES")):
        inner = (
            '<circle cx="12" cy="12" r="3"/>'
            '<path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12'
            'M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>'
        )
    elif any(x in t for x in ("CIL", "V6", "V8", "BOXER", "2.5L", "3.5L", "4.0L", "3.0L", "2.4L", "2.0L")):
        inner = (
            '<rect x="2" y="7" width="14" height="10" rx="2"/>'
            '<path d="M16 10h4v4h-4M5 7V5M11 7V5"/>'
        )
    else:
        inner = (
            '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 '
            '12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
    )


def _img_b64(path: str) -> tuple[str, str]:
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    elif data[:4] == b"RIFF":
        mime = "image/webp"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    else:
        mime = "image/jpeg"
    return base64.b64encode(data).decode(), mime


def _confetti_svg(seed: int = 42) -> str:
    """Geometric celebration particles — angular, motorsport-style."""
    rng = random.Random(seed)
    shapes = []
    for _ in range(38):
        x     = rng.randint(40, 1040)
        y     = rng.randint(30, 650)
        w     = rng.randint(3, 7)
        h     = rng.randint(10, 22)
        angle = rng.randint(-50, 50)
        color = rng.choice([_WHITE, _RED, _GRAY])
        op    = round(rng.uniform(0.07, 0.16), 2)
        shapes.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'fill="{color}" opacity="{op}" transform="rotate({angle},{x},{y})"/>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'style="position:absolute;inset:0;width:100%;height:100%;z-index:16;pointer-events:none">'
        + "".join(shapes) + "</svg>"
    )


# ── Templates ─────────────────────────────────────────────────────────────────

def template_inventory(model: str, year: str = "2025", trim: str = "",
                        price: str = "", car_image_url: str = "",
                        promo: str = "", animated: bool = False) -> str:
    """
    RACING BOLD — franja diagonal roja + carro protagonista sobre ella.
    Anton gigante, specs bar, CTA footer con teléfono.
    animated=True activa keyframes CSS (para render_to_video):
    franja barre desde la derecha, carro entra desde la izquierda,
    título revela, specs escalonados.
    """
    from PIL import Image as _Img  # type: ignore[import]
    import io as _io

    has_car_image  = False
    car_img_tag    = '<div class="car-placeholder"></div>'
    reflection_tag = ""

    if car_image_url and car_image_url.startswith("file://"):
        local_path = car_image_url[7:]
        if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
            img     = _Img.open(local_path).convert("RGBA")
            bbox    = img.getbbox()
            cropped = img.crop(bbox) if bbox else img
            buf     = _io.BytesIO()
            cropped.save(buf, format="PNG")
            b64     = base64.b64encode(buf.getvalue()).decode()
            src     = f"data:image/png;base64,{b64}"
            car_img_tag    = f'<img class="car-img" src="{src}" alt="{model}">'
            reflection_tag = f'<img class="car-refl" src="{src}" alt="">'
            has_car_image  = True

    s1, s2, s3 = MODEL_SPECS_3.get(model, ("DISPONIBLE", "EN HOLLYWOOD", "FLORIDA"))
    trim_html  = f'<div class="trim-line">{trim}</div>' if trim else ""
    refl_block = f'<div class="refl-zone">{reflection_tag}</div>' if has_car_image else ""

    # Offer bar — red pill button above CTA
    if promo and price:
        offer_label = f"{promo} &nbsp;·&nbsp; {price}"
    elif promo:
        offer_label = promo
    elif price:
        offer_label = price
    else:
        offer_label = ""
    promo_html = (
        f'<div class="promo-pill">'
        f'<span class="promo-dot"></span>{offer_label}</div>'
    ) if offer_label else ""

    anim_css = """
  /* ── MODO ANIMADO ── */
  .slash       { animation: slashIn   0.8s cubic-bezier(.22,1,.36,1) both; }
  .slash-line  { animation: slashIn   0.8s cubic-bezier(.22,1,.36,1) 0.08s both; }
  .car-zone    { animation: carIn     1.1s cubic-bezier(.22,1,.36,1) 0.45s both; }
  .refl-zone   { animation: fadeIn    0.8s ease-out 1.4s both; }
  .model-name  { animation: riseIn    0.7s cubic-bezier(.22,1,.36,1) 1.15s both; }
  .trim-line   { animation: riseIn    0.6s ease-out 1.35s both; }
  .divider     { animation: growBar   0.5s ease-out 1.5s both; }
  .stat-cell:nth-child(1) { animation: riseIn 0.5s ease-out 1.55s both; }
  .stat-cell:nth-child(2) { animation: riseIn 0.5s ease-out 1.70s both; }
  .stat-cell:nth-child(3) { animation: riseIn 0.5s ease-out 1.85s both; }
  .promo-pill  { animation: popIn     0.45s cubic-bezier(.34,1.56,.64,1) 2.05s both; }
  .badge       { animation: fadeIn    0.5s ease-out 2.2s both; }
  .year-tag    { animation: fadeIn    0.5s ease-out 0.9s both; }
  .cta-strip   { animation: ctaUp     0.6s cubic-bezier(.22,1,.36,1) 0.25s both; }
  .cta-text    { animation: ctaPulse  1.6s ease-in-out 2.6s 2; }

  @keyframes slashIn  { from { transform: translateX(650px) rotate(16deg); } to { transform: translateX(0) rotate(16deg); } }
  @keyframes carIn    { from { transform: translateX(-1250px); } to { transform: translateX(0); } }
  @keyframes riseIn   { from { opacity:0; transform: translateY(70px); } to { opacity:1; transform: translateY(0); } }
  @keyframes fadeIn   { from { opacity:0; } to { opacity:1; } }
  @keyframes growBar  { from { width:0; } to { width:40px; } }
  @keyframes popIn    { from { opacity:0; transform: scale(.6); } to { opacity:1; transform: scale(1); } }
  @keyframes ctaUp    { from { transform: translateY(80px); } to { transform: translateY(0); } }
  @keyframes ctaPulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.05); } }
""" if animated else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">{_FONTS}
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1080px; background:{_BG}; overflow:hidden; position:relative; font-family:'Anton',sans-serif; }}

/* franja diagonal racing */
.slash {{
  position:absolute; top:-140px; right:-300px;
  width:500px; height:1500px;
  background:{_RED};
  transform:rotate(16deg);
  z-index:8;
}}
.slash-line {{
  position:absolute; top:-140px; right:-385px;
  width:34px; height:1500px;
  background:#fff;
  transform:rotate(16deg);
  z-index:8;
}}

.atmos {{
  position:absolute; inset:0; z-index:1;
  background:
    radial-gradient(ellipse at 65% 15%, rgba(20,15,10,0.95) 0%, transparent 50%),
    radial-gradient(ellipse at 5% 100%, rgba(235,10,30,0.04) 0%, transparent 40%);
}}
.ghost {{
  position:absolute; top:-15px; left:-10px; z-index:2;
  font-size:290px; color:rgba(255,255,255,0.018);
  line-height:0.82; letter-spacing:-8px; white-space:nowrap; user-select:none;
}}
.top-stripe {{
  position:absolute; top:0; left:0; right:0; height:2px;
  background:linear-gradient(90deg,transparent,{_RED} 20%,{_RED} 50%,transparent);
  z-index:50;
}}
/* Year — top left, prominent red */
.year-tag {{
  position:absolute; top:30px; left:60px; z-index:40;
  font-family:'Bebas Neue',sans-serif; font-size:28px;
  color:{_RED}; letter-spacing:6px;
}}
/* EN STOCK badge — top right */
.badge {{
  position:absolute; top:24px; right:28px; z-index:50;
  background:rgba(235,10,30,0.10);
  backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px);
  border:1px solid rgba(235,10,30,0.45);
  color:{_WHITE}; padding:7px 20px;
  font-family:'Inter',sans-serif; font-size:11px; font-weight:700; letter-spacing:7px; text-transform:uppercase;
}}
/* Red glow — 30% opacity, blur 150px (spec) */
.car-glow {{
  position:absolute; left:50%; transform:translateX(-50%);
  top:24%; width:860px; height:440px;
  background:radial-gradient(ellipse at 50% 65%, rgba(235,10,30,0.30) 0%, transparent 68%);
  filter:blur(150px); z-index:5; pointer-events:none;
}}
/* Car zone — center, slightly right */
.car-zone {{
  position:absolute; left:20%; top:8%; width:72%; height:54%;
  display:flex; align-items:flex-end; justify-content:center; z-index:20;
}}
.car-img {{
  width:100%; height:100%; object-fit:contain; object-position:center bottom;
  filter:
    drop-shadow(0 60px 80px rgba(0,0,0,0.80))
    drop-shadow(0 20px 40px rgba(0,0,0,0.55));
}}
.car-placeholder {{
  width:100%; height:100%;
  background:radial-gradient(ellipse at center, rgba(235,10,30,0.03) 0%, transparent 70%);
}}
/* Ground line */
.ground {{
  position:absolute; top:63%; left:50%; transform:translateX(-50%);
  width:900px; height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,0.06) 25%,rgba(255,255,255,0.10) 50%,rgba(255,255,255,0.06) 75%,transparent);
  z-index:18;
}}
/* Reflection — 15% opacity */
.refl-zone {{
  position:absolute; left:20%; top:63%; width:72%; height:16%;
  transform:scaleY(-1); z-index:15; pointer-events:none;
  opacity:0.15;
  -webkit-mask-image:linear-gradient(to bottom,rgba(0,0,0,0.65) 0%,transparent 100%);
  mask-image:linear-gradient(to bottom,rgba(0,0,0,0.65) 0%,transparent 100%);
  overflow:hidden;
}}
.car-refl {{ width:100%; height:100%; object-fit:contain; object-position:center top; }}

/* Model info — bottom left */
.info {{
  position:absolute; left:0; top:65%; right:0; z-index:30; padding:0 60px;
}}
.model-name {{
  font-size:168px; color:{_WHITE}; letter-spacing:1px; line-height:0.84;
  text-shadow:0 4px 40px rgba(0,0,0,0.9);
}}
.trim-line {{
  font-family:'Bebas Neue',sans-serif; font-size:28px;
  letter-spacing:10px; color:{_GRAY}; margin-top:4px;
}}
/* Thin red divider */
.divider {{
  width:40px; height:1.5px; background:{_RED}; margin:14px 0;
  box-shadow:0 0 8px rgba(235,10,30,0.5);
}}

/* Stats bar — 3-column glass panel */
.stats-bar {{
  position:absolute; left:0; bottom:84px; right:0; z-index:35;
  padding:0 60px;
}}
.stats-inner {{
  display:flex; align-items:stretch;
  background:rgba(255,255,255,0.03);
  backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
  border:1px solid rgba(255,255,255,0.07);
}}
.stat-cell {{
  flex:1; display:flex; align-items:center; gap:12px;
  padding:14px 20px; color:rgba(160,160,160,0.8);
}}
.stat-cell + .stat-cell {{
  border-left:1px solid rgba(255,255,255,0.07);
}}
.stat-icon {{ flex-shrink:0; color:rgba(235,10,30,0.65); }}
.stat-text {{
  font-family:'Bebas Neue',sans-serif; font-size:22px;
  color:{_WHITE}; letter-spacing:2px; line-height:1;
}}

/* Promo pill — above stats */
.promo-pill {{
  position:absolute; left:60px; bottom:168px; z-index:36;
  display:inline-flex; align-items:center; gap:10px;
  background:{_RED}; padding:8px 22px 8px 16px;
  font-family:'Inter',sans-serif; font-size:18px; font-weight:700;
  letter-spacing:2px; color:{_WHITE}; text-transform:uppercase;
  clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%);
}}
.promo-dot {{
  width:8px; height:8px; border-radius:50%; background:rgba(255,255,255,0.7); flex-shrink:0;
}}

/* Franja roja inferior */
.cta-strip {{
  position:absolute; left:0; bottom:0; right:0; height:76px; z-index:40;
  display:flex; align-items:center; justify-content:space-between;
  padding:0 60px;
  background:linear-gradient(90deg,{_RED} 0%,#9a0010 55%,#6a000a 100%);
}}
.cta-text {{
  font-family:'Inter',sans-serif; font-size:16px; font-weight:400;
  letter-spacing:0.18em; color:rgba(255,255,255,0.85);
}}
.footer-logo svg {{
  width:44px; height:31px;
  filter:drop-shadow(0 1px 4px rgba(0,0,0,0.5));
}}
{_GRAIN_CSS}
{anim_css}
</style></head>
<body>
<div class="atmos"></div>
<div class="ghost">{model.upper()}</div>
<div class="slash"></div>
<div class="slash-line"></div>
<div class="top-stripe"></div>
<div class="year-tag">{year}</div>
<div class="badge">EN STOCK</div>
<div class="car-glow"></div>
<div class="car-zone">{car_img_tag}</div>
<div class="ground"></div>
{refl_block}
<div class="info">
  <div class="model-name">{model.upper()}</div>
  {trim_html}
  <div class="divider"></div>
</div>
<div class="stats-bar">
  <div class="stats-inner">
    <div class="stat-cell"><span class="stat-icon">{_IC_ENGINE}</span><span class="stat-text">{s1}</span></div>
    <div class="stat-cell"><span class="stat-icon">{_IC_LEAF}</span><span class="stat-text">{s2}</span></div>
    <div class="stat-cell"><span class="stat-icon">{_IC_SPEED}</span><span class="stat-text">{s3}</span></div>
  </div>
</div>
{promo_html}
<div class="cta-strip">
  <div class="footer-logo">{_TOYOTA}</div>
  <div class="cta-text">@tucarroconalejo &nbsp;·&nbsp; ESCRÍBEME (954) 910-6671</div>
</div>
{_VIGNETTE}
</body></html>"""


def _photo_template(*, seed: int, titulo: str, acento: str, photo_path: str) -> str:
    """Base compartida: quote-style + foto centrada + vignette radial + texto grande."""
    has_photo = photo_path and os.path.exists(photo_path) and os.path.getsize(photo_path) > 1000
    if has_photo:
        b64, mime = _img_b64(photo_path)
        foto_html = f'<img class="foto" src="data:{mime};base64,{b64}" alt="">'
    else:
        foto_html = ""

    particles = _warm_particles_svg(seed=seed, w=1080, h=1350)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@700&family=Inter:wght@700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}

  body {{
    width: 1080px;
    height: 1350px;
    background: #181818;
    overflow: hidden;
    position: relative;
  }}

  /* foto full-bleed centrada */
  .foto {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center center;
    z-index: 1;
  }}

  /* atmósfera dorada en esquinas */
  .atmos {{
    position: absolute; inset: 0; z-index: 2;
    background:
      radial-gradient(ellipse 70% 55% at 15% 90%, rgba(255,179,0,0.09) 0%, transparent 100%),
      radial-gradient(ellipse 60% 50% at 85% 10%, rgba(255,179,0,0.06) 0%, transparent 100%);
  }}

  /* vignette radial suave: centro casi transparente → bordes ligeros */
  .vignette {{
    position: absolute; inset: 0; z-index: 3;
    background: radial-gradient(
      ellipse 85% 85% at 50% 50%,
      rgba(0,0,0,0.00) 0%,
      rgba(0,0,0,0.18) 100%
    );
  }}

  /* texto parte superior */
  .contenido {{
    position: absolute;
    top: 60px; left: 0; right: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    padding: 0 72px;
    z-index: 20;
  }}

  /* Inter bold blanco — +30% sobre los 80px anteriores */
  .titulo {{
    font-family: 'Inter', sans-serif;
    font-size: 104px;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1.05;
    letter-spacing: -0.01em;
    text-shadow: 0 4px 20px rgba(0,0,0,0.85);
  }}

  /* Dancing Script dorado — +30% sobre los 108px anteriores */
  .acento {{
    font-family: 'Dancing Script', cursive;
    font-size: 140px;
    font-weight: 700;
    color: #FFB300;
    line-height: 1.1;
    text-shadow: 0 4px 24px rgba(0,0,0,0.75), 0 0 50px rgba(255,179,0,0.14);
    margin-top: 6px;
  }}

  /* Felicidades — Dancing Script dorado, igual que .acento del quote */
  .felicidades {{
    font-family: 'Dancing Script', cursive;
    font-size: 68px;
    font-weight: 700;
    color: #FFB300;
    line-height: 1.1;
    text-shadow: 0 3px 20px rgba(0,0,0,0.6), 0 0 40px rgba(255,179,0,0.12);
    margin-top: 8px;
  }}

  /* franja roja inferior — igual que tips */
  .footer {{
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 76px;
    background: linear-gradient(90deg, {_RED} 0%, #9a0010 55%, #6a000a 100%);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 72px;
    z-index: 30;
  }}

  .footer-logo svg {{
    width: 44px; height: 31px;
    filter: drop-shadow(0 1px 4px rgba(0,0,0,0.5));
  }}

  .footer-handle {{
    font-family: 'Inter', sans-serif;
    font-size: 16px;
    font-weight: 400;
    letter-spacing: 0.18em;
    color: rgba(255,255,255,0.85);
  }}
</style>
</head>
<body>
  {foto_html}
  <div class="atmos"></div>
  <div class="vignette"></div>
  {particles}
  <div class="contenido">
    <div class="titulo">{titulo}</div>
    <div class="acento">{acento}</div>
    <div class="felicidades">&#10024; Felicidades &#10024;</div>
  </div>
  <div class="footer">
    <div class="footer-logo">{_TOYOTA}</div>
    <span class="footer-handle">@tucarroconalejo &nbsp;·&nbsp; Hollywood Toyota</span>
  </div>
</body>
</html>"""


def template_entrega_especial(model: str, year: str = "2026",  # noqa: ARG001
                               customer_name: str = "", photo_path: str = "") -> str:
    _ = model, year  # API pública requerida por main.py
    return _photo_template(
        seed=77,
        titulo="Entrega",
        acento=customer_name if customer_name else "Especial",
        photo_path=photo_path,
    )


def template_new_car_day(model: str, year: str = "2026",  # noqa: ARG001
                          customer_name: str = "", photo_path: str = "") -> str:
    _ = year  # API pública requerida por main.py
    return _photo_template(
        seed=55,
        titulo="New Car",
        acento=customer_name if customer_name else model,
        photo_path=photo_path,
    )


def template_inventory_clean(model: str, year: str = "2026", trim: str = "",
                              photo_path: str = "", promo: str = "") -> str:
    """
    CLEAN REAL (estilo @yourcarmoment) — foto lifestyle full-bleed,
    tipografía mínima, gradiente sutil abajo. Cero poster gráfico.
    photo_path: foto AI fotorrealista o foto real del lote.
    """
    b64, mime = _img_b64(photo_path)
    trim_html = f'<div class="trim">{trim}</div>' if trim else ""
    promo_html = f'<div class="promo">{promo}</div>' if promo else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1080px; overflow:hidden; position:relative; background:#0A0A0A; }}

.foto {{
  position:absolute; inset:0; width:100%; height:100%;
  object-fit:cover; object-position:center;
}}
.grad {{
  position:absolute; left:0; right:0; bottom:0; height:46%;
  background:linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.72) 78%);
}}
.grad-top {{
  position:absolute; left:0; right:0; top:0; height:16%;
  background:linear-gradient(0deg, transparent 0%, rgba(0,0,0,0.35) 100%);
}}

.kicker {{
  position:absolute; top:52px; left:60px;
  font-family:'Inter',sans-serif; font-size:19px; font-weight:600;
  letter-spacing:0.42em; color:rgba(255,255,255,0.92);
}}
.chip {{
  position:absolute; top:44px; right:56px;
  border:1px solid rgba(255,255,255,0.65);
  padding:8px 20px;
  font-family:'Inter',sans-serif; font-size:14px; font-weight:600;
  letter-spacing:0.3em; color:#fff;
}}

.info {{
  position:absolute; left:60px; right:60px; bottom:64px;
}}
.modelo {{
  font-family:'Bebas Neue',sans-serif; font-size:110px;
  color:#fff; line-height:0.95; letter-spacing:0.015em;
  text-shadow:0 2px 24px rgba(0,0,0,0.45);
}}
.trim {{
  font-family:'Inter',sans-serif; font-size:22px; font-weight:400;
  letter-spacing:0.22em; color:rgba(255,255,255,0.85);
  text-transform:uppercase; margin-top:6px;
}}
.linea {{
  width:56px; height:3px; background:{_RED}; margin:20px 0 16px;
}}
.promo {{
  font-family:'Inter',sans-serif; font-size:24px; font-weight:600;
  color:#fff; margin-bottom:6px;
}}
.cta {{
  font-family:'Inter',sans-serif; font-size:19px; font-weight:400;
  letter-spacing:0.06em; color:rgba(255,255,255,0.75);
}}
.cta b {{ color:#fff; font-weight:600; }}
</style></head>
<body>
<img class="foto" src="data:{mime};base64,{b64}" alt="{model}">
<div class="grad"></div>
<div class="grad-top"></div>
<div class="kicker">TOYOTA · {year}</div>
<div class="chip">EN STOCK</div>
<div class="info">
  <div class="modelo">{model.upper()}</div>
  {trim_html}
  <div class="linea"></div>
  {promo_html}
  <div class="cta">@tucarroconalejo &nbsp;·&nbsp; <b>Escríbeme (954) 910-6671</b></div>
</div>
</body></html>"""


def template_quote(line1: str, line2: str = "", accent: str = "") -> str:
    """
    MIAMI HEAT — gradiente atardecer rojo-negro South Florida,
    líneas Bebas Neue blancas, palabra acento Anton gigante con
    gradiente cálido. La palabra acento NO se repite: se extrae
    de las líneas si ya aparece en ellas.
    """
    accent_word = accent if accent else (line2 if line2 else "")
    # Evitar duplicado: si el acento ya está en una línea, quitarlo de ella
    def _strip(line: str) -> str:
        if accent_word and accent_word.lower() in line.lower():
            idx = line.lower().rfind(accent_word.lower())
            line = (line[:idx] + line[idx + len(accent_word):]).strip(" ,.:;—-")
        return line
    l1 = _strip(line1)
    l2 = _strip(line2) if (line2 and accent) else ""
    lines_html = f'<div class="ql">{l1}</div>'
    if l2:
        lines_html += f'<div class="ql">{l2}</div>'

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Bebas+Neue&family=Inter:wght@400;700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}

  body {{
    width: 1080px;
    height: 1080px;
    background: linear-gradient(180deg, #0A0A0A 0%, #1a0508 45%, #5c0a14 78%, {_RED} 130%);
    overflow: hidden;
    position: relative;
  }}

  /* brillo cálido de atardecer al fondo */
  .atmos {{
    position: absolute;
    left: 0; right: 0; bottom: 90px;
    height: 420px;
    z-index: 1;
    background: radial-gradient(ellipse at 50% 100%, rgba(255,122,69,0.25) 0%, transparent 60%);
  }}

  .kicker {{
    position: absolute;
    top: 78px; left: 72px;
    font-family: 'Inter', sans-serif;
    font-size: 20px; font-weight: 700;
    letter-spacing: 0.4em;
    color: #ff9d8a;
    z-index: 20;
  }}

  .contenido {{
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 90px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0 72px;
    z-index: 20;
  }}

  .ql {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 110px;
    color: #FFFFFF;
    line-height: 1.0;
    letter-spacing: 0.01em;
    text-shadow: 0 4px 24px rgba(0,0,0,0.55);
  }}

  .acento {{
    font-family: 'Anton', sans-serif;
    font-size: 240px;
    line-height: 1;
    margin-top: 8px;
    background: linear-gradient(90deg, #ffb199, {_RED});
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    filter: drop-shadow(0 6px 20px rgba(0,0,0,0.45));
  }}

  .footer {{
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 90px;
    background: rgba(0,0,0,0.55);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 60px;
    z-index: 30;
  }}

  .footer-left {{ display:flex; align-items:center; gap:20px; }}
  .footer-left svg {{ width: 44px; height: 31px; filter: drop-shadow(0 1px 4px rgba(0,0,0,0.5)); }}

  .footer-handle {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 32px;
    letter-spacing: 0.06em;
    color: #FFFFFF;
  }}

  .footer-cta {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 32px;
    letter-spacing: 0.06em;
    color: #ff9d8a;
  }}
</style>
</head>
<body>
  <div class="atmos"></div>
  <div class="kicker">HOLLYWOOD · FLORIDA</div>
  <div class="contenido">
    {lines_html}
    <div class="acento">{accent_word.upper()}</div>
  </div>
  <div class="footer">
    <div class="footer-left">{_TOYOTA}<span class="footer-handle">@tucarroconalejo</span></div>
    <span class="footer-cta">ESCRÍBEME · (954) 910-6671</span>
  </div>
</body>
</html>"""


def template_tips_html(title: str, points: list) -> str:
    """PREMIUM MINIMAL — negro limpio, tipografía editorial Inter,
    números Bebas rojos, subtítulos (título::subtítulo) renderizados."""
    items_html = ""
    for i, point in enumerate(points[:5]):
        parts = str(point).split("::", 1)
        txt = parts[0].strip()
        sub = parts[1].strip() if len(parts) > 1 else ""
        sub_html = f'<div class="sub">{sub}</div>' if sub else ""
        items_html += f"""
    <div class="item">
      <span class="num">0{i+1}</span>
      <div class="body">
        <div class="txt">{txt}</div>
        {sub_html}
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}

  body {{
    width: 1080px;
    height: 1080px;
    background: #0A0A0A;
    overflow: hidden;
    position: relative;
  }}

  .tick {{
    position: absolute;
    top: 88px; left: 72px;
    width: 70px; height: 6px;
    background: {_RED};
  }}

  .kicker {{
    position: absolute;
    top: 126px; left: 72px;
    font-family: 'Inter', sans-serif;
    font-size: 20px; font-weight: 400;
    letter-spacing: 0.45em;
    color: #666;
  }}

  .contenido {{
    position: absolute;
    top: 190px; left: 0; right: 0; bottom: 90px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0 72px;
    z-index: 20;
  }}

  .titulo {{
    font-family: 'Inter', sans-serif;
    font-size: 58px;
    font-weight: 900;
    color: #FFFFFF;
    line-height: 1.12;
    letter-spacing: -0.01em;
    margin-bottom: 44px;
  }}
  .titulo .rojo {{ color: {_RED}; }}

  .item {{
    display: flex;
    align-items: flex-start;
    gap: 26px;
    padding: 17px 0;
    border-bottom: 1px solid rgba(255,255,255,0.09);
  }}
  .item:last-child {{ border-bottom: none; }}

  .num {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 46px;
    color: {_RED};
    line-height: 1;
    min-width: 56px;
    padding-top: 2px;
  }}

  .body {{ flex: 1; }}

  .txt {{
    font-family: 'Inter', sans-serif;
    font-size: 29px;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1.25;
  }}

  .sub {{
    font-family: 'Inter', sans-serif;
    font-size: 21px;
    font-weight: 400;
    color: #8a8a8a;
    line-height: 1.3;
    margin-top: 4px;
  }}

  .footer {{
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 90px;
    background: #111111;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 60px;
    z-index: 30;
  }}

  .footer-left {{ display:flex; align-items:center; gap:20px; }}
  .footer-left svg {{ width: 44px; height: 31px; }}

  .footer-handle {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 32px;
    letter-spacing: 0.06em;
    color: #FFFFFF;
  }}

  .footer-cta {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 32px;
    letter-spacing: 0.06em;
    color: {_RED};
  }}
</style>
</head>
<body>
  <div class="tick"></div>
  <div class="kicker">TU CARRO CON ALEJO</div>
  <div class="contenido">
    <div class="titulo">{title}</div>
    {items_html}
  </div>
  <div class="footer">
    <div class="footer-left">{_TOYOTA}<span class="footer-handle">@tucarroconalejo</span></div>
    <span class="footer-cta">ESCRÍBEME · (954) 910-6671</span>
  </div>
</body>
</html>"""


def template_carousel(slide_number: int, total_slides: int, title: str,
                       headline: str, body_lines: list,
                       icon: str = "") -> str:
    """
    Educational carousel slide — 15% header, 70% content, 15% footer.
    Inter body, 3 hierarchy levels max, breathable mobile-first spacing.
    """
    lines_html = "".join(
        f'<div class="body-line"><span class="dot"></span><span class="line-text">{line}</span></div>'
        for line in body_lines[:4]
    )
    icon_html = f'<div class="icon">{icon}</div>' if icon else ""
    progress  = round((slide_number / total_slides) * 100)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">{_FONTS}
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:1080px; height:1080px; background:{_BG};
  overflow:hidden; position:relative; font-family:'Inter',sans-serif;
}}
.bg-layer {{
  position:absolute; inset:0; z-index:1;
  background:radial-gradient(ellipse at 80% 20%,rgba(15,15,20,0.9) 0%,transparent 60%);
}}
/* Header — 15% (~162px) */
.header {{
  position:absolute; top:0; left:0; right:0; height:162px; z-index:20;
  display:flex; align-items:center; justify-content:space-between;
  padding:0 72px; border-bottom:1px solid rgba(255,255,255,0.06);
}}
.brand {{
  font-family:'Anton',sans-serif; font-size:28px; color:{_WHITE}; letter-spacing:3px;
}}
.brand span {{ color:{_RED}; }}
.slide-count {{
  font-family:'Inter',sans-serif; font-size:14px; font-weight:500;
  color:{_GRAY}; letter-spacing:4px;
}}
.progress {{
  position:absolute; bottom:0; left:0; height:2px; z-index:25;
  background:{_RED}; width:{progress}%; box-shadow:0 0 8px rgba(235,10,30,0.5);
}}
/* Content — 70% (~756px) */
.content {{
  position:absolute; top:162px; left:0; right:0; height:756px; z-index:10;
  display:flex; flex-direction:column; justify-content:center; padding:0 72px;
}}
.topic-tag {{
  display:inline-flex; align-items:center; gap:10px; margin-bottom:28px;
  font-family:'Bebas Neue',sans-serif; font-size:20px;
  letter-spacing:8px; color:rgba(235,10,30,0.80); text-transform:uppercase;
}}
.topic-tag::before {{ content:''; display:inline-block; width:20px; height:1px; background:{_RED}; }}
.headline {{
  font-family:'Anton',sans-serif; font-size:80px; color:{_WHITE};
  letter-spacing:1px; line-height:0.88; margin-bottom:36px;
}}
.icon {{ font-size:60px; margin-bottom:24px; }}
.body-line {{ display:flex; align-items:flex-start; gap:18px; margin-bottom:22px; }}
.dot {{
  display:inline-block; width:6px; height:6px; border-radius:50%;
  background:{_RED}; flex-shrink:0; margin-top:11px;
  box-shadow:0 0 6px rgba(235,10,30,0.5);
}}
.line-text {{
  font-size:30px; font-weight:400; color:rgba(245,245,245,0.82); line-height:1.35;
}}
/* Footer — 15% (~162px) */
.footer {{
  position:absolute; bottom:0; left:0; right:0; height:162px; z-index:20;
  display:flex; align-items:center; justify-content:space-between;
  padding:0 72px; border-top:1px solid rgba(255,255,255,0.06);
}}
.handle {{ font-size:16px; font-weight:300; letter-spacing:5px; color:rgba(160,160,160,0.40); }}
.cta-footer {{
  display:flex; align-items:center; gap:10px; font-family:'Bebas Neue',sans-serif;
  font-size:20px; letter-spacing:5px; color:{_GRAY}; text-transform:uppercase;
}}
.cta-arrow {{ color:{_RED}; }}
{_GRAIN_CSS}
</style></head>
<body>
<div class="bg-layer"></div>
<div class="header">
  <div class="brand">TUCARRO <span>CON ALEJO</span></div>
  <div class="slide-count">{slide_number:02d} / {total_slides:02d}</div>
  <div class="progress"></div>
</div>
<div class="content">
  <div class="topic-tag">{title}</div>
  {icon_html}
  <div class="headline">{headline}</div>
  {lines_html}
</div>
<div class="footer">
  <div class="handle">@tucarroconalejo</div>
  <div class="cta-footer">Hollywood Toyota <span class="cta-arrow">&#8594;</span></div>
</div>
</body></html>"""


def template_ai_promo(model: str, year: str, photo_path: str, promo: str = "") -> str:
    """Slide 1/3 — Hero: foto full-bleed + overlay texto estilo quote."""
    b64, mime = _img_b64(photo_path)
    photo_uri = f"data:{mime};base64,{b64}"
    particles = _warm_particles_svg(seed=hash(model) % 999, w=1080, h=1350)
    promo_html = f'<div class="promo-tag">{promo}</div>' if promo else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Bebas+Neue&family=Inter:wght@700;400&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; position:relative; background:#181818; }}

  .foto {{
    position:absolute; inset:0;
    width:100%; height:100%;
    object-fit:cover; object-position:center 30%;
    z-index:1;
  }}
  .vignette {{
    position:absolute; inset:0; z-index:2;
    background:
      linear-gradient(to bottom, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.10) 40%, rgba(0,0,0,0.10) 60%, rgba(0,0,0,0.70) 100%);
  }}
  .atmos {{
    position:absolute; inset:0; z-index:3;
    background:
      radial-gradient(ellipse 70% 50% at 10% 90%, rgba(255,179,0,0.07) 0%, transparent 100%),
      radial-gradient(ellipse 60% 40% at 90% 10%, rgba(255,179,0,0.05) 0%, transparent 100%);
  }}

  /* texto — arriba */
  .contenido {{
    position:absolute; top:60px; left:0; right:0;
    padding:0 72px; z-index:20;
    display:flex; flex-direction:column;
  }}
  .slide-label {{
    font-family:'Inter', sans-serif;
    font-size:13px; font-weight:400;
    letter-spacing:0.22em; text-transform:uppercase;
    color:rgba(255,255,255,0.45);
    margin-bottom:14px;
  }}
  .titulo {{
    font-family:'Anton', sans-serif;
    font-size:130px; font-weight:400;
    color:#FFFFFF; line-height:1.0;
    text-shadow: 0 4px 20px rgba(0,0,0,0.85);
  }}
  .acento {{
    font-family:'Bebas Neue', sans-serif;
    font-size:52px; font-weight:400;
    color:#fff; line-height:1.1;
    letter-spacing:0.14em;
    text-shadow: 0 4px 24px rgba(0,0,0,0.75);
    margin-top:10px;
  }}
  .promo-tag {{
    margin-top:20px;
    display:inline-flex; align-items:center; gap:10px;
    background:rgba(235,0,40,0.85); padding:10px 24px;
    font-family:'Inter', sans-serif; font-size:22px; font-weight:700;
    color:#fff; letter-spacing:0.06em;
  }}

  /* franja roja inferior */
  .footer {{
    position:absolute; bottom:0; left:0; right:0; height:76px; z-index:30;
    background:linear-gradient(90deg,{_RED} 0%,#9a0010 55%,#6a000a 100%);
    display:flex; align-items:center; justify-content:space-between; padding:0 72px;
  }}
  .footer svg {{ width:44px; height:31px; filter:drop-shadow(0 1px 4px rgba(0,0,0,0.5)); }}
  .footer-handle {{
    font-family:'Inter', sans-serif; font-size:16px; font-weight:400;
    letter-spacing:0.18em; color:rgba(255,255,255,0.85);
  }}
</style>
</head>
<body>
  <img class="foto" src="{photo_uri}" alt="">
  <div class="vignette"></div>
  <div class="atmos"></div>
  {particles}
  <div class="contenido">
    <div class="slide-label">Toyota {year} &nbsp;·&nbsp; 01 / 03</div>
    <div class="titulo">{model.upper()}</div>
    <div class="acento">HOLLYWOOD TOYOTA</div>
    {promo_html}
  </div>
  <div class="footer">
    <div>{_TOYOTA}</div>
    <span class="footer-handle">@tucarroconalejo &nbsp;·&nbsp; ESCRÍBEME (954) 910-6671</span>
  </div>
</body>
</html>"""


def template_ai_promo_s2(model: str, year: str, promo: str = "") -> str:
    """Slide 2/3 — RACING BOLD: negro + franja diagonal roja, Anton gigante."""
    specs = MODEL_SPECS_3.get(model, ("", "", ""))
    s1, s2, s3 = specs

    items_html = ""
    for i, spec in enumerate([s1, s2, s3]):
        if spec:
            items_html += f"""
    <div class="item">
      <span class="num">0{i+1}</span>
      <span class="txt">{spec}</span>
    </div>"""

    promo_html = f'<div class="promo-tag">{promo}</div>' if promo else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Bebas+Neue&family=Inter:wght@400;700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; position:relative; background:#0A0A0A; }}

  /* franja diagonal racing */
  .slash {{
    position:absolute; top:-120px; right:-320px;
    width:540px; height:1750px;
    background:{_RED};
    transform:rotate(16deg);
    z-index:1;
  }}
  .slash-line {{
    position:absolute; top:-120px; right:-410px;
    width:38px; height:1750px;
    background:#fff;
    transform:rotate(16deg);
    z-index:1;
  }}

  .contenido {{
    position:absolute; top:0; left:0; right:200px; bottom:90px;
    display:flex; flex-direction:column; justify-content:center;
    padding:0 72px; z-index:20;
  }}

  .slide-label {{
    font-family:'Inter', sans-serif;
    font-size:16px; font-weight:700;
    letter-spacing:0.35em; text-transform:uppercase;
    color:#888;
    margin-bottom:18px;
  }}
  .anio {{
    font-family:'Bebas Neue', sans-serif;
    font-size:44px; color:{_RED};
    letter-spacing:0.12em; line-height:1;
  }}
  .titulo {{
    font-family:'Anton', sans-serif;
    font-size:150px; color:#FFFFFF;
    line-height:1.0; margin-bottom:52px;
  }}

  .item {{
    display:flex; align-items:center; gap:24px;
    padding:18px 0;
    border-bottom:1px solid rgba(255,255,255,0.10);
  }}
  .item:last-child {{ border-bottom:none; }}
  .num {{
    font-family:'Bebas Neue', sans-serif;
    font-size:44px; color:{_RED};
    min-width:56px; line-height:1;
  }}
  .txt {{
    font-family:'Bebas Neue', sans-serif;
    font-size:40px; color:#FFFFFF;
    letter-spacing:0.04em;
  }}

  .promo-tag {{
    margin-top:40px;
    align-self:flex-start;
    background:{_RED}; padding:14px 30px;
    font-family:'Bebas Neue', sans-serif; font-size:34px;
    color:#fff; letter-spacing:0.08em;
  }}

  .footer {{
    position:absolute; bottom:0; left:0; right:0; height:90px; z-index:30;
    background:{_RED};
    display:flex; align-items:center; justify-content:space-between; padding:0 60px;
  }}
  .footer-left {{ display:flex; align-items:center; gap:20px; }}
  .footer-left svg {{ width:44px; height:31px; }}
  .footer-handle {{
    font-family:'Bebas Neue', sans-serif; font-size:32px;
    letter-spacing:0.06em; color:#fff;
  }}
  .footer-cta {{
    font-family:'Bebas Neue', sans-serif; font-size:32px;
    letter-spacing:0.06em; color:#fff;
  }}
</style>
</head>
<body>
  <div class="slash"></div>
  <div class="slash-line"></div>
  <div class="contenido">
    <div class="slide-label">ESPECIFICACIONES · 02 / 03</div>
    <div class="anio">TOYOTA · {year}</div>
    <div class="titulo">{model.upper()}</div>
    {items_html}
    {promo_html}
  </div>
  <div class="footer">
    <div class="footer-left">{_TOYOTA}<span class="footer-handle">@tucarroconalejo</span></div>
    <span class="footer-cta">ESCRÍBEME · (954) 910-6671</span>
  </div>
</body>
</html>"""


def template_ai_promo_s3(model: str, promo: str = "") -> str:
    """Slide 3/3 — RACING BOLD: CTA con Anton gigante + teléfono protagonista."""
    promo_line = promo if promo else "Oferta especial del mes"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Bebas+Neue&family=Inter:wght@400;700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; position:relative; background:#0A0A0A; }}

  .slash {{
    position:absolute; top:-120px; right:-320px;
    width:540px; height:1750px;
    background:{_RED};
    transform:rotate(16deg);
    z-index:1;
  }}
  .slash-line {{
    position:absolute; top:-120px; right:-410px;
    width:38px; height:1750px;
    background:#fff;
    transform:rotate(16deg);
    z-index:1;
  }}

  .contenido {{
    position:absolute; top:0; left:0; right:200px; bottom:90px;
    display:flex; flex-direction:column; justify-content:center;
    padding:0 72px; z-index:20;
  }}

  .slide-label {{
    font-family:'Inter', sans-serif;
    font-size:16px; font-weight:700;
    letter-spacing:0.35em; text-transform:uppercase;
    color:#888;
    margin-bottom:18px;
  }}
  .pregunta {{
    font-family:'Anton', sans-serif;
    font-size:96px; color:#FFFFFF;
    line-height:1.05;
  }}
  .acento {{
    font-family:'Anton', sans-serif;
    font-size:130px; color:{_RED};
    line-height:1.05;
    text-shadow:4px 4px 0 #fff;
    margin-bottom:44px;
  }}

  .promo-box {{
    align-self:flex-start;
    background:{_RED}; padding:14px 30px;
    margin-bottom:48px;
  }}
  .promo-text {{
    font-family:'Bebas Neue', sans-serif; font-size:34px;
    color:#fff; letter-spacing:0.08em;
  }}

  .phone {{
    font-family:'Anton', sans-serif; font-size:100px;
    color:#FFFFFF; line-height:1;
    margin-bottom:14px;
  }}
  .cta-sub {{
    font-family:'Bebas Neue', sans-serif; font-size:32px;
    color:#888; letter-spacing:0.08em;
  }}

  .footer {{
    position:absolute; bottom:0; left:0; right:0; height:90px; z-index:30;
    background:{_RED};
    display:flex; align-items:center; justify-content:space-between; padding:0 60px;
  }}
  .footer-left {{ display:flex; align-items:center; gap:20px; }}
  .footer-left svg {{ width:44px; height:31px; }}
  .footer-handle {{
    font-family:'Bebas Neue', sans-serif; font-size:32px;
    letter-spacing:0.06em; color:#fff;
  }}
  .footer-cta {{
    font-family:'Bebas Neue', sans-serif; font-size:32px;
    letter-spacing:0.06em; color:#fff;
  }}
</style>
</head>
<body>
  <div class="slash"></div>
  <div class="slash-line"></div>
  <div class="contenido">
    <div class="slide-label">03 / 03 · CONTÁCTAME HOY</div>
    <div class="pregunta">¿LISTO PARA TU</div>
    <div class="acento">NUEVO {model.upper()}?</div>
    <div class="promo-box"><span class="promo-text">{promo_line}</span></div>
    <div class="phone">(954) 910-6671</div>
    <div class="cta-sub">ESCRÍBEME O LLAMA — SIN COMPROMISO</div>
  </div>
  <div class="footer">
    <div class="footer-left">{_TOYOTA}<span class="footer-handle">@tucarroconalejo</span></div>
    <span class="footer-cta">ESCRÍBEME · (954) 910-6671</span>
  </div>
</body>
</html>"""
