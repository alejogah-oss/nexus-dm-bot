import json
import random
import schedule
import time
from datetime import date, datetime

from content_agent import generate_content, pick_model_for_post, check_monthly_promo_reminder, get_promo_for_model, generate_tips_points, get_current_model_year
from marketplace_agent import sync as marketplace_sync
from drive_reader import get_latest_photo_path
from image_agent import get_car_jelly_url, generate_ai_promo_image, generate_celebration_post
from meta_publisher import publish_content, publish_carousel
from nexus_agency import review_post
from html_renderer import render_to_image
from templates import (
    template_inventory,
    template_quote,
    template_tips_html,
    MODEL_SPECS,
)

# ── PARRILLA OFICIAL — 2 posts/día ──
# Growth-Leo — REVISADA 10 ago 2026 según engagement real (ver
# nexus-content-pipeline-diagnosis-aug2026 / memoria): Entrega y New Car Day
# (foto real) son los únicos formatos que convierten (avg 3-42 eng/post).
# Inventory, Tips y AI Promo estaban en 0-0.86 avg — se reduce su peso y se
# amplía el de foto real. Aprobado por Alejo.
#
# MAÑANA 12pm: contenido informativo/inventario
# NOCHE  8pm:  contenido emocional/celebratorio
#
# Lunes:     New Car Day    + Entrega
# Martes:    Entrega        + Reel (video → Fotos, Alejo agrega música en IG)
# Miércoles: Entrega        + New Car Day
# Jueves:    Inventory      + Entrega
# Viernes:   New Car Day    + Reel
# Sábado:    Tips           + Entrega
# Domingo:   Quote          + AI Promo
PARRILLA_2X = {
    # weekday: [(type_morning, "12:00"), (type_night, "20:00")]
    0: [("new_car_day", "12:00"), ("entrega",     "20:00")],  # Lunes
    1: [("entrega",     "12:00"), ("reel",        "20:00")],  # Martes
    2: [("entrega",     "12:00"), ("new_car_day", "20:00")],  # Miércoles
    3: [("inventory",   "12:00"), ("entrega",     "20:00")],  # Jueves
    4: [("new_car_day", "12:00"), ("reel",        "20:00")],  # Viernes
    5: [("tips",        "12:00"), ("entrega",     "20:00")],  # Sábado
    6: [("quote",       "09:00"), ("ai_promo",    "20:00")],  # Domingo
}

# Keep PARRILLA as alias for manual --now calls
PARRILLA = {k: v[0] for k, v in PARRILLA_2X.items()}

LOG_FILE = "posts_log.json"


def _log_post(post_type: str, model: str, promo: str, results: dict):
    """Saves post result to log for dashboard tracking."""
    try:
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                log = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            log = []

        log.append({
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "post_type": post_type,
            "model": model,
            "promo": promo,
            "fb_id": results.get("facebook", {}).get("id", ""),
            "ig_id": results.get("instagram", {}).get("id", ""),
        })

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


QUOTE_POOL = [
    ("Aquí empieza", "tu nueva", "historia"),
    ("Más que carros,", "", "momentos"),
    ("Tu próximo Toyota", "te está", "esperando"),
    ("El carro de", "tus sueños", "existe"),
    ("No esperes más,", "tu Toyota", "te llama"),
    ("Todo empieza", "con un", "mensaje"),
    ("Hay un Toyota", "hecho", "para ti"),
]

ENTREGA_MESSAGES = [
    "NUEVA FAMILIA TOYOTA",
    "SUEÑO CUMPLIDO",
    "EL PRÓXIMO ERES TÚ",
    "BIENVENIDO A LA FAMILIA",
    "UN NUEVO COMIENZO",
]

TIPS_TOPICS = [
    "por qué el Toyota RAV4 es el SUV más vendido en USA",
    "cómo mantener tu Toyota en perfecto estado por más años",
    "qué hace diferente a un Toyota Tacoma de otros pickups",
    "ventajas de tener un Toyota híbrido en Florida",
    "qué revisar antes de comprar tu próximo carro",
    "por qué la comunidad latina confía en Toyota",
    "cómo el Toyota Camry se convirtió en un clásico americano",
    "señales de que es hora de cambiar tu carro actual",
    "por qué el valor de reventa de Toyota es el mejor del mercado",
    "qué modelo Toyota es ideal para tu familia",
]


