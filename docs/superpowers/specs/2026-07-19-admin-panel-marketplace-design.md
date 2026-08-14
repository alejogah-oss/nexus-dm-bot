# Administrador "Tu Carro con Alejo" — Panel de publicación a Marketplace

**Fecha:** 2026-07-19
**Autor:** NEXUS (Alejo + Claude)
**Estado:** Diseño aprobado — pendiente escribir plan de implementación

---

## Objetivo

Un panel administrativo que muestre el estado de publicación de cada carro
capturado con el VIN Scanner, permita editar los que aún no se han publicado, y
permita a Alejo publicar **un carro a la vez** en Facebook Marketplace **a su
sola discreción**, con confirmación visual física en el Mac Pro.

## Contexto y restricciones (CRÍTICAS)

- **Cuenta de Facebook marcada:** Meta puso un checkpoint a la cuenta
  `tucarroconalejo@gmail.com` en julio 2026; el bot de Marketplace lleva sin
  correr desde el 16 de junio. Por eso el bot **nunca** publica solo ni en lote:
  llena el formulario y **se detiene antes del botón Publicar de Facebook**;
  Alejo revisa y da Publicar él mismo.
- **Corre SOLO en el Mac Pro.** El bot de Chrome necesita navegador visible
  (`headless=False`), lo que exige un escritorio real. El MacBook Air NUNCA
  corre este bot (ver `feedback_nexus_macbook_air_no_automation`).
- **Inventarios separados:** el inventario del sitio web del dealer (Toyotas
  nuevos, vía `tucarroconalejo.com/api.php`) y el inventario del scanner (usados,
  cualquier marca, en `inventario/`) son fuentes distintas y NO se mezclan. Este
  panel opera **solo sobre el inventario del scanner**.
- **Teléfono:** (954) 910-6671 — nunca cambiar.
- **Auth:** misma `SCANNER_KEY` fail-closed que ya usa el scanner.

## Arquitectura

El panel es una ruta nueva (`/admin`) servida por el mismo `scanner_server.py`
que ya corre 24/7 en el Mac Pro. Reusa la misma infraestructura, auth, LaunchAgent
e inventario que el scanner. No se monta un segundo servidor ni una segunda URL.

```
Mac Pro (siempre prendido)
  scanner_server.py (Flask, HTTPS Tailscale :8443)
    /scanner        → PWA del scanner (ya existe)
    /admin          → NUEVO panel administrador
    /api/scanner/*  → endpoints existentes (list/get/update inventory)
    /api/admin/*    → NUEVOS endpoints (estado + lanzar publicación)
  inventario/<slug>/
    listing.json    → + campos de estado de publicación (NUEVO)
    photos/*.jpg
    copy.md, video.mp4
  marketplace_poster.py → + función de publicación de carros del scanner (NUEVO)
```

## Componentes

### 1. Estado de publicación persistente (por carro)

Hoy `marketplace_poster.py` guarda solo los éxitos en un JSON global
(`marketplace_posted.json`) y los fallos se pierden (solo imprime + screenshot).

Cambio: cada carro guarda su estado dentro de su propio `listing.json`:

- `published` (bool, default `false`)
- `published_at` (str ISO, o `null`)
- `last_error` (str, o `null`) — mensaje del último fallo de publicación

El estado se escribe cuando el panel lanza una publicación y cuando Alejo la marca
como publicada. Sobrevive reinicios porque vive en disco junto al carro.

### 2. Panel de estado (`/admin`)

Página HTML servida en `/admin`, pide la `SCANNER_KEY` una vez (igual que el
scanner, `localStorage`). Muestra una tarjeta por carro del scanner:

- Foto de portada (primera foto), título, precio, millaje.
- **Badge de estado:**
  - `🟡 Sin publicar` — `published: false`, sin error.
  - `🟢 Publicado` + fecha — `published: true`.
  - `🔴 Falló` — `last_error` presente y no publicado.
- Botón **Editar** (para `🟡` y `🔴`): abre el editor de campos (título,
  descripción, precio, millaje, color, notas) reusando el endpoint PUT que ya
  existe (`/api/scanner/inventory/<slug>`).
