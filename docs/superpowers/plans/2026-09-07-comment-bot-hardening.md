# Comment Bot Endurecido — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reactivar la respuesta a comentarios de @tucarroconalejo (FB + IG) con 7 guardas en capas que hacen imposible el loop de auto-respuestas del incidente del 6 sep 2026, respondiendo solo por DM privado + 1 comentario público a comentarios con intención real de compra.

**Architecture:** El webhook normaliza cada evento de comentario de IG/FB a un dict común y lo pasa a `comment_bot.handle_comment`, que aplica en orden: kill switch → identidad → solo top-level → dedupe → rate limit → clasificación de intención → (backstop de Meta). Si pasa todo, manda una respuesta privada (Graph API `private_replies` en FB, `/messages` con `recipient.comment_id` en IG) y un único comentario público fijo, y registra el `comment_id` en `comments_handled.json`.

**Tech Stack:** Python 3.14, Flask (webhook), `anthropic` (Haiku para clasificación y redacción), `requests` (Graph API v19.0), `pytest` + `unittest.mock`. Store en JSON plano (patrón de `leads_activity.json` / `marketplace_posted.json`).

---

## File Structure

| Archivo | Responsabilidad | Acción |
|---|---|---|
| `comment_bot.py` | Toda la lógica de comentarios: guardas, clasificación, redacción, envío, store. | Reescritura completa. |
| `comments_handled.json` | Store persistente `{comment_id: {ts, platform, post_id, intent, actions}}`. | Se crea en runtime (no se commitea; va a `.gitignore`). |
| `webhook_server.py` | Normaliza payloads de `comments`/`feed`/`mention` y llama a `handle_comment`. Nunca deja que una excepción de comentarios rompa el 200. | Modificar import + 3 ramas (líneas ~250-262 en `main`). |
| `tests/test_comment_bot.py` | Tests unitarios de cada guarda + test de regresión del loop + gate de intención + dry run. | Crear. |
| `tests/test_webhook_comments.py` | Tests de la normalización IG/FB y de que una excepción no rompe el webhook. | Crear. |
| `.env` (local) y Render env | `COMMENT_BOT_ENABLED`, `COMMENT_BOT_DRY_RUN`. | Añadir, default `0`. |
| `.gitignore` | Añadir `comments_handled.json`. | Modificar. |
| `docs/superpowers/specs/2026-09-07-comment-bot-hardening-design.md` | Spec aprobado. | Ya existe — se commitea en Task 1. |

### Contrato del `event` dict (usado en todo el plan)

```python
{
    "platform":   "facebook" | "instagram",
    "comment_id": str,   # id del comentario
    "author_id":  str,   # from.id / sender.id — "" si Meta lo omite
    "text":       str,   # texto del comentario
    "post_id":    str,   # id del post/media/anuncio
    "parent_id":  str,   # "" si es comentario top-level; id del padre si es respuesta
}
```

### Esquema de `comments_handled.json`

```json
{
  "<comment_id>": {
    "ts": 1725700000,
    "platform": "instagram",
    "post_id": "<post_id>",
    "intent": "COMPRA",
    "actions": ["private_ig", "public_ig"]
  }
}
```

`actions` vacío = el comentario se evaluó pero no se respondió (intención no accionable). Sirve para dedupe sin volver a llamar a Haiku.

### Constantes (en `comment_bot.py`)

```python
GRAPH            = "https://graph.facebook.com/v19.0"
HANDLED_STORE    = os.path.join(os.path.dirname(__file__), "comments_handled.json")
PUBLIC_ACK       = "¡Te escribimos al DM! 🙌"
INTENT_ACTIONABLE = {"COMPRA", "PRECIO", "CREDITO"}
MAX_PER_HOUR_GLOBAL = 5
MAX_PER_HOUR_POST   = 3
PRIVATE_REPLY_WINDOW_DAYS = 7   # límite de Meta, informativo
```

---

## Task 1: Rama, spec commit, flags de entorno

**Files:**
- Modify: `.gitignore`
- Modify: `.env` (local, no se commitea)
- Commit: `docs/superpowers/specs/2026-09-07-comment-bot-hardening-design.md`

- [ ] **Step 1: Reconciliar la rama de trabajo**

El working tree puede estar en `feature/admin-marketplace-panel`, que **no** tiene los commits `19bd18a` (comment bot desactivado) ni `a056c95` (fix auto-respuesta DMs). Todo este trabajo sale de `main`.

```bash
cd /Users/macbookpro/nexus-automation
git stash push -u -m "wip antes de comment-bot-hardening"   # si hay cambios sin commitear
git checkout main
git pull origin main
git checkout -b feature/comment-bot-hardening
git log --oneline -1   # debe mostrar 19bd18a o posterior
```

Expected: `git log` muestra `19bd18a fix(webhook): desactiva comment bot` como HEAD (o un commit que lo incluya).

> Nota para Alejo: el rebase de `feature/admin-marketplace-panel` sobre `main` es un tema aparte y manual (tiene WIP de 5 archivos). No bloquea este plan, pero esa rama **no debe mergearse a `main`** hasta rebasarla, o reintroduce el loop.

- [ ] **Step 2: Añadir el store al `.gitignore`**

Abrir `.gitignore` y añadir al final:

```
comments_handled.json
```

- [ ] **Step 3: Añadir flags a `.env` local**

Añadir a `/Users/macbookpro/nexus-automation/.env`:

```
COMMENT_BOT_ENABLED=0
COMMENT_BOT_DRY_RUN=0
```

- [ ] **Step 4: Commit del spec y del gitignore**

```bash
git add docs/superpowers/specs/2026-09-07-comment-bot-hardening-design.md .gitignore
git commit -m "docs: spec comment bot endurecido + ignora comments_handled.json

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Expected: commit creado en `feature/comment-bot-hardening`.

---

## Task 2: Store `comments_handled.json` (load / save)

**Files:**
- Modify: `comment_bot.py` (reescritura — empezar por el encabezado + helpers de store)
- Test: `tests/test_comment_bot.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_comment_bot.py`:

```python
import json
import time
from unittest.mock import patch, mock_open, MagicMock

import comment_bot


# ── Store: comments_handled.json ──────────────────────────────────────────────

