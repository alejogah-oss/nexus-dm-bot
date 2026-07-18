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
