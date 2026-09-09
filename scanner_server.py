"""Servidor liviano SOLO del VIN Scanner — para correr en el MacBook Pro.

No importa dm_bot, comment_bot ni marketplace: solo los endpoints del scanner
y la PWA estática. Inventario persistente vía INVENTORY_DIR (disco del Pro).
Arranca: venv/bin/python3 scanner_server.py  (puerto env SCANNER_PORT, default 8770)
"""
import os
from pathlib import Path
from flask import Flask, send_file
from dotenv import load_dotenv

load_dotenv()

from scanner_api import bp as scanner_bp
from admin_api import admin_bp

app = Flask(__name__)
app.register_blueprint(scanner_bp)
app.register_blueprint(admin_bp)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # video walkaround

_HERE = Path(__file__).parent


@app.get("/scanner")
def scanner_pwa():
    return send_file(_HERE / "static/scanner/index.html")


@app.get("/static/scanner/<path:filename>")
def scanner_static(filename):
    return send_file(_HERE / "static/scanner" / filename)


@app.get("/admin")
def admin_panel():
    return send_file(_HERE / "static/admin/index.html")


@app.get("/static/admin/<path:filename>")
def admin_static(filename):
    return send_file(_HERE / "static/admin" / filename)


@app.get("/health")
def health():
    return {"ok": True, "inventory_dir": os.environ.get("INVENTORY_DIR", "default")}


if __name__ == "__main__":
    port = int(os.environ.get("SCANNER_PORT", "8770"))
    cert = os.environ.get("SCANNER_CERT")
    key = os.environ.get("SCANNER_KEY_FILE")
    # Con cert/key (Tailscale) → HTTPS en toda la tailnet (cámara del iPhone OK).
    # Sin ellos → HTTP local para pruebas.
    if cert and key and os.path.exists(cert) and os.path.exists(key):
        app.run(host="0.0.0.0", port=port, ssl_context=(cert, key))
    else:
        app.run(host="127.0.0.1", port=port)
