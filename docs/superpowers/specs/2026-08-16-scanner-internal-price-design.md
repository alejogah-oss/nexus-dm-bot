# Precio real privado + rango de alternativas en el scanner

**Fecha:** 2026-08-16
**Pedido por:** Alejo

## Problema

Hoy el scanner tiene un único campo `price`, que es el **enganche/down payment**
publicado en Marketplace y el sitio (regla `DOWN_PAYMENT_THRESHOLD`, ver
memoria `nexus-scanner-enganche-rule`) — nunca el precio total real del carro.
El bot de Marketplace (`marketplace_inbox_bot.py` → `_marketplace_voice()` en
`dm_bot.py`) no tiene forma de conocer el precio real de un carro usado del
scanner para usarlo en conversación si el cliente lo pregunta, ni de sugerir
otras opciones del inventario si dice que está caro.

## Hallazgo de seguridad relacionado

`_enrich_car()` en `marketplace_inbox_bot.py` matchea por año+modelo contra
TODO el inventario público (`api.php?action=list`), sin distinguir usados del
scanner. Si un usado del scanner con `price` < $10,000 (un enganche, no un
precio total) queda activo en el sitio, el bot hoy lo toma como si fuera el
precio total del carro — no fue diseñado así, es un efecto colateral no
detectado hasta ahora. Este cambio lo cierra como parte del mismo trabajo
(ver sección 4).

## Diseño

### 1. Campos nuevos en el scanner (privados, nunca publicados)

En `listing.json` de cada carro, dos campos nuevos y opcionales:

- `internal_price` (número) — precio real del carro. Solo para uso interno
  del bot.
- `alt_price_low` / `alt_price_high` (números) — rango de precio para
  ofrecer otras opciones del inventario si el cliente dice que este carro
  está caro.

**Por qué es seguro que nunca se publiquen:** ni `site_publisher.build_payload()`
ni los `fields` que arma `marketplace_poster.post_scanner_car()` hacen
passthrough de `listing.json` — ambos arman su propio diccionario campo por
campo. Los campos nuevos simplemente no se agregan a esas listas, así que
quedan estructuralmente imposibles de publicar por accidente (no depende de
un guard que alguien pueda olvidar).

**UI (`static/scanner/index.html` + `app.js`):**
- Paso 2 (captura): dos inputs nuevos junto al campo de precio existente,
  claramente etiquetados como privados/opcionales.
- Editor de "Pendientes": los mismos dos campos, para poder cargarlos después
  de escanear.
- Backend: `save_inventory()` ya persiste el dict completo tal cual llega, no
  requiere cambios. `update_inventory_item()` sí necesita agregar
  `internal_price`, `alt_price_low`, `alt_price_high` a su whitelist de
  campos editables.

### 2. El bot da el precio real como ancla (mismo mecanismo que carros nuevos)

En `marketplace_inbox_bot.py`, después de `_enrich_car()` (que resuelve el
VIN vía matching público), un paso nuevo cruza ese VIN contra el inventario
local del scanner (`INVENTORY_DIR`, mismo que usa `scanner_api.py` —
acceso directo por filesystem, sin nueva API):

- Si el VIN matchea un carro del scanner:
  - Si tiene `internal_price` cargado → se usa como `car['price']`,
    `car['price_hi'] = 0` (fuerza la rama de "único trim, sin rango" que ya
    existe en `_marketplace_voice()` — es la misma redacción usada hoy para
    un vehículo nuevo del que solo hay una versión en stock).
  - Si tiene `alt_price_low`/`alt_price_high` → se agregan al `car` dict para
    el paso 3.
  - Si NO tiene `internal_price` cargado → `car['price'] = 0` (cierra el
    hallazgo de la sección anterior: sin este campo, el bot no da ningún
    número de un usado del scanner, como debería ser hoy).
- Si el VIN no matchea ningún carro del scanner (inventario normal, no
  scanner) → comportamiento actual sin cambios.

`_marketplace_voice()` no cambia su lógica de calificación (financiar/cash →
dar el número → showroom si insiste exacto) — solo recibe un `price` que
ahora puede venir de un carro usado real.

### 3. Rango de alternativas — nunca inventa carros

Cuando `alt_price_low`/`alt_price_high` están presentes, `marketplace_inbox_bot.py`
filtra el inventario público cacheado (`_get_inventory()`, ya existe, TTL 10
min) por precio dentro de ese rango, excluye el VIN actual, deduplica por
(año, modelo, trim), limita a 4 resultados máximo, y arma un texto corto
(mismo estilo que `_price_table()`). Ese texto se pasa en el `car` dict como
`alt_options_text`.

En `_marketplace_voice()`, un bloque de prompt nuevo (solo si
`alt_options_text` viene con contenido): si el cliente dice que el carro está
caro / fuera de presupuesto, el bot menciona esas opciones reales de la lista
— nunca inventa año/modelo/precio fuera de ella — y cierra con una pregunta,
respetando el estilo de una pregunta por mensaje.

### 4. Alcance

Solo `marketplace_inbox_bot.py` / `_marketplace_voice()` (conversación sobre
un listing puntual de Marketplace). El bot general de Instagram/Facebook
(`dm_bot.py`, canal no ligado a un listing) sigue sin dar precios de usados,
sin cambios.

## Testing

- Tests existentes: `tests/test_scanner_api.py`,
  `tests/test_scanner_server_admin.py`, `tests/test_marketplace_scanner.py` —
  extender con casos para los campos nuevos (whitelist de
  `update_inventory_item`, que nunca aparezcan en `build_payload()` ni en los
  `fields` de Marketplace).
- Caso nuevo para el matching VIN→scanner en `marketplace_inbox_bot.py`: con
  `internal_price`, sin él, y sin match (carro normal).
- Caso nuevo para `alt_options_text`: rango con resultados, rango vacío, sin
  rango cargado.

## Fuera de alcance

- No se toca el campo `price` (enganche) existente ni la regla
  `DOWN_PAYMENT_THRESHOLD`.
- No se cambia el matching aproximado por año+modelo de `_enrich_car()` para
  el resto del inventario (fuera de scanner) — es un problema preexistente
  distinto, no se toca en este trabajo.
- No se extiende a `dm_bot.py` canal general (decisión explícita de Alejo).
