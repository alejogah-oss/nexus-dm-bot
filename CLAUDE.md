# NEXUS — @tucarroconalejo
**Proyecto de automatización de redes sociales + Marketplace**

## Cliente
- **Alejo** — asesor de ventas Toyota, Hollywood Toyota, Florida
- Instagram/Facebook: @tucarroconalejo
- Email: alejogah@gmail.com / tucarroconalejo@gmail.com
- Tel: (954) 310-6671

---

## Arquitectura general

```
Mac de Alejo (local)          Render.com (24/7)           Meta
─────────────────────         ─────────────────           ────────────────
main.py --schedule     →      webhook_server.py    ←→     Facebook Page
  └─ content_agent.py         └─ dm_bot.py                Instagram
  └─ templates.py             └─ comment_bot.py           Messenger DMs
  └─ image_agent.py           └─ marketplace_agent.py
  └─ drive_reader.py
  └─ meta_publisher.py        crm.tucarroconalejo.com
                              └─ crm_client.py (webhook)
marketplace_poster.py  →      Facebook Marketplace (browser)
```

---

## Módulos — estado actual

### ✅ FUNCIONANDO

**Publicación (main.py + scheduler)**
- 2 posts/día, parrilla fija por día de la semana
- Tipos: `inventory`, `tips`, `quote`, `new_car_day`, `entrega`
- Publicar manualmente: `venv/bin/python3 main.py --now inventory`
- Iniciar scheduler: `pkill -f "main.py --schedule" 2>/dev/null && venv/bin/python3 main.py --schedule &`

**Templates de imagen (templates.py)**
- 5 templates HTML→JPG vía Playwright (todos aprobados)
- Franja roja diagonal, Anton/Barlow Condensed, año 2026
- 1. `inventory` — jelly car + specs + promo
- 2. `new_car_day` — foto cliente full-bleed
- 3. `entrega` — foto + "ENTREGA ESPECIAL"
- 4. `quote` — fondo oscuro + palabra acento GIGANTE (190px)
- 5. `tips` — HTML, barra roja, lista 01-05

**Sistema de fotos (drive_reader.py)**
- Google Drive API directa (sin app de escritorio)
- Service account: `nexus-drive-reader@nexus-tucarroconalejo.iam.gserviceaccount.com`
- Folder: `nexus-fotos` (alejogah@gmail.com Drive)
- Folder ID: `1TFgiLp-sVgTZLQpP5XOLuj1DlgErLZ31`
- Lógica: foto nueva → úsala; si no → FIFO infinito desde fotos_cache/
- HEIC → JPG automático

**DM Bot (dm_bot.py + webhook_server.py)**
- Corre en Render.com → https://bot.tucarroconalejo.com
- Responde DMs de Facebook + Instagram con Claude Sonnet 4.6
- Token de página: no vence (Page Access Token permanente)
- Webhook URL: https://bot.tucarroconalejo.com/webhook
- Verify Token: `nexus_alejo_2026`

**Feed de vehículos CSV (webhook_server.py)**
- URL: https://bot.tucarroconalejo.com/feed/vehicles.csv
- 137 vehículos únicos (deduplicado por yr/model/trim/color — INTENCIONAL)
- Imágenes: https://bot.tucarroconalejo.com/feed/image/{VIN}
- Dealer: Hollywood Toyota, 2200 N State Rd 7, Hollywood FL 33021

**Catálogo Meta (Business Manager)**
- BM alejogah@gmail.com → ID: 1551722759597838
- Catálogo vehículos → ID: 1137133291627950
- Feed conectado al CSV del bot (6 fuentes de datos activas)
- BM tucarroconalejo@gmail.com → ID: 1975334699886381 (solo ecommerce, no vehicles)

**Integración CRM (crm_client.py)**
- Webhook: https://crm.tucarroconalejo.com/api/webhook/tucarro
- Agent code: `alejo` (⚠️ verificar que existe en la DB del CRM)
- Flujo: HOT LEAD detectado → Claude Haiku extrae datos → POST al CRM
- Campos: nombre, teléfono, email, modelo de interés

### 🟡 CONSTRUIDO — BLOQUEADO TEMPORALMENTE

**Marketplace Poster (marketplace_poster.py)**
- Script completo para publicar los 137 vehículos en Facebook Marketplace
- Usa Playwright + sesión guardada: `browser_session/fb_session.json`
- Formulario completamente mapeado: Vehicle type, Year, Make, Model, Mileage, Body style, Color, Condition, Fuel type, Price, Description, Foto
- **BLOQUEADO**: cuenta tucarroconalejo@gmail.com requiere verificación de identidad en Meta
- **Acción pendiente**: Alejo completa verificación manualmente en Facebook
- **Para correr después de verificar**: `venv/bin/python3 marketplace_poster.py 137`
- Log de publicados: `marketplace_posted.json` (se crea al primer publish)

