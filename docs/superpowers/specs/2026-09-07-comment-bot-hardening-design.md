# Comment bot endurecido — diseño

**Fecha:** 2026-09-07
**Autor:** Alejo + Claude (agente Wire)
**Estado:** aprobado, pendiente de plan de implementación

---

## Contexto y motivación

El 6 sep 2026 se detectó que `comment_bot.py` estaba en loop, escribiendo comentarios
en las publicaciones y anuncios de @tucarroconalejo. La limpieza posterior encontró
**~950 comentarios que la propia cuenta se había puesto a sí misma**, en 3 episodios:

| Publicación | Fecha | Comentarios del bot |
|---|---|---|
| Post orgánico IG (`18100973753462190`) | 17 jul 2026 | 260 |
| Post orgánico IG (`18149063305502550`) | 15 ago 2026 | 634 |
| Anuncio "Luisa Pagos Toyota 2026" (`18441230887135851`) | 6 sep 2026 | 53 |

### Causa raíz

`webhook_server.py` enrutaba **todo** evento de comentario (`field == "comments"` IG,
`field == "feed"` FB, `field == "mention"`) a `handle_instagram_comment` /
`handle_facebook_comment`, sin ninguna comprobación de identidad. Cuando el bot posteaba
una respuesta, esa respuesta generaba un nuevo evento `comments` → el bot volvía a
responder → loop infinito. El handler de DMs sí tiene ese guard
(`webhook_server.py:108`, `sender_id == PAGE_ID`); el de comentarios no.

Efecto secundario: el system prompt de `comment_bot.py` trata cualquier entrada ambigua
como "eres el asistente, responde", así que al recibir su propio texto Haiku degeneraba
en meta-respuestas ("¡Perfecto! Estoy listo para responder comentarios como Alejo",
"Comparte el comentario original del cliente").

### Estado actual (post-incidente)

- **Meta:** el campo `feed` fue removido de `subscribed_apps` de la página.
  Suscripción actual: `messages, messaging_postbacks, messaging_referrals`.
- **Código:** `main` tiene el commit `19bd18a` que neutraliza las 3 ramas de
  comentarios en `webhook_server.py`. Render corre `main`, así que producción está a salvo.
- **Limpieza:** los ~950 comentarios del bot fueron borrados vía Graph API
  (`comment_cleanup_run.py`). Verificado: 0 comentarios del bot restantes.
- **Divergencia de ramas:** la rama `feature/admin-marketplace-panel` **no** tiene
  `19bd18a` ni `a056c95` (fix de auto-respuesta de DMs). Su `webhook_server.py`
  reintroduce ambos bugs si se mergea sin rebase.

---

## Decisiones de producto (aprobadas por Alejo)

1. **Comportamiento:** respuesta privada 1 vez + 1 comentario público genérico.
   No responder en hilo, no ida y vuelta.
2. **Filtro:** Haiku clasifica primero. Solo responde a intención real de
   compra / precio / crédito. Ignora felicitaciones, emojis sueltos, trolls y spam.
3. **Plataformas:** Facebook e Instagram (mismas guardas en ambas).
4. **No reactivar** hasta que todo lo de abajo esté en producción y verificado.

---

## Arquitectura

### Componentes

| Componente | Responsabilidad |
|---|---|
| `webhook_server.py` | Reactivar las 3 ramas de comentarios pasando por **un único** punto de entrada guardado (`process_comment_event`). Extraer `from.id` y `parent_id` del payload (hoy solo se saca `username` / `name`). |
| `comment_bot.py` | Reescritura. Ya no postea en hilo. Guard de identidad, dedupe, clasificación de intención, respuesta privada, 1 comentario público, rate limit, kill switch. |
| `comments_handled.json` | **Nuevo.** Store persistente de `comment_id` ya atendidos. Sigue el patrón de `marketplace_posted.json` / `marketplace_inbox_state.json`. Estructura: `{ comment_id: { ts, platform, intent, actions: [...] } }`. |

