# NEXUS — @tucarroconalejo
**Sistema de ventas digital automatizado para Alejo Garcia, asesor Toyota en Hollywood Toyota, Florida.**
**Última actualización: junio 19, 2026**

---

## Cliente
- **Alejo Garcia** — asesor de ventas Toyota, Hollywood Toyota, Florida
- Instagram/Facebook: @tucarroconalejo
- Email: alejogah@gmail.com / tucarroconalejo@gmail.com
- Tel: (954) 910-6671 ← CRÍTICO: nunca cambiar este número
- Dealer: Hollywood Toyota, 2200 N State Rd 7, Hollywood FL 33021

---

## Skills de diseño UI/UX
Cuando se requiera diseño visual usar:
- `ui-ux-pro-max` — estilos, paletas, tipografías, layouts
- `design` — identidad visual, logos, banners sociales
- `banner-design` — banners para Facebook, Instagram, ads
- `frontend-design` — componentes web de alta calidad
- `ui-styling` — shadcn/ui, Tailwind, dark mode
- Colores NEXUS: rojo `#EB0A1E`, negro `#0A0A0A`, fuentes Anton/Bebas Neue/Inter

---

## Arquitectura general

```
Mac de Alejo (local)          Render.com (24/7)           Meta
─────────────────────         ─────────────────           ────────────────
main.py --schedule     →      webhook_server.py    ←→     Facebook Page
  └─ content_agent.py         └─ dm_bot.py                Instagram
  └─ templates.py             └─ comment_bot.py           Messenger DMs
  └─ image_agent.py           └─ crm_client.py
  └─ drive_reader.py          └─ pulse.py (pendiente)
  └─ meta_publisher.py
marketplace_poster.py  →      Facebook Marketplace (browser)

Sitio web: Hostinger → tucarroconalejo.com
  └─ index.html (landing)
  └─ inventario.html (430+ vehículos con paginador + filtros)
  └─ chat-widget.js (bot integrado, lead capture)
```

---

## Módulos — estado actual

### ✅ FUNCIONANDO

**Sitio web (Hostinger — tucarroconalejo.com)**
- Landing `index.html`: hero Sequoia 2026 blanca, testimonios, sección pasos
- Botón ESCRÍBEME del nav → abre chat widget directamente
- `inventario.html`: 430+ vehículos, paginador (20 por página), filtros flotantes (año, modelo, tracción, condición, color)
- Botón ME INTERESA en cada carro → abre bot con mensaje prearmado del vehículo
- `chat-widget.js`: lead capture (nombre → teléfono → conversación), API → bot.tucarroconalejo.com
- Dark/light mode con `data-theme`, localStorage key `tcca-theme`
- Archivos deploy: `/Users/macbookpro/Desktop/tucarroconalejo-deploy/`

**DM Bot (dm_bot.py + webhook_server.py — Render.com)**
- URL: https://bot.tucarroconalejo.com
- Responde DMs de Facebook + Instagram + web chat del sitio
- Voz: habla como parte del equipo ("nosotros", "por aquí"), no repite "Alejo" constantemente
- Máximo 2 oraciones por respuesta, 1 pregunta por mensaje
- Links de inventario solo como último recurso, uno a la vez
- [HOT LEAD] es etiqueta silenciosa — nunca se muestra al cliente
- `max_tokens: 160`, modelo: claude-sonnet-4-6
- Webhook URL: https://bot.tucarroconalejo.com/webhook | Verify Token: `nexus_alejo_2026`
- Web chat endpoint: https://bot.tucarroconalejo.com/web-chat (CORS abierto)
- Caché de inventario: 5 min TTL en memoria para imágenes

**CRM (crm_client.py)**
- Webhook: https://crm.tucarroconalejo.com/api/webhook/tucarro
- Agent code: `alejo` ✅ verificado
- Flujo HOT LEAD: Claude Haiku extrae datos + genera nota de conversación con contexto real
- Nota incluye: nombre cliente, modelo de interés, situación, urgencia, detalles para primer contacto
- Campos enviados: nombre, teléfono, email, modelo, nota de conversación, link al chat

**Meta Token (renovado junio 19, 2026)**
- Token permanente (expires_at: 0) ✅
- App: "nexus" (ID: 26747167188295193)
- Página: Tucarro-con-Alejo (ID: 765862069934682)
- Permisos activos: catalog_management, pages_show_list, pages_messaging, instagram_basic, instagram_manage_comments, instagram_content_publish, pages_read_engagement, pages_manage_posts, pages_manage_metadata, business_management, whatsapp_business_management
- Webhook suscrito a: `messages`, `messaging_postbacks`, `feed` (comentarios FB incluidos)

**Publicación (main.py + scheduler)**
- 2 posts/día, parrilla fija por día de la semana
- Tipos: `inventory`, `tips`, `quote`, `new_car_day`, `entrega`
- Publicar manualmente: `venv/bin/python3 main.py --now inventory`
- Iniciar scheduler: `pkill -f "main.py --schedule" 2>/dev/null && venv/bin/python3 main.py --schedule &`

