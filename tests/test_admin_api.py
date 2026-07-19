import json, os
from pathlib import Path
os.environ["SCANNER_KEY"] = "testkey"
import scanner_api, admin_api

def _car(tmp_path, slug="2019-Civic-004352", **extra):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    folder = Path(tmp_path) / slug
    (folder / "photos").mkdir(parents=True)
    data = {"vin": "1HGCM82633A004352", "yr": "2019", "make": "Honda",
            "model": "Civic", "trim": "EX", "color": "Blue", "price": 16500,
            "mileage": 45000, "title": "2019 Honda Civic EX", "description": "d"}
    data.update(extra)
    (folder / "listing.json").write_text(json.dumps(data))
    (folder / "photos" / "01.jpg").write_bytes(b"a")
    return folder

def test_read_status_defaults(tmp_path):
    folder = _car(tmp_path)
    st = admin_api.read_status(folder)
    assert st == {"published": False, "published_at": None, "last_error": None}

def test_set_status_persists(tmp_path):
    folder = _car(tmp_path)
    admin_api.set_status(folder, published=True, published_at="2026-07-19 10:00")
    st = admin_api.read_status(folder)
    assert st["published"] is True and st["published_at"] == "2026-07-19 10:00"
    # no borra los datos originales del carro
    data = json.loads((folder / "listing.json").read_text())
    assert data["make"] == "Honda" and data["price"] == 16500

from flask import Flask
from unittest.mock import patch

app = Flask(__name__); app.register_blueprint(admin_api.admin_bp)
cl = app.test_client()
H = {"X-Scanner-Key": "testkey"}

def test_inventory_lista_con_estado(tmp_path):
    _car(tmp_path)
    r = cl.get("/api/admin/inventory", headers=H)
    assert r.status_code == 200
    it = r.json["items"][0]
    assert it["make"] == "Honda" and it["published"] is False and it["photos"] == 1
    assert r.json["publishing"] is None

def test_inventory_auth_401(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    assert cl.get("/api/admin/inventory").status_code == 401

def test_publish_lanza_y_bloquea(tmp_path):
    _car(tmp_path)
    admin_api._lock_file().unlink(missing_ok=True)
    with patch.object(admin_api, "_launch_publish", return_value=os.getpid()) as lp:
        r = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r.status_code == 200 and r.json["ok"] is True
        lp.assert_called_once_with("2019-Civic-004352")
        # segundo intento mientras el PID sigue vivo → 409
        r2 = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r2.status_code == 409
    admin_api._lock_file().unlink(missing_ok=True)

def test_publish_slug_inexistente_404(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    admin_api._lock_file().unlink(missing_ok=True)
    assert cl.post("/api/admin/publish/noexiste", headers=H).status_code == 404

def test_lock_muerto_se_limpia(tmp_path):
    _car(tmp_path)
    with patch.object(admin_api, "_launch_publish", return_value=2147480000):  # PID muerto
        r = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r.status_code == 200
        r2 = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r2.status_code == 200  # el lock anterior estaba muerto → se reintenta
    admin_api._lock_file().unlink(missing_ok=True)

def test_mark_publicado(tmp_path):
    folder = _car(tmp_path)
    r = cl.post("/api/admin/mark/2019-Civic-004352", headers=H)
    assert r.status_code == 200 and r.json["published"] is True and r.json["published_at"]
    assert admin_api.read_status(folder)["published"] is True
    assert not admin_api._lock_file().exists()

# ── Bugs de review sobre el lock "un carro a la vez" ────────────────

def test_mark_no_borra_lock_de_otro_carro(tmp_path):
    # Bug 1: admin_mark borraba el lock incondicionalmente, incluso si
    # pertenecía a OTRO carro en publicación activa.
    _car(tmp_path, slug="2019-Civic-004352")
    _car(tmp_path, slug="2020-Accord-005555")
    admin_api._lock_file().unlink(missing_ok=True)
    with patch.object(admin_api, "_launch_publish", return_value=os.getpid()):
        r = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r.status_code == 200
        # mark de B (otro carro) mientras A publica: NO debe tocar el lock de A
        rm_b = cl.post("/api/admin/mark/2020-Accord-005555", headers=H)
        assert rm_b.status_code == 200
        assert admin_api._lock_file().exists()
        # publish de A sigue bloqueado — el lock de A sigue vivo
        r2 = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r2.status_code == 409
        # mark del propio carro A sí libera su lock
        rm_a = cl.post("/api/admin/mark/2019-Civic-004352", headers=H)
        assert rm_a.status_code == 200
        assert not admin_api._lock_file().exists()
    admin_api._lock_file().unlink(missing_ok=True)

def test_pid_no_numerico_no_rompe_inventory(tmp_path):
    # Bug 2: pid no numérico en un lock JSON válido causaba 500 (ValueError
    # sin capturar) en vez de auto-limpiarse como el JSON corrupto.
    _car(tmp_path)
    admin_api._lock_file().write_text(json.dumps({"slug": "x", "pid": "abc"}))
    r = cl.get("/api/admin/inventory", headers=H)
    assert r.status_code == 200
    assert r.json["publishing"] is None
    assert not admin_api._lock_file().exists()

def test_pid_invalido_no_bloquea_para_siempre(tmp_path):
    # Bug 3: os.kill(pid, 0) con pid <= 0 no lanza excepción, así que un
    # lock con pid -1/0 se interpretaba como "vivo" para siempre.
    _car(tmp_path)
    admin_api._lock_file().write_text(json.dumps({"slug": "x", "pid": -1}))
    with patch.object(admin_api, "_launch_publish", return_value=os.getpid()):
        r = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r.status_code == 200  # no 409 perpetuo
    admin_api._lock_file().unlink(missing_ok=True)

# ── FIX 1 (review final): race del lock — check-then-write no atómico ──

def test_publish_mutex_existe_y_serializa_seccion_critica(tmp_path):
    import threading
    # el mutex a nivel de módulo debe existir y ser un lock real
    assert isinstance(admin_api._PUBLISH_MUTEX, type(threading.Lock()))
    _car(tmp_path)
    admin_api._lock_file().unlink(missing_ok=True)
    with patch.object(admin_api, "_launch_publish", return_value=os.getpid()):
        # dos publish secuenciales bajo el mutex: el primero pasa, el segundo
        # ve el lock ya escrito y devuelve 409 (no dos Chrome lanzados)
        r1 = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r1.status_code == 200
        r2 = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
        assert r2.status_code == 409
    admin_api._lock_file().unlink(missing_ok=True)

def test_publish_slug_inexistente_404_no_toma_mutex_bloqueado(tmp_path):
    # el 404 de slug inexistente debe devolverse ANTES de tomar el mutex,
    # incluso si el mutex está tomado por otro hilo.
    scanner_api.INVENTORY_DIR = str(tmp_path)
    admin_api._lock_file().unlink(missing_ok=True)
    assert admin_api._PUBLISH_MUTEX.acquire(blocking=False)
    try:
        r = cl.post("/api/admin/publish/noexiste", headers=H)
        assert r.status_code == 404
    finally:
        admin_api._PUBLISH_MUTEX.release()
