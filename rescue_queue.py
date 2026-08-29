"""Cola de rescates pendientes, guardada en el estado del bot de Marketplace.

Cada vez que el bot le contesta a un cliente queda anotado a qué hora habría
que rescatarlo si no vuelve a escribir. Si el cliente contesta, se cancela.

El estado es el mismo `marketplace_inbox_state.json` que ya existe, con
llaves `rescue_<thread_id>` — así no hay un archivo nuevo que mantener.
"""
import os
from datetime import datetime, timedelta

import price_ranges
from rescue_timing import (next_scan_interval, rescue_delay_minutes,
                           rescue_message, shift_into_window)

PREFIX = "rescue_"
# Llaves de control. A propósito NO empiezan por "rescue_": comparten el
# archivo de estado con los rescates y due() no debe confundirlas con threads.
NEXT_CHECK_KEY = "next_rescue_check"
LAST_INTERVAL_KEY = "last_rescue_interval"


def should_check_now(state, ahora=None):
    """¿Toca revisar la cola? Cada 30/33/37/41/44/50 minutos, sorteado, sin
    repetir el intervalo anterior — un reloj exacto delata al bot."""
    import time as _time
    ahora = _time.time() if ahora is None else ahora
    if ahora < state.get(NEXT_CHECK_KEY, 0):
        return False
    intervalo = next_scan_interval(state.get(LAST_INTERVAL_KEY))
    state[LAST_INTERVAL_KEY] = intervalo
    state[NEXT_CHECK_KEY] = ahora + intervalo * 60
    return True


def sending_enabled():
    """Apagado por defecto. Arranca en seco: registra a quién le habría
    escrito, sin escribirle. Se prende con RESCUE_ENABLED=1 en Render."""
    return os.environ.get("RESCUE_ENABLED") == "1"


def build_message(entry):
    """El texto que le tocaría a este cliente, o "" si no hay nada que decirle."""
    rango = price_ranges.get_range((entry or {}).get("vin", ""))
    if not rango:
        return ""
    low, high = rango
    # Los rescates encolados antes de que existiera "lang" van en español.
    return rescue_message((entry or {}).get("model", ""), low, high,
                          lang=(entry or {}).get("lang", "es"))


def schedule(state, thread_id, car, ahora=None, lang="es"):
    """Anota cuándo tocaría rescatar este thread. Sin VIN no se anota nada:
    sin VIN no hay rango, y sin rango no hay mensaje que mandar."""
    vin = (car or {}).get("vin", "")
    if not vin:
        return
    ahora = ahora or datetime.now()
    vence = shift_into_window(ahora + timedelta(minutes=rescue_delay_minutes()))
    state[f"{PREFIX}{thread_id}"] = {
        "due_at": vence.isoformat(),
        "vin": vin,
        "model": (car or {}).get("model", ""),
        "lang": lang,
        "done": False,
    }


def due(state, ahora=None):
    """Threads a los que ya les tocaba el rescate."""
    ahora = ahora or datetime.now()
    pendientes = []
    for key, entry in state.items():
        if not key.startswith(PREFIX) or not isinstance(entry, dict):
            continue
        if entry.get("done"):
            continue
        try:
            vence = datetime.fromisoformat(entry.get("due_at", ""))
        except (TypeError, ValueError):
            continue  # entrada corrupta: se ignora, el bot no se cae por esto
        if vence <= ahora:
            pendientes.append(key[len(PREFIX):])
    return pendientes


def cancel(state, thread_id):
    """El cliente contestó — ya no hay nada que rescatar."""
    state.pop(f"{PREFIX}{thread_id}", None)


def mark_done(state, thread_id):
    """Ya se le escribió. Se marca en vez de borrarse para que un reinicio no
    lo devuelva a la cola."""
    entry = state.get(f"{PREFIX}{thread_id}")
    if isinstance(entry, dict):
        entry["done"] = True
