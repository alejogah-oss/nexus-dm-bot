"""Gunicorn config — NEXUS webhook server."""
import os

workers = 1       # Un solo worker para que el marketplace bot no se duplique
threads  = 4      # Threads por worker para concurrencia en requests
timeout  = 120
bind     = f"0.0.0.0:{os.getenv('PORT', '5001')}"


def post_fork(server, worker):
    """Arranca servicios de fondo en el worker después del fork."""
    from webhook_server import _keep_alive, _start_marketplace_bot
    _keep_alive()
    _start_marketplace_bot()
