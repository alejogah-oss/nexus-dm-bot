# Marketplace Bot — Fixes para lograr más citas agendadas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir las causas raíz (técnicas y de guion) por las que las conversaciones del bot de Marketplace no llegan a agendar una cita en el showroom, identificadas en la auditoría del 24 de julio de 2026 hecha por Wire (técnico), Ink (copy/flujo) y Psique (psicología del consumidor).

**Architecture:** Son 6 cambios independientes y acumulativos sobre archivos ya existentes — ninguno requiere módulos nuevos. Los primeros 4 son fixes de código (`marketplace_inbox_bot.py`, `appointments.py`, `dm_bot.py`) con lógica pura extraída a funciones testeables con `pytest`. Los últimos 2 son reescrituras de los prompts del sistema (`_marketplace_voice` y `BOT_VOICE` en `dm_bot.py`), verificados con tests de contenido (assert de substrings), siguiendo el mismo patrón que ya usa `tests/test_listing_voice.py` en este repo.

**Tech Stack:** Python 3.11, pytest, Playwright (async), Anthropic SDK, Twilio (vía `pulse.py`).

**Fuera de alcance de este plan:** confirmar con Alejo qué canceló las 3 citas del 21 de julio a las 3:13am (`nexus_appointments.json`) — es una pregunta operativa, no un fix de código.

---

## Antes de empezar

```bash
cd /Users/macbookpro/nexus-automation
git status   # confirmar que no hay cambios sin commitear de otra sesión
venv/bin/python3 -m pytest tests/ -q   # baseline: confirmar que la suite pasa ANTES de tocar nada
```

Expected: la suite actual pasa en verde (o el estado ya conocido) antes de empezar — si algo falla aquí, no es de este plan, anótalo y sigue.

---

### Task 1: Cortar el loop infinito de "sin listing" en el bot de Marketplace

**Contexto:** en `marketplace_inbox_bot.py`, cuando `process_thread()` no logra identificar de qué carro es un listing (falla intermitente del header de Messenger), imprime "SALTANDO" y hace `return` sin marcar el mensaje como visto — así que en el siguiente ciclo de polling (60s) lo vuelve a detectar como "nuevo" y repite indefinidamente, sin nunca avisar a nadie. En los logs esto dejó clientes de alta intención sin respuesta por más de 2.5 horas.

**Files:**
- Modify: `marketplace_inbox_bot.py:363-370`
- Test: `tests/test_marketplace_inbox_bot.py` (nuevo)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_marketplace_inbox_bot.py`:

```python
import marketplace_inbox_bot as mib


def test_track_car_resolution_failure_incrementa_contador():
    failures = {}
    for expected_count in range(1, 5):
        count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
        assert count == expected_count
        assert should_alert is False


def test_track_car_resolution_failure_alerta_al_llegar_al_threshold():
    failures = {"t1": 4}
    count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
    assert count == 5
    assert should_alert is True


def test_track_car_resolution_failure_no_alerta_de_nuevo_tras_threshold():
    failures = {"t1": 5}
    count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
    assert count == 6
    assert should_alert is False


def test_track_car_resolution_failure_threads_distintos_no_se_mezclan():
    failures = {}
    mib._track_car_resolution_failure(failures, "t1", threshold=5)
    mib._track_car_resolution_failure(failures, "t1", threshold=5)
    count, _ = mib._track_car_resolution_failure(failures, "t2", threshold=5)
    assert count == 1
    assert failures == {"t1": 2, "t2": 1}
```

- [ ] **Step 2: Correr el test para confirmar que falla**

Run: `venv/bin/python3 -m pytest tests/test_marketplace_inbox_bot.py -v`
Expected: FAIL — `AttributeError: module 'marketplace_inbox_bot' has no attribute '_track_car_resolution_failure'`

- [ ] **Step 3: Implementar la función pura**

En `marketplace_inbox_bot.py`, agregar cerca de los otros globals de estado (después de la línea 54, antes de la línea 56 en blanco):

```python
_car_resolution_failures: dict[str, int] = {}   # {f"{thread_id}:{msg_hash}": intentos}
CAR_RESOLUTION_ALERT_THRESHOLD = 5              # ~5 ciclos de polling normal (~5 min)


def _track_car_resolution_failure(failures: dict[str, int], key: str, threshold: int = CAR_RESOLUTION_ALERT_THRESHOLD) -> tuple[int, bool]:
    """Incrementa el contador de fallos de resolución de carro para `key`.
    Retorna (conteo_actual, True solo el ciclo exacto en que se cruza el threshold)."""
    count = failures.get(key, 0) + 1
    failures[key] = count
    return count, count == threshold
```

- [ ] **Step 4: Correr el test para confirmar que pasa**

Run: `venv/bin/python3 -m pytest tests/test_marketplace_inbox_bot.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Conectar la función al bloque "sin listing"**

En `marketplace_inbox_bot.py`, reemplazar el bloque actual (líneas 363-370):

```python
    if not car:
        print(f"  [BOT] Sin listing de Marketplace — SALTANDO {thread_id}", flush=True)
        # Auto-cura: si el sidebar dio ID numérico en vez del nombre, forzar un
        # goto/reload real en el próximo scan completo para recuperar los títulos
        # (sin esto el thread queda mudo hasta la recarga horaria)
        global _last_full_load
        _last_full_load = 0.0
        return
```

por:

```python
    if not car:
        key = f"{thread_id}:{msg_hash}"
        fails, should_alert = _track_car_resolution_failure(_car_resolution_failures, key)
        print(f"  [BOT] Sin listing de Marketplace — SALTANDO {thread_id} (intento {fails})", flush=True)
        if should_alert:
            pulse_notify(
                "MARKETPLACE_ERROR",
                f"El bot lleva {fails} ciclos sin poder identificar el carro del thread "
                f"{thread_id} ({sender_name or 'sin nombre'}) — el cliente no ha recibido "
                f"respuesta. Revisa: https://www.messenger.com/marketplace/t/{thread_id}"
            )
        # Auto-cura: si el sidebar dio ID numérico en vez del nombre, forzar un
        # goto/reload real en el próximo scan completo para recuperar los títulos
        # (sin esto el thread queda mudo hasta la recarga horaria)
        global _last_full_load
        _last_full_load = 0.0
        return
    _car_resolution_failures.pop(f"{thread_id}:{msg_hash}", None)
```

- [ ] **Step 6: Verificar que el módulo sigue importando sin errores**

Run: `venv/bin/python3 -c "import marketplace_inbox_bot"`
Expected: sin output, sin traceback (los prints `[MIB] ... imported` son esperados)

- [ ] **Step 7: Correr toda la suite de tests**

Run: `venv/bin/python3 -m pytest tests/ -q`
Expected: todos los tests pasan, incluyendo los 4 nuevos.

- [ ] **Step 8: Commit**

```bash
git add marketplace_inbox_bot.py tests/test_marketplace_inbox_bot.py
git commit -m "fix: alertar y contar reintentos cuando el bot no puede identificar el carro de un thread"
```

---

### Task 2: Desacoplar la creación de citas del tag [HOT LEAD] + evitar duplicados

**Contexto:** hoy `extract_appointment_from_conversation()` solo se llama dentro de `if is_hot:` en `marketplace_inbox_bot.py` y en `dm_bot.py` — si el modelo no incluyó `[HOT LEAD]` en el mensaje exacto donde el cliente dio la fecha, la cita nunca se registra. En el log: 16 detecciones de HOT LEAD, solo 4 citas creadas automáticamente. Al llamarla en cada respuesta hay que evitar crear una cita duplicada cada vez que el cliente repite o confirma la misma fecha.

**Files:**
- Modify: `appointments.py:126` (nueva función antes de `create_appointment`), `appointments.py:316-320` (guard dentro de `extract_appointment_from_conversation`)
- Modify: `marketplace_inbox_bot.py:426-438`
- Modify: `dm_bot.py:424-440`
- Test: `tests/test_appointments.py` (nuevo)

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_appointments.py`:

```python
import json
from unittest.mock import patch, MagicMock

import appointments