def _build_image(post_type: str, model: str, year: str, topic: str = "", quote: tuple = ()) -> str:
    """Genera la imagen correcta según el tipo de post."""
    slug = model.lower().replace(" ", "_")

    if post_type == "inventory":
        # REDISEÑADO 10 ago 2026 (Growth-Leo, aprobado por Alejo): el pipeline
        # viejo dependía de car_library/*.png, que está vacío — 0.00 avg
        # engagement en 7 posts porque nunca se generaba la foto real y caía
        # siempre al fallback Racing con jelly. Ahora usa foto real del mismo
        # pool que entrega/new_car_day (carpeta nexus-fotos en Drive).
        photo = get_latest_photo_path()
        if not photo:
            print("🔴 inventory abortado — no hay fotos en Drive ni en cache.")
            print("   Sube una foto a la carpeta nexus-fotos en Google Drive.")
            return None
        print(f"Foto real encontrada: {photo}")
        return generate_celebration_post(photo, "inventory", subtitle=f"Disponible ahora", model=model, year=year)

    if post_type == "new_car_day":
        photo = get_latest_photo_path()
        if not photo:
            print("🔴 new_car_day abortado — no hay fotos en Drive ni en cache.")
            print("   Sube una foto a la carpeta nexus-fotos en Google Drive.")
            return None
        print(f"Foto real encontrada: {photo}")
        return generate_celebration_post(photo, "new_car_day", model=model, year=year)

    if post_type == "entrega":
        photo = get_latest_photo_path()
        if not photo:
            print("🔴 entrega abortado — no hay fotos en Drive ni en cache.")
            print("   Sube una foto a la carpeta nexus-fotos en Google Drive.")
            return None
        print(f"Foto real encontrada: {photo}")
        msg = random.choice(ENTREGA_MESSAGES)
        return generate_celebration_post(photo, "entrega", subtitle=msg, model=model, year=year)

    if post_type == "quote":
        q = quote or random.choice(QUOTE_POOL)
        return render_to_image(
            template_quote(*q),
            "/tmp/nexus_quote.jpg"
        )

    if post_type == "ai_promo":
        promo = quote[0] if quote else ""
        return generate_ai_promo_image(model, promo, year)

    # tips — REDISEÑADO 10 ago 2026: foto real de fondo (mismo pool que
    # entrega/new_car_day) en vez de negro puro (0.86 avg engagement antes).
    points = generate_tips_points(topic) if topic else []
    tips_photo = get_latest_photo_path() or ""
    return render_to_image(
        template_tips_html(topic or f"Toyota {model}", points, photo_path=tips_photo),
        f"/tmp/nexus_tips_{slug}.jpg"
    )


def _build_topic(post_type: str, model: str, year: str, quote: tuple = ()) -> str:
    if post_type == "inventory":
        return f"Toyota {model} {year} disponible en Hollywood Toyota, Florida"
    elif post_type == "new_car_day":
        return f"celebración de entrega de un Toyota {model} {year} nuevo"
    elif post_type == "entrega":
        return f"entrega especial de un Toyota {model} {year} a un cliente feliz"
    elif post_type == "quote":
        phrase = " ".join(p for p in quote if p)
        return f"reflexión motivacional inspirada en la frase: '{phrase}'"
    elif post_type == "ai_promo":
        promo = get_promo_for_model(model) or "oferta especial del mes"
        return f"promoción del mes para Toyota {model}: {promo}"
    else:
        return random.choice(TIPS_TOPICS)


