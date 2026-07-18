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
    with patch.object(scanner_api, "_claude_create", return_value=fake):
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
    with patch.object(scanner_api, "_claude_create", return_value=fake):
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

def test_inventory_no_photos_400(tmp_path):
    scanner_api.INVENTORY_DIR = str(tmp_path)
    data = {"vin": "1HGCM82633A004352", "yr": "2021", "model": "Corolla", "trim": "SE",
            "color": "Blanco", "price": 17500, "mileage": 42000,
            "title": "t", "description": "d", "notes": ""}
    r = c.post("/api/scanner/inventory", headers=H, data={"data": json.dumps(data)})
    assert r.status_code == 400 and "foto" in r.json["error"]
