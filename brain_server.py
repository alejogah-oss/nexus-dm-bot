#!/usr/bin/env python3
"""
NEXUS Brain Server — WebSocket bridge for brain.html
Corre módulos REALES de NEXUS en paralelo y transmite eventos en vivo.

Servicios activos:
  ✅ main.py --now inventory    → Post real en Instagram + Facebook
  ✅ dm_bot.generate_reply()    → Genera respuesta real con Claude API
  ✅ crm_client.send_to_crm()  → POST real al CRM webhook
  ✅ comment_bot.generate...()  → Genera respuesta real a comentario
  ✅ Inventory CSV feed         → Fetch real del feed de 430 vehículos
  ❌ marketplace_poster.py      → Excluido (por decisión)
"""
import asyncio
import json
import os
import re
import csv as _csv
import sys
import aiohttp
import websockets
from datetime import datetime
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, '.env'))
sys.path.insert(0, BASE)

CLIENTS: set = set()
PORT = 8765


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def broadcast(ev: dict):
    if not CLIENTS:
        return
    msg = json.dumps(ev, ensure_ascii=False)
    await asyncio.gather(
        *[c.send(msg) for c in CLIENTS.copy()],
        return_exceptions=True
    )


async def emit(node=None, tool=None, status=None, msg='', log_type='thinking', module=''):
    await broadcast({
        'type': 'event', 'module': module,
        'node': node, 'tool': tool,
        'status': status, 'msg': msg,
        'log_type': log_type, 'ts': ts()
    })


# ── stdout → brain event mapping ──
PATTERNS = [
    (r'NEXUS Automation|@tucarroconalejo',
     dict(node='input', status='thinking', log_type='nexus')),
    (r'Tipo:\s*\S+',
     dict(node='tokenizer', status='thinking', log_type='thinking')),
    (r'Modelo: Toyota',
     dict(node='context', status='thinking', log_type='thinking')),
    (r'Promo del mes',
     dict(node='context', status='thinking', log_type='thinking')),
    (r'[Gg]enerando imagen|image_agent|generate_ai|jelly',
     dict(node='tools', tool='Agent', status='tool', log_type='tool')),
    (r'Imagen lista|fotos_cache|car_library|photo_path',
     dict(node='tools', tool='Read', status='tool', log_type='tool')),
    (r'[Rr]eview|[Aa]gency|nexus_agency',
     dict(node='reasoning', status='thinking', log_type='thinking')),
    (r'rechaz|[Rr]ejected',
     dict(node='output', status='complete', log_type='error')),
    (r'Vista previa|caption|copy',
     dict(node='reasoning', status='thinking', log_type='thinking')),
    (r'[Pp]ublicando|publish_content|upload_image|graph\.facebook|[Cc]arousel',
     dict(node='tools', tool='Meta API', status='tool', log_type='tool')),
    (r'Resultados:|ig_post_id|fb_post_id|publicado|post_id',
     dict(node='output', status='writing', log_type='writing')),
    (r'[Ee]rror|[Ee]xcepci|abortado|Traceback|❌',
     dict(node=None, status=None, log_type='error')),
    (r'✅|éxito|success\b|completado',
     dict(node='output', status='complete', log_type='complete')),
]


def classify(line: str) -> dict:
    for pat, base in PATTERNS:
        if re.search(pat, line):
            ev = {**base}
            ev.setdefault('node', None)
            ev.setdefault('tool', None)
            ev.setdefault('status', None)
            ev.setdefault('log_type', 'thinking')
            return ev
    return dict(node=None, tool=None, status=None, log_type='thinking')


# ════════════════════════════════════════════════════════════
#  MÓDULO 1: main.py --now inventory  (post real a Meta)
# ════════════════════════════════════════════════════════════

