import json, os
from pathlib import Path
from unittest.mock import patch, MagicMock
os.environ["SCANNER_KEY"] = "testkey"
import scanner_api, admin_api
from flask import Flask

app = Flask(__name__)
app.register_blueprint(admin_api.admin_bp)
app.register_blueprint(scanner_api.bp)
cl = app.test_client()
H = {"X-Scanner-Key": "testkey"}

def _car(tmp_path, slug="2019-Civic-004352", vin="1HGCM82633A004352", **extra):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    folder = Path(tmp_path) / slug
    (folder / "photos").mkdir(parents=True)
    data = {"vin": vin, "yr": "2019", "make": "Honda", "model": "Civic",
            "color": "Blue", "price": 16500, "mileage": 45000,
            "title": "2019 Honda Civic", "description": "d"}
    data.update(extra)
    (folder / "listing.json").write_text(json.dumps(data))
    return folder

def _data(folder):
    return json.loads((folder / "listing.json").read_text())

def _ok_resp():
    r = MagicMock(); r.json.return_value = {"ok": True}; r.raise_for_status.return_value = None
    return r

def test_inactivar_borra_del_sitio_y_marca(tmp_path):
    folder = _car(tmp_path, site_id=8170, site_synced=True)
    with patch.object(admin_api.site_publisher, "SITE_ADMIN_PASSWORD", "pw"), \
         patch.object(admin_api.requests, "post", return_value=_ok_resp()) as post:
        r = cl.post("/api/admin/inactivate/2019-Civic-004352", headers=H)
    assert r.status_code == 200 and r.json["removed_from_site"] is True
    assert post.call_args.kwargs["json"] == {"id": 8170}
    assert "action=delete" in post.call_args.args[0]
    d = _data(folder)
    assert d["inactive"] is True and d["inactive_at"]
    assert "site_id" not in d and d["site_id_removed"] == 8170

def test_inactivar_sin_site_id_no_llama_al_sitio(tmp_path):
    folder = _car(tmp_path)
    with patch.object(admin_api.requests, "post") as post:
        r = cl.post("/api/admin/inactivate/2019-Civic-004352", headers=H)
    assert r.status_code == 200 and not post.called
    assert _data(folder)["inactive"] is True

def test_si_el_sitio_falla_no_queda_inactivo(tmp_path):
    folder = _car(tmp_path, site_id=8170)
    with patch.object(admin_api.site_publisher, "SITE_ADMIN_PASSWORD", "pw"), \
         patch.object(admin_api.requests, "post", side_effect=Exception("timeout")):
        r = cl.post("/api/admin/inactivate/2019-Civic-004352", headers=H)
    assert r.status_code == 502
    d = _data(folder)
    assert not d.get("inactive") and d["site_id"] == 8170

def test_no_se_publica_un_inactivo(tmp_path):
    _car(tmp_path, inactive=True)
    with patch.object(admin_api, "_launch_publish") as launch:
        r = cl.post("/api/admin/publish/2019-Civic-004352", headers=H)
    assert r.status_code == 409 and not launch.called

def test_editar_un_inactivo_no_lo_resube_al_sitio(tmp_path):
    _car(tmp_path, inactive=True)
    with patch.object(scanner_api, "_sync_to_site_bg") as sync:
        r = cl.put("/api/scanner/inventory/2019-Civic-004352", headers=H, json={"price": 15000})
    assert r.status_code == 200 and not sync.called

def test_reactivar_limpia_y_resube_como_pendiente(tmp_path):
    folder = _car(tmp_path, inactive=True, inactive_at="x", site_id_removed=8170)
    with patch.object(scanner_api, "_sync_to_site_bg") as sync:
        r = cl.post("/api/admin/reactivate/2019-Civic-004352", headers=H)
    assert r.status_code == 200 and sync.called
    d = _data(folder)
    assert "inactive" not in d and "site_id" not in d

def test_inventario_expone_inactivo(tmp_path):
    _car(tmp_path, inactive=True, inactive_at="2026-10-02 10:00")
    it = cl.get("/api/admin/inventory", headers=H).json["items"][0]
    assert it["inactive"] is True and it["inactive_at"] == "2026-10-02 10:00"

def test_cuadrar_lote_vin_completo_y_ultimos_6(tmp_path):
    _car(tmp_path, "a", vin="1HGCM82633A004352")
    _car(tmp_path, "b", vin="JTDBCMFE1R3012345")
    _car(tmp_path, "c", vin="5TDKZ3DC8PS999888")
    _car(tmp_path, "d", vin="4T1G11AK0RU777666", inactive=True)  # ya inactivo: no se lista
    texto = "1HGCM82633A004352\n012345 TUNDRA\n123123"
    r = cl.post("/api/admin/reconcile", headers=H, json={"vins": texto})
    assert r.status_code == 200
    assert [m["slug"] for m in r.json["missing"]] == ["c"]
    assert r.json["not_scanned"] == ["123123"]

def test_cuadrar_sin_vins_es_400(tmp_path):
    _car(tmp_path)
    r = cl.post("/api/admin/reconcile", headers=H, json={"vins": "hola TUNDRA"})
    assert r.status_code == 400

def test_cuadrar_avisa_inactivo_que_sigue_en_el_lote(tmp_path):
    _car(tmp_path, "d", vin="4T1G11AK0RU777666", inactive=True)
    r = cl.post("/api/admin/reconcile", headers=H, json={"vins": "777666"})
    assert [b["slug"] for b in r.json["back_in_lot"]] == ["d"]
    assert r.json["missing"] == [] and r.json["not_scanned"] == []
