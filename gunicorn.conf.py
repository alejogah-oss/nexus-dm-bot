"""Gunicorn config — NEXUS webhook server."""
import os

workers     = 1      # Un solo worker — el marketplace bot no se duplica
threads     = 4      # Threads para concurrencia en requests
timeout     = 120
preload_app = False  # Cada worker importa el módulo fresco (threads nacen en el worker)
bind        = f"0.0.0.0:{os.getenv('PORT', '5001')}"