async def run_inventory_post():
    python = os.path.join(BASE, 'venv', 'bin', 'python3')
    label = 'main.py'

    await emit(node='input', status='thinking', log_type='nexus', module=label,
               msg='▸ [MAIN] Iniciando post de inventario...')

    try:
        proc = await asyncio.create_subprocess_exec(
            python, 'main.py', '--now', 'inventory',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=BASE,
        )
        async for raw in proc.stdout:
            line = raw.decode('utf-8', errors='replace').rstrip()
            if not line or re.match(r'^=+$', line):
                continue
            ev = classify(line)
            await broadcast({
                'type': 'event', 'module': label,
                'msg': f'[MAIN] {line}',
                'ts': ts(), **ev
            })

        await proc.wait()
        rc = proc.returncode
        await emit(module=label, log_type='complete' if rc == 0 else 'error',
                   msg=f'✓ [MAIN] Post terminado (exit {rc})',
                   node='output', status='complete' if rc == 0 else None)

    except Exception as e:
        await emit(module=label, log_type='error', msg=f'❌ [MAIN] {e}')


# ════════════════════════════════════════════════════════════
#  MÓDULO 2: DM Bot — generate_reply() con Claude real
# ════════════════════════════════════════════════════════════

async def run_dm_bot_test():
    label = 'DM Bot'

    await emit(node='input', status='thinking', log_type='nexus', module=label,
               msg='▸ [DM BOT] Iniciando prueba real de respuesta...')
    await asyncio.sleep(0.5)

    # Simula un DM entrante real
    test_message = '¿Tienen RAV4 2024 disponible? Necesito algo familiar y buen gas mileage'
    await emit(node='tokenizer', status='thinking', log_type='thinking', module=label,
               msg=f'▸ [DM BOT] Mensaje recibido: "{test_message}"')
    await asyncio.sleep(0.3)

    await emit(node='context', status='thinking', log_type='thinking', module=label,
               msg='▸ [DM BOT] Cargando voz del bot y reglas de negocio...')

    await emit(node='reasoning', tool='Agent', status='tool', log_type='tool', module=label,
               msg='▸ [DM BOT] Llamando Claude API (claude-sonnet-4-6, max 160 tokens)...')

    loop = asyncio.get_event_loop()
    try:
        def _sync_generate():
            from dm_bot import generate_reply
            return generate_reply([], test_message)

        reply, is_hot = await loop.run_in_executor(None, _sync_generate)

        hot_tag = ' [🔥 HOT LEAD detectado]' if is_hot else ''
        await emit(node='output', status='writing', log_type='writing', module=label,
                   msg=f'▸ [DM BOT] Respuesta generada{hot_tag}:')
        await emit(node='output', status='writing', log_type='complete', module=label,
                   msg=f'  → "{reply}"')

        if is_hot:
            await emit(node='tools', tool='CRM', status='tool', log_type='tool', module=label,
                       msg='▸ [DM BOT] HOT LEAD → notificando CRM...')

    except Exception as e:
        await emit(module=label, log_type='error', msg=f'❌ [DM BOT] {str(e)[:120]}')

    await emit(module=label, log_type='complete',
               msg='✓ [DM BOT] Test completado', node='output')


# ════════════════════════════════════════════════════════════
#  MÓDULO 3: CRM — send_to_crm() con lead de prueba real
# ════════════════════════════════════════════════════════════

