import os
os.environ["SCANNER_KEY"] = "testkey"
import scanner_server

c = scanner_server.app.test_client()

def test_admin_page_sirve():
    r = c.get("/admin")
    assert r.status_code == 200 and b"ADMINISTRADOR" in r.data

def test_admin_static_sirve():
    assert c.get("/static/admin/admin.js").status_code == 200

def test_admin_api_registrado_y_protegido():
    # blueprint montado: sin clave → 401 (no 404)
    assert c.get("/api/admin/inventory").status_code == 401