def test_load_handled_store_inexistente_devuelve_dict_vacio():
    with patch("os.path.exists", return_value=False):
        assert comment_bot._load_handled() == {}


def test_load_handled_store_corrupto_devuelve_dict_vacio():
    # Un JSON roto no debe crashear el webhook — se ignora y se sigue.
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data="{ roto")):
            assert comment_bot._load_handled() == {}


def test_save_y_load_roundtrip(tmp_path):
    store_file = tmp_path / "comments_handled.json"
    with patch.object(comment_bot, "HANDLED_STORE", str(store_file)):
        comment_bot._save_handled({"c1": {"ts": 123, "actions": []}})
        assert comment_bot._load_handled() == {"c1": {"ts": 123, "actions": []}}
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v`
Expected: FAIL — `AttributeError: module 'comment_bot' has no attribute '_load_handled'`

- [ ] **Step 3: Reescribir el encabezado de `comment_bot.py` con los helpers de store**

Reemplazar **todo** el contenido actual de `comment_bot.py` (se reconstruye por partes en las tareas siguientes) por:

```python
"""
Comment Bot — responde comentarios en posts y anuncios de @tucarroconalejo.
Cubre Facebook (feed) e Instagram (comments).

7 guardas en capas antes de responder (ver docs/superpowers/specs/2026-09-07-*):
  1. kill switch  2. identidad  3. solo top-level  4. dedupe
  5. rate limit   6. intención  7. backstop de Meta (1 private reply / comentario)

Incidente que motivó esto: 6 sep 2026, ~950 comentarios en loop porque no había
guarda de identidad y el bot se respondía a sí mismo.
"""
import json
import os
import time

import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

client            = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID           = os.getenv("META_PAGE_ID", "")
IG_USER_ID        = os.getenv("META_IG_USER_ID", "")
_OWN_IDS          = {i for i in (PAGE_ID, IG_USER_ID) if i}

GRAPH             = "https://graph.facebook.com/v19.0"
HANDLED_STORE     = os.path.join(os.path.dirname(__file__), "comments_handled.json")
PUBLIC_ACK        = "¡Te escribimos al DM! 🙌"
INTENT_ACTIONABLE = {"COMPRA", "PRECIO", "CREDITO"}
MAX_PER_HOUR_GLOBAL = 5
MAX_PER_HOUR_POST   = 3
PRIVATE_REPLY_WINDOW_DAYS = 7


def _enabled() -> bool:
    return os.getenv("COMMENT_BOT_ENABLED", "0") == "1"


def _dry_run() -> bool:
    return os.getenv("COMMENT_BOT_DRY_RUN", "0") == "1"


# ── Store ────────────────────────────────────────────────────────────────────

