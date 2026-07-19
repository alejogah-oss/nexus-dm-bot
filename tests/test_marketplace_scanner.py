import json
import marketplace_poster

def test_scanner_car_fields_usa_datos_reales():
    car = {"make": "Honda", "model": "Civic", "yr": "2019",
           "mileage": 45000, "price": 16500, "color": "Blue",
           "title": "2019 Honda Civic EX", "description": "buen carro"}
    f = marketplace_poster.scanner_car_fields(car)
    assert f["make"] == "Honda"        # marca real, NO "Toyota"
    assert f["mileage"] == "45000"     # millaje real, NO "500"
    assert f["price"] == "16500"       # precio completo, NO enganche (20%)
    assert f["interior_color"] == "Black"
    assert f["exterior_color"] == "Blue"
    assert f["condition"] == "Excellent"
    assert f["title"] == "2019 Honda Civic EX"

def test_scanner_car_fields_make_fallback():
    # Si el scanner no trae marca, cae a Toyota (dealer Toyota) sin romper
    f = marketplace_poster.scanner_car_fields({"model": "Corolla", "yr": "2020",
                                               "mileage": 10, "price": 20000, "color": "White"})
    assert f["make"] == "Toyota" and f["exterior_color"] == "White"

# ── FIX 2 (review final): badge 🔴 "Falló" nunca se dispara ──────────

def test_record_publish_error_escribe_last_error(tmp_path, monkeypatch):
    slug = "2019-Civic-004352"
    folder = tmp_path / slug
    folder.mkdir()
    (folder / "listing.json").write_text(json.dumps({
        "vin": "1HGCM82633A004352", "yr": "2019", "make": "Honda",
        "model": "Civic", "title": "2019 Honda Civic EX",
    }))
    monkeypatch.setenv("INVENTORY_DIR", str(tmp_path))

    marketplace_poster.record_publish_error(slug, "boom")

    data = json.loads((folder / "listing.json").read_text())
    assert data["last_error"] == "boom"
    # no borra los datos originales del carro
    assert data["make"] == "Honda" and data["title"] == "2019 Honda Civic EX"

def test_record_publish_error_slug_inexistente_no_lanza(tmp_path, monkeypatch):
    monkeypatch.setenv("INVENTORY_DIR", str(tmp_path))
    # no debe lanzar excepción aunque el slug/listing.json no exista
    marketplace_poster.record_publish_error("no-existe-este-slug", "boom")
