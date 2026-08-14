"""
NEXUS — Watchdog del bot de Marketplace.

Vigila que marketplace_inbox_bot.py (vía refresh_mp_session.py) siga vivo de
verdad, no solo a nivel de proceso. El caso real que motivó esto (23 jul 2026):
el proceso Python seguía corriendo pero el browser de Playwright murió
(SIGKILL) y el bot quedó ~14h sin loggear nada ni contestar clientes.

Dos partes con reglas de timing distintas:
- El CHEQUEO (leer el mtime de un log local) no toca Facebook para nada.
  Corre ~CHECKS_PER_DAY veces al día, en horarios aleatorios distintos
  cada día (uno por franja de ACTIVE_HOURS, nunca fuera de ese rango —
  pedido de Alejo: con poca actividad real no hace falta más seguido,
  y así tampoco queda un patrón fijo).
- El REINICIO sí vuelve a abrir messenger.com — ese es el que de verdad
  importa mantener no-robótico, por eso lleva jitter antes de ejecutarse
  y un cooldown para no reintentar en bucle.

SOLO debe correr en el MacBook Pro — mismo motivo que el bot de Marketplace
en sí (dos sesiones de Facebook peleando = riesgo real de checkpoint).
Ver memoria feedback-nexus-macbook-air-no-automation.
"""
import datetime
import json
import os
import random
import socket
import subprocess
import time

from dotenv import load_dotenv

from pulse import pulse_notify

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "logs", "marketplace_bot.log")
STATE_PATH = os.path.join(BASE_DIR, "marketplace_watchdog_state.json")
LAUNCH_LABEL = "com.nexus.marketplace.bot"

ACTIVE_HOURS = (8, 22)  # debe coincidir con marketplace_inbox_bot.ACTIVE_HOURS
ZOMBIE_THRESHOLD_ACTIVE = 8 * 60       # sin línea nueva en el momento del chequeo = sospechoso
CHECKS_PER_DAY = 4                     # ~4 chequeos/día, horario distinto y aleatorio cada día
RESTART_JITTER_RANGE = (60, 300)       # 1-5 min de espera antes de reiniciar (sí toca FB)
RESTART_COOLDOWN = 20 * 60             # no relanzar más de 1 vez cada 20 min
ALERT_COOLDOWN = 20 * 60               # no repetir alerta del mismo incidente antes de 20 min


def _is_pro() -> bool:
    host = socket.gethostname().lower()
    return "pro" in host and "air" not in host


def _random_check_times(day: datetime.date, n: int = CHECKS_PER_DAY) -> list:
    """n horarios aleatorios dentro de ACTIVE_HOURS, uno por franja para que
    queden repartidos en el día en vez de caer todos juntos por azar."""
    h_start, h_end = ACTIVE_HOURS
    window_start = datetime.datetime.combine(day, datetime.time(hour=h_start))
    window_end = datetime.datetime.combine(day, datetime.time(hour=h_end))
    bucket = (window_end - window_start).total_seconds() / n
    times = []
    for i in range(n):
        offset = random.uniform(i * bucket, (i + 1) * bucket)
        times.append(window_start + datetime.timedelta(seconds=offset))
    return times


def _load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_restart_ts": 0, "last_alert_ts": 0}


def _save_state(state: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def _gap_seconds() -> float:
    if not os.path.exists(LOG_PATH):
        return float("inf")
    return time.time() - os.path.getmtime(LOG_PATH)


def _restart_bot():
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "kickstart", "-k", f"gui/{uid}/{LAUNCH_LABEL}"],
        check=False,
    )


def _check_once(state: dict) -> dict:
    gap = _gap_seconds()
    threshold = ZOMBIE_THRESHOLD_ACTIVE

    if gap <= threshold:
        return state

    now = time.time()
    minutes = gap / 60

    if now - state.get("last_alert_ts", 0) > ALERT_COOLDOWN:
        pulse_notify(
            "MARKETPLACE_ERROR",
            f"Bot de Marketplace sin actividad hace {minutes:.0f} min. "
            f"Reintentando reinicio en breve.",
        )
        state["last_alert_ts"] = now
        _save_state(state)

    if now - state.get("last_restart_ts", 0) <= RESTART_COOLDOWN:
        print(f"[WATCHDOG] Zombie detectado (gap={minutes:.0f}m) pero en cooldown de reinicio — espero", flush=True)
        return state

    jitter = random.uniform(*RESTART_JITTER_RANGE)
    print(f"[WATCHDOG] Zombie detectado (gap={minutes:.0f}m) — reinicio en {jitter:.0f}s", flush=True)
    time.sleep(jitter)

    # Recheck: pudo recuperarse solo durante el jitter
    if _gap_seconds() <= threshold:
        print("[WATCHDOG] Se recuperó solo durante la espera — no hace falta reiniciar", flush=True)
        return state

    print("[WATCHDOG] Ejecutando kickstart -k sobre com.nexus.marketplace.bot", flush=True)
    _restart_bot()
    state["last_restart_ts"] = time.time()
    _save_state(state)
    return state


def main():
    if not _is_pro():
        print(f"[WATCHDOG] Host '{socket.gethostname()}' no es el Pro — me niego a correr aquí.", flush=True)
        return

    print(f"[WATCHDOG] Iniciado en {socket.gethostname()} — {CHECKS_PER_DAY}x/día, horario aleatorio dentro de {ACTIVE_HOURS}", flush=True)
    state = _load_state()

    while True:
        now = datetime.datetime.now()
        pending = [t for t in _random_check_times(now.date()) if t > now]
        if not pending:
            pending = _random_check_times(now.date() + datetime.timedelta(days=1))

        print(f"[WATCHDOG] Próximos chequeos: {', '.join(t.strftime('%H:%M') for t in pending)}", flush=True)

        for check_time in pending:
            wait = (check_time - datetime.datetime.now()).total_seconds()
            if wait > 0:
                time.sleep(wait)
            state = _check_once(state)


if __name__ == "__main__":
    main()