def _load_handled() -> dict:
    if not os.path.exists(HANDLED_STORE):
        return {}
    try:
        with open(HANDLED_STORE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_handled(store: dict) -> None:
    with open(HANDLED_STORE, "w") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add comment_bot.py tests/test_comment_bot.py
git commit -m "feat(comment-bot): helpers de store comments_handled.json

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2b: `.env.example` / documentación de flags

**Files:**
- Modify: `comment_bot.py` (docstring de módulo ya cubre; no cambia código)
- Modify: `CLAUDE.md` (sección de variables de entorno, si existe)

- [ ] **Step 1: Verificar si `CLAUDE.md` documenta env vars**

Run: `grep -n "COMMENT_BOT\|META_PAGE_ACCESS_TOKEN\|ENABLED" CLAUDE.md`
Expected: si aparece una lista de variables de entorno, añadir dos líneas:

```
COMMENT_BOT_ENABLED=0    # 1 = el bot responde comentarios. Default apagado.
COMMENT_BOT_DRY_RUN=0    # 1 = corre guardas + clasificación pero NO postea nada.
```

Si `CLAUDE.md` no tiene esa sección, saltar este paso (el docstring del módulo lo cubre).

- [ ] **Step 2: Commit (si hubo cambio)**

```bash
git add CLAUDE.md
git commit -m "docs: documenta COMMENT_BOT_ENABLED / COMMENT_BOT_DRY_RUN

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Guardas puras — `is_own_author`, `is_reply`, `already_handled`

**Files:**
- Modify: `comment_bot.py`
- Test: `tests/test_comment_bot.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_comment_bot.py`:

```python
# ── Guarda 2: identidad ──────────────────────────────────────────────────────

def test_is_own_author_page_id():
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123", "IG456"}):
        assert comment_bot.is_own_author("PAGE123") is True


def test_is_own_author_ig_id():
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123", "IG456"}):
        assert comment_bot.is_own_author("IG456") is True


def test_is_own_author_tercero():
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123", "IG456"}):
        assert comment_bot.is_own_author("cliente789") is False


def test_is_own_author_vacio_es_falso():
    # author_id "" (Meta lo omitió) no debe contar como propio.
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123"}):
        assert comment_bot.is_own_author("") is False


# ── Guarda 3: solo top-level ─────────────────────────────────────────────────

def test_is_reply_con_parent_id():
    ev = {"comment_id": "c2", "parent_id": "c1", "post_id": "p1"}
    assert comment_bot.is_reply(ev) is True


def test_is_reply_sin_parent_id():
    ev = {"comment_id": "c1", "parent_id": "", "post_id": "p1"}
    assert comment_bot.is_reply(ev) is False


def test_is_reply_parent_igual_al_post_no_es_reply():
    # Algunos payloads de FB ponen parent_id == post_id para comentarios top-level.
    ev = {"comment_id": "c1", "parent_id": "p1", "post_id": "p1"}
    assert comment_bot.is_reply(ev) is False


# ── Guarda 4: dedupe ────────────────────────────────────────────────────────

def test_already_handled_true():
    with patch.object(comment_bot, "_load_handled", return_value={"c1": {"ts": 1}}):
        assert comment_bot.already_handled("c1") is True


def test_already_handled_false():
    with patch.object(comment_bot, "_load_handled", return_value={}):
        assert comment_bot.already_handled("c1") is False
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k "own_author or is_reply or already_handled"`
Expected: FAIL — `AttributeError: module 'comment_bot' has no attribute 'is_own_author'`

- [ ] **Step 3: Implementar las guardas puras**

Añadir a `comment_bot.py` después de `_save_handled`:

```python
# ── Guardas puras ────────────────────────────────────────────────────────────

def is_own_author(author_id: str) -> bool:
    """Guarda 2. True si el comentario lo escribió nuestra propia página / cuenta IG."""
    return bool(author_id) and author_id in _OWN_IDS


def is_reply(event: dict) -> bool:
    """Guarda 3. True si el comentario es respuesta a otro comentario (no top-level)."""
    parent = event.get("parent_id") or ""
    post = event.get("post_id") or ""
    return bool(parent) and parent != post


def already_handled(comment_id: str) -> bool:
    """Guarda 4. True si ya evaluamos este comment_id antes."""
    return comment_id in _load_handled()
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k "own_author or is_reply or already_handled"`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add comment_bot.py tests/test_comment_bot.py
git commit -m "feat(comment-bot): guardas identidad / top-level / dedupe

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Guarda 5 — rate limit

**Files:**
- Modify: `comment_bot.py`
- Test: `tests/test_comment_bot.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_comment_bot.py`:

```python
# ── Guarda 5: rate limit ────────────────────────────────────────────────────

def _store_con_respuestas(n_global, post_id="pX", n_post=0, edad_seg=60):
    """Genera un store con n_global respuestas recientes (actions no vacío),
    de las cuales n_post son en post_id."""
    now = time.time()
    store = {}
    for i in range(n_global):
        store[f"g{i}"] = {"ts": now - edad_seg, "post_id": "otro",
                          "actions": ["private_ig"]}
    for i in range(n_post):
        store[f"p{i}"] = {"ts": now - edad_seg, "post_id": post_id,
                          "actions": ["private_ig"]}
    return store


def test_rate_limit_global_alcanzado():
    store = _store_con_respuestas(5)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is True


def test_rate_limit_global_no_alcanzado():
    store = _store_con_respuestas(4)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is False


def test_rate_limit_por_post_alcanzado():
    store = _store_con_respuestas(0, post_id="pX", n_post=3)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is True


def test_rate_limit_ignora_respuestas_viejas():
    # Respuestas de hace más de 1 hora no cuentan.
    store = _store_con_respuestas(10, edad_seg=3700)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is False


def test_rate_limit_ignora_entradas_sin_accion():
    # Comentarios evaluados pero no respondidos (actions vacío) no cuentan.
    now = time.time()
    store = {f"s{i}": {"ts": now - 60, "post_id": "pX", "actions": []}
             for i in range(10)}
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is False
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k rate_limit`
Expected: FAIL — `AttributeError: ... 'rate_limited'`

- [ ] **Step 3: Implementar `rate_limited`**

Añadir a `comment_bot.py` después de `already_handled`:

```python
def rate_limited(post_id: str) -> bool:
    """Guarda 5. True si ya se respondió >= MAX_PER_HOUR_GLOBAL en la última hora,
    o >= MAX_PER_HOUR_POST en este post en la última hora. Solo cuenta entradas
    con una respuesta real enviada (actions no vacío)."""
    cutoff = time.time() - 3600
    store = _load_handled()
    recientes = [
        r for r in store.values()
        if r.get("ts", 0) >= cutoff and r.get("actions")
    ]
    if len(recientes) >= MAX_PER_HOUR_GLOBAL:
        return True
    en_post = [r for r in recientes if r.get("post_id") == post_id]
    return len(en_post) >= MAX_PER_HOUR_POST
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k rate_limit`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add comment_bot.py tests/test_comment_bot.py
git commit -m "feat(comment-bot): guarda de rate limit (5/h global, 3/h por post)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Guarda 6 — clasificación de intención (Haiku)

**Files:**
- Modify: `comment_bot.py`
- Test: `tests/test_comment_bot.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_comment_bot.py`:

```python
# ── Guarda 6: intención ─────────────────────────────────────────────────────

def _mock_anthropic_text(texto):
    resp = MagicMock()
    resp.content = [MagicMock(text=texto)]
    return resp


def test_classify_intent_normaliza_a_mayusculas_y_recorta():
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("  compra\n")):
        assert comment_bot.classify_intent("quiero un corolla") == "COMPRA"


def test_classify_intent_valor_desconocido_cae_a_otro():
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("no sé qué es")):
        assert comment_bot.classify_intent("hola") == "OTRO"


def test_classify_intent_error_de_api_devuelve_error():
    # Falla cerrado: si Haiku falla, la clasificación devuelve "ERROR" y el
    # orquestador NO responde.
    with patch.object(comment_bot.client.messages, "create",
                      side_effect=RuntimeError("timeout")):
        assert comment_bot.classify_intent("hola") == "ERROR"
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k classify_intent`
Expected: FAIL — `AttributeError: ... 'classify_intent'`

- [ ] **Step 3: Implementar `classify_intent`**

Añadir a `comment_bot.py`:

```python
_INTENT_LABELS = {"COMPRA", "PRECIO", "CREDITO", "POSITIVO", "NEGATIVO", "SPAM", "OTRO"}

_CLASSIFY_SYSTEM = """Clasifica el comentario de una publicación de un concesionario Toyota.
Responde con UNA sola palabra, exactamente una de estas:

COMPRA   - quiere comprar / cambiar de carro / pregunta disponibilidad de un modelo
PRECIO   - pregunta precio, cuota mensual, enganche
CREDITO  - pregunta por financiamiento, aprobación, mal crédito, sin seguro social
POSITIVO - felicitación, agradecimiento, emoji suelto, "bonito carro"
NEGATIVO - queja, reclamo, insulto, "puras mentiras", troll
SPAM     - publicidad ajena, links, nada que ver
OTRO     - cualquier otra cosa

Solo la palabra. Sin explicación, sin puntuación."""


