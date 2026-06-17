"""
NEXUS Marketplace Analytics — Efectividad de listings por vehículo.
Registra mensajes, hot leads, citas y declinaciones por listing publicado.
Calcula un score de efectividad para saber qué carros generan más interés.
"""
import os
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE_DIR, "marketplace_analytics.json")
POSTED_FILE = os.path.join(BASE_DIR, "marketplace_posted.json")


# ─────────────────────────────────────────────
# Efectividad: peso de cada señal
# ─────────────────────────────────────────────
WEIGHTS = {
    "messages":    1,   # alguien preguntó
    "hot_leads":   5,   # listo para comprar
    "appointments": 10, # confirmó visita
    "declined":   -2,   # rechazó dos veces
}


def _car_key(car: dict) -> str:
    return f"{car['yr']}|{car['model']}|{car.get('trim', '')}"


def _load() -> dict:
    if not os.path.exists(STATS_FILE):
        return {}
    try:
        with open(STATS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(stats: dict):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def _ensure_entry(stats: dict, car: dict) -> dict:
    """Crea entrada para el listing si no existe."""
    key = _car_key(car)
    if key not in stats:
        stats[key] = {
            "key":          key,
            "yr":           car["yr"],
            "model":        car["model"],
            "trim":         car.get("trim", ""),
            "color":        car.get("color", ""),
            "vin":          car.get("vin", ""),
            "down_payment": car.get("down_payment", 0),
            "messages":     0,
            "hot_leads":    0,
            "appointments": 0,
            "declined":     0,
            "first_contact": datetime.now().isoformat(),
            "last_contact":  datetime.now().isoformat(),
        }
    return stats


# ─────────────────────────────────────────────
# Tracking — llamado desde dm_bot.py
# ─────────────────────────────────────────────

def track_message(car: dict):
    """Un cliente envió un mensaje sobre este listing."""
    stats = _load()
    stats = _ensure_entry(stats, car)
    key = _car_key(car)
    stats[key]["messages"] += 1
    stats[key]["last_contact"] = datetime.now().isoformat()
    _save(stats)


def track_hot_lead(car: dict):
    """El bot detectó un HOT LEAD en este listing."""
    stats = _load()
    stats = _ensure_entry(stats, car)
    key = _car_key(car)
    stats[key]["hot_leads"] += 1
    stats[key]["last_contact"] = datetime.now().isoformat()
    _save(stats)


def track_declined(car: dict):
    """El cliente rechazó venir (SHOWROOM_DECLINED)."""
    stats = _load()
    stats = _ensure_entry(stats, car)
    key = _car_key(car)
    stats[key]["declined"] += 1
    _save(stats)


def track_appointment(car: dict):
    """Se agendó una cita desde este listing."""
    stats = _load()
    stats = _ensure_entry(stats, car)
    key = _car_key(car)
    stats[key]["appointments"] += 1
    _save(stats)


# ─────────────────────────────────────────────
# Análisis — llamado desde API y dashboard
# ─────────────────────────────────────────────

def _score(entry: dict) -> float:
    return sum(entry.get(k, 0) * w for k, w in WEIGHTS.items())


def get_stats_ranked() -> list:
    """
    Retorna todos los listings publicados con sus stats y score de efectividad.
    Combina marketplace_posted.json (listings publicados) con analytics (engagement).
    Los listings sin mensajes también aparecen (score 0).
    """
    # Cargar listings publicados
    try:
        with open(POSTED_FILE) as f:
            posted = json.load(f)
    except Exception:
        posted = {}

    analytics = _load()
    result = []

    for key, pub in posted.items():
        parts = key.split("|")
        yr    = int(parts[0]) if parts else 0
        model = parts[1] if len(parts) > 1 else ""
        trim  = parts[2] if len(parts) > 2 else ""

        stats = analytics.get(key, {})
        entry = {
            "key":          key,
            "yr":           yr,
            "model":        model,
            "trim":         trim,
            "title":        pub.get("title", f"{yr} Toyota {model} {trim}"),
            "vin":          pub.get("vin", stats.get("vin", "")),
            "down_payment": pub.get("down", stats.get("down_payment", 0)),
            "posted_at":    pub.get("posted_at", ""),
            "messages":     stats.get("messages", 0),
            "hot_leads":    stats.get("hot_leads", 0),
            "appointments": stats.get("appointments", 0),
            "declined":     stats.get("declined", 0),
            "last_contact": stats.get("last_contact", ""),
            "color":        stats.get("color", ""),
        }
        entry["score"] = _score(entry)
        entry["conversion_rate"] = (
            round(entry["hot_leads"] / entry["messages"] * 100)
            if entry["messages"] > 0 else 0
        )
        result.append(entry)

    # Listings con analytics pero no en posted (edge case)
    for key, stats in analytics.items():
        if key not in posted:
            entry = dict(stats)
            entry["score"] = _score(entry)
            entry["conversion_rate"] = (
                round(entry["hot_leads"] / entry["messages"] * 100)
                if entry["messages"] > 0 else 0
            )
            entry["title"] = entry.get("title", f"{entry['yr']} Toyota {entry['model']} {entry['trim']}")
            result.append(entry)

    result.sort(key=lambda x: (x["score"], x["messages"]), reverse=True)
    return result


def get_summary() -> dict:
    """Resumen global para el dashboard banner."""
    stats = get_stats_ranked()
    total_messages  = sum(s["messages"] for s in stats)
    total_hot_leads = sum(s["hot_leads"] for s in stats)
    total_appts     = sum(s["appointments"] for s in stats)
    top = stats[0] if stats and stats[0]["messages"] > 0 else None
    return {
        "total_listings": len(stats),
        "total_messages":  total_messages,
        "total_hot_leads": total_hot_leads,
        "total_appointments": total_appts,
        "top_listing": top,
        "conversion_rate": (
            round(total_hot_leads / total_messages * 100) if total_messages > 0 else 0
        ),
    }


# ─────────────────────────────────────────────
# CLI — inspección manual
# ─────────────────────────────────────────────

if __name__ == "__main__":
    ranked = get_stats_ranked()
    summary = get_summary()

    print(f"\n{'━'*80}")
    print(f"  NEXUS Marketplace Analytics — {summary['total_listings']} listings")
    print(f"  Total mensajes: {summary['total_messages']}  |  Hot Leads: {summary['total_hot_leads']}  |  Citas: {summary['total_appointments']}")
    print(f"  Tasa de conversión global: {summary['conversion_rate']}%")
    if summary["top_listing"]:
        top = summary["top_listing"]
        print(f"  🏆 Más efectivo: {top['title']} — Score {top['score']}")
    print(f"{'━'*80}\n")

    print(f"{'#':3} {'Carro':38} {'Msg':5} {'HOT':5} {'Citas':6} {'Dec':5} {'Score':6} {'Conv%':6}")
    print("-" * 80)
    for i, s in enumerate(ranked[:20], 1):
        name = f"{s['yr']} {s['model']} {s['trim']}"[:37]
        print(
            f"{i:3} {name:38} {s['messages']:5} {s['hot_leads']:5} "
            f"{s['appointments']:6} {s['declined']:5} {s['score']:6.0f} {s['conversion_rate']:5}%"
        )
