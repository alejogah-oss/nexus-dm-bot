"""
NEXUS Pulse — Alertas en tiempo real a Alejo.
Envía SMS via Twilio cuando hay HOT LEAD, SHOWROOM_DECLINED u otros eventos críticos.
Fallback a email si Twilio no está configurado.
"""
import os, smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

ALEJO_PHONE = os.getenv("ALEJO_PHONE", "+19549106671")
ALEJO_EMAIL = "alejogah@gmail.com"

_MESSAGES = {
    "HOT_LEAD": (
        "🔥 HOT LEAD — NEXUS\n"
        "{detail}\n\n"
        "Responde rápido — el cliente está listo."
    ),
    "SHOWROOM_DECLINED": (
        "📋 Lead frío — NEXUS\n"
        "{detail}\n\n"
        "Contacta personalmente para no perderlo."
    ),
    "BOT_DOWN": (
        "🚨 NEXUS BOT CAÍDO\n"
        "{detail}\n\n"
        "Revisar Render.com de inmediato."
    ),
    "MARKETPLACE_ERROR": (
        "⚠️ Error Marketplace — NEXUS\n"
        "{detail}"
    ),
    "MORNING_BRIEF": "{detail}",
}


def pulse_notify(event: str, detail: str):
    """Punto de entrada principal. Envía alerta según tipo de evento."""
    template = _MESSAGES.get(event, "NEXUS: {event}\n{detail}")
    body = template.format(detail=detail, event=event)

    sent = _try_sms(body)
    if not sent:
        _try_email(event, body)


def _try_sms(body: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")

    if not all([sid, token]):
        print("[PULSE] Twilio no configurado — usando fallback email")
        return False

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(
            body=body,
            from_="whatsapp:+14155238886",
            to=f"whatsapp:{ALEJO_PHONE}"
        )
        print(f"[PULSE] ✅ WhatsApp enviado a {ALEJO_PHONE}")
        return True
    except Exception as e:
        print(f"[PULSE] ❌ WhatsApp falló: {e}")
        return False


def _try_email(subject: str, body: str):
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not all([user, password]):
        print("[PULSE] ❌ Sin configuración de email — alerta no enviada")
        return

    try:
        msg = MIMEText(body)
        msg["Subject"] = f"NEXUS — {subject}"
        msg["From"] = user
        msg["To"] = ALEJO_EMAIL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(user, password)
            s.send_message(msg)
        print(f"[PULSE] ✅ Email enviado a {ALEJO_EMAIL}")
    except Exception as e:
        print(f"[PULSE] ❌ Email falló: {e}")
