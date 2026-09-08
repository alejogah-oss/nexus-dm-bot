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
