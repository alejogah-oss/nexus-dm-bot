"""
NEXUS Appointments — Sistema de citas para Alejo Garcia.
- Captura de citas desde conversaciones del bot
- Notificación inmediata a Alejo vía WhatsApp
- Recordatorios automáticos (5pm del día anterior)
- Confirmación y cancelación desde CLI
"""
import os
import json
import uuid
import argparse
import urllib.parse
import anthropic
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from pulse import pulse_notify

load_dotenv()

APPOINTMENTS_FILE = os.path.join(os.path.dirname(__file__), "nexus_appointments.json")
DEALER_ADDRESS = "2200 N State Rd 7, Hollywood, FL 33021"
_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ─────────────────────────────────────────────
# Google Calendar link
# ─────────────────────────────────────────────

_DAY_NAMES = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _parse_date(date_pref: str, time_pref: str = "") -> tuple[date | None, int, int]:
    """
    Retorna (fecha, hora, minuto) desde texto libre.
    Soporta: 'YYYY-MM-DD', 'mañana', 'hoy', nombre de día en español/inglés.
    """
    today = date.today()
    d = None
    h, m = 10, 0  # default: 10am

    # Parse hora
    if time_pref:
        for fmt in ("%I:%M%p", "%H:%M", "%I%p"):
            try:
                t = datetime.strptime(time_pref.replace(" ", "").upper(), fmt)
                h, m = t.hour, t.minute
                break
            except ValueError:
                pass
        if "pm" in time_pref.lower() and h < 12:
            h += 12
        elif "am" in time_pref.lower() and h == 12:
            h = 0

    dp = date_pref.strip().lower()

    # ISO format
    try:
        d = date.fromisoformat(date_pref.strip()[:10])
        return d, h, m
    except ValueError:
        pass

    if "mañana" in dp or "manana" in dp or "tomorrow" in dp:
        d = today + timedelta(days=1)
    elif "hoy" in dp or "today" in dp:
        d = today
    else:
        for name, wd in _DAY_NAMES.items():
            if name in dp:
                days_ahead = (wd - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                d = today + timedelta(days=days_ahead)
                break

    return d, h, m


def google_calendar_link(date_pref: str, time_pref: str, customer_name: str, car: str) -> str:
    """Genera link de Google Calendar para agregar la cita con un tap."""
    d, h, m = _parse_date(date_pref, time_pref)
    if not d:
        d = date.today() + timedelta(days=1)

    start = datetime(d.year, d.month, d.day, h, m)
    end   = datetime(d.year, d.month, d.day, h + 1, m)

    fmt = "%Y%m%dT%H%M%S"
    params = urllib.parse.urlencode({
        "text":     f"Cita Toyota — {customer_name}",
        "dates":    f"{start.strftime(fmt)}/{end.strftime(fmt)}",
        "details":  f"Carro: {car}\nCliente: {customer_name}\nContacto: Alejo (954) 310-6671",
        "location": DEALER_ADDRESS,
    })
    return f"https://calendar.google.com/calendar/r/eventedit?{params}"


# ─────────────────────────────────────────────
# Data layer
# ─────────────────────────────────────────────

def _load() -> list:
    if not os.path.exists(APPOINTMENTS_FILE):
        return []
    try:
        with open(APPOINTMENTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save(appointments: list):
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(appointments, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────

def create_appointment(
    customer_id: str,
    platform: str,
    car_description: str,
    date_preference: str,
    time_preference: str = "",
    customer_name: str = "",
    customer_phone: str = "",
) -> dict:
    """
    Crea una cita nueva y notifica a Alejo vía WhatsApp.
    Retorna el dict de la cita creada.
    """
    appt_id = uuid.uuid4().hex[:8]
    appt = {
        "id": appt_id,
        "customer_id": customer_id,
        "customer_name": customer_name or "Sin nombre",
        "customer_phone": customer_phone or "",
        "platform": platform,
        "car": car_description,
        "date_preference": date_preference,
        "time_preference": time_preference or "Sin especificar",
        "status": "pending",           # pending | confirmed | cancelled
        "created_at": datetime.now().isoformat(),
        "reminded_day_before": False,
        "reminded_morning": False,
    }

    appointments = _load()
    appointments.append(appt)
    _save(appointments)

    _notify_new_appointment(appt)
    print(f"[APPT] ✅ Cita creada: {appt_id} — {customer_name} — {date_preference}")
    return appt


def _notify_new_appointment(appt: dict):
    """Envía WhatsApp a Alejo con los datos de la nueva cita + link de Google Calendar."""
    name = appt["customer_name"]
    car = appt["car"]
    date_pref = appt["date_preference"]
    time_pref = appt["time_preference"]
    platform = appt["platform"].upper()
    appt_id = appt["id"]
    phone = appt["customer_phone"]
    phone_line = f"\n📞 Tel: {phone}" if phone else ""

    gcal = google_calendar_link(date_pref, time_pref, name, car)

    detail = (
        f"📅 NUEVA CITA — NEXUS\n"
        f"Cliente: {name} ({platform}){phone_line}\n"
        f"Carro: {car}\n"
        f"Fecha: {date_pref}\n"
        f"Hora: {time_pref}\n\n"
        f"➕ Google Calendar:\n{gcal}\n\n"
        f"ID: {appt_id}\n"
        f"Confirmar: python3 appointments.py --confirm {appt_id}\n"
        f"Cancelar:  python3 appointments.py --cancel {appt_id}"
    )
    pulse_notify("MORNING_BRIEF", detail)


# ─────────────────────────────────────────────
# Status management
# ─────────────────────────────────────────────

def confirm_appointment(appt_id: str) -> bool:
    """Marca la cita como confirmada y notifica a Alejo."""
    appointments = _load()
    for appt in appointments:
        if appt["id"] == appt_id:
            appt["status"] = "confirmed"
            appt["confirmed_at"] = datetime.now().isoformat()
            _save(appointments)
            print(f"[APPT] ✅ Cita {appt_id} CONFIRMADA — {appt['customer_name']} / {appt['date_preference']}")
            pulse_notify(
                "MORNING_BRIEF",
                f"✅ CITA CONFIRMADA\n{appt['customer_name']} — {appt['car']}\n{appt['date_preference']} {appt['time_preference']}"
            )
            return True
    print(f"[APPT] ❌ No se encontró cita con ID: {appt_id}")
    return False


def cancel_appointment(appt_id: str, reason: str = "") -> bool:
    """Marca la cita como cancelada."""
    appointments = _load()
    for appt in appointments:
        if appt["id"] == appt_id:
            appt["status"] = "cancelled"
            appt["cancelled_at"] = datetime.now().isoformat()
            if reason:
                appt["cancel_reason"] = reason
            _save(appointments)
            print(f"[APPT] ❌ Cita {appt_id} CANCELADA — {appt['customer_name']}")
            return True
    print(f"[APPT] ❌ No se encontró cita con ID: {appt_id}")
    return False


# ─────────────────────────────────────────────
# Queries
# ─────────────────────────────────────────────

def list_appointments(status_filter: str = None, days_ahead: int = 7) -> list:
    """Retorna citas activas. Filtra por status si se indica."""
    appointments = _load()
    active = [a for a in appointments if a["status"] != "cancelled"]
    if status_filter:
        active = [a for a in active if a["status"] == status_filter]
    return sorted(active, key=lambda a: a["created_at"], reverse=True)


def get_todays_appointments() -> list:
    """Citas de hoy (por created_at en las últimas 24h, o marcadas como hoy)."""
    today = date.today().isoformat()
    return [
        a for a in _load()
        if a["status"] != "cancelled"
        and (a["date_preference"].startswith(today)
             or today in a["date_preference"]
             or a["created_at"].startswith(today))
    ]


def get_tomorrows_appointments() -> list:
    """Citas donde date_preference contiene mañana."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    appointments = _load()
    return [
        a for a in appointments
        if a["status"] != "cancelled"
        and not a.get("reminded_day_before", False)
        and (a["date_preference"].startswith(tomorrow)
             or tomorrow in a["date_preference"])
    ]


def get_pending_count() -> int:
    """Número de citas pendientes de confirmar."""
    return sum(1 for a in _load() if a["status"] == "pending")


# ─────────────────────────────────────────────
# AI: extract appointment from conversation
# ─────────────────────────────────────────────

def extract_appointment_from_conversation(history: list, car: dict, sender_id: str, platform: str) -> dict | None:
    """
    Usa Claude Haiku para detectar si el cliente mencionó una fecha/hora para venir.
    Si encuentra fecha, crea la cita automáticamente.
    Retorna el dict de la cita o None si no se detectó fecha.
    """
    if not history:
        return None

    convo_text = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in history[-12:]
    )

    today_str = date.today().isoformat()

    response = _claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                f"Hoy es {today_str}. Analiza esta conversación de venta de carros. "
                f"¿El cliente mencionó CUÁNDO quiere venir al dealer? "
                f"Responde SOLO con JSON válido:\n\n"
                f"{convo_text}\n\n"
                f"Formato exacto (null si no mencionó):\n"
                f'{{"fecha": null, "hora": null, "nombre": null, "telefono": null}}\n\n'
                f"Para fecha: usa formato YYYY-MM-DD si puedes, o descripción natural (ej: \"este sábado\", \"mañana\"). "
                f"Solo incluye si el cliente lo dijo explícitamente."
            )
        }]
    )

    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].split("```")[0].replace("json", "").strip()

    try:
        data = json.loads(text)
        if not data.get("fecha"):
            return None

        car_desc = f"{car['yr']} Toyota {car['model']} {car.get('trim', '')} {car['color']}".strip()
        appt = create_appointment(
            customer_id=sender_id,
            platform=platform,
            car_description=car_desc,
            date_preference=data["fecha"],
            time_preference=data.get("hora") or "",
            customer_name=data.get("nombre") or "",
            customer_phone=data.get("telefono") or "",
        )
        return appt
    except Exception as e:
        print(f"[APPT] Error extrayendo cita: {e}")
        return None


# ─────────────────────────────────────────────
# Reminders
# ─────────────────────────────────────────────

def send_day_before_reminders():
    """
    Envía recordatorio de citas de mañana a las 5pm.
    Corre vía LaunchAgent.
    """
    appointments = _load()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    pending = [
        a for a in appointments
        if a["status"] != "cancelled"
        and not a.get("reminded_day_before", False)
        and (a["date_preference"].startswith(tomorrow) or tomorrow in a["date_preference"])
    ]

    if not pending:
        print("[APPT] Sin citas para mañana.")
        return

    lines = [f"📅 CITAS DE MAÑANA ({tomorrow}):"]
    for a in pending:
        status_icon = "✅" if a["status"] == "confirmed" else "⏳"
        lines.append(
            f"{status_icon} {a['customer_name']} — {a['car']}\n"
            f"   Hora: {a['time_preference']} | {a['platform'].upper()}"
        )
        if a["customer_phone"]:
            lines.append(f"   📞 {a['customer_phone']}")

    lines += ["", "Confirma con el cliente antes de las 6pm."]

    pulse_notify("MORNING_BRIEF", "\n".join(lines))

    # Marcar como recordados
    for a in appointments:
        if a.get("id") in [p["id"] for p in pending]:
            a["reminded_day_before"] = True
    _save(appointments)
    print(f"[APPT] Recordatorio enviado — {len(pending)} cita(s) mañana.")


def get_appointments_summary_for_briefing() -> str:
    """
    Retorna resumen de citas para incluir en el briefing matutino.
    """
    all_appts = _load()
    active = [a for a in all_appts if a["status"] != "cancelled"]

    if not active:
        return ""

    today_str = date.today().isoformat()
    today_appts = [
        a for a in active
        if a["date_preference"].startswith(today_str) or today_str in a["date_preference"]
    ]
    pending_count = sum(1 for a in active if a["status"] == "pending")

    lines = ["", "📅 CITAS:"]
    if today_appts:
        lines.append(f"  Hoy: {len(today_appts)} cita(s)")
        for a in today_appts:
            icon = "✅" if a["status"] == "confirmed" else "⏳"
            lines.append(f"    {icon} {a['customer_name']} — {a['time_preference']}")
    else:
        lines.append("  Hoy: Sin citas agendadas")

    if pending_count > 0:
        lines.append(f"  ⏳ Pendientes de confirmar: {pending_count}")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def _print_appointments_table(appointments: list):
    if not appointments:
        print("Sin citas.")
        return
    print(f"\n{'ID':8} {'Estado':12} {'Cliente':18} {'Carro':28} {'Fecha':14} {'Hora':10} {'Platform':10}")
    print("-" * 110)
    for a in appointments:
        status_map = {"pending": "⏳ Pendiente", "confirmed": "✅ Confirmada", "cancelled": "❌ Cancelada"}
        print(
            f"{a['id']:8} {status_map.get(a['status'], a['status']):12} "
            f"{a['customer_name'][:17]:18} {a['car'][:27]:28} "
            f"{a['date_preference'][:13]:14} {a['time_preference'][:9]:10} {a['platform']}"
        )
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS Appointments")
    parser.add_argument("--list", action="store_true", help="Listar todas las citas activas")
    parser.add_argument("--pending", action="store_true", help="Listar citas pendientes de confirmar")
    parser.add_argument("--confirm", metavar="ID", help="Confirmar una cita por ID")
    parser.add_argument("--cancel", metavar="ID", help="Cancelar una cita por ID")
    parser.add_argument("--remind", action="store_true", help="Enviar recordatorio de citas de mañana")
    parser.add_argument("--new", nargs="+", metavar="ARG", help="Crear cita manual: --new NOMBRE FECHA HORA CARRO")
    args = parser.parse_args()

    if args.list:
        _print_appointments_table(list_appointments())
    elif args.pending:
        _print_appointments_table(list_appointments(status_filter="pending"))
    elif args.confirm:
        confirm_appointment(args.confirm)
    elif args.cancel:
        cancel_appointment(args.cancel)
    elif args.remind:
        send_day_before_reminders()
    elif args.new:
        if len(args.new) < 2:
            print("Uso: --new NOMBRE FECHA [HORA] [CARRO]")
        else:
            nombre = args.new[0]
            fecha = args.new[1]
            hora = args.new[2] if len(args.new) > 2 else ""
            carro = " ".join(args.new[3:]) if len(args.new) > 3 else "Toyota"
            create_appointment("manual", "manual", carro, fecha, hora, nombre)
    else:
        parser.print_help()