### Diseño de unidades

- **`webhook_server.py` → `process_comment_event(platform, payload)`**
  Qué hace: normaliza el payload de IG/FB a un dict común
  `{comment_id, author_id, text, post_id, parent_id, platform}` y lo pasa a `comment_bot`.
  Depende de: `comment_bot.handle_comment`.
  Interfaz: una función, entrada = payload crudo de Meta, salida = None (efecto: puede
  disparar respuestas). No lanza excepciones hacia el webhook.

- **`comment_bot.py` → `handle_comment(event: dict) -> str`**
  Qué hace: aplica los 7 filtros en orden; si pasa, envía respuesta privada + 1 público;
  registra en el store. Devuelve un código de resultado (`"skipped:identity"`,
  `"skipped:reply"`, `"skipped:dedupe"`, `"skipped:ratelimit"`, `"skipped:intent"`,
  `"replied"`, `"error:<x>"`) para logging y tests.
  Depende de: `comments_handled.json`, Graph API, Anthropic API, `pulse.py` (alerta).

- **`comment_bot.py` → funciones puras testeables por separado:**
  `is_own_author(author_id)`, `is_reply(event)`, `already_handled(comment_id)`,
  `rate_limited(post_id)`, `classify_intent(text) -> str`.

### Guardas en capas (orden de evaluación)

1. **Kill switch** — `COMMENT_BOT_ENABLED` (env, default `"0"`). El webhook no enruta
   el evento si está apagado.
2. **Identidad** — `event["author_id"] in {PAGE_ID, IG_USER_ID}` → `skipped:identity`.
   *(esta es la guarda que faltaba y causó el loop.)*
3. **Solo top-level** — `event["parent_id"]` presente y distinto de `post_id`
   (el comentario es respuesta a otro comentario) → `skipped:reply`.
4. **Dedupe** — `comment_id` ya en `comments_handled.json` → `skipped:dedupe`.
5. **Rate limit** — máx. **5/hora global** y **3/hora por publicación**.
   Se excede → log + alerta a Pulse + `skipped:ratelimit`.
6. **Intención** — `classify_intent(text)` con Haiku. Solo `COMPRA` / `PRECIO` /
   `CREDITO` continúan. Cualquier otra (`POSITIVO`, `NEGATIVO`, `SPAM`, `OTRO`) →
   se marca como atendido en el store y `skipped:intent`.
7. **Backstop de Meta** — la Graph API solo permite **1 respuesta privada por
   comentario** y solo dentro de **7 días**. Aunque todas las guardas anteriores
   fallaran, esto corta el loop.

### Acción cuando el evento pasa los 7 filtros

- **Respuesta privada (1 vez):**
  - FB: `POST /{comment_id}/private_replies` con `message=`, page token.
  - IG: `POST /{IG_USER_ID}/messages` con
    `{"recipient": {"comment_id": "<id>"}, "message": {"text": "..."}}`.
  - Texto corto, voz de Alejo, invita a seguir por DM. Sin precios/tasas/cuotas.
- **1 comentario público genérico:** *"¡Te escribimos al DM! 🙌"* (una sola frase fija,
  sin variantes, nunca como respuesta a una respuesta).
- **Registro:** `comments_handled.json[comment_id] = {ts, platform, intent, actions}`.
- **Red de seguridad del teléfono:** el número correcto de Alejo es **(954) 910-6671**
  (ya está bien en `COMMENT_VOICE`). Pero Haiku/Claude a veces alucina `310-6671`
  pese a la regla — `dm_bot.py:222` y `:574` ya tienen el guard
  `text.replace("310-6671", "910-6671")`. Replicar ese mismo guard sobre la salida
  de `generate_private_reply`.

### Flujo de datos

