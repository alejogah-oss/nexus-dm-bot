"""Sorteo de tiempos del rescate de leads callados en Marketplace.

Todo aleatorio a propósito: un bot que revisa cada 30 minutos exactos y
contesta a las 2 horas clavadas se delata solo. Ver diseño 29 ago 2026.
"""

import random
import re
from datetime import datetime, time, timedelta

SCAN_MINUTES = (30, 33, 37, 41, 44, 50)
RESCUE_MIN_MINUTES = 90
RESCUE_MAX_MINUTES = 120

# Horario decente para escribirle a un cliente
OPEN_HOUR = 8
CLOSE_HOUR = 21
MORNING_START = 8
MORNING_SPAN_HOURS = 2


def next_scan_interval(previous=None):
    """Minutos hasta la próxima revisión — nunca el mismo que el anterior."""
    opciones = [m for m in SCAN_MINUTES if m != previous]
    return random.choice(opciones)


def rescue_delay_minutes():
    """Minutos de silencio antes de escribirle — sorteado por cliente."""
    return random.uniform(RESCUE_MIN_MINUTES, RESCUE_MAX_MINUTES)


def shift_into_window(momento):
    """Corre el envío a la mañana si cae fuera del horario decente."""
    if OPEN_HOUR <= momento.hour < CLOSE_HOUR:
        return momento
    dia = momento.date()
    if momento.hour >= CLOSE_HOUR:
        dia += timedelta(days=1)
    manana = datetime.combine(dia, time(MORNING_START))
    return manana + timedelta(seconds=random.uniform(0, MORNING_SPAN_HOURS * 3600))


# Palabras que solo aparecen en uno de los dos idiomas. No es un detector
# general: solo tiene que acertar entre inglés y español en mensajes cortos de
# alguien preguntando por un carro.
_EN_WORDS = {"the", "is", "are", "this", "still", "available", "how", "much",
             "price", "what", "you", "your", "for", "with", "down", "payment",
             "im", "i", "interested", "car", "truck", "want", "can", "do",
             "does", "have", "and", "would", "like", "thanks", "hi", "hello"}
_ES_WORDS = {"el", "la", "los", "las", "que", "por", "para", "con", "precio",
             "cuanto", "cuánto", "esta", "está", "disponible", "carro", "camioneta",
             "quiero", "me", "interesa", "puedo", "tiene", "hola", "gracias",
             "pago", "inicial", "enganche", "financiamiento", "es", "un", "una"}


def detect_language(texto):
    """"es" o "en". Ante la duda, español: es el idioma del mensaje aprobado."""
    texto = (texto or "").lower()
    if any(c in texto for c in "¿¡ñáéíóú"):
        return "es"
    palabras = set(re.findall(r"[a-záéíóúñ]+", texto))
    return "en" if len(palabras & _EN_WORDS) > len(palabras & _ES_WORDS) else "es"


def rescue_message(model, low, high, lang="es"):
    """Texto del rescate. Sin rango válido o sin modelo devuelve "" — y sin
    texto el bot no manda nada, que es justo lo que se quiere."""
    model = (model or "").strip()
    low, high = int(low or 0), int(high or 0)
    if not model or low <= 0 or high <= 0 or high <= low:
        return ""
    if lang == "en":
        return (f"Hey, are you still thinking about the {model}? If the price "
                f"doesn't work for you, I have other options between "
                f"${low:,} and ${high:,}.")
    return (f"¿Qué tal, seguís pensando en la {model}? Si el precio no te cuadra, "
            f"tengo otras opciones entre ${low:,} y ${high:,}.")
