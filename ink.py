"""
Ink — Agente de bienvenida de NEXUS.
Configura el Messenger Profile de Meta (greeting + Get Started button).
Correr UNA VEZ para activar: python3 ink.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

PAGE_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
BASE = "https://graph.facebook.com/v21.0/me/messenger_profile"

GREETING = [
    {
        "locale": "default",
        "text": "Hola 👋 Soy el asistente de Alejo, asesor Toyota en Hollywood, FL. ¿Buscas tu próximo carro? Estás en el lugar correcto."
    },
    {
        "locale": "es_LA",
        "text": "Hola 👋 Soy el asistente de Alejo, asesor Toyota en Hollywood, FL. ¿Buscas tu próximo carro? Estás en el lugar correcto."
    }
]

WELCOME_TEXT = (
    "¡Hola! Bienvenido a Tu Carro con Alejo 🙌\n\n"
    "Soy el asistente de Alejo — asesor de ventas Toyota en Hollywood, Florida.\n\n"
    "Cuéntame, ¿qué modelo Toyota te interesa? O si tienes alguna pregunta sobre crédito, "
    "trade-in o disponibilidad, aquí estamos.\n\n"
    "Alejo te responde personalmente al (954) 910-6671 o por aquí directo 👇"
)


def set_messenger_profile() -> bool:
    """Sets greeting text and Get Started button. Run once to activate."""
    payload = {
        "get_started": {"payload": "GET_STARTED"},
        "greeting": GREETING,
    }
    resp = requests.post(BASE, params={"access_token": PAGE_TOKEN}, json=payload, timeout=10)
    result = resp.json()
    if result.get("result") == "success":
        print("✅ Ink — Messenger Profile configurado correctamente.")
        print("   Get Started button: activo")
        print("   Greeting: activo (default + es_LA)")
        return True
    else:
        print(f"🔴 Error configurando Messenger Profile: {result}")
        return False


def get_current_profile() -> dict:
    """Returns current Messenger Profile settings."""
    resp = requests.get(
        BASE,
        params={
            "fields": "get_started,greeting",
            "access_token": PAGE_TOKEN
        },
        timeout=10
    )
    return resp.json()


if __name__ == "__main__":
    print("── Ink — Configurando bienvenida Meta ──────────────────")
    print()
    print("Mensaje de bienvenida que recibirán los nuevos usuarios:")
    print("-" * 50)
    print(WELCOME_TEXT)
    print("-" * 50)
    print()

    confirm = input("¿Activar en Meta? (s/n): ").strip().lower()
    if confirm == "s":
        set_messenger_profile()
    else:
        print("Cancelado.")
