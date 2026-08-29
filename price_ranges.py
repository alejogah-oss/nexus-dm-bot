"""Puente entre el bot y la tabla de rangos del CRM.

El rango de alternativas de cada carro lo define Alejo en /admin. Vivía en
listing.json, en el disco efímero de Render, que se borra en cada despliegue;
ahora vive en MySQL, en el CRM, que sí está siempre arriba.

Regla de oro: nada de acá levanta una excepción. Si el CRM no contesta, el
bot sigue atendiendo clientes — simplemente no rescata a nadie ese rato.
"""
import os
import requests

from crm_client import CRM_WEBHOOK_KEY  # misma llave del webhook, no se duplica acá

RANGE_URL = os.getenv("CRM_RANGE_URL", "https://crm.tucarroconalejo.com/api/range")
TIMEOUT = 10

_HEADERS = {"Content-Type": "application/json", "X-Api-Key": CRM_WEBHOOK_KEY}


def get_range(vin):
    """Devuelve (bajo, alto) para ese VIN, o None si no hay rango cargado."""
    vin = (vin or "").strip().upper()
    if not vin:
        return None
    try:
        r = requests.get(RANGE_URL, params={"vin": vin}, headers=_HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        low, high = int(data.get("alt_price_low") or 0), int(data.get("alt_price_high") or 0)
        return (low, high) if low > 0 and high > low else None
    except Exception as e:
        print(f"[RANGE] No se pudo leer el rango de {vin}: {e}")
        return None


def save_range(vin, low, high, internal=0):
    """Replica en la tabla del CRM el rango que Alejo acaba de editar en /admin.

    Devuelve False sin llamar al CRM si no hay rango que guardar. Si el CRM
    está caído tampoco revienta: el rango queda en listing.json igual, solo
    que sin replicar.
    """
    vin = (vin or "").strip().upper()
    low, high = int(low or 0), int(high or 0)
    if not vin or low <= 0 or high <= low:
        return False
    try:
        r = requests.post(
            RANGE_URL,
            json={"vin": vin, "alt_price_low": low, "alt_price_high": high,
                  "internal_price": int(internal or 0)},
            headers=_HEADERS, timeout=TIMEOUT,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[RANGE] No se pudo guardar el rango de {vin}: {e}")
        return False


def claim_rescue(thread_id, vin, model, message, dry_run=True):
    """Reclama el rescate de un thread. True solo la PRIMERA vez.

    Fail-closed: si el CRM no responde devuelve False y el bot no escribe. Un
    lead sin rescatar es mejor que un cliente recibiendo el mismo mensaje cada
    vez que el servidor reinicia y pierde su estado local.
    """
    try:
        r = requests.post(
            f"{RANGE_URL}/rescue/claim",
            json={"thread_id": thread_id, "vin": vin, "model": model,
                  "message": message, "dry_run": dry_run},
            headers=_HEADERS, timeout=TIMEOUT,
        )
        return r.status_code == 200 and bool(r.json().get("claimed"))
    except Exception as e:
        print(f"[RANGE] No se pudo reclamar el rescate de {thread_id}: {e}")
        return False


def mark_sent(thread_id):
    """Confirma que el mensaje salió de verdad (deja de ser 'seco')."""
    try:
        r = requests.post(f"{RANGE_URL}/rescue/sent", json={"thread_id": thread_id},
                          headers=_HEADERS, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception as e:
        print(f"[RANGE] No se pudo confirmar el envío de {thread_id}: {e}")
        return False