async def run_crm_test():
    label = 'CRM'

    await emit(node='input', status='thinking', log_type='nexus', module=label,
               msg='▸ [CRM] Iniciando sync de lead de prueba...')
    await asyncio.sleep(0.3)

    await emit(node='context', status='thinking', log_type='thinking', module=label,
               msg='▸ [CRM] Preparando datos del lead...')

    await emit(node='tools', tool='CRM', status='tool', log_type='tool', module=label,
               msg='▸ [CRM] POST → crm.tucarroconalejo.com/api/webhook/tucarro')

    loop = asyncio.get_event_loop()
    try:
        def _sync_crm():
            from crm_client import send_to_crm
            test_lead = {
                'name':     'Test Brain NEXUS',
                'phone':    '(954) 555-0001',
                'email':    '',
                'model':    'RAV4 2024',
                'platform': 'brain_test',
                'sender_id': 'brain_test_001',
            }
            return send_to_crm(test_lead, conversation_summary='[BRAIN TEST] Lead generado por prueba de sistema')

        result = await loop.run_in_executor(None, _sync_crm)

        status_code = result.get('status_code', result.get('status', '?'))
        ok = str(status_code).startswith('2') or result.get('ok') or result.get('success')
        emoji = '✅' if ok else '⚠️'
        await emit(node='memory', status='thinking', log_type='complete' if ok else 'error',
                   module=label,
                   msg=f'▸ [CRM] Response: {emoji} HTTP {status_code} — {str(result)[:80]}')

    except Exception as e:
        await emit(module=label, log_type='error', msg=f'❌ [CRM] {str(e)[:120]}')

    await emit(module=label, log_type='complete',
               msg='✓ [CRM] Sync completado', node='output')


# ════════════════════════════════════════════════════════════
#  MÓDULO 4: Comment Bot — genera respuesta real a comentario
# ════════════════════════════════════════════════════════════

async def run_comment_bot_test():
    label = 'Comment Bot'

    await emit(node='input', status='thinking', log_type='nexus', module=label,
               msg='▸ [COMMENT BOT] Iniciando prueba de respuesta a comentario...')
    await asyncio.sleep(0.4)

    test_comment = '¿Cuánto sale mensual el Camry? 🙏'
    await emit(node='tokenizer', status='thinking', log_type='thinking', module=label,
               msg=f'▸ [COMMENT BOT] Comentario: "{test_comment}"')

    await emit(node='reasoning', tool='Agent', status='tool', log_type='tool', module=label,
               msg='▸ [COMMENT BOT] Generando respuesta con Claude...')

    loop = asyncio.get_event_loop()
    try:
        def _sync_comment():
            from comment_bot import generate_comment_reply
            return generate_comment_reply(test_comment, post_context='Post de inventario Camry 2024')

        reply = await loop.run_in_executor(None, _sync_comment)

        await emit(node='output', status='writing', log_type='writing', module=label,
                   msg=f'▸ [COMMENT BOT] Respuesta:')
        await emit(node='output', status='writing', log_type='complete', module=label,
                   msg=f'  → "{reply}"')

    except Exception as e:
        await emit(module=label, log_type='error', msg=f'❌ [COMMENT BOT] {str(e)[:120]}')

    await emit(module=label, log_type='complete',
               msg='✓ [COMMENT BOT] Test completado')


# ════════════════════════════════════════════════════════════
#  MÓDULO 5: Inventory CSV feed (lectura real)
# ════════════════════════════════════════════════════════════

async def run_inventory_check():
    label = 'Inventory'

    await emit(node='input', status='thinking', log_type='nexus', module=label,
               msg='▸ [INVENTORY] Fetching live CSV feed...')
    await asyncio.sleep(0.2)

    feed_url = 'https://bot.tucarroconalejo.com/feed/vehicles.csv'
    await emit(node='tools', tool='Read', status='tool', log_type='tool', module=label,
               msg=f'▸ [INVENTORY] GET {feed_url}')

    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(feed_url,
                             timeout=aiohttp.ClientTimeout(total=12),
                             headers={'User-Agent': 'NEXUS-Brain/1.0'}) as r:
                text = await r.text(encoding='utf-8', errors='replace')
                lines = text.strip().splitlines()
                count = max(0, len(lines) - 1)

                await emit(node='context', status='thinking', log_type='thinking',
                           module=label,
                           msg=f'▸ [INVENTORY] {count} vehículos activos en feed')

                if len(lines) > 1:
                    reader = _csv.DictReader(lines)
                    models: dict = {}
                    for row in reader:
                        m = (row.get('model') or row.get('Model') or
                             row.get('title') or row.get('Title') or '').strip()
                        yr = (row.get('year') or row.get('Year') or '').strip()
                        if m:
                            models[m] = yr

                    sample = list(models.items())[:5]
                    txt = ', '.join(f"{yr} {m}" if yr else m for m, yr in sample)
                    await emit(node='reasoning', status='thinking', log_type='thinking',
                               module=label, msg=f'▸ [INVENTORY] Muestra: {txt}...')

        except Exception as e:
            await emit(module=label, log_type='error',
                       msg=f'❌ [INVENTORY] {str(e)[:80]}')

    await emit(module=label, log_type='complete',
               msg='✓ [INVENTORY] Feed check completado', node='output')


