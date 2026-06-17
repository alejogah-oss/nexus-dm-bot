"""
NEXUS Assist — Asistente personal de Alejo Garcia.
- Briefing diario vía WhatsApp (8am)
- Registro de eventos HOT LEAD / SHOWROOM_DECLINED
- Recordatorios de follow-up (3 días después de lead frío)
- Verificación de salud del bot
"""
import os
import json
import argparse
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pulse import pulse_notify
from appointments import get_appointments_summary_for_briefing

load_dotenv()

EVENTS_FILE = os.path.join(os.path.dirname(__file__), "nexus_events.json")
BOT_URL = "https://bot.tucarroconalejo.com/health"


# ─────────────────────────────────────────────
# Event logging
# ─────────────────────────────────────────────

def log_event(event_type: str, detail: str, platform: str = ""):
    """Registra un evento en el log local para tracking y briefings."""
    events = _load_events()
    events.append({
        "ts": datetime.now().isoformat(),
        "type": event_type,       # HOT_LEAD | SHOWROOM_DECLINED | BOT_DOWN | LISTING_PUBLISHED
        "detail": detail,
        "platform": platform,
        "followed_up": False,
    })
    _save_events(events)


def _load_events() -> list:
    if not os.path.exists(EVENTS_FILE):
        return []
    try:
        with open(EVENTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_events(events: list):
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────
# Bot health check
# ─────────────────────────────────────────────

def check_bot_health() -> bool:
    """Retorna True si el bot en Render responde OK."""
    try:
        resp = requests.get(BOT_URL, timeout=8)
        return resp.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────
# Morning briefing
# ─────────────────────────────────────────────

def morning_briefing():
    """
    Genera y envía el resumen diario a las 8am vía WhatsApp.
    Incluye: leads del día anterior, pendientes de follow-up, estado del bot.
    """
    events = _load_events()
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    # Eventos de las últimas 24h
    recent = [e for e in events if e["ts"].startswith(yesterday_str)]
    hot_leads = [e for e in recent if e["type"] == "HOT_LEAD"]
    declined = [e for e in recent if e["type"] == "SHOWROOM_DECLINED"]

    # Follow-ups pendientes (SHOWROOM_DECLINED hace 3 días, no seguidos)
    three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    follow_ups = [
        e for e in events
        if e["type"] == "SHOWROOM_DECLINED"
        and e["ts"].startswith(three_days_ago)
        and not e.get("followed_up", False)
    ]

    # Marketplace listings publicados
    listings_count = _count_listings()

    # Estado del bot
    bot_ok = check_bot_health()
    bot_status = "✅ Activo" if bot_ok else "🚨 CAÍDO"

    # Construir mensaje
    day_name = datetime.now().strftime("%A %d %b").capitalize()
    lines = [
        f"☀️ NEXUS — Buenos días Alejo",
        f"📅 {day_name}",
        "",
        f"📊 AYER ({yesterday_str.split('-')[2]}/{yesterday_str.split('-')[1]}):",
        f"  🔥 Hot Leads: {len(hot_leads)}",
        f"  📋 Leads fríos: {len(declined)}",
        "",
    ]

    if follow_ups:
        lines.append(f"⚡ FOLLOW-UP URGENTE:")
        for fu in follow_ups[:3]:
            short = fu["detail"][:60] if fu["detail"] else "Sin detalle"
            lines.append(f"  → {short}")
        lines.append("")

    # Citas del día
    appt_summary = get_appointments_summary_for_briefing()
    if appt_summary:
        lines.append(appt_summary)
        lines.append("")

    lines += [
        f"🚗 Marketplace: {listings_count} listings activos",
        f"🤖 Bot: {bot_status}",
        "",
        f"Buena suerte hoy — equipo NEXUS 💪",
    ]

    message = "\n".join(lines)

    # Marcar follow-ups como enviados
    updated = False
    for e in events:
        if (e["type"] == "SHOWROOM_DECLINED"
                and e["ts"].startswith(three_days_ago)
                and not e.get("followed_up", False)):
            e["followed_up"] = True
            updated = True
    if updated:
        _save_events(events)

    pulse_notify("MORNING_BRIEF", message)
    print(f"[ASSIST] ✅ Briefing enviado:\n{message}")

    # Si el bot está caído, disparar alerta adicional
    if not bot_ok:
        pulse_notify("BOT_DOWN", "Bot caído — detectado en briefing matutino")


def _count_listings() -> int:
    """Cuenta los listings publicados en marketplace_posted.json."""
    posted_file = os.path.join(os.path.dirname(__file__), "marketplace_posted.json")
    try:
        with open(posted_file, "r") as f:
            data = json.load(f)
        return len(data)
    except Exception:
        return 0


# ─────────────────────────────────────────────
# Follow-up reminder (también ejecutable vía cron)
# ─────────────────────────────────────────────

def send_followup_reminders():
    """
    Envía recordatorio de follow-up para leads fríos de hace 3 días.
    Puede correrse independientemente del briefing matutino.
    """
    events = _load_events()
    three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    pending = [
        e for e in events
        if e["type"] == "SHOWROOM_DECLINED"
        and e["ts"].startswith(three_days_ago)
        and not e.get("followed_up", False)
    ]

    for e in pending:
        pulse_notify(
            "SHOWROOM_DECLINED",
            f"FOLLOW-UP (+3 días)\n{e['detail'][:120]}"
        )
        e["followed_up"] = True
        print(f"[ASSIST] Follow-up enviado: {e['detail'][:60]}")

    if pending:
        _save_events(events)
    else:
        print("[ASSIST] Sin follow-ups pendientes hoy.")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS Assist")
    parser.add_argument("--brief", action="store_true", help="Enviar briefing matutino")
    parser.add_argument("--followup", action="store_true", help="Revisar y enviar follow-ups")
    parser.add_argument("--health", action="store_true", help="Verificar estado del bot")
    parser.add_argument("--log", nargs=2, metavar=("TIPO", "DETALLE"), help="Registrar evento manual")
    args = parser.parse_args()

    if args.brief:
        morning_briefing()
    elif args.followup:
        send_followup_reminders()
    elif args.health:
        ok = check_bot_health()
        print(f"[ASSIST] Bot {'ACTIVO ✅' if ok else 'CAÍDO 🚨'}")
        if not ok:
            pulse_notify("BOT_DOWN", "Bot caído — verificación manual")
    elif args.log:
        log_event(args.log[0], args.log[1])
        print(f"[ASSIST] Evento registrado: {args.log[0]} — {args.log[1]}")
    else:
        parser.print_help()
