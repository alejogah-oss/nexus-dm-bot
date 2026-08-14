"""
NEXUS Local Server — Dashboard + API de citas + Leads CRM.
Corre en el Mac de Alejo en puerto 8090.
Accesible desde el celular en la misma WiFi: http://<IP-del-Mac>:8090
"""
import os
import json
import socket
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from appointments import confirm_appointment, cancel_appointment, _load
from marketplace_analytics import get_stats_ranked, get_summary
from metrics_agent import refresh_metrics, get_cached
from lens_report import generate as lens_generate, latest_report_path

PORT = 8090
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVENTS_FILE = os.path.join(BASE_DIR, "nexus_events.json")


def _load_events() -> list:
    try:
        with open(EVENTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_events(events: list) -> None:
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def delete_lead(ts: str) -> bool:
    events = _load_events()
    filtered = [e for e in events if e.get("ts") != ts]
    if len(filtered) < len(events):
        _save_events(filtered)
        return True
    return False


def toggle_followup(ts: str) -> bool:
    events = _load_events()
    for e in events:
        if e.get("ts") == ts:
            e["followed_up"] = not e.get("followed_up", False)
            _save_events(events)
            return True
    return False


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
        path = self.path.split("?")[0]  # strip query params

        # API: confirmar cita
        if path.startswith("/api/confirm/"):
            appt_id = path.split("/api/confirm/")[1].strip("/")
            ok = confirm_appointment(appt_id)
            self._json({"ok": ok, "id": appt_id})

        # API: cancelar cita
        elif path.startswith("/api/cancel/"):
            appt_id = path.split("/api/cancel/")[1].strip("/")
            ok = cancel_appointment(appt_id)
            self._json({"ok": ok, "id": appt_id})

        # API: lista de citas
        elif path == "/api/appointments":
            appointments = _load()
            self._json(appointments)

        # API: marketplace analytics
        elif path == "/api/marketplace-stats":
            self._json(get_stats_ranked())

        elif path == "/api/marketplace-summary":
            self._json(get_summary())

        # API: métricas de engagement (caché local, actualiza desde Meta)
        elif path == "/api/metrics":
            self._json(get_cached())

        elif path == "/api/metrics/refresh":
            self._json(refresh_metrics())

        # API: leads CRM (nexus_events.json)
        elif path == "/api/leads":
            self._json(_load_events())

        # API: reporte Lens — abre en browser (HTML inline) o descarga
        elif path == "/api/lens-report/latest":
            report_path = latest_report_path()
            if not report_path:
                _, report_path = lens_generate(save=True)
            self._html_file(report_path)

        elif path == "/api/lens-report/generate":
            _, report_path = lens_generate(save=True)
            self._html_file(report_path)

        # Archivos estáticos (dashboard.html, posts_log.json, etc.)
        else:
            super().do_GET()

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/leads/"):
            ts = urllib.parse.unquote(path.split("/api/leads/")[1].strip("/"))
            ok = delete_lead(ts)
            self._json({"ok": ok, "ts": ts})
        else:
            self.send_response(404)
            self.end_headers()

    def do_PATCH(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/leads/") and path.endswith("/followup"):
            ts = urllib.parse.unquote(
                path.split("/api/leads/")[1].replace("/followup", "").strip("/")
            )
            ok = toggle_followup(ts)
            self._json({"ok": ok, "ts": ts})
        else:
            self.send_response(404)
            self.end_headers()

    def _html_file(self, file_path: str):
        try:
            with open(file_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

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