def classify_intent(text: str) -> str:
    """Guarda 6. Devuelve una etiqueta de _INTENT_LABELS, o "ERROR" si Haiku falla."""
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": text[:500]}],
        )
        label = resp.content[0].text.strip().upper()
        first = label.split()[0].strip(".,!") if label else "OTRO"
        return first if first in _INTENT_LABELS else "OTRO"
    except Exception as e:
        print(f"[COMMENT] classify_intent falló: {e}")
        return "ERROR"
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k classify_intent`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add comment_bot.py tests/test_comment_bot.py
git commit -m "feat(comment-bot): clasificación de intención con Haiku (falla cerrado)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Redacción de la respuesta privada + `COMMENT_VOICE` + red de seguridad del teléfono

> El número correcto de Alejo es **(954) 910-6671** y `comment_bot.py` YA lo tiene bien.
> No hay nada que "arreglar" en el texto. Lo que se añade es el mismo guard que ya
> tiene `dm_bot.py` (`text.replace("310-6671", "910-6671")`) porque Haiku a veces
> alucina el `310` pese a la regla del prompt.

**Files:**
- Modify: `comment_bot.py`
- Test: `tests/test_comment_bot.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_comment_bot.py`:

```python
# ── Redacción ───────────────────────────────────────────────────────────────

def test_comment_voice_tiene_el_telefono_correcto():
    # El número correcto de Alejo es (954) 910-6671 (ver .env ALEJO_PHONE,
    # nexus_agency.py). El 310 es una alucinación recurrente de Claude.
    assert "(954) 910-6671" in comment_bot.COMMENT_VOICE
    assert "310-6671" not in comment_bot.COMMENT_VOICE


def test_comment_voice_prohibe_precios():
    v = comment_bot.COMMENT_VOICE.lower()
    assert "nunca" in v and ("precio" in v or "mensualidad" in v or "tasa" in v)


def test_generate_private_reply_usa_haiku_y_recorta():
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("  ¡Claro! Te escribo por DM 🙌\n")):
        out = comment_bot.generate_private_reply("quiero un corolla", "COMPRA")
    assert out == "¡Claro! Te escribo por DM 🙌"


def test_generate_private_reply_corrige_telefono_alucinado():
    # Mismo guard que dm_bot.py:222 — si Haiku pone 310-6671, se corrige a 910-6671.
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("Llama al (954) 310-6671 🙌")):
        out = comment_bot.generate_private_reply("hola", "COMPRA")
    assert "310-6671" not in out
    assert "910-6671" in out


def test_generate_private_reply_fallo_usa_texto_de_respaldo():
    with patch.object(comment_bot.client.messages, "create",
                      side_effect=RuntimeError("boom")):
        out = comment_bot.generate_private_reply("hola", "COMPRA")
    assert "DM" in out or "954" in out   # respaldo fijo, nunca vacío
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k "comment_voice or private_reply"`
Expected: FAIL (`AttributeError` en `generate_private_reply`; `COMMENT_VOICE` aún tiene 910)

- [ ] **Step 3: Añadir `COMMENT_VOICE` corregido y `generate_private_reply`**

Añadir a `comment_bot.py` (después de las constantes, antes de las guardas):

```python
COMMENT_VOICE = """Eres el asistente de Alejo, asesor de ventas en Hollywood Toyota, Florida.
Escribes un mensaje PRIVADO a alguien que comentó en una publicación o anuncio.

TONO:
- Cálido, breve, de persona real — máximo 2 oraciones
- Español natural de Florida/USA
- Nada de sonar a folleto ni a bot corporativo

REGLAS ABSOLUTAS:
- NUNCA des precios, mensualidades ni tasas específicas
- NUNCA prometas crédito garantizado
- El teléfono de Alejo es SIEMPRE (954) 910-6671 — nunca otro número
- El objetivo es que siga la conversación por aquí (DM) o llame al (954) 910-6671

Responde SOLO con el texto del mensaje. Sin comillas, sin explicaciones."""

_PRIVATE_FALLBACK = {
    "COMPRA":  "¡Hola! Con gusto te ayudo con eso — cuéntame qué modelo buscas y lo vemos. También puedes llamar a Alejo al (954) 910-6671 🙌",
    "PRECIO":  "¡Hola! Los mejores números te los da Alejo directo. Escríbeme por aquí o llama al (954) 910-6671 y lo revisamos 👇",
    "CREDITO": "¡Hola! Trabajamos con varias opciones de financiamiento. Cuéntame tu caso por aquí o llama al (954) 910-6671 y te orientamos 💪",
}


def generate_private_reply(text: str, intent: str) -> str:
    """Redacta el DM privado. Si Haiku falla, usa un texto de respaldo fijo."""
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            system=COMMENT_VOICE,
            messages=[{"role": "user", "content": f"Comentario del cliente: \"{text[:400]}\""}],
        )
        out = resp.content[0].text.strip()
        # Red de seguridad: Claude a veces alucina 310-6671 (igual que en dm_bot.py).
        out = out.replace("310-6671", "910-6671")
        if out:
            return out
    except Exception as e:
        print(f"[COMMENT] generate_private_reply falló: {e}")
    return _PRIVATE_FALLBACK.get(intent, _PRIVATE_FALLBACK["COMPRA"])
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k "comment_voice or private_reply"`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add comment_bot.py tests/test_comment_bot.py
git commit -m "feat(comment-bot): redacción de DM privado + guard anti-alucinación del teléfono

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Envío — respuesta privada y comentario público (FB + IG)

**Files:**
- Modify: `comment_bot.py`
- Test: `tests/test_comment_bot.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_comment_bot.py`:

```python
# ── Envío (Graph API) ───────────────────────────────────────────────────────

def _mock_post_ok():
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"id": "reply_1"}
    return r


def test_send_private_reply_fb_llama_endpoint_private_replies():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        ok = comment_bot.send_private_reply("facebook", "c1", "hola")
    assert ok is True
    url = mp.call_args[0][0]
    assert url.endswith("/c1/private_replies")


def test_send_private_reply_ig_usa_messages_con_comment_id():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        with patch.object(comment_bot, "IG_USER_ID", "IG456"):
            ok = comment_bot.send_private_reply("instagram", "c1", "hola")
    assert ok is True
    url = mp.call_args[0][0]
    assert url.endswith("/IG456/messages")
    body = mp.call_args[1]["json"]
    assert body["recipient"] == {"comment_id": "c1"}
    assert body["message"] == {"text": "hola"}


