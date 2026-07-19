import io, json, os
from unittest.mock import patch
os.environ["SCANNER_KEY"] = "testkey"
import scanner_api
from flask import Flask

app = Flask(__name__); app.register_blueprint(scanner_api.bp)
c = app.test_client()
H = {"X-Scanner-Key": "testkey"}

def test_auth_required():
    assert c.post("/api/scanner/vin").status_code == 401

def test_vin_endpoint():
    with patch.object(scanner_api, "_ocr", return_value="1HGCM82633A004352"), \
         patch.object(scanner_api, "decode_vin", return_value={"yr": "2003", "model": "Accord"}):
        r = c.post("/api/scanner/vin", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "vin.jpg")})
    assert r.status_code == 200 and r.json["valid"] is True and r.json["car"]["yr"] == "2003"

def test_odometer_endpoint():
    with patch.object(scanner_api, "_ocr", return_value="42,350"):
        r = c.post("/api/scanner/odometer", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "odo.jpg")})
    assert r.json["mileage"] == 42350

def test_listing_endpoint():
    fake = json.dumps({"title": "2021 Toyota Corolla SE", "description": "desc"})
    with patch.object(scanner_api, "_copy_call", return_value=fake):
        r = c.post("/api/scanner/listing", headers=H,
                   json={"yr": "2021", "make": "Toyota", "model": "Corolla", "trim": "SE",
                         "engine": "", "fuel": "", "body": "", "drive": "",
                         "mileage": 42000, "price": 17500, "notes": ""})
    assert r.json["title"].startswith("2021")

def test_inventory_saves(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    data = {"vin": "1HGCM82633A004352", "yr": "2021", "model": "Corolla", "trim": "SE",
            "color": "Blanco", "price": 17500, "mileage": 42000,
            "title": "t", "description": "d", "notes": ""}
    r = c.post("/api/scanner/inventory", headers=H, data={
        "data": json.dumps(data),
        "photos": [(io.BytesIO(b"a"), "1.jpg"), (io.BytesIO(b"b"), "2.jpg")],
        "video": (io.BytesIO(b"v"), "walk.mp4")})
    folder = tmp_path / r.json["folder"].split("/")[-1]
    assert (folder / "listing.json").exists() and (folder / "photos" / "01.jpg").exists() \
        and (folder / "video.mp4").exists() and (folder / "copy.md").exists()

def test_auth_fails_closed_without_env_key():
    with patch.dict(os.environ):
        del os.environ["SCANNER_KEY"]
        r = c.post("/api/scanner/vin", headers=H)
        r2 = c.post("/api/scanner/vin")  # sin header tampoco pasa (None != None)
    assert r.status_code == 401 and r2.status_code == 401

def test_listing_title_truncated_100():
    fake = json.dumps({"title": "X" * 150, "description": "d"})
    with patch.object(scanner_api, "_copy_call", return_value=fake):
        r = c.post("/api/scanner/listing", headers=H,
                   json={"yr": "2021", "make": "Toyota", "model": "Corolla", "trim": "",
                         "engine": "", "fuel": "", "body": "", "drive": "",
                         "mileage": 42000, "price": 17500, "notes": ""})
    assert len(r.json["title"]) == 100

def test_listing_missing_keys_400():
    r = c.post("/api/scanner/listing", headers=H, json={"yr": "2021"})
    assert r.status_code == 400 and "faltan campos" in r.json["error"]

def test_vin_retry_con_sonnet_cuando_haiku_falla():
    # Haiku devuelve basura → el endpoint reintenta con Sonnet y logra VIN válido
    with patch.object(scanner_api, "_ocr", side_effect=["XXXX", "1HGCM82633A004352"]) as ocr, \
         patch.object(scanner_api, "decode_vin", return_value={"yr": "2003"}):
        r = c.post("/api/scanner/vin", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "vin.jpg")})
    assert r.status_code == 200 and r.json["valid"] is True
    assert ocr.call_count == 2
    assert ocr.call_args_list[1].kwargs.get("model") == scanner_api.COPY_MODEL

def test_vin_ocr_con_confusion_se_repara():
    # OCR lee B donde había 8 — repair_vin lo corrige sin segunda llamada
    with patch.object(scanner_api, "_ocr", return_value="1HGCMB2633A004352") as ocr, \
         patch.object(scanner_api, "decode_vin", return_value={}):
        r = c.post("/api/scanner/vin", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "vin.jpg")})
    assert r.json["vin"] == "1HGCM82633A004352" and r.json["valid"] is True
    assert ocr.call_count == 1

