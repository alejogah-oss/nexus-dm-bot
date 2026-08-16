import json
import time
import marketplace_inbox_bot as mib


def test_track_car_resolution_failure_incrementa_contador():
    failures = {}
    for expected_count in range(1, 5):
        count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
        assert count == expected_count
        assert should_alert is False


def test_track_car_resolution_failure_alerta_al_llegar_al_threshold():
    failures = {"t1": 4}
    count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
    assert count == 5
    assert should_alert is True


def test_track_car_resolution_failure_no_alerta_de_nuevo_tras_threshold():
    failures = {"t1": 5}
    count, should_alert = mib._track_car_resolution_failure(failures, "t1", threshold=5)
    assert count == 6
    assert should_alert is False


def test_track_car_resolution_failure_threads_distintos_no_se_mezclan():
    failures = {}
    mib._track_car_resolution_failure(failures, "t1", threshold=5)
    mib._track_car_resolution_failure(failures, "t1", threshold=5)
    count, _ = mib._track_car_resolution_failure(failures, "t2", threshold=5)
    assert count == 1
    assert failures == {"t1": 2, "t2": 1}


def test_session_alert_transition_primera_caida_alerta():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=False, alert_already_sent=False)
    assert should_alert is True
    assert new_state is True


def test_session_alert_transition_no_repite_alerta_mientras_sigue_caida():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=False, alert_already_sent=True)
    assert should_alert is False
    assert new_state is True


def test_session_alert_transition_reset_al_recuperar_sesion():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=True, alert_already_sent=True)
    assert should_alert is False
    assert new_state is False


def test_session_alert_transition_sin_cambios_si_ya_estaba_bien():
    should_alert, new_state = mib._session_alert_transition(currently_logged_in=True, alert_already_sent=False)
    assert should_alert is False
    assert new_state is False


# ── Precio real privado + rango de alternativas (spec 2026-08-16) ──────────
# _apply_scanner_pricing: cruce VIN resuelto -> inventario local del scanner.

def _write_scanner_car(tmp_path, vin, **extra):
    folder = tmp_path / vin
    folder.mkdir()
    data = {"vin": vin, "yr": 2019, "model": "Civic", "trim": "EX", "color": "Blue",
            "price": 3000, "mileage": 45000, "title": "t", "description": "d"}
    data.update(extra)
    (folder / "listing.json").write_text(json.dumps(data))
    return folder


def _reset_scanner_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(mib, "INVENTORY_DIR", str(tmp_path))
    mib._scanner_inv_cache["ts"] = 0.0
    mib._scanner_inv_cache["by_vin"] = {}


def _set_public_inventory(monkeypatch, vehicles):
    monkeypatch.setitem(mib._inventory_cache, "vehicles", vehicles)
    monkeypatch.setitem(mib._inventory_cache, "ts", time.time())


def test_apply_scanner_pricing_con_internal_price_fuerza_unico_trim(tmp_path, monkeypatch):
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VIN123", internal_price=15000)
    car = {"yr": 2019, "model": "Civic", "vin": "VIN123", "price": 3000, "price_hi": 5000}
    out = mib._apply_scanner_pricing(car)
    assert out["price"] == 15000
    assert out["price_hi"] == 0


def test_apply_scanner_pricing_sin_internal_price_fuerza_precio_cero(tmp_path, monkeypatch):
    # Fix de seguridad: sin internal_price cargado, el bot NUNCA debe mostrar el
    # enganche del scanner (<$10k) como si fuera el precio total del carro.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VIN456")  # sin internal_price
    car = {"yr": 2019, "model": "Civic", "vin": "VIN456", "price": 3000, "price_hi": 5000}
    out = mib._apply_scanner_pricing(car)
    assert out["price"] == 0
    assert out["price_hi"] == 0


def test_apply_scanner_pricing_ambiguo_entre_dos_unidades_no_da_precio(tmp_path, monkeypatch):
    # Dos Corolla LE 2023 distintos escaneados -> el VIN resuelto por año+modelo+trim
    # (Marketplace no muestra VIN) podría ser el equivocado. Más seguro no dar
    # ningún número que arriesgarse a dar el precio real de la otra unidad.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VIN_A", yr=2023, model="Corolla", trim="LE", internal_price=15000)
    _write_scanner_car(tmp_path, "VIN_B", yr=2023, model="Corolla", trim="LE", internal_price=17000)
    car = {"yr": 2023, "model": "Corolla", "vin": "VIN_A", "price": 3000, "price_hi": 5000}
    out = mib._apply_scanner_pricing(car)
    assert out["price"] == 0
    assert out["price_hi"] == 0