- Botón **Publicar este carro** (para `🟡` y `🔴`): dispara la publicación.
- Los `🟢 Publicado` se muestran como registro pero sin acciones de publicar.

### 3. Publicación de carros del scanner (nueva, separada de la del dealer)

Función nueva en `marketplace_poster.py` que publica **un** carro leído del
`inventario/<slug>/` del scanner (no del sitio web). A diferencia de la función
del dealer:

- **Marca:** valor real del carro (no fijo "Toyota").
- **Millaje:** valor real del odómetro (no fijo "500").
- **Precio:** precio completo real (no enganche = 20%).
- **Color interior:** "Black" por defecto (coincide con lo que ya hace el bot).
- **Fotos:** las del `inventario/<slug>/photos/` (no las del feed del dealer).
- **Descripción:** el copy ya generado en `copy.md`/`listing.json`.

Flujo al pulsar "Publicar este carro":

1. El endpoint `/api/admin/publish/<slug>` lanza el bot en el Mac Pro
   (subproceso, navegador visible).
2. El bot abre Chrome con la sesión guardada, llena el formulario de Marketplace
   con los datos reales del carro y sus fotos.
3. El bot **se detiene antes del botón Publicar de Facebook** y deja Chrome
   abierto.
4. Alejo revisa visualmente en el Mac Pro y da **Publicar** él mismo.
5. Alejo marca el carro como publicado en el panel (botón **Marcar publicado**),
   que hace `published: true` + `published_at`.
6. Si el bot falla al llenar el formulario, guarda `last_error` y el carro queda
   `🔴 Falló`.

**Solo un carro a la vez:** el panel no permite lanzar una nueva publicación
mientras haya un bot de Chrome abierto (lock simple).

## Flujo de datos

```
Alejo (en el Mac Pro) → /admin → lista de carros con badges de estado
  ├─ Editar   → PUT /api/scanner/inventory/<slug> (existente)
  ├─ Publicar → POST /api/admin/publish/<slug>
  │              → subproceso marketplace_poster (scanner car, Chrome visible)
  │              → llena formulario, se detiene antes de Publicar
  │              → Alejo da Publicar en Facebook manualmente
  └─ Marcar publicado → POST /api/admin/mark/<slug>  → listing.json published:true
```

## Manejo de errores

- **Bot ya corriendo:** `/api/admin/publish` responde 409 "ya hay una publicación
  en curso"; el panel deshabilita el botón mientras tanto.
- **Fallo al llenar el formulario:** se guarda `last_error`, badge `🔴`, con el
  mensaje visible en la tarjeta.
- **Sesión de Facebook expirada:** el bot lo detecta (no encuentra el formulario)
  y guarda un `last_error` claro ("sesión FB expirada — renovar").
- **Auth:** cualquier endpoint sin `SCANNER_KEY` válida responde 401 (fail-closed).
- **Slug inválido / carro inexistente:** 404 (misma validación anti path-traversal
  que ya usa el scanner).

## Pruebas

- Estado persistente: escribir/leer `published`, `published_at`, `last_error` en
  `listing.json`; carros nuevos default `false`.
- Panel: lista carros del `inventario/`, badges correctos por estado, botones
  Editar/Publicar solo en no publicados.
- Endpoints admin: `publish` lanza subproceso y hace lock; segundo `publish`
  concurrente → 409; `mark` cambia estado; auth 401; slug inválido 404.
- Publicación scanner: la función arma el formulario con marca/millaje/precio
  reales del carro del scanner (probado con un `listing.json` de ejemplo, sin
  tocar Facebook — se verifica que los campos que llenaría son los reales).
- El bot se detiene antes de Publicar (no hay click en el botón Publicar de FB).

## Fuera de alcance (YAGNI)

- Publicación remota desde el iPhone con captura/aprobación (Alejo confirma
  físicamente en el Mac Pro).
- Publicación en lote / automática (siempre uno a uno, a discreción de Alejo).
- Publicar carros del inventario del sitio web (eso ya lo hace la función
  existente del dealer; este panel es solo para el scanner).
- Renovación automática de la sesión de Facebook.
```