```
evento webhook (comments / feed / mention)
  → COMMENT_BOT_ENABLED == "1"? no → drop
  → normalizar payload → {comment_id, author_id, text, post_id, parent_id, platform}
  → author_id ∈ {PAGE_ID, IG_USER_ID}? → skipped:identity
  → parent_id presente (es respuesta)? → skipped:reply
  → comment_id en store? → skipped:dedupe
  → rate limit (global u/post) excedido? → log + alerta Pulse → skipped:ratelimit
  → classify_intent(text) → intent
  → intent ∉ {COMPRA, PRECIO, CREDITO}? → store como atendido → skipped:intent
  → enviar respuesta privada (según plataforma)
  → enviar 1 comentario público fijo
  → store[comment_id] = {ts, platform, intent, actions}
  → return "replied"
```

---

## Manejo de errores

- Toda llamada a Graph API y a Anthropic envuelta en try/except. Error de red = log,
  no propaga, no crashea el proceso.
- Error de Meta "ya respondiste a este comentario" (private reply duplicado) → se trata
  como éxito y se registra en el store.
- `webhook_server.py` **siempre devuelve `200` rápido**, con todo el procesamiento de
  comentarios dentro de try/except. Si algo falla, se loguea pero Meta recibe 200 (evita
  ráfaga de reintentos).
- Si `classify_intent` falla (timeout, error de API) → **no se responde** (falla cerrado).
  Se registra `error:classify` y no se marca como atendido (se reintentará si Meta reenvía).

---

## Pruebas

### Unit
- `is_own_author`: id de la página / IG → `True`; id de tercero → `False`.
- `is_reply`: evento con `parent_id` → `True`; sin `parent_id` → `False`.
- `already_handled`: segundo evento con el mismo `comment_id` → `True`.
- `rate_limited`: 6º evento en una hora → `True`; 4º en la misma publicación → `True`.
- `classify_intent`: un caso por categoría (COMPRA, PRECIO, CREDITO, POSITIVO,
  NEGATIVO, SPAM, OTRO) con textos representativos.

### Regresión del loop (obligatorio)
- Fixture: payload real de `field == "comments"` correspondiente a **una respuesta
  posteada por la propia cuenta** (tomado de `ig_incident_comments_20260906.json` +
  forma del webhook). `handle_comment` debe devolver `skipped:identity` y **no** hacer
  ninguna llamada a Graph API (mock que falla el test si se invoca).

### Dry run
- `COMMENT_BOT_DRY_RUN=1`: `handle_comment` corre todas las guardas y la clasificación,
  loguea qué postearía, pero **no** llama a Graph API para escribir.

---

## Rama y despliegue

1. **Rebase** de `feature/admin-marketplace-panel` sobre `main`
   (que ya tiene `19bd18a` + `a056c95`), resolviendo `webhook_server.py` a favor de la
   versión de `main` + el WIP legítimo del panel admin. Verificar que el resultado
   **no** reintroduce las ramas de comentarios en loop ni el bug de auto-respuesta de DMs.
2. El trabajo de este diseño sale de una **rama nueva desde `main`**
   (`feature/comment-bot-hardening`).
3. Merge del código endurecido a `main` con `COMMENT_BOT_ENABLED=0`. Deploy a Render.
   Verificar: `curl https://bot.tucarroconalejo.com/health` → 200; DMs FB/IG intactos.
4. `COMMENT_BOT_DRY_RUN=1` + `COMMENT_BOT_ENABLED=1`; re-suscribir `feed` (FB) y
   configurar `comments` (IG) en Meta. Probar en **una** publicación orgánica durante
   ~1 día. Leer logs.
5. Quitar `DRY_RUN`. Rate limit bajo (5/h global). Vigilar 2–3 días.
6. Ampliar a todas las publicaciones si sale limpio.

---

## Fuera de alcance (YAGNI)

- Verificación del lado Facebook del incidente de jul/ago (el token no tiene
  `pages_read_user_content`). Decisión de Alejo: dejar por ahora.
- Respuestas públicas variadas / conversación en hilo.
- Panel/UI para revisar comentarios atendidos.
- Traducción automática de respuestas (el bot responde en el idioma del comentario vía
  el prompt, sin lógica adicional).
