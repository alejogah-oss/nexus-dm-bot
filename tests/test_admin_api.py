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
