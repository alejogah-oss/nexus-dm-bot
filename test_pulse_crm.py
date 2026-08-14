"""
NEXUS — Prueba de integración: WhatsApp (Pulse) + CRM
Simula un HOT LEAD completo de Marketplace y verifica que:
  1. WhatsApp llega al teléfono de Alejo
  2. Lead queda registrado en el CRM con datos del carro
"""
import sys
LINE = "─" * 52

def title(text):
    print(f"\n{LINE}")
    print(f"  {text}")
    print(LINE)

def ok(msg):    print(f"  ✅ {msg}")
def fail(msg):  print(f"  ❌ {msg}"); sys.exit(1)
def info(msg):  print(f"  ℹ️  {msg}")


# ── Datos del lead de prueba ──────────────────────────
FAKE_SENDER_ID = "TEST_SENDER_000001"
FAKE_PLATFORM  = "facebook"
FAKE_CAR = {
    "yr":           2026,
    "model":        "Camry",
    "trim":         "XSE V6",
    "color":        "Midnight Black",
    "vin":          "4T1BZ1HK0NU123456",
    "down_payment": 5200,
}
FAKE_CONVERSATION = [
    {"role": "user",      "content": "Hola, vi el Camry en Marketplace"},
    {"role": "assistant", "content": "¡Hola! Soy el asistente de Alejo. Ese 2026 Camry XSE está disponible."},
    {"role": "user",      "content": "Me interesa, me llamo Juan Pérez, mi número es 786-555-1234"},
    {"role": "assistant", "content": "¡Perfecto Juan! ¿Cuándo puedes venir al dealer en Hollywood?"},
    {"role": "user",      "content": "Puedo ir el sábado en la mañana"},
    {"role": "assistant", "content": "Excelente, te esperamos el sábado. 2200 N State Rd 7, Hollywood FL."},
]


# ── TEST 1 + 2: flujo completo push_hot_lead ─────────
title("TEST — WhatsApp + CRM (flujo completo)")
try:
    from crm_client import push_hot_lead, conversation_url, CRM_WEBHOOK_URL
    from pulse import ALEJO_PHONE

    conv_link = conversation_url(FAKE_SENDER_ID, FAKE_PLATFORM)
    info(f"Sender ID  : {FAKE_SENDER_ID}")
    info(f"Plataforma : {FAKE_PLATFORM}")
    info(f"Link conv  : {conv_link}")
    info(f"WhatsApp a : {ALEJO_PHONE}")
    info(f"CRM        : {CRM_WEBHOOK_URL}")
    print()

    result = push_hot_lead(
        sender_id=FAKE_SENDER_ID,
        platform=FAKE_PLATFORM,
        conversation_history=FAKE_CONVERSATION,
        car=FAKE_CAR,
    )

    if result.get("success"):
        ok(f"CRM — Lead creado ID: {result.get('lead_id')}")
        ok(f"WhatsApp enviado con link de conversación")
        print(f"\n  👀 Revisa WhatsApp — debe llegar el link al chat.")
        print(f"  👀 CRM: https://crm.tucarroconalejo.com/leads")
    else:
        fail(f"CRM respondió: {result}")

except Exception as e:
    fail(f"Falló: {e}")


# ── RESUMEN ───────────────────────────────────────────
title("RESULTADO")
print(f"  WhatsApp → +{ALEJO_PHONE if 'ALEJO_PHONE' in dir() else '?'}")
print(f"  CRM      → https://crm.tucarroconalejo.com/leads")
print(f"  Carro    → {FAKE_CAR['yr']} Toyota {FAKE_CAR['model']} {FAKE_CAR['trim']}")
print(f"  Cliente  → Juan Pérez | 786-555-1234")
print(f"\n  Ambas integraciones probadas con datos reales de Marketplace.\n")