def test_has_open_appointment_true_si_pending(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "abc", "status": "pending"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("abc") is True


def test_has_open_appointment_true_si_confirmed(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "abc", "status": "confirmed"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("abc") is True


def test_has_open_appointment_false_si_cancelada(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "abc", "status": "cancelled"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("abc") is False


def test_has_open_appointment_false_si_no_existe(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text("[]")
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("xyz") is False


def test_extract_appointment_no_llama_a_claude_si_ya_hay_cita_abierta(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "cust1", "status": "pending"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))

    with patch.object(appointments._claude.messages, "create") as mock_create:
        result = appointments.extract_appointment_from_conversation(
            history=[{"role": "user", "content": "puedo ir el sábado"}],
            car={"yr": 2026, "model": "Camry", "trim": "", "color": ""},
            sender_id="cust1",
            platform="marketplace",
        )

    assert result is None
    mock_create.assert_not_called()


def test_extract_appointment_si_llama_a_claude_cuando_no_hay_cita_abierta(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text("[]")
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text='{"fecha": null, "hora": null, "nombre": null, "telefono": null}')]

    with patch.object(appointments._claude.messages, "create", return_value=fake_response) as mock_create:
        result = appointments.extract_appointment_from_conversation(
            history=[{"role": "user", "content": "hola"}],
            car={"yr": 2026, "model": "Camry", "trim": "", "color": ""},
            sender_id="cust2",
            platform="marketplace",
        )

    assert result is None
    mock_create.assert_called_once()
```

- [ ] **Step 2: Correr los tests para confirmar que fallan**

Run: `venv/bin/python3 -m pytest tests/test_appointments.py -v`
Expected: FAIL en los primeros 4 tests con `AttributeError: module 'appointments' has no attribute '_has_open_appointment'`; los últimos 2 fallan porque hoy `extract_appointment_from_conversation` siempre llama a Claude.

- [ ] **Step 3: Implementar `_has_open_appointment`**

En `appointments.py`, agregar justo antes de `def create_appointment(` (línea 127):

```python
def _has_open_appointment(customer_id: str) -> bool:
    """True si ya existe una cita pending/confirmed para este cliente — evita duplicados."""
    appointments = _load()
    return any(
        a.get("customer_id") == customer_id and a.get("status") != "cancelled"
        for a in appointments
    )


```

- [ ] **Step 4: Conectar el guard dentro de `extract_appointment_from_conversation`**

En `appointments.py`, en `extract_appointment_from_conversation` (línea 278), agregar el guard justo después del docstring y antes de `if not history:` (línea 284):

```python
def extract_appointment_from_conversation(history: list, car: dict, sender_id: str, platform: str) -> dict | None:
    """
    Usa Claude Haiku para detectar si el cliente mencionó una fecha/hora para venir.
    Si encuentra fecha, crea la cita automáticamente.
    Retorna el dict de la cita o None si no se detectó fecha.
    """
    if _has_open_appointment(sender_id):
        return None

    if not history:
        return None
```

- [ ] **Step 5: Correr los tests para confirmar que pasan**

Run: `venv/bin/python3 -m pytest tests/test_appointments.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Sacar la llamada de dentro de `if is_hot:` en `marketplace_inbox_bot.py`**

Reemplazar (líneas 428-438):

```python
    # HOT LEAD — igual que dm_bot.handle_marketplace_message
    if is_hot:
        print(f"  [BOT] 🔥 HOT LEAD — {sender_name}")
        try:
            push_hot_lead(thread_id, "marketplace_personal", full_history, car=car)
        except Exception as e:
            print(f"  [BOT] Error CRM HOT LEAD: {e}")
        log_event("HOT_LEAD", f"Marketplace personal | {sender_name} | {last_msg[:80]}", "marketplace")
        if car:
            track_hot_lead(car)
            extract_appointment_from_conversation(full_history, car, thread_id, "marketplace")
```

por:

```python
    # HOT LEAD — igual que dm_bot.handle_marketplace_message
    if is_hot:
        print(f"  [BOT] 🔥 HOT LEAD — {sender_name}")
        try:
            push_hot_lead(thread_id, "marketplace_personal", full_history, car=car)
        except Exception as e:
            print(f"  [BOT] Error CRM HOT LEAD: {e}")
        log_event("HOT_LEAD", f"Marketplace personal | {sender_name} | {last_msg[:80]}", "marketplace")
        if car:
            track_hot_lead(car)

    # Se intenta extraer la cita en CADA respuesta, no solo cuando el modelo marcó
    # [HOT LEAD] en ese mensaje exacto — el cliente puede confirmar la fecha en un
    # turno posterior sin que el modelo repita la etiqueta. _has_open_appointment()
    # evita crear duplicados si ya hay una cita pending/confirmed para este thread.
    if car:
        extract_appointment_from_conversation(full_history, car, thread_id, "marketplace")
```

- [ ] **Step 7: Sacar la llamada de dentro de `if is_hot:` en `dm_bot.py`**

Reemplazar (líneas 424-440):

```python
    if is_hot:
        print(f"\n🔥 MARKETPLACE HOT LEAD — {platform.upper()} | {sender_id[:12]}...")
        note = save_note(sender_id, platform, history)
        if note["changed"]:
            pulse_notify(
                event="HOT_LEAD",
                detail=(
                    f"⚠️ CAMBIO DE CITA — Marketplace\n"
                    f"Cita anterior: {note['prev_appointment']}\n"
                    f"Nueva cita: {note['appointment']}\n"
                    f"Hora: {note['timestamp']}"
                )
            )
        push_hot_lead(sender_id, platform, history, car=car)
        log_event("HOT_LEAD", f"Marketplace {car['yr']} {car['model']} {car.get('trim','')} | {text[:80]}", platform)
        track_hot_lead(car)
        extract_appointment_from_conversation(history, car, sender_id, platform)
```

por:

```python
    if is_hot:
        print(f"\n🔥 MARKETPLACE HOT LEAD — {platform.upper()} | {sender_id[:12]}...")
        note = save_note(sender_id, platform, history)
        if note["changed"]:
            pulse_notify(
                event="HOT_LEAD",
                detail=(
                    f"⚠️ CAMBIO DE CITA — Marketplace\n"
                    f"Cita anterior: {note['prev_appointment']}\n"
                    f"Nueva cita: {note['appointment']}\n"
                    f"Hora: {note['timestamp']}"
                )
            )
        push_hot_lead(sender_id, platform, history, car=car)
        log_event("HOT_LEAD", f"Marketplace {car['yr']} {car['model']} {car.get('trim','')} | {text[:80]}", platform)
        track_hot_lead(car)

    # Igual que en marketplace_inbox_bot.py: se intenta en cada respuesta, no solo
    # cuando el modelo marcó [HOT LEAD] en ese mensaje — _has_open_appointment()
    # evita duplicados.
    extract_appointment_from_conversation(history, car, sender_id, platform)
```

- [ ] **Step 8: Verificar que los módulos siguen importando sin errores**

Run: `venv/bin/python3 -c "import appointments, marketplace_inbox_bot, dm_bot"`
Expected: sin traceback.

- [ ] **Step 9: Correr toda la suite de tests**

Run: `venv/bin/python3 -m pytest tests/ -q`
Expected: todos pasan.

- [ ] **Step 10: Commit**

```bash
git add appointments.py marketplace_inbox_bot.py dm_bot.py tests/test_appointments.py
git commit -m "fix: extraer citas en cada respuesta del bot, no solo cuando hay tag HOT LEAD, con guard anti-duplicados"
```

---

### Task 3: Loguear el texto completo de cada respuesta del bot

**Contexto:** hoy solo se loguea "✅ Respondido a X", nunca el contenido — imposible auditar después si una respuesta fue correcta o violó alguna regla de negocio.

**Files:**
- Modify: `marketplace_inbox_bot.py:409`
- Modify: `dm_bot.py:417` (después del envío, dentro de `handle_marketplace_message`)

- [ ] **Step 1: Agregar el log en `marketplace_inbox_bot.py`**

Reemplazar (línea 407-409):

```python
    try:
        await _type_and_send(page, reply)
        print(f"  [BOT] ✅ Respondido a {sender_name}")
```

por:

```python
    try:
        await _type_and_send(page, reply)
        print(f"  [BOT] ✅ Respondido a {sender_name}")
        print(f"  [BOT] 💬 {reply}", flush=True)
```

- [ ] **Step 2: Agregar el log en `dm_bot.py`**

Reemplazar (líneas 413-417):

```python
    if platform == "instagram":
        send_instagram_reply(sender_id, clean_reply)
    else:
        send_facebook_reply(sender_id, clean_reply)
```

por:

```python
    if platform == "instagram":
        send_instagram_reply(sender_id, clean_reply)
    else:
        send_facebook_reply(sender_id, clean_reply)
    print(f"[MP-{platform.upper()}] 💬 {clean_reply}", flush=True)
```

- [ ] **Step 3: Verificar que los módulos siguen importando sin errores**

Run: `venv/bin/python3 -c "import marketplace_inbox_bot, dm_bot"`
Expected: sin traceback.

- [ ] **Step 4: Smoke test manual del import y sintaxis**

Run: `venv/bin/python3 -m py_compile marketplace_inbox_bot.py dm_bot.py`
Expected: sin output, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add marketplace_inbox_bot.py dm_bot.py
git commit -m "feat: loguear el texto completo de cada respuesta del bot para poder auditarla"
```

---

### Task 4: Alertar de inmediato cuando se cae la sesión de Facebook

**Contexto:** cuando la sesión de FB expira, el bot deja de responder a TODOS los clientes hasta que alguien la renueva manualmente (2FA). Hoy solo el watchdog externo detecta esto, y solo después de 8 minutos sin nuevas líneas en el log — un proxy indirecto. Se necesita una alerta explícita en el momento exacto en que se detecta el redirect a login, sin spamear en cada ciclo mientras sigue caída.

**Files:**
- Modify: `marketplace_inbox_bot.py:54` (nuevo global), `marketplace_inbox_bot.py:837-839`
- Test: `tests/test_marketplace_inbox_bot.py` (agregar al archivo del Task 1)

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_marketplace_inbox_bot.py`:

```python
def test_session_alert_transition_primera_caida_alerta():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=False, alert_already_sent=False)
    assert should_alert is True
    assert new_state is True


def test_session_alert_transition_no_repite_alerta_mientras_sigue_caida():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=False, alert_already_sent=True)
    assert should_alert is False
    assert new_state is True


def test_session_alert_transition_reset_al_recuperar_sesion():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=True, alert_already_sent=True)
    assert should_alert is False
    assert new_state is False


def test_session_alert_transition_sin_cambios_si_ya_estaba_bien():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=True, alert_already_sent=False)
    assert should_alert is False
    assert new_state is False
```

- [ ] **Step 2: Correr los tests para confirmar que fallan**

Run: `venv/bin/python3 -m pytest tests/test_marketplace_inbox_bot.py -v -k session_alert`
Expected: FAIL — `AttributeError: module 'marketplace_inbox_bot' has no attribute '_session_alert_transition'`

- [ ] **Step 3: Implementar la función pura y el global**

En `marketplace_inbox_bot.py`, agregar junto a `_last_full_load` (línea 54):

```python
_last_full_load: float = 0.0  # último goto/reload real del inbox (el sidebar vive por WebSocket)
_session_expired_alert_sent: bool = False  # evita spamear la alerta mientras la sesión sigue caída


def _session_alert_transition(currently_logged_in: bool, alert_already_sent: bool) -> tuple[bool, bool]:
    """Decide si hay que enviar la alerta de sesión caída este ciclo.
    Retorna (debe_alertar_ahora, nuevo_valor_de_alert_already_sent)."""
    if currently_logged_in:
        return False, False
    if alert_already_sent:
        return False, True
    return True, True
```

- [ ] **Step 4: Correr los tests para confirmar que pasan**

Run: `venv/bin/python3 -m pytest tests/test_marketplace_inbox_bot.py -v -k session_alert`
Expected: PASS (4 tests)

- [ ] **Step 5: Conectar la función al chequeo real de sesión (modo LOCAL_MODE)**

Reemplazar en `marketplace_inbox_bot.py` (líneas 836-839):

```python
                _last_full_load = time.time()
                print(f"[BOT] LOCAL: url={page.url[:80]}", flush=True)
            if "login" in page.url:
                print("[BOT] LOCAL: redirigió a login — sesión expirada, re-loguear", flush=True)
                return
```

por:

```python
                _last_full_load = time.time()
                print(f"[BOT] LOCAL: url={page.url[:80]}", flush=True)
            global _session_expired_alert_sent
            session_ok = "login" not in page.url
            should_alert, _session_expired_alert_sent = _session_alert_transition(
                currently_logged_in=session_ok, alert_already_sent=_session_expired_alert_sent
            )
            if should_alert:
                pulse_notify(
                    "MARKETPLACE_ERROR",
                    "La sesión de Facebook del bot de Marketplace expiró — nadie está "
                    "recibiendo respuesta hasta que alguien la renueve manualmente (2FA). "
                    "Corre en el Pro: venv/bin/python3 refresh_mp_session.py"
                )
            if not session_ok:
                print("[BOT] LOCAL: redirigió a login — sesión expirada, re-loguear", flush=True)
                return
```

- [ ] **Step 6: Verificar que el módulo sigue importando sin errores**

Run: `venv/bin/python3 -c "import marketplace_inbox_bot"`
Expected: sin traceback.

- [ ] **Step 7: Correr toda la suite de tests**

Run: `venv/bin/python3 -m pytest tests/ -q`
Expected: todos pasan.

- [ ] **Step 8: Commit**

```bash
git add marketplace_inbox_bot.py tests/test_marketplace_inbox_bot.py
git commit -m "feat: alertar por WhatsApp de inmediato cuando se cae la sesión de Facebook, sin spamear mientras sigue caída"
```

---

### Task 5: Reescribir el guion de ventas de Marketplace (`_marketplace_voice`)

**Contexto (hallazgos de Ink y Psique):** el pivot a cita es condicional a frases específicas del cliente; si se despide con un simple "gracias" el guion prohíbe insistir una sola vez; no hay rama para "mi esposo/esposa decide"; no hay rama para pedidos de Carfax/historial (señal de alta intención hoy ignorada); cuando solo hay un trim en stock el texto dice "ronda los $X" en vez de aclarar que no hay rango; el pivot a "usados" pide WhatsApp sin dar ningún valor antes, lo cual se siente como evasiva. La pregunta de cierre "¿para cuándo te queda fácil venir?" es abierta y de bajo compromiso — la propia data de citas (`nexus_appointments.json`) tiene una cita con `date_preference: "mañana"` que nunca se concretó.

**Files:**
- Modify: `dm_bot.py:280-373` (función `_marketplace_voice`)
- Test: `tests/test_marketplace_voice.py` (nuevo)

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_marketplace_voice.py`:

```python
from dm_bot import _marketplace_voice

CAR_CON_RANGO = {"yr": 2026, "model": "Camry", "trim": "LE", "color": "White",
                  "price": 28000, "price_hi": 35000, "vin": "1FAKE"}
CAR_UN_SOLO_TRIM = {"yr": 2026, "model": "GR Supra", "trim": "3.0", "color": "Red",
                     "price": 58000, "price_hi": 0, "vin": "2FAKE"}


def test_ofrece_dos_horarios_concretos_no_pregunta_abierta():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in p
    assert "¿Para cuándo te queda fácil venir?" not in p


def test_cierre_exige_un_intento_de_agendar_antes_de_despedirse():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "UN intento obligatorio de cierre suave" in p


def test_tiene_rama_para_decisor_ausente():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "DECISOR AUSENTE" in p
    assert "tráelo(a) también" in p


def test_tiene_rama_para_carfax_historial():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "HISTORIAL / CARFAX" in p


def test_un_solo_trim_aclara_que_no_hay_rango():
    p = _marketplace_voice(CAR_UN_SOLO_TRIM)
    assert "no hay rango porque solo tenemos esta versión" in p


def test_usados_da_valor_antes_de_pedir_whatsapp():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "Sí manejamos usados en ese rango" in p
```

- [ ] **Step 2: Correr los tests para confirmar que fallan**

Run: `venv/bin/python3 -m pytest tests/test_marketplace_voice.py -v`
Expected: FAIL — varios `assert ... in p` fallan porque el texto actual no tiene ninguna de estas frases.

- [ ] **Step 3: Reescribir el bloque de precio de un solo trim**

En `dm_bot.py`, dentro de `_marketplace_voice`, reemplazar (líneas 292-294):

```python
        else:
            precio_info = f"PRECIO: ${price:,} (único trim disponible en stock). Taxes y fees van aparte."
            regla_precio = f'Ronda los ${price:,} más taxes y fees — el número final se afina en persona según el trim exacto. Cierra siempre con: "¿Lo estás viendo para financiar o cash?"'
```

por:

```python
        else:
            precio_info = f"PRECIO: ${price:,} (único trim disponible en stock, no hay rango porque solo tenemos esta versión). Taxes y fees van aparte."
            regla_precio = f'Aclara que no hay rango porque solo tenemos esta versión en stock ahora mismo: ronda los ${price:,} más taxes y fees, el número final se afina en persona. Cierra siempre con: "¿Lo estás viendo para financiar o cash?"'
```

- [ ] **Step 3b: Actualizar `mensualidad_alt` para usar el mismo cierre de horarios concretos**

La variable `mensualidad_alt` contiene la frase vieja "¿Para cuándo te queda fácil venir?" y aparece **dos veces, con texto idéntico**, en `dm_bot.py`: una dentro del bloque `if price > 0:` (líneas 295-297) y otra dentro del `else:` de precio no disponible (líneas 301-303). Hay que reemplazar **ambas** ocurrencias — si no, el test del Step 7 (`test_ofrece_dos_horarios_concretos_no_pregunta_abierta`) sigue fallando porque la frase vieja seguiría viva en esta variable aunque ya no esté en el resto del prompt.

En cada una de las dos ocurrencias, reemplazar:

```python
        mensualidad_alt = ('- Si quiere una validación real sin venir: "Llena esta aplicación de crédito rápida: https://facredit.online/quick/ — es un simulador, toma menos de 5 minutos y sin compromiso."\n'
                           '- Si tampoco quiere el formulario aún: "La mejor forma es que te acerques al dealer — en minutos sales con tu número exacto. ¿Para cuándo te queda fácil venir?" (pivotea a agendar la cita).\n'
                           '- NUNCA inventes un monto mensual.')
```

por:

```python
        mensualidad_alt = ('- Si quiere una validación real sin venir: "Llena esta aplicación de crédito rápida: https://facredit.online/quick/ — es un simulador, toma menos de 5 minutos y sin compromiso."\n'
                           '- Si tampoco quiere el formulario aún: "La mejor forma es que te acerques al dealer — en minutos sales con tu número exacto. Tengo espacio hoy en la tarde o mañana en la mañana, ¿cuál te queda mejor?" (pivotea a agendar la cita con el FLUJO DE AGENDAMIENTO paso 2).\n'
                           '- NUNCA inventes un monto mensual.')
```

(el resto de la función, con la indentación de 4 espacios en la segunda y tercera línea del literal, queda igual — solo cambia el texto entre comillas de la segunda línea)

- [ ] **Step 4: Reescribir FLUJO DE AGENDAMIENTO**

Reemplazar (líneas 330-335):

```python
FLUJO DE AGENDAMIENTO — el número y la cita salen solos, nunca como requisito de entrada:
1. Responde siempre primero lo que el cliente preguntó — nunca abras pidiendo el teléfono.
2. Detecta interés real: pregunta por el número exacto o la mensualidad, dice cuándo lo necesita, o habla de su carro actual ("el que tengo", "quiero cambiar mi..."). Ahí pivotea con naturalidad: "¿Para cuándo te queda fácil acercarte? Ahí te confirmamos todo con tu situación exacta."
3. Cuando confirme un día → pide el número en el mismo paso: "Perfecto, ¿me dejas tu número para coordinarte mejor?"
4. Con día + número → cierra: "Listo, quedas agendado para el [día] — te esperamos." + da la dirección: 2200 N State Rd 7, Hollywood, FL 33021 + agrega [HOT LEAD]
Sigue llevando tú la conversación con preguntas — nunca sueltes información y te quedes pasivo.
```

por:

```python
FLUJO DE AGENDAMIENTO — el número y la cita salen solos, nunca como requisito de entrada:
1. Responde siempre primero lo que el cliente preguntó — nunca abras pidiendo el teléfono.
2. Después de CUALQUIER respuesta de precio, mensualidad, crédito, Carfax o disponibilidad de usados, cierra ese mismo mensaje ofreciendo dos horarios concretos: "Tengo espacio hoy en la tarde o mañana en la mañana — ¿cuál te queda mejor?" (ajusta los horarios al momento real del día). No esperes ninguna señal adicional del cliente para ofrecerlo — es parte automática de la respuesta.
3. Cuando confirme uno de los dos horarios → pide el número en el mismo paso: "Perfecto, ¿me dejas tu número para coordinarte mejor?"
4. Con día + número → cierra: "Listo, quedas agendado para el [día] — te esperamos." + da la dirección: 2200 N State Rd 7, Hollywood, FL 33021 + agrega [HOT LEAD]
Sigue llevando tú la conversación con preguntas — nunca sueltes información y te quedes pasivo.

DECISOR AUSENTE — si menciona que alguien más decide (esposo, esposa, pareja, socio):
No lo trates como rechazo ni sigas calificando solo con quien te escribe — es señal de que ya se imagina comprando, no de que se va a ir. Reconócelo e invita a ambos a la cita: "Perfecto, mejor así — tráelo(a) también, entre los dos lo ven con calma y sin presión. ¿Qué día les queda bien a ambos?" Sigue el FLUJO DE AGENDAMIENTO normal desde ahí.
```

- [ ] **Step 5: Reescribir CIERRE DE CONVERSACIÓN**

Reemplazar (líneas 363-366):

```python
CIERRE DE CONVERSACIÓN:
Si el cliente se despide, agradece, dice que no por ahora, o ya confirmó que viene al showroom — responde con UNA sola frase corta y cálida de despedida. SIN pregunta, sin seguir vendiendo, sin agregar información nueva. Solo vuelve a hablar si el cliente te escribe de nuevo.
Ejemplos ES: "Perfecto, qué gusto hablar contigo — aquí estamos cuando quieras dar el siguiente paso." · "Genial, gracias a ti — nos vemos pronto por el dealer." · "Está bien, sin problema — cualquier cosa me escribes."
Ejemplos EN: "Sounds good, thanks for reaching out — we're here whenever you're ready." · "Perfect, appreciate you — see you soon at the dealership." · "No worries at all — just reach out whenever works for you."
```

por:

```python
CIERRE DE CONVERSACIÓN:
Si el cliente se despide o agradece SIN haber confirmado todavía un horario, tienes UN intento obligatorio de cierre suave antes de dejarlo ir: ofrece los dos horarios concretos del FLUJO DE AGENDAMIENTO paso 2 en una sola frase corta, sin sonar insistente. Ejemplo ES: "Un gusto — antes de irte, tengo espacio hoy en la tarde o mañana en la mañana, ¿te late pasar a verlo?" Ejemplo EN: "Great talking to you — before you go, I've got time today or tomorrow morning if you want to swing by and see it."
Si el cliente rechaza ese intento, dice que no por ahora, ya confirmó que viene al showroom, o ya rechazó 2 veces antes (ver RECHAZOS) — ahí sí responde con UNA sola frase corta y cálida de despedida. SIN pregunta, sin seguir vendiendo, sin agregar información nueva. Solo vuelve a hablar si el cliente te escribe de nuevo.
Ejemplos ES: "Perfecto, qué gusto hablar contigo — aquí estamos cuando quieras dar el siguiente paso." · "Genial, gracias a ti — nos vemos pronto por el dealer." · "Está bien, sin problema — cualquier cosa me escribes."
Ejemplos EN: "Sounds good, thanks for reaching out — we're here whenever you're ready." · "Perfect, appreciate you — see you soon at the dealership." · "No worries at all — just reach out whenever works for you."
```

- [ ] **Step 6: Reescribir CARROS USADOS y agregar HISTORIAL / CARFAX**

Reemplazar (líneas 352-357):

```python
CARROS USADOS / EL LISTING NO ES LO QUE BUSCA:
Detecta las señales aunque el cliente no diga "usado": pide años anteriores (ej. "2017 al 2018"), menciona millaje (ej. "con 100,000"), su presupuesto está claramente por debajo de este carro, o confunde el enganche del anuncio con lo que quiere gastar en total. Revisa TODO el historial — si en cualquier mensaje anterior pidió algo distinto al carro del listing, eso es lo que busca.
- Ante cualquiera de esas señales NO insistas con el carro del listing — pivotea de una: tenemos un inventario extenso de usados que cambia todos los días, y esa información (opciones, fotos y precios) la enviamos por WhatsApp.
- Confirma los datos necesarios uno por uno: nombre, número de WhatsApp, y qué busca (año, presupuesto o millaje máximo).
- Cuando tengas nombre + número → confirma "te mando las opciones por WhatsApp" y agrega [HOT LEAD] al final.
- NUNCA des precios ni inventes disponibilidad de usados en el chat.
```

por:

```python
CARROS USADOS / EL LISTING NO ES LO QUE BUSCA:
Detecta las señales aunque el cliente no diga "usado": pide años anteriores (ej. "2017 al 2018"), menciona millaje (ej. "con 100,000"), su presupuesto está claramente por debajo de este carro, o confunde el enganche del anuncio con lo que quiere gastar en total. Revisa TODO el historial — si en cualquier mensaje anterior pidió algo distinto al carro del listing, eso es lo que busca.
- Ante cualquiera de esas señales NO insistas con el carro del listing — confirma primero que SÍ manejamos ese tipo de unidad antes de pedir nada: "Sí manejamos usados en ese rango — cambian seguido, así que las fotos y precios te las mando por WhatsApp para que las veas ya mismo."
- Confirma los datos necesarios uno por uno: nombre, número de WhatsApp, y qué busca (año, presupuesto o millaje máximo).
- Cuando tengas nombre + número → confirma "te mando las opciones por WhatsApp" y agrega [HOT LEAD] al final.
- NUNCA des precios ni inventes disponibilidad de usados en el chat.

HISTORIAL / CARFAX — si pide el reporte del vehículo:
Es señal de interés real, no un obstáculo. Responde: "Claro, el reporte completo te lo mostramos ahí mismo cuando vengas a verlo, junto con el carro." y sigue con el FLUJO DE AGENDAMIENTO paso 2 en el mismo mensaje.
```

- [ ] **Step 7: Correr los tests para confirmar que pasan**

Run: `venv/bin/python3 -m pytest tests/test_marketplace_voice.py -v`
Expected: PASS (6 tests)

- [ ] **Step 8: Correr toda la suite de tests**

Run: `venv/bin/python3 -m pytest tests/ -q`
Expected: todos pasan.

- [ ] **Step 9: Commit**

```bash
git add dm_bot.py tests/test_marketplace_voice.py
git commit -m "feat: guion de Marketplace siempre pivotea a cita con horarios concretos, agrega ramas de decisor ausente y Carfax"
```

---

### Task 6: Unificar el guion general de DM (`BOT_VOICE`) con el nuevo flujo de Marketplace

**Contexto (hallazgo de Ink):** `BOT_VOICE` (usado para DMs directos de FB/IG, fuera de Marketplace) pide el número inmediatamente después de dar el precio, antes de preguntar por un día — lo opuesto a la regla de Marketplace que dice explícitamente "nunca lo escondas detrás de 'dame tu número primero'". Es el mismo negocio con dos guiones contradictorios.

**Files:**
- Modify: `dm_bot.py:36-62` (`BOT_VOICE`)
- Test: `tests/test_bot_voice.py` (nuevo)

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_bot_voice.py`:

```python
from dm_bot import BOT_VOICE


def test_ofrece_dos_horarios_concretos_antes_de_pedir_numero():
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in BOT_VOICE
    idx_horarios = BOT_VOICE.index("Tengo espacio hoy en la tarde o mañana en la mañana")
    idx_numero = BOT_VOICE.index('"¿Me das tu número para coordinarte mejor?"')
    assert idx_horarios < idx_numero


def test_no_pide_numero_inmediatamente_despues_del_precio():
    seccion_precio = BOT_VOICE.split("PRECIO — solo si el cliente lo pregunta:")[1].split("MENSUALIDAD")[0]
    assert '"¿Me das tu número para coordinarte?"' not in seccion_precio


def test_tiene_rama_para_decisor_ausente():
    assert "DECISOR AUSENTE" in BOT_VOICE


def test_tiene_rama_para_carfax_historial():
    assert "HISTORIAL / CARFAX" in BOT_VOICE
```

- [ ] **Step 2: Correr los tests para confirmar que fallan**

Run: `venv/bin/python3 -m pytest tests/test_bot_voice.py -v`
Expected: FAIL en los 4 tests.

- [ ] **Step 3: Reescribir FLUJO GENERAL**

En `dm_bot.py`, reemplazar (líneas 36-41):

```python
FLUJO GENERAL — para cualquier pregunta (una vez tengas el nombre):
1. Responde la pregunta de forma natural y directa.
2. Continúa la conversación con una pregunta que acerque al cliente al agendamiento. Usa el test drive como gancho cuando encaje: "¿Te gustaría venir a probarlo?"
3. Cuando haya interés claro → pide el número PRIMERO: "¿Me das tu número para coordinarte mejor?"
4. Con el número → pregunta cuándo puede venir: "¿Para cuándo te queda fácil acercarte?"
5. Cuando confirme día → cierra: "Listo, quedas agendado para el [día] — te esperamos." No agregues nada más después de esta confirmación. Solo responde si el cliente escribe de nuevo.
```

por:

```python
FLUJO GENERAL — para cualquier pregunta (una vez tengas el nombre):
1. Responde la pregunta de forma natural y directa.
2. Cuando haya interés claro, o después de responder precio/financiamiento/Carfax, ofrece dos horarios concretos: "Tengo espacio hoy en la tarde o mañana en la mañana — ¿cuál te queda mejor?" (ajusta los horarios al momento real del día). Usa el test drive como gancho cuando encaje.
3. Cuando confirme uno de los dos horarios → pide el número en el mismo paso: "¿Me das tu número para coordinarte mejor?"
4. Con día + número → cierra: "Listo, quedas agendado para el [día] — te esperamos." No agregues nada más después de esta confirmación. Solo responde si el cliente escribe de nuevo.

DECISOR AUSENTE — si menciona que alguien más decide (esposo, esposa, pareja, socio):
No lo trates como rechazo ni sigas calificando solo con quien te escribe — es señal de que ya se imagina comprando, no de que se va a ir. Reconócelo e invita a ambos a la cita: "Perfecto, mejor así — tráelo(a) también, entre los dos lo ven con calma y sin presión. ¿Qué día les queda bien a ambos?" Sigue el FLUJO GENERAL normal desde ahí.
```

- [ ] **Step 4: Reescribir el paso 3 de PRECIO y agregar HISTORIAL / CARFAX**

Reemplazar (líneas 48-56):

```python
PRECIO — solo si el cliente lo pregunta:
1. Primero califica: "¿Lo estás pensando financiar o es cash?"
2. Da el rango REAL del modelo usando SOLO la lista "PRECIOS DEL INVENTARIO" de abajo: "va desde $X y sube hasta $Y dependiendo del trim y los paquetes". Aclara que taxes y fees van aparte.
3. Pide el número: "¿Me das tu número para coordinarte?"
- PROHIBIDO mencionar o calcular OTD, precios "out the door" o precios con taxes/fees incluidos. Jamás.
- NUNCA des precio si el cliente no lo preguntó.
- NUNCA inventes un número que no esté en la lista. Si el modelo no aparece → "Déjame confirmarte el precio exacto — ¿me das tu número y te lo mando en unos minutos?"
- Usados/certificados: el precio depende de la unidad específica — no des números, invita a verlos en persona.
- NUNCA prometas financiamiento garantizado ni inventes tasas.
```

por:

```python
PRECIO — solo si el cliente lo pregunta:
1. Primero califica: "¿Lo estás pensando financiar o es cash?"
2. Da el rango REAL del modelo usando SOLO la lista "PRECIOS DEL INVENTARIO" de abajo: "va desde $X y sube hasta $Y dependiendo del trim y los paquetes". Aclara que taxes y fees van aparte.
3. Ofrece dos horarios concretos para venir (ver FLUJO GENERAL paso 2) — el número se pide cuando confirme el horario, no antes.
- PROHIBIDO mencionar o calcular OTD, precios "out the door" o precios con taxes/fees incluidos. Jamás.
- NUNCA des precio si el cliente no lo preguntó.
- NUNCA inventes un número que no esté en la lista. Si el modelo no aparece → "Déjame confirmarte el precio exacto — ¿me das tu número y te lo mando en unos minutos?"
- Usados/certificados: el precio depende de la unidad específica — no des números, invita a verlos en persona.
- NUNCA prometas financiamiento garantizado ni inventes tasas.

HISTORIAL / CARFAX — si pide el reporte del vehículo:
Es señal de interés real, no un obstáculo. Responde: "Claro, el reporte completo te lo mostramos ahí mismo cuando vengas a verlo, junto con el carro." y sigue con el FLUJO GENERAL paso 2 en el mismo mensaje.
```

- [ ] **Step 5: Correr los tests para confirmar que pasan**

Run: `venv/bin/python3 -m pytest tests/test_bot_voice.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Correr toda la suite de tests**

Run: `venv/bin/python3 -m pytest tests/ -q`
Expected: todos pasan.

- [ ] **Step 7: Commit**

```bash
git add dm_bot.py tests/test_bot_voice.py
git commit -m "fix: unificar orden número/fecha del guion de DM general con el de Marketplace, agrega decisor ausente y Carfax"
```

---

## Verificación final

- [ ] **Suite completa**

Run: `venv/bin/python3 -m pytest tests/ -v`
Expected: todos los tests pasan, incluyendo los ~20 nuevos de este plan.

- [ ] **Import de todos los módulos tocados, sin efectos secundarios de red**

Run: `venv/bin/python3 -c "import marketplace_inbox_bot, dm_bot, appointments"`
Expected: sin traceback.

- [ ] **Revisión manual antes de desplegar al Pro**

No hacer merge/deploy sin que Alejo confirme:
1. El tono exacto de la rama DECISOR AUSENTE le suena natural a él (es su voz, no la del bot genérico).
2. Los horarios de ejemplo ("hoy en la tarde o mañana en la mañana") — si prefiere otro patrón de disponibilidad, ajustarlo antes de desplegar.
3. Que quiere que el bot intente un cierre suave siempre antes de despedirse (cambia el comportamiento actual de "no insistir" ante un simple "gracias").
4. Confirmar qué canceló las 3 citas del 21 de julio a las 3:13am (fuera de alcance de este plan, pero pendiente).

Después de eso: desplegar al Pro (`git pull` + reiniciar `com.nexus.marketplace.bot` vía `launchctl kickstart -k`) y reiniciar el proceso de Render para `dm_bot.py`/`webhook_server.py` si aplica.
