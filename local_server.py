"""
NEXUS Local Server — Dashboard + API de citas.
Corre en el Mac de Alejo en puerto 8090.
Accesible desde el celular en la misma WiFi: http://<IP-del-Mac>:8090
"""
import os
import json
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from appointments import confirm_appointment, cancel_appointment, _load
from marketplace_analytics import get_stats_ranked, get_summary

PORT = 8090
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "localhost"


class NexusHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # silenciar logs repetitivos

    def do_GET(self):
        # API: confirmar cita
        if self.path.startswith("/api/confirm/"):
            appt_id = self.path.split("/api/confirm/")[1].strip("/")
            ok = confirm_appointment(appt_id)
            self._json({"ok": ok, "id": appt_id})

        # API: cancelar cita
        elif self.path.startswith("/api/cancel/"):
            appt_id = self.path.split("/api/cancel/")[1].strip("/")
            ok = cancel_appointment(appt_id)
            self._json({"ok": ok, "id": appt_id})

        # API: lista de citas
        elif self.path == "/api/appointments":
            appointments = _load()
            self._json(appointments)

        # API: marketplace analytics
        elif self.path == "/api/marketplace-stats":
            self._json(get_stats_ranked())

        elif self.path == "/api/marketplace-summary":
            self._json(get_summary())

        # Archivos estáticos (dashboard.html, posts_log.json, etc.)
        else:
            super().do_GET()

    def _json(self, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    local_ip = _get_local_ip()
    server = HTTPServer(("0.0.0.0", PORT), NexusHandler)
    print(f"[NEXUS] Dashboard corriendo:")
    print(f"  Mac:      http://localhost:{PORT}")
    print(f"  Celular:  http://{local_ip}:{PORT}   (misma WiFi)")
    server.serve_forever()