### ❌ PENDIENTE DE ACTIVAR

**Comentarios (comment_bot.py)**
- Código listo, pero faltan permisos en el token:
  - `pages_manage_metadata` (comentarios FB)
  - `instagram_business_manage_comments` (comentarios IG)
- Regenerar Page Access Token con esos permisos en Meta for Developers → App "nexus"

**Ink — Get Started (ink.py)**
- Botón "Get Started" para nuevos usuarios en Messenger
- Pendiente activar desde Meta for Developers

**Notificación HOT LEAD al teléfono (Wire)**
- Push notification cuando bot detecta lead caliente
- No implementado aún

**LaunchAgent (scheduler 24/7)**
- El scheduler de publicación depende de que el Mac esté prendido
- Pendiente configurar LaunchAgent para que arranque automáticamente

---

## Infraestructura

| Componente | Dónde corre | URL |
|---|---|---|
| Scheduler + posts | Mac de Alejo | local |
| DM Bot + webhook | Render.com | https://bot.tucarroconalejo.com |
| Feed CSV + imágenes | Render.com | https://bot.tucarroconalejo.com/feed/ |
| Dashboard | Mac (local) | http://localhost:8090/dashboard.html |
| Inventario | Hostinger | https://tucarroconalejo.com/api.php?action=list |
| CRM | Externo | https://crm.tucarroconalejo.com |

**GitHub**: github.com/alejogah-oss/nexus-dm-bot (solo webhook/bot — el scheduler es local)

---

## Cuentas y credenciales (.env)

```
META_PAGE_ID=765862069934682
META_IG_USER_ID=17841476248130016
META_CATALOG_ID=1137133291627950
META_BUSINESS_ID=1975334699886381   # ⚠️ El catálogo es de BM 1551722759597838
META_PAGE_ACCESS_TOKEN=...          # ⚠️ Rotar — fue expuesto en chat
ANTHROPIC_API_KEY=...               # ⚠️ Rotar — fue expuesto en chat
CRM_WEBHOOK_URL=https://crm.tucarroconalejo.com/api/webhook/tucarro
CRM_WEBHOOK_KEY=crm-wh-k3y-2025-AutoXz9pLm
CRM_AGENT_CODE=alejo
VERIFY_TOKEN=nexus_alejo_2026
```

**Sesiones de browser guardadas:**
- `browser_session/fb_session.json` — tucarroconalejo@gmail.com (Marketplace)

---

## Parrilla de contenido (2 posts/día)

| Día | 12:00pm | 8:00pm |
|-----|---------|--------|
| Lun | inventory | tips |
| Mar | entrega | quote |
| Mié | tips | inventory |
| Jue | quote | new_car_day |
| Vie | new_car_day | inventory |
| Sáb | tips | quote |
| Dom | quote | tips |

---

## Reglas de contenido (ABSOLUTAS)
- NUNCA mencionar precios específicos del vehículo
- NUNCA prometer financiamiento sin confirmación
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

# Iniciar scheduler
pkill -f "main.py --schedule" 2>/dev/null
venv/bin/python3 main.py --schedule &

# Dashboard local
venv/bin/python3 -m http.server 8090 &
open http://localhost:8090/dashboard.html

# Marketplace (después de verificar identidad)
venv/bin/python3 marketplace_poster.py 137

# Renovar sesión de browser si expira
venv/bin/python3 fb_session.py
```

---

## Pendientes (en orden de prioridad)

- [ ] **Alejo verifica identidad** en Facebook Marketplace (cuenta tucarroconalejo@gmail.com)
- [ ] Correr `marketplace_poster.py 137` después de verificación
- [ ] Rotar ANTHROPIC_API_KEY y META_PAGE_ACCESS_TOKEN (expuestos en chat anterior)
- [ ] Verificar CRM_AGENT_CODE (`alejo`) en base de datos del CRM
- [ ] Activar comentarios: regenerar token con `pages_manage_metadata` + `instagram_business_manage_comments`
- [ ] Actualizar lex_bank.json con frases reales de Alejo
- [ ] Wire — notificación push HOT LEAD al teléfono
- [ ] LaunchAgent para scheduler 24/7
- [ ] Lens — primer reporte analytics (~julio 2026, 14 días de datos)
- [ ] Limpiar PNGs de debug del directorio (son temporales de la semana de setup)