def test_send_private_reply_ya_respondido_cuenta_como_exito():
    # Meta: (#10900) ya se envió una private reply para este comentario.
    r = MagicMock()
    r.status_code = 400
    r.json.return_value = {"error": {"code": 10900, "message": "already replied"}}
    with patch("comment_bot.requests.post", return_value=r):
        assert comment_bot.send_private_reply("facebook", "c1", "hola") is True


def test_send_private_reply_error_de_red_devuelve_false():
    with patch("comment_bot.requests.post", side_effect=comment_bot.requests.exceptions.Timeout()):
        assert comment_bot.send_private_reply("facebook", "c1", "hola") is False


def test_send_public_ack_fb():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        ok = comment_bot.send_public_ack("facebook", "c1")
    assert ok is True
    assert mp.call_args[0][0].endswith("/c1/comments")
    assert mp.call_args[1]["json"]["message"] == comment_bot.PUBLIC_ACK


def test_send_public_ack_ig_usa_replies():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        ok = comment_bot.send_public_ack("instagram", "c1")
    assert ok is True
    assert mp.call_args[0][0].endswith("/c1/replies")
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k "send_private or send_public"`
Expected: FAIL — `AttributeError: ... 'send_private_reply'`

- [ ] **Step 3: Implementar los senders**

Añadir a `comment_bot.py`:

```python
# ── Envío ───────────────────────────────────────────────────────────────────

_ALREADY_REPLIED_CODES = {10900, 100}  # Meta: private reply duplicada / ya no aplica


def _post_graph(url: str, *, params=None, json_body=None) -> tuple[bool, dict]:
    """POST a Graph API. Devuelve (ok, payload). ok=True si 2xx o si Meta dice
    que ya se respondió a ese comentario."""
    try:
        r = requests.post(url, params=params or {}, json=json_body, timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"[COMMENT] red falló en {url}: {e}")
        return False, {}
    try:
        payload = r.json()
    except ValueError:
        payload = {}
    if r.status_code == 200 and payload.get("id"):
        return True, payload
    code = (payload.get("error") or {}).get("code")
    if code in _ALREADY_REPLIED_CODES:
        print(f"[COMMENT] Meta: comentario ya atendido (code {code}) — se cuenta como hecho")
        return True, payload
    print(f"[COMMENT] Graph API error {r.status_code}: {payload}")
    return False, payload


def send_private_reply(platform: str, comment_id: str, message: str) -> bool:
    if platform == "instagram":
        ok, _ = _post_graph(
            f"{GRAPH}/{IG_USER_ID}/messages",
            params={"access_token": PAGE_ACCESS_TOKEN},
            json_body={"recipient": {"comment_id": comment_id},
                       "message": {"text": message}},
        )
        return ok
    ok, _ = _post_graph(
        f"{GRAPH}/{comment_id}/private_replies",
        params={"access_token": PAGE_ACCESS_TOKEN, "message": message},
    )
    return ok


def send_public_ack(platform: str, comment_id: str) -> bool:
    edge = "replies" if platform == "instagram" else "comments"
    ok, _ = _post_graph(
        f"{GRAPH}/{comment_id}/{edge}",
        params={"access_token": PAGE_ACCESS_TOKEN},
        json_body={"message": PUBLIC_ACK},
    )
    return ok
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k "send_private or send_public"`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add comment_bot.py tests/test_comment_bot.py
git commit -m "feat(comment-bot): senders private reply + comentario público (FB/IG)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: Orquestador `handle_comment` (incluye test de regresión del loop)

**Files:**
- Modify: `comment_bot.py`
- Test: `tests/test_comment_bot.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_comment_bot.py`:

```python
# ── Orquestador handle_comment ──────────────────────────────────────────────

def _event(**over):
    ev = {"platform": "instagram", "comment_id": "c1", "author_id": "cliente789",
          "text": "quiero un corolla", "post_id": "p1", "parent_id": ""}
    ev.update(over)
    return ev