def _run_reel():
    """Reel de entrega (receta Shot): video → Fotos (iCloud) → Alejo le pone
    música trending en la app IG y lo publica. No se publica por API."""
    import subprocess
    from drive_reader import get_next_photo
    from reel_maker import make_reel, import_to_photos

    photo = get_next_photo()
    if not photo:
        _log_post("reel", "-", "", {"error": "no_photo"})
        return {"error": "no_photo", "message": "No hay fotos disponibles. Sube fotos a nexus-fotos en Drive."}
    try:
        reel = make_reel(photo)
    except Exception as e:
        print(f"🔴 Reel falló: {e}")
        _log_post("reel", "-", "", {"error": str(e)})
        return {"error": "reel_failed", "message": str(e)}

    try:
        import_to_photos(reel)
    except Exception as e:
        print(f"🔴 Reel generado pero falló el import a Fotos: {e}")
        subprocess.run(
            ["osascript", "-e",
             'display notification "Reel generado pero NO se pudo importar a Fotos — revisa NEXUS" '
             'with title "NEXUS · Shot" sound name "Basso"'],
            check=False, capture_output=True,
        )
        _log_post("reel", "-", "", {"error": f"import_to_photos: {e}", "reel": reel})
        return {"error": "import_failed", "message": str(e), "reel": reel}

    subprocess.run(
        ["osascript", "-e",
         'display notification "Reel listo en Fotos — ponle música en IG y publícalo" '
         'with title "NEXUS · Shot" sound name "Glass"'],
        check=False, capture_output=True,
    )
    try:
        from pulse import pulse_notify
        pulse_notify("REEL_READY", f"Video: {reel}")
    except Exception as e:
        print(f"[PULSE] No se pudo notificar REEL_READY: {e}")
    _log_post("reel", "-", "", {"reel": reel, "status": "en_fotos"})
    print(f"🎬 Reel listo en Fotos (sync iPhone): {reel}")
    return {"reel": reel, "status": "en_fotos"}