# ════════════════════════════════════════════════════════════
#  MÓDULO 6: DM Bot webhook health check (Render)
# ════════════════════════════════════════════════════════════

async def run_webhook_check():
    label = 'Webhook'

    await emit(node='tools', tool='DM Bot', status='tool', log_type='tool', module=label,
               msg='▸ [WEBHOOK] Verificando DM Bot en Render.com...')

    async with aiohttp.ClientSession() as s:
        try:
            async with s.get('https://bot.tucarroconalejo.com/webhook',
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                emoji = '✅' if r.status < 400 else '⚠️'
                await emit(node='output', status='thinking', log_type='thinking',
                           module=label,
                           msg=f'▸ [WEBHOOK] bot.tucarroconalejo.com: HTTP {r.status} {emoji}')
        except Exception as e:
            await emit(module=label, log_type='error',
                       msg=f'❌ [WEBHOOK] {str(e)[:80]}')

    await emit(module=label, log_type='complete',
               msg='✓ [WEBHOOK] Health check completado')


# ════════════════════════════════════════════════════════════
#  ORQUESTADOR: corre todos los módulos en paralelo
# ════════════════════════════════════════════════════════════

async def run_all():
    await broadcast({
        'type': 'start_all',
        'msg':  '🚀 NEXUS — todos los sistemas arrancando en paralelo',
        'log_type': 'nexus',
        'ts': ts()
    })

    await asyncio.gather(
        run_inventory_post(),       # Real: post a Instagram/Facebook
        run_dm_bot_test(),          # Real: genera reply con Claude API
        run_crm_test(),             # Real: POST lead al CRM webhook
        run_comment_bot_test(),     # Real: genera respuesta comentario con Claude
        run_inventory_check(),      # Real: fetch CSV feed
        run_webhook_check(),        # Real: ping al bot en Render
    )

    await broadcast({
        'type': 'all_done',
        'msg':  '✓ Todos los sistemas completados',
        'log_type': 'complete',
        'ts': ts()
    })


# ════════════════════════════════════════════════════════════
#  WebSocket handler
# ════════════════════════════════════════════════════════════

async def handler(ws):
    CLIENTS.add(ws)
    print(f'[{ts()}] Cliente conectado ({len(CLIENTS)} activos)')

    await ws.send(json.dumps({
        'type': 'connected',
        'msg':  'NEXUS Brain Server v1.0 — online ✅',
        'log_type': 'nexus',
        'ts': ts()
    }))

    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
                cmd  = data.get('cmd')
                if cmd == 'run_all':
                    asyncio.create_task(run_all())
                elif cmd == 'ping':
                    await ws.send(json.dumps({'type': 'pong', 'ts': ts()}))
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.discard(ws)
        print(f'[{ts()}] Cliente desconectado ({len(CLIENTS)} activos)')


async def main():
    print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    print('  NEXUS Brain Server v1.0')
    print(f'  ws://localhost:{PORT}')
    print()
    print('  Servicios reales:')
    print('  ✅ main.py --now inventory (post Meta)')
    print('  ✅ DM Bot generate_reply() (Claude API)')
    print('  ✅ CRM send_to_crm() (webhook real)')
    print('  ✅ Comment Bot generate_reply() (Claude)')
    print('  ✅ Inventory CSV feed (430 vehículos)')
    print('  ✅ DM Bot webhook health (Render)')
    print('  ❌ Marketplace (excluido)')
    print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    async with websockets.serve(handler, 'localhost', PORT):
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())