def test_vin_decode_directo():
    with patch.object(scanner_api, "decode_vin", return_value={"yr": "2003", "model": "Accord"}):
        r = c.post("/api/scanner/vin-decode", headers=H, json={"vin": "1hgcm82633a004352"})
    assert r.status_code == 200 and r.json["valid"] is True and r.json["car"]["yr"] == "2003"

def test_vin_decode_sin_vin_400():
    assert c.post("/api/scanner/vin-decode", headers=H, json={}).status_code == 400

def test_vin_missing_photo_400():
    assert c.post("/api/scanner/vin", headers=H).status_code == 400

def test_ocr_failure_502():
    with patch.object(scanner_api, "_ocr", side_effect=RuntimeError("api caída")):
        r = c.post("/api/scanner/odometer", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "odo.jpg")})
    assert r.status_code == 502 and "reintenta" in r.json["error"]

def test_nhtsa_down_returns_empty_car():
    with patch.object(scanner_api, "_ocr", return_value="1HGCM82633A004352"), \
         patch.object(scanner_api, "decode_vin", side_effect=RuntimeError("timeout")):
        r = c.post("/api/scanner/vin", headers=H,
                   data={"photo": (io.BytesIO(b"jpg"), "vin.jpg")})
    assert r.status_code == 200 and r.json["valid"] is True and r.json["car"] == {}

def test_listing_bad_json_400():
    r = c.post("/api/scanner/listing", headers=H, data="no es json",
               content_type="application/json")
    assert r.status_code == 400

def test_inventory_malformed_data_400():
    r = c.post("/api/scanner/inventory", headers=H, data={"data": "{roto"})
    assert r.status_code == 400

def test_inventory_missing_keys_400(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    r = c.post("/api/scanner/inventory", headers=H, data={
        "data": json.dumps({"vin": "1HGCM82633A004352", "yr": "2021"}),
        "photos": (io.BytesIO(b"a"), "1.jpg")})
    assert r.status_code == 400 and "faltan campos" in r.json["error"]

def _guardar_carro(tmp_path, titulo="Corolla lindo"):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    data = {"vin": "1HGCM82633A004352", "yr": "2021", "model": "Corolla", "trim": "SE",
            "color": "Blanco", "price": 17500, "mileage": 42000,
            "title": titulo, "description": "descripcion larga", "notes": ""}
    r = c.post("/api/scanner/inventory", headers=H, data={
        "data": json.dumps(data),
        "photos": [(io.BytesIO(b"a"), "1.jpg"), (io.BytesIO(b"b"), "2.jpg")]})
    return r.json["folder"].split("/")[-1]

def test_pendientes_list(tmp_path):
    slug = _guardar_carro(tmp_path)
    r = c.get("/api/scanner/inventory", headers=H)
    assert r.status_code == 200 and len(r.json["items"]) == 1
    item = r.json["items"][0]
    assert item["slug"] == slug and item["photos"] == 2 and item["video"] is False
    assert item["title"] == "Corolla lindo"

def test_pendiente_get_y_update(tmp_path):
    slug = _guardar_carro(tmp_path)
    r = c.get(f"/api/scanner/inventory/{slug}", headers=H)
    assert r.status_code == 200 and r.json["data"]["price"] == 17500
    r2 = c.put(f"/api/scanner/inventory/{slug}", headers=H,
               json={"price": 16900, "title": "Nuevo titulo"})
    assert r2.status_code == 200 and r2.json["data"]["price"] == 16900
    r3 = c.get(f"/api/scanner/inventory/{slug}", headers=H)
    assert r3.json["data"]["title"] == "Nuevo titulo"

def test_pendiente_slug_invalido_404(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    assert c.get("/api/scanner/inventory/../etc", headers=H).status_code == 404
    assert c.get("/api/scanner/inventory/noexiste", headers=H).status_code == 404

def test_pendiente_photo_auth_por_query(tmp_path):
    slug = _guardar_carro(tmp_path)
    assert c.get(f"/api/scanner/inventory/{slug}/photo/1").status_code == 401
    r = c.get(f"/api/scanner/inventory/{slug}/photo/1?key=testkey")
    assert r.status_code == 200 and r.data == b"a"
    assert c.get(f"/api/scanner/inventory/{slug}/photo/9?key=testkey").status_code == 404

def test_inventory_no_photos_400(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    data = {"vin": "1HGCM82633A004352", "yr": "2021", "model": "Corolla", "trim": "SE",
            "color": "Blanco", "price": 17500, "mileage": 42000,
            "title": "t", "description": "d", "notes": ""}
    r = c.post("/api/scanner/inventory", headers=H, data={"data": json.dumps(data)})
    assert r.status_code == 400 and "foto" in r.json["error"]