@patch("comment_bot.requests.post")
def test_handle_comment_kill_switch_apagado(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "0")
    assert comment_bot.handle_comment(_event()) == "skipped:disabled"
    mp.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_ignora_comentario_propio_LOOP_REGRESSION(mp, monkeypatch):
    # REGRESIÓN DEL INCIDENTE 6 sep 2026: un comentario cuyo autor es nuestra
    # propia cuenta IG NUNCA debe procesarse. Sin esto el bot se responde a sí
    # mismo y entra en loop (fueron ~950 comentarios).
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_OWN_IDS", {"IG456"}):
        res = comment_bot.handle_comment(_event(author_id="IG456"))
    assert res == "skipped:identity"
    mp.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_ignora_respuesta_anidada(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    res = comment_bot.handle_comment(_event(parent_id="c0"))
    assert res == "skipped:reply"
    mp.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_dedupe(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", return_value={"c1": {"ts": 1}}):
        res = comment_bot.handle_comment(_event())
    assert res == "skipped:dedupe"
    mp.assert_not_called()


@patch("comment_bot.pulse_notify")
@patch("comment_bot.requests.post")
def test_handle_comment_rate_limit_avisa_a_pulse(mp, mpulse, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=True):
        res = comment_bot.handle_comment(_event())
    assert res == "skipped:ratelimit"
    mp.assert_not_called()
    mpulse.assert_called_once()


@patch("comment_bot.requests.post")
def test_handle_comment_felicitacion_no_responde_pero_se_registra(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    saved = {}
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="POSITIVO"), \
         patch.object(comment_bot, "_save_handled", side_effect=lambda s: saved.update(s)):
        res = comment_bot.handle_comment(_event(text="bonito carro!"))
    assert res == "skipped:intent"
    mp.assert_not_called()
    assert saved["c1"]["actions"] == []


@patch("comment_bot.requests.post")
def test_handle_comment_error_de_clasificacion_no_responde(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="ERROR"):
        res = comment_bot.handle_comment(_event())
    assert res == "skipped:classify_error"
    mp.assert_not_called()


def test_handle_comment_intencion_compra_responde_privado_y_publico(monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    saved = {}
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="COMPRA"), \
         patch.object(comment_bot, "generate_private_reply", return_value="Te escribo 🙌"), \
         patch.object(comment_bot, "send_private_reply", return_value=True) as sp, \
         patch.object(comment_bot, "send_public_ack", return_value=True) as pa, \
         patch.object(comment_bot, "_save_handled", side_effect=lambda s: saved.update(s)):
        res = comment_bot.handle_comment(_event())
    assert res == "replied"
    sp.assert_called_once_with("instagram", "c1", "Te escribo 🙌")
    pa.assert_called_once_with("instagram", "c1")
    assert saved["c1"]["intent"] == "COMPRA"
    assert saved["c1"]["actions"] == ["private_instagram", "public_instagram"]


def test_handle_comment_dry_run_no_postea(monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    monkeypatch.setenv("COMMENT_BOT_DRY_RUN", "1")
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="COMPRA"), \
         patch.object(comment_bot, "send_private_reply") as sp, \
         patch.object(comment_bot, "send_public_ack") as pa, \
         patch.object(comment_bot, "_save_handled") as sv:
        res = comment_bot.handle_comment(_event())
    assert res == "dryrun:would_reply:COMPRA"
    sp.assert_not_called()
    pa.assert_not_called()
    sv.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_nunca_lanza_excepcion(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", side_effect=RuntimeError("disco lleno")):
        res = comment_bot.handle_comment(_event())
    assert res.startswith("error:")
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v -k handle_comment`
Expected: FAIL — `AttributeError: ... 'handle_comment'` / `'pulse_notify'`

- [ ] **Step 3: Implementar `handle_comment`**

Añadir a `comment_bot.py` el import de pulse (arriba, junto a los otros imports):

```python
from pulse import pulse_notify
```

Y al final del archivo:

```python
# ── Orquestador ─────────────────────────────────────────────────────────────

def handle_comment(event: dict) -> str:
    """Punto de entrada único. Aplica las 7 guardas y responde si corresponde.
    NUNCA lanza excepción — devuelve un código de resultado para logging/tests."""
    try:
        return _handle_comment_inner(event)
    except Exception as e:
        print(f"[COMMENT] handle_comment error: {type(e).__name__}: {e}")
        return f"error:{type(e).__name__}"


def _handle_comment_inner(event: dict) -> str:
    cid      = event.get("comment_id", "")
    platform = event.get("platform", "")
    post_id  = event.get("post_id", "")
    text     = event.get("text", "") or ""

    # 1. kill switch
    if not _enabled():
        return "skipped:disabled"
    # 2. identidad
    if is_own_author(event.get("author_id", "")):
        print(f"[COMMENT] {cid}: autor propio — ignorado (guarda anti-loop)")
        return "skipped:identity"
    # 3. solo top-level
    if is_reply(event):
        return "skipped:reply"
    # 4. dedupe
    if not cid or already_handled(cid):
        return "skipped:dedupe"
    # 5. rate limit
    if rate_limited(post_id):
        pulse_notify("MARKETPLACE_ERROR",
                     f"Comment bot en rate limit — comentario {cid} en post {post_id} sin responder.")
        return "skipped:ratelimit"
    # 6. intención
    intent = classify_intent(text)
    if intent == "ERROR":
        return "skipped:classify_error"
    if intent not in INTENT_ACTIONABLE:
        _record(cid, platform, post_id, intent, actions=[])
        return "skipped:intent"

    # dry run: hasta acá corre todo, pero no postea ni registra
    if _dry_run():
        print(f"[COMMENT] DRY RUN — respondería a {cid} ({intent}): {text[:60]}")
        return f"dryrun:would_reply:{intent}"

    # responder
    reply = generate_private_reply(text, intent)
    actions = []
    if send_private_reply(platform, cid, reply):
        actions.append(f"private_{platform}")
    if send_public_ack(platform, cid):
        actions.append(f"public_{platform}")
    _record(cid, platform, post_id, intent, actions)
    print(f"[COMMENT] {cid} ({intent}) → {actions}")
    return "replied"


def _record(cid: str, platform: str, post_id: str, intent: str, actions: list) -> None:
    store = _load_handled()
    store[cid] = {"ts": time.time(), "platform": platform,
                  "post_id": post_id, "intent": intent, "actions": actions}
    _save_handled(store)
```

- [ ] **Step 4: Correr para verificar que pasan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_comment_bot.py -v`
Expected: PASS (todo el archivo, ~40 tests)

- [ ] **Step 5: Borrar las funciones muertas del `comment_bot.py` viejo**

Verificar que ya no queda nada de la API vieja:

```bash
grep -n "handle_facebook_comment\|handle_instagram_comment\|generate_comment_reply\|reply_to_facebook_comment\|reply_to_instagram_comment" comment_bot.py
```

Expected: sin resultados. Si aparece alguno, borrar esas funciones (ya no se usan; el webhook pasa a `handle_comment` en la Task 9).

- [ ] **Step 6: Commit**

```bash
git add comment_bot.py tests/test_comment_bot.py
git commit -m "feat(comment-bot): orquestador handle_comment con 7 guardas + regresión del loop

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: Conectar `webhook_server.py`

**Files:**
- Modify: `webhook_server.py` (import línea ~14; ramas `comments`/`feed`/`mention` líneas ~250-262 en `main`)
- Test: `tests/test_webhook_comments.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_webhook_comments.py`:

```python
from unittest.mock import patch
import webhook_server


def test_normaliza_evento_ig_comments():
    value = {
        "id": "IGC1",
        "from": {"id": "cliente789", "username": "juan"},
        "text": "quiero un corolla",
        "media": {"id": "MEDIA1"},
    }
    ev = webhook_server._comment_event("instagram", "comments", value)
    assert ev == {
        "platform": "instagram", "comment_id": "IGC1", "author_id": "cliente789",
        "text": "quiero un corolla", "post_id": "MEDIA1", "parent_id": "",
    }


def test_normaliza_evento_ig_comments_con_parent():
    value = {"id": "IGC2", "from": {"id": "x"}, "text": "hola",
             "media": {"id": "M1"}, "parent_id": "IGC1"}
    ev = webhook_server._comment_event("instagram", "comments", value)
    assert ev["parent_id"] == "IGC1"


def test_normaliza_evento_fb_feed():
    value = {"item": "comment", "verb": "add", "comment_id": "FBC1",
             "post_id": "POST1", "from": {"id": "PAGE?", "name": "Ana"},
             "message": "precio?"}
    ev = webhook_server._comment_event("facebook", "feed", value)
    assert ev == {
        "platform": "facebook", "comment_id": "FBC1", "author_id": "PAGE?",
        "text": "precio?", "post_id": "POST1", "parent_id": "",
    }


def test_normaliza_evento_fb_feed_ignora_no_comment():
    value = {"item": "reaction", "verb": "add"}
    assert webhook_server._comment_event("facebook", "feed", value) is None


def test_normaliza_evento_fb_mention_usa_sender():
    value = {"comment_id": "FBC9", "post_id": "POST9",
             "sender": {"id": "tercero", "name": "Luis"}, "message": "@pagina info"}
    ev = webhook_server._comment_event("facebook", "mention", value)
    assert ev["author_id"] == "tercero"
    assert ev["comment_id"] == "FBC9"


def test_webhook_no_rompe_si_handle_comment_explota():
    payload = {"object": "instagram", "entry": [{"changes": [
        {"field": "comments", "value": {"id": "C1", "from": {"id": "x"},
         "text": "hola", "media": {"id": "M1"}}}]}]}
    with webhook_server.app.test_client() as c:
        with patch("webhook_server.handle_comment", side_effect=RuntimeError("boom")):
            r = c.post("/webhook", json=payload)
    assert r.status_code == 200
```

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_webhook_comments.py -v`
Expected: FAIL — `AttributeError: module 'webhook_server' has no attribute '_comment_event'`

- [ ] **Step 3: Cambiar el import en `webhook_server.py`**

Línea ~14, reemplazar:

```python
from comment_bot import handle_facebook_comment, handle_instagram_comment
```

por:

```python
from comment_bot import handle_comment
```

- [ ] **Step 4: Añadir el normalizador `_comment_event`**

Añadir cerca de los otros helpers de `webhook_server.py` (p. ej. después de `_postback_referral`):

```python
def _comment_event(platform: str, field: str, value: dict) -> dict | None:
    """Normaliza un payload de comentario (IG 'comments' / FB 'feed' / FB 'mention')
    al contrato común que consume comment_bot.handle_comment. Devuelve None si el
    evento no es un comentario nuevo."""
    if field == "comments":  # Instagram
        return {
            "platform": "instagram",
            "comment_id": value.get("id", ""),
            "author_id": (value.get("from") or {}).get("id", ""),
            "text": value.get("text", "") or "",
            "post_id": (value.get("media") or {}).get("id", ""),
            "parent_id": value.get("parent_id", "") or "",
        }
    if field == "feed":  # Facebook
        if value.get("item") != "comment" or value.get("verb") != "add":
            return None
        return {
            "platform": "facebook",
            "comment_id": value.get("comment_id", ""),
            "author_id": (value.get("from") or {}).get("id", ""),
            "text": value.get("message", "") or "",
            "post_id": value.get("post_id", ""),
            "parent_id": value.get("parent_id", "") or "",
        }
    if field == "mention":  # Facebook — etiquetan a la página en un comentario
        return {
            "platform": "facebook",
            "comment_id": value.get("comment_id", ""),
            "author_id": (value.get("sender") or {}).get("id", ""),
            "text": value.get("message", "") or "",
            "post_id": value.get("post_id", ""),
            "parent_id": value.get("parent_id", "") or "",
        }
    return None
```

- [ ] **Step 5: Reemplazar las 3 ramas desactivadas**

En `webhook_server.py`, reemplazar el bloque (en `main` son las líneas ~248-262, los tres `elif field == ...` con `print("... DESACTIVADO ...")`) por:

```python
            # Comentarios: IG 'comments', FB 'feed', FB 'mention'.
            # Todo pasa por comment_bot.handle_comment, que aplica las 7 guardas
            # (kill switch, identidad, top-level, dedupe, rate limit, intención).
            # Una excepción aquí NUNCA debe romper el 200 del webhook.
            elif field in ("comments", "feed", "mention"):
                try:
                    platform = "instagram" if field == "comments" else "facebook"
                    ev = _comment_event(platform, field, value)
                    if ev and ev["comment_id"]:
                        result = handle_comment(ev)
                        print(f"[COMMENT] {field} {ev['comment_id']}: {result}")
                except Exception as e:
                    print(f"[COMMENT] error procesando {field}: {type(e).__name__}: {e}")
```

- [ ] **Step 6: Correr para verificar que pasan**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest tests/test_webhook_comments.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Correr toda la suite**

Run: `cd /Users/macbookpro/nexus-automation && venv/bin/python3 -m pytest -q`
Expected: PASS. Si algún test viejo importaba `handle_facebook_comment` / `handle_instagram_comment`, actualizarlo o borrarlo (buscar con `grep -rn "handle_facebook_comment\|handle_instagram_comment" tests/`).

- [ ] **Step 8: Commit**

```bash
git add webhook_server.py tests/test_webhook_comments.py
git commit -m "feat(webhook): reactiva comentarios vía comment_bot.handle_comment (7 guardas)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 10: Verificación local + checklist de rollout

**Files:**
- Create: `docs/superpowers/plans/2026-09-07-comment-bot-rollout.md`

- [ ] **Step 1: Smoke test del webhook con el bot APAGADO**

```bash
cd /Users/macbookpro/nexus-automation
COMMENT_BOT_ENABLED=0 venv/bin/python3 -c "
import webhook_server
payload = {'object':'instagram','entry':[{'changes':[{'field':'comments','value':{'id':'C1','from':{'id':'x'},'text':'quiero un corolla','media':{'id':'M1'}}}]}]}
with webhook_server.app.test_client() as c:
    r = c.post('/webhook', json=payload)
    print(r.status_code, r.data)
"
```

Expected: `200 b'ok'`, y en consola `[COMMENT] comments C1: skipped:disabled`.

- [ ] **Step 2: Smoke test de la regresión del loop (bot ENCENDIDO, autor propio)**

```bash
cd /Users/macbookpro/nexus-automation
IG_ID=$(grep META_IG_USER_ID .env | cut -d= -f2)
COMMENT_BOT_ENABLED=1 venv/bin/python3 -c "
import webhook_server, os
own = os.getenv('META_IG_USER_ID')
payload = {'object':'instagram','entry':[{'changes':[{'field':'comments','value':{'id':'SELF1','from':{'id':own},'text':'Estoy listo para responder','media':{'id':'M1'}}}]}]}
with webhook_server.app.test_client() as c:
    r = c.post('/webhook', json=payload)
    print(r.status_code)
"
```

Expected: `200`, consola `[COMMENT] comments SELF1: skipped:identity`. **Cero llamadas a Graph API.**

- [ ] **Step 3: Escribir el checklist de rollout**

Crear `docs/superpowers/plans/2026-09-07-comment-bot-rollout.md`:

```markdown
# Comment Bot — checklist de rollout

## Pre-requisitos
- [ ] `feature/comment-bot-hardening` mergeada a `main`.
- [ ] Suite verde: `venv/bin/python3 -m pytest -q`.

## Fase 1 — deploy apagado
- [ ] En Render (servicio `nexus-dm-bot`): añadir env `COMMENT_BOT_ENABLED=0`, `COMMENT_BOT_DRY_RUN=0`.
- [ ] Deploy de `main`. Esperar `live`.
- [ ] `curl https://bot.tucarroconalejo.com/health` → `{"status":"ok",...}`.
- [ ] Mandar un DM de prueba a la página FB e IG → el bot responde (DMs intactos).

## Fase 2 — dry run en Meta
- [ ] Meta for Developers → app `nexus` → Webhooks de la página:
      re-suscribir `feed`. Para IG, suscribir `comments` (necesita permiso
      `instagram_manage_comments` — el token ya lo tiene, verificar con debug_token).
- [ ] Render env: `COMMENT_BOT_DRY_RUN=1`, `COMMENT_BOT_ENABLED=1`. Deploy.
- [ ] Comentar desde una cuenta personal en UNA publicación orgánica reciente
      ("¿tienen corolla 2024?").
- [ ] Render logs: debe aparecer `[COMMENT] comments <id>: dryrun:would_reply:COMPRA`
      y NINGÚN comentario nuevo publicado.
- [ ] Dejar 24 h. Revisar que no haya `error:` ni `skipped:ratelimit` inesperados.

## Fase 3 — vivo, rate limit bajo
- [ ] Render env: `COMMENT_BOT_DRY_RUN=0`. Deploy.
- [ ] Comentar de prueba → verificar: llega 1 DM privado + aparece 1 comentario
      público "¡Te escribimos al DM! 🙌" y NADA más en el hilo.
- [ ] Comentar una felicitación ("bonito!") → NO responde, pero queda en
      `comments_handled.json` con `actions: []`.
- [ ] Vigilar `comments_handled.json` y logs 2-3 días.

## Fase 4 — ampliar
- [ ] Si sale limpio, subir `MAX_PER_HOUR_GLOBAL` / `MAX_PER_HOUR_POST` si hace falta.

## Kill switch
En cualquier momento: Render env `COMMENT_BOT_ENABLED=0` + deploy. O quitar
`feed`/`comments` de la suscripción en Meta (corte inmediato, sin deploy).
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-09-07-comment-bot-rollout.md
git commit -m "docs: checklist de rollout del comment bot

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Abrir PR**

```bash
git push -u origin feature/comment-bot-hardening
gh pr create --title "Comment bot endurecido — 7 guardas anti-loop" --body "$(cat <<'EOF'
## Qué

Reactiva la respuesta a comentarios (FB + IG) con 7 guardas en capas que hacen
imposible el loop del incidente del 6 sep 2026 (~950 comentarios en auto-respuesta).

- Guarda de identidad (la que faltaba), solo top-level, dedupe persistente,
  rate limit (5/h global, 3/h por post), clasificación de intención con Haiku.
- Responde solo por DM privado + 1 comentario público fijo, solo a intención
  real de compra/precio/crédito.
- Kill switch `COMMENT_BOT_ENABLED` (default 0) + `COMMENT_BOT_DRY_RUN`.
- Guard anti-alucinación del teléfono en el DM (mismo que dm_bot.py; el número correcto es (954) 910-6671).
- Test de regresión del loop incluido.

Se despliega APAGADO. Rollout en `docs/superpowers/plans/2026-09-07-comment-bot-rollout.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Kill switch → Task 8 (`_enabled`), Task 1 (env).
- Guarda identidad → Task 3 + Task 8 (regresión del loop).
- Solo top-level → Task 3.
- Dedupe → Task 3 + Task 2 (store).
- Rate limit + alerta Pulse → Task 4 + Task 8.
- Intención (Haiku) → Task 5 + Task 8 (gate).
- Backstop de Meta → Task 7 (`_ALREADY_REPLIED_CODES`).
- Respuesta privada FB/IG → Task 7.
- 1 comentario público fijo → Task 7 (`PUBLIC_ACK`).
- Store schema → Task 2 + Task 8 (`_record`).
- Guard anti-alucinación del teléfono → Task 6.
- Webhook normalización + no romper 200 → Task 9.
- Dry run → Task 8.
- Tests unitarios + regresión + dry run → Tasks 2-9.
- Rama/despliegue → Task 1 + Task 10.
- Fuera de alcance (FB del incidente, respuestas variadas, UI) → no hay tareas ✓.

**Placeholder scan:** sin TBD/TODO. Todo paso de código muestra el código.

**Type consistency:**
- `event` dict: mismas claves en Task 9 (`_comment_event`), Task 8 (`_event` de test y `_handle_comment_inner`).
- `actions`: `["private_<platform>", "public_<platform>"]` en Task 8 (`_record`, test) — consistente.
- `_load_handled`/`_save_handled`/`_record`/`rate_limited`/`classify_intent`/`generate_private_reply`/`send_private_reply`/`send_public_ack`/`handle_comment`: firmas idénticas donde se referencian.
- Resultado de `handle_comment`: `skipped:disabled|identity|reply|dedupe|ratelimit|intent|classify_error`, `dryrun:would_reply:<intent>`, `replied`, `error:<Type>` — usado igual en tests y en el webhook (solo se loguea).