**Templates de imagen (templates.py)** — sistema visual (jul 14 2026, aprobado por Alejo)
- **Clean Real** (estilo @yourcarmoment — foto lifestyle full-bleed + tipografía mínima): `inventory` (`template_inventory_clean` + `generate_lifestyle_inventory_photo`; fallback → Racing con jelly)
- **⛔ REGLA ABSOLUTA (jul 14 2026): los píxeles del carro NUNCA pasan por IA.** Ni text-to-image ni Kontext i2i — ambos redibujan generaciones VIEJAS aunque se les prohíba (verificado: Camry 2026 → Kontext devolvió el modelo 2018-2024). La IA solo genera FONDOS vacíos; el carro real (car_library/*.png, renders oficiales 2026 con alpha) se compone encima con PIL, píxeles intactos. Lo mismo aplica a fotos de Drive: se usan tal cual o con i2i solo-fondo verificado.
- **Racing Bold** (negro + franja diagonal roja + Anton): `ai_promo` s1/s2/s3, fallback inventory; versión `animated=True` para video
- **Miami Heat** (gradiente atardecer rojo-negro + Bebas/Anton): `quote`
- **Premium Minimal** (negro limpio + Inter editorial + números Bebas rojos): `tips`
- `new_car_day` / `entrega` — foto real cliente full-bleed (pipeline Shot)
- TODOS los footers llevan CTA: `@tucarroconalejo · ESCRÍBEME (954) 910-6671`
- PROHIBIDO: Dancing Script/cursivas, corazones/bokeh dorado fuera de celebraciones
- Slides 4:5 SIEMPRE con `render_to_image(..., height=1350)` — sin eso se recortan 270px

**Posts animados (html_renderer.py → render_to_video)**
- `template_inventory(..., animated=True)` + `render_to_video(html, out.mp4, duration_s=6.5)`
- Graba la animación CSS con Playwright (webm) y convierte a MP4 30fps con ffmpeg del venv
- Animación: franja barre → carro entra → título revela → specs escalonados → CTA pulsa
- Pendiente decisión: publicar los MP4 por API requiere agregar video a meta_publisher.py

**Sistema de fotos (drive_reader.py)**
- Google Drive API directa — Service account: `nexus-drive-reader@nexus-tucarroconalejo.iam.gserviceaccount.com`
- Folder ID: `1TFgiLp-sVgTZLQpP5XOLuj1DlgErLZ31`
- Lógica: foto nueva → úsala; si no → FIFO infinito desde fotos_cache/
- HEIC → JPG automático

**Feed de vehículos CSV (webhook_server.py)**
- URL: https://bot.tucarroconalejo.com/feed/vehicles.csv
- 137 vehículos únicos (deduplicado por yr/model/trim/color — INTENCIONAL)
- Imágenes: https://bot.tucarroconalejo.com/feed/image/{VIN} | Cache-Control: 24h

**Catálogo Meta (Business Manager)**
- BM alejogah@gmail.com → ID: 1551722759597838
- Catálogo vehículos → ID: 1137133291627950
- Feed conectado al CSV del bot

---

### 🟡 CONSTRUIDO — BLOQUEADO

**Bot de comentarios (comment_bot.py)**
- Código listo
- Token ya tiene permisos `pages_manage_metadata` + `instagram_manage_comments` ✅
- Webhook suscrito a `feed` (comentarios FB) ✅
- ⚠️ Falta suscribir comentarios de Instagram (campo diferente al de FB)
- ⚠️ Falta activar desde webhook_server.py (conectar comment_bot a los eventos `feed`)

**Marketplace Poster (marketplace_poster.py)**
- Script completo con Playwright + sesión guardada: `browser_session/fb_session.json`
- BLOQUEADO: Meta no permite publicación de vehículos para esta cuenta
- Estado: descartado temporalmente

---

### ❌ PENDIENTE DE CONSTRUIR

**Pulse — Notificaciones HOT LEAD (pulse.py)**
- Enviar SMS/WhatsApp a Alejo cuando bot detecta HOT LEAD
- Ver skill `nexus-pulse` para implementación con Twilio

**LaunchAgent — Scheduler 24/7**
- El scheduler depende de que el Mac esté prendido
- Configurar com.nexus.scheduler.plist en ~/Library/LaunchAgents/

**Módulo de Campañas (futuro)**
- Requiere App Review de Meta para `ads_management` + `ads_read`
- Solicitar solo cuando el módulo esté construido

---

## Infraestructura

| Componente | Dónde corre | URL |
|---|---|---|
| Scheduler + posts | Mac de Alejo | local |
| DM Bot + webhook | Render.com | https://bot.tucarroconalejo.com |
| Web chat | Render.com | https://bot.tucarroconalejo.com/web-chat |
| Feed CSV + imágenes | Render.com | https://bot.tucarroconalejo.com/feed/ |
| Sitio web | Hostinger | https://tucarroconalejo.com |
| Dashboard | Mac (local) | http://localhost:8090/dashboard.html |
| CRM | Externo | https://crm.tucarroconalejo.com |

**GitHub**: github.com/alejogah-oss/nexus-dm-bot (webhook/bot — scheduler es local)

---

## Cuentas y credenciales (.env)

```
META_PAGE_ID=765862069934682
META_IG_USER_ID=17841476248130016
META_CATALOG_ID=1137133291627950
META_BUSINESS_ID=1975334699886381
META_PAGE_ACCESS_TOKEN=...    # ✅ Renovado jun 19, 2026 — permanente
META_APP_SECRET=...           # ⚠️ Rotar — expuesto en chat jun 19 2026
ANTHROPIC_API_KEY=...         # ⚠️ Rotar — expuesto en chat anterior
CRM_WEBHOOK_URL=https://crm.tucarroconalejo.com/api/webhook/tucarro
CRM_WEBHOOK_KEY=crm-wh-k3y-2025-AutoXz9pLm
CRM_AGENT_CODE=alejo
VERIFY_TOKEN=nexus_alejo_2026
```

**Sesiones de browser:**
- `browser_session/fb_session.json` — tucarroconalejo@gmail.com

---

## Parrilla de contenido (2 posts/día)

| Día | 12:00pm | 8:00pm |
|-----|---------|--------|
| Lun | inventory | entrega |
| Mar | entrega | reel |
| Mié | entrega | inventory |
| Jue | ai_promo | entrega |
| Vie | new_car_day | reel |
| Sáb | tips | ai_promo |
| Dom | quote | tips |

**Tipo `reel`** (jul 2026): video con receta Shot (`reel_maker.py`) — foto real FIFO → 2 clips Kling (órbita personas + beauty shot carro) → crossfade + textos 3 actos → se importa a Fotos (iCloud → iPhone) y Alejo le pone música trending en IG y publica. NO se publica por API. Receta: `~/.claude/skills/nexus-shot/references/reel-recipe.md`

**Fotos de Drive:** FIFO estricto — siempre la más antigua sin usar, cada foto se usa UNA vez. Si se agotan → post abortado + alerta para subir fotos.

**⚠️ Scheduler corre vía LaunchAgent `com.nexus.tucarroconalejo.scheduler` (KeepAlive, Python 3.11).** NO usar `pkill + relanzar manual` — launchd lo respawnea y quedan duplicados. Para reiniciar: `launchctl kickstart -k gui/$(id -u)/com.nexus.tucarroconalejo.scheduler`

---

## Reglas de contenido (ABSOLUTAS)
- NUNCA mencionar precios específicos del vehículo
- NUNCA prometer financiamiento sin confirmación
- NUNCA cambiar el teléfono (954) 910-6671
- Promos vigentes junio 2026: $0 inicial, bajo crédito, bono $500
- Camry: $1,000 extra si ya tiene Toyota
- Tacoma/Tundra: financiamiento desde 2.9%
- Preguntar promos nuevas cada 1ro de mes

---

## Comandos frecuentes

```bash
cd /Users/macbookpro/nexus-automation

# Publicar manualmente
venv/bin/python3 main.py --now inventory   # tipos: inventory entrega new_car_day tips quote

# Scheduler
pkill -f "main.py --schedule" 2>/dev/null && venv/bin/python3 main.py --schedule &

# Dashboard local
venv/bin/python3 -m http.server 8090 & && open http://localhost:8090/dashboard.html

# Verificar bot en Render
curl https://bot.tucarroconalejo.com/health

# Renovar sesión browser si expira
venv/bin/python3 fb_session.py
```

---

## Pendientes (en orden de prioridad)

### Seguridad
- [ ] Rotar `META_APP_SECRET` — expuesto en chat jun 19 2026
- [ ] Rotar `ANTHROPIC_API_KEY` — expuesto en chat anterior

### Activar
- [ ] Conectar `comment_bot.py` a eventos `feed` del webhook (falta lógica en webhook_server.py)
- [ ] Suscribir comentarios de Instagram al webhook
- [ ] Pulse — SMS HOT LEAD a Alejo (Twilio, ver skill nexus-pulse)
- [x] LaunchAgent — ya existe: `com.nexus.tucarroconalejo.scheduler` (KeepAlive)

### Crecimiento / SEO
- [ ] Crear `sitemap.xml` + registrar en Google Search Console
- [ ] Vincular `tucarroconalejo.com` en Google Business Profile
- [ ] Registrar NAP en Cars.com, CarGurus, AutoTrader
- [ ] Crear `og-image.jpg` (1200×630px) para previews en redes

### Contenido
- [ ] Reemplazar testimonios placeholder con citas reales de clientes
- [ ] Actualizar `lex_bank.json` con frases reales de Alejo

### Futuro
- [ ] Módulo de campañas — solicitar App Review Meta para ads_management + ads_read
- [ ] Lens — primer reporte analytics (~julio 2026, 14 días de datos)
