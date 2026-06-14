import json
import random
import schedule
import time
from datetime import date, datetime

from content_agent import generate_content, pick_model_for_post, check_monthly_promo_reminder, get_promo_for_model, generate_tips_points
from marketplace_agent import sync as marketplace_sync
from drive_reader import get_latest_photo_path
from image_agent import get_car_jelly_url
from meta_publisher import publish_content
from nexus_agency import review_post
from html_renderer import render_to_image
from templates import (
    template_new_car_day,
    template_entrega_especial,
    template_inventory,
    template_quote,
    template_tips_html,
    MODEL_SPECS,
)

# ── PARRILLA OFICIAL — 2 posts/día ──
# Growth-Leo + Nova — picos audiencia latina South Florida
#
# MAÑANA 12pm: contenido informativo/inventario
# NOCHE  8pm:  contenido emocional/celebratorio
#
# Lunes:     Inventory      + Tips
# Martes:    Entrega/NCD    + Quote
# Miércoles: Tips           + Inventory
# Jueves:    Quote          + Entrega/NCD
# Viernes:   New Car Day    + Inventory
# Sábado:    Tips           + Quote
# Domingo:   Quote          + Tips
PARRILLA_2X = {
    # weekday: [(type_morning, "12:00"), (type_night, "20:00")]
    0: [("inventory",   "12:00"), ("tips",        "20:00")],  # Lunes
    1: [("entrega",     "12:00"), ("quote",        "20:00")],  # Martes
    2: [("tips",        "12:00"), ("inventory",    "20:00")],  # Miércoles
    3: [("quote",       "12:00"), ("new_car_day",  "20:00")],  # Jueves
    4: [("new_car_day", "12:00"), ("inventory",    "20:00")],  # Viernes
    5: [("tips",        "12:00"), ("quote",        "20:00")],  # Sábado
    6: [("quote",       "09:00"), ("tips",         "20:00")],  # Domingo
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


def _build_image(post_type: str, model: str, promo: str = "", topic: str = "") -> str:
    """Genera la imagen correcta según el tipo de post."""
    slug = model.lower().replace(" ", "_")

    if post_type == "inventory":
        jelly = get_car_jelly_url(model)
        return render_to_image(
            template_inventory(model, "2026", "", "", jelly or "", promo),
            f"/tmp/nexus_inventory_{slug}.jpg"
        )

    if post_type == "new_car_day":
        photo = get_latest_photo_path()
        if not photo:
            print("🔴 new_car_day abortado — no hay fotos en Drive ni en cache.")
            print("   Sube una foto a la carpeta nexus-fotos en Google Drive.")
            return None
        print(f"Foto real encontrada: {photo}")
        return render_to_image(
            template_new_car_day(model, "2026", photo_path=photo),
            f"/tmp/nexus_newcarday_{slug}.jpg"
        )

    if post_type == "entrega":
        photo = get_latest_photo_path()
        if not photo:
            print("🔴 entrega abortado — no hay fotos en Drive ni en cache.")
            print("   Sube una foto a la carpeta nexus-fotos en Google Drive.")
            return None
        print(f"Foto real encontrada: {photo}")
        return render_to_image(
            template_entrega_especial(model, "2026", photo_path=photo),
            f"/tmp/nexus_entrega_{slug}.jpg"
        )

    if post_type == "quote":
        q = random.choice(QUOTE_POOL)
        return render_to_image(
            template_quote(*q),
            "/tmp/nexus_quote.jpg"
        )

    # tips — HTML template consistent with brand system
    points = generate_tips_points(topic) if topic else []
    return render_to_image(
        template_tips_html(topic or f"Toyota {model}", points),
        f"/tmp/nexus_tips_{slug}.jpg"
    )


def _build_topic(post_type: str, model: str) -> str:
    if post_type == "inventory":
        return f"Toyota {model} 2025 disponible en Hollywood Toyota, Florida"
    elif post_type == "new_car_day":
        return f"celebración de entrega de un Toyota {model} nuevo"
    elif post_type == "entrega":
        return f"entrega especial de un Toyota {model} a un cliente feliz"
    elif post_type == "quote":
        return "el sueño de tener tu propio Toyota hecho realidad"
    else:
        return random.choice(TIPS_TOPICS)


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

    # Seleccionar modelo del inventario real
    model = pick_model_for_post()

    print(f"\n{'='*52}")
    print(f"  NEXUS Automation — @tucarroconalejo")
    print(f"  Tipo:   {post_type.upper()}")
    print(f"  Modelo: Toyota {model}")
    print(f"{'='*52}")

    # Obtener promo primero — se usa tanto en imagen como en texto
    promo = get_promo_for_model(model) or ""
    if promo:
        print(f"Promo del mes: {promo}")

    # Topic antes de imagen (tips template lo necesita)
    topic = _build_topic(post_type, model)

    # Generar imagen
    print("Generando imagen...")
    image_path = _build_image(post_type, model, promo, topic=topic)
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

    # NEXUS Agency review — Growth-Leo + Frame aprueban antes de publicar
    review = review_post(post_type, model, image_path, content["facebook"], content["instagram"])
    if not review.get("approved", True):
        print(f"\n🔴 NEXUS Agency rechazó el post.")
        _log_post(post_type, model, promo, {"rejected": review.get("issues", [])})
        return {"rejected": True, "issues": review.get("issues", []), "fix": review.get("fix", "")}

    # Publicar
    results = publish_content(
        facebook_text=content["facebook"],
        instagram_caption=content["instagram"],
        local_image_path=image_path
    )

    print(f"\nResultados: {results}")
    _log_post(post_type, model, promo, results)
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

        # Marketplace sync — every Sunday at 6am
        schedule.every().sunday.at("06:00").do(marketplace_sync)
        print("  Domingo 06:00 → Marketplace sync")

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