def run_daily_post(post_type: str | None = None):
    # Recordatorio de promos el día 1 de cada mes
    if check_monthly_promo_reminder():
        print("\n⚠️  RECORDATORIO: Es inicio de mes.")
        print("   Actualiza las promociones en: nexus-automation/promotions.json")
        print("   Dile a NEXUS cuáles son las promos de este mes.\n")

    # Determinar tipo de post según parrilla experta
    if not post_type:
        weekday = date.today().weekday()
        entry = PARRILLA.get(weekday, (None, None))
        post_type = entry[0] if entry[0] else "tips"

    # Reel: pipeline de video propio — no pasa por imagen/copy/publicación API
    if post_type == "reel":
        return _run_reel()

    # Seleccionar modelo del inventario real + año vigente
    model = pick_model_for_post()
    year  = get_current_model_year()

    print(f"\n{'='*52}")
    print(f"  NEXUS Automation — @tucarroconalejo")
    print(f"  Tipo:   {post_type.upper()}")
    print(f"  Modelo: Toyota {model} {year}")
    print(f"{'='*52}")

    # Obtener promo primero — se usa tanto en imagen como en texto
    promo = get_promo_for_model(model) or ""
    if promo:
        print(f"Promo del mes: {promo}")

    # Para quotes: elegir la frase UNA sola vez para alinear imagen y copy
    # Para ai_promo: pasar la promo como primer elemento del tuple
    if post_type == "quote":
        selected_quote = tuple(random.choice(QUOTE_POOL))
    elif post_type == "ai_promo":
        selected_quote = (promo or "oferta especial del mes",)
    else:
        selected_quote = ()

    # Topic antes de imagen (tips template lo necesita)
    topic = _build_topic(post_type, model, year, quote=selected_quote)

    # Generar imagen
    print("Generando imagen...")
    image_path = _build_image(post_type, model, year, topic=topic, quote=selected_quote)
    if image_path is None:
        _log_post(post_type, model, promo, {"error": "no_photo"})
        return {"error": "no_photo", "message": "No hay fotos disponibles. Sube fotos a nexus-fotos en Drive."}
    print(f"Imagen lista: {image_path}")

    # Generar texto — specs como contexto creativo (no repetición literal)
    specs = MODEL_SPECS.get(model, "") if post_type == "inventory" else ""
    content = generate_content(topic, model, specs=specs or None)
    content["promo_used"] = promo

    print("\n--- Vista previa Instagram ---")
    print(content["instagram"])

    # NEXUS Agency review — usa el slide 1 si hay carousel
    review_image = image_path[0] if isinstance(image_path, list) else image_path
    review = review_post(post_type, model, review_image, content["facebook"], content["instagram"])

    if not review.get("approved", True):
        print(f"\n🔴 NEXUS Agency rechazó el post.")
        _log_post(post_type, model, promo, {"rejected": review.get("issues", [])})
        return {"rejected": True, "issues": review.get("issues", []), "fix": review.get("fix", "")}

    # Publicar — carousel si hay múltiples slides (ai_promo), imagen única si no
    if isinstance(image_path, list):
        results = publish_carousel(
            facebook_text=content["facebook"],
            instagram_caption=content["instagram"],
            local_paths=image_path,
        )
    else:
        results = publish_content(
            facebook_text=content["facebook"],
            instagram_caption=content["instagram"],
            local_image_path=image_path,
        )

    print(f"\nResultados: {results}")
    _log_post(post_type, model, promo, results)
    try:
        from pulse import pulse_notify
        fb_ok = "id" in results.get("facebook", {})
        ig_ok = "id" in results.get("instagram", {})
        estado = f"FB {'✅' if fb_ok else '❌'} · IG {'✅' if ig_ok else '❌'}"
        pulse_notify("POST_PUBLISHED", f"{post_type.upper()} — Toyota {model} {year}\n{estado}")
    except Exception as e:
        print(f"[PULSE] No se pudo notificar POST_PUBLISHED: {e}")
    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--schedule":
        print("NEXUS — Modo programado activo")
        print("Parrilla Growth-Leo + Nova:")
        print("  Lunes    12:00pm → Inventory")
        print("  Martes    8:00pm → Entrega / New Car Day")
        print("  Miércoles 8:00pm → Tips")
        print("  Viernes   8:00pm → Entrega / New Car Day")
        print("  Domingo   9:00am → Quote")
        print()

        # 2 posts/día — todos los días de la semana
        days = [
            schedule.every().monday,
            schedule.every().tuesday,
            schedule.every().wednesday,
            schedule.every().thursday,
            schedule.every().friday,
            schedule.every().saturday,
            schedule.every().sunday,
        ]
        day_names = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]

        for i, day in enumerate(days):
            slots = PARRILLA_2X[i]
            for post_type, hora in slots:
                day.at(hora).do(run_daily_post, post_type=post_type)
                print(f"  {day_names[i]} {hora} → {post_type}")

        # Marketplace sync (catalogo Meta) — DESACTIVADO 2026-08-09 por Alejo:
        # redundante, Marketplace real ya se maneja con nexus scanner. Ademas este
        # job se atascaba con error de permiso del token (catalog_management) y
        # bloqueaba toda la cola de posts del dia.
        # schedule.every().sunday.at("06:00").do(marketplace_sync)
        print("  Domingo 06:00 → Marketplace sync [DESACTIVADO]")

        # Lens weekly report — every Tuesday at 9am
        from lens_report import generate as lens_generate
        def _run_lens():
            try:
                _, path = lens_generate(save=True)
                print(f"[LENS] Reporte generado: {path}")
                # Avisar a Alejo y abrir el reporte — sin esto nadie lo ve
                import subprocess as _sp
                _sp.run(["open", path], check=False)
                _sp.run(["osascript", "-e",
                         'display notification "Reporte semanal Lens listo — se abrió en tu navegador" '
                         'with title "NEXUS · Lens" sound name "Glass"'],
                        check=False, capture_output=True)
            except Exception as e:
                print(f"[LENS] Error generando reporte: {e}")
        schedule.every().tuesday.at("09:00").do(_run_lens)
        print("  Martes  09:00 → Reporte Lens")

        next_jobs = sorted(schedule.jobs, key=lambda j: j.next_run)
        print(f"\nPróximo post: {next_jobs[0].next_run.strftime('%A %d/%m a las %I:%M %p')}")
        print("Scheduler activo — 14 posts/semana")
        print("Esperando...")
        while True:
            schedule.run_pending()
            time.sleep(60)

    elif len(sys.argv) > 1 and sys.argv[1] == "--now":
        tipo = sys.argv[2] if len(sys.argv) > 2 else None
        run_daily_post(post_type=tipo)

    else:
        print("\nNEXUS Automation — Tu Carro con Alejo")
        print("=" * 40)
        print("1. Publicar ahora (parrilla del día)")
        print("2. Publicar inventory card")
        print("3. Publicar New Car Day")
        print("4. Publicar Entrega Especial")
        print("5. Publicar Quote inspiracional")
        print("6. Activar modo programado (9am y 6pm)")
        print()
        opcion = input("Elige (1-6): ").strip()

        mapa = {
            "1": None,
            "2": "inventory",
            "3": "new_car_day",
            "4": "entrega",
            "5": "quote",
        }

        if opcion in mapa:
            run_daily_post(post_type=mapa[opcion])
        elif opcion == "6":
            schedule.every().day.at("09:00").do(run_daily_post)
            schedule.every().day.at("18:00").do(run_daily_post)
            print("Programado. Publicará a las 9:00am y 6:00pm.")
            while True:
                schedule.run_pending()
                time.sleep(60)