def test_apply_scanner_pricing_sin_ambiguedad_una_sola_unidad_da_precio(tmp_path, monkeypatch):
    # Control: con una sola unidad de esa especificación, sigue funcionando normal.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VIN_A", yr=2023, model="Corolla", trim="LE", internal_price=15000)
    _write_scanner_car(tmp_path, "VIN_C", yr=2022, model="Camry", trim="SE", internal_price=20000)
    car = {"yr": 2023, "model": "Corolla", "vin": "VIN_A", "price": 3000, "price_hi": 5000}
    out = mib._apply_scanner_pricing(car)
    assert out["price"] == 15000
    assert out["price_hi"] == 0


def test_apply_scanner_pricing_sin_match_no_toca_el_car(tmp_path, monkeypatch):
    # VIN no matchea ningún carro del scanner (inventario normal) -> sin cambios.
    _reset_scanner_cache(monkeypatch, tmp_path)
    car = {"yr": 2019, "model": "Camry", "vin": "VIN_NORMAL", "price": 28000, "price_hi": 32000}
    out = mib._apply_scanner_pricing(dict(car))
    assert out == car


def test_apply_scanner_pricing_sin_vin_no_toca_el_car():
    car = {"yr": 2019, "model": "Camry", "price": 28000}
    out = mib._apply_scanner_pricing(dict(car))
    assert out == car


# ── alt_options_text: rango de alternativas nunca inventa carros ───────────

def test_alt_options_text_con_resultados_excluye_vin_actual_y_dedupe(tmp_path, monkeypatch):
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VINALT", alt_price_low=10000, alt_price_high=15000)
    vehicles = [
        {"yr": 2018, "model": "Corolla", "trim": "LE", "price": 11000, "vin": "OTHER1"},
        {"yr": 2018, "model": "Corolla", "trim": "LE", "price": 11500, "vin": "OTHER2"},  # dup key
        {"yr": 2019, "model": "Camry", "trim": "SE", "price": 14000, "vin": "OTHER3"},
        {"yr": 2020, "model": "RAV4", "trim": "XLE", "price": 30000, "vin": "OTHER4"},  # fuera de rango
        {"yr": 2017, "model": "Civic", "trim": "EX", "price": 12000, "vin": "VINALT"},  # VIN actual
    ]
    _set_public_inventory(monkeypatch, vehicles)
    car = {"yr": 2017, "model": "Civic", "vin": "VINALT", "price": 3000}
    out = mib._apply_scanner_pricing(car)
    assert "alt_options_text" in out
    text = out["alt_options_text"]
    assert "Corolla" in text and "Camry" in text
    assert "RAV4" not in text
    assert text.count("Corolla") == 1  # dedupe por (yr, modelo, trim)
    lines = text.split("\n")
    assert not any("11500" in ln for ln in lines)  # el duplicado no aparece
    assert not any(ln.strip("- ").startswith("2017 Civic") for ln in lines)  # nunca el VIN actual


def test_alt_options_text_vacio_si_no_hay_resultados_en_rango(tmp_path, monkeypatch):
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VINALT2", alt_price_low=50000, alt_price_high=60000)
    _set_public_inventory(monkeypatch, [
        {"yr": 2019, "model": "Civic", "trim": "EX", "price": 16000, "vin": "X"}])
    car = {"yr": 2019, "model": "Civic", "vin": "VINALT2"}
    out = mib._apply_scanner_pricing(car)
    assert "alt_options_text" not in out


def test_alt_options_text_ausente_sin_rango_cargado(tmp_path, monkeypatch):
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VINALT3", internal_price=15000)  # sin alt_price_low/high
    _set_public_inventory(monkeypatch, [
        {"yr": 2019, "model": "Civic", "trim": "EX", "price": 16000, "vin": "X"}])
    car = {"yr": 2019, "model": "Civic", "vin": "VINALT3"}
    out = mib._apply_scanner_pricing(car)
    assert "alt_options_text" not in out


def test_alt_options_text_limita_a_4_resultados(tmp_path, monkeypatch):
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VINALT4", alt_price_low=10000, alt_price_high=20000)
    vehicles = [
        {"yr": 2015 + i, "model": f"Model{i}", "trim": "LE", "price": 11000 + i * 100, "vin": f"V{i}"}
        for i in range(6)
    ]
    _set_public_inventory(monkeypatch, vehicles)
    car = {"yr": 2019, "model": "Civic", "vin": "VINALT4"}
    out = mib._apply_scanner_pricing(car)
    assert len(out["alt_options_text"].split("\n")) == 4
