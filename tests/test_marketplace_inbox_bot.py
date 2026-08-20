import json
import time
import marketplace_inbox_bot as mib


# ── _parse_car_from_text: reconoce CUALQUIER marca, no solo Toyota ─────────
# Bug real (16 ago 2026): el regex exigía la palabra "Toyota" literal en el
# título del listing de Marketplace, así que un trade-in de otra marca (Lexus,
# Nissan, Mercedes-Benz) nunca resolvía car context -> "Sin listing de
# Marketplace" -> el bot se quedaba callado con clientes reales (Applez/Lexus
# RX350, Jorge y Kimonia/Nissan Altima, confirmados en el log de producción).

def test_parse_car_from_text_toyota_sigue_funcionando():
    car = mib._parse_car_from_text("2026 Toyota RAV4")
    assert car == {"yr": 2026, "make": "Toyota", "model": "RAV4", "trim": "",
                    "color": "", "down_payment": 0, "vin": ""}


def test_parse_car_from_text_marca_no_toyota():
    car = mib._parse_car_from_text("2022 Lexus RX350")
    assert car["make"] == "Lexus" and car["model"] == "RX350" and car["yr"] == 2022


def test_parse_car_from_text_nissan():
    car = mib._parse_car_from_text("2025 Nissan Altima")
    assert car["make"] == "Nissan" and car["model"] == "Altima"


def test_parse_car_from_text_marca_con_guion():
    car = mib._parse_car_from_text("2020 Mercedes-Benz GLE-Class - White")
    assert car["make"] == "Mercedes-Benz" and car["model"] == "GLE-Class"


def test_parse_car_from_text_con_prefijo_nombre_cliente():
    # Formato real de sender_name: "Nombre · AÑO MARCA MODELO"
    car = mib._parse_car_from_text("Kimonia · 2025 Nissan Altima")
    assert car["make"] == "Nissan" and car["model"] == "Altima" and car["yr"] == 2025


def test_parse_car_from_text_modelo_multi_palabra():
    car = mib._parse_car_from_text("Benito · 2026 Toyota rav4 plug-in hybrid")
    assert car["make"] == "Toyota" and car["model"] == "rav4 plug-in hybrid"


def test_parse_car_from_text_sin_match_devuelve_none():
    assert mib._parse_car_from_text("hola, ¿cómo estás?") is None


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


def test_apply_scanner_pricing_resuelve_por_spec_cuando_no_hay_vin_del_publico(tmp_path, monkeypatch):
    # Usados: no están en el API público, así que _enrich_car no resuelve el VIN
    # (Marketplace tampoco lo muestra — el header solo trae año+modelo). El bot
    # debe resolver el VIN contra el inventario local del scanner por año+modelo
    # y aplicar el internal_price igual. yr del scanner es STRING, del header INT.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "2T2YZMDA9NC331574", yr="2022", model="RX",
                       trim="350 F Sport High", internal_price=45280,
                       alt_price_low=42000, alt_price_high=48000)
    _set_public_inventory(monkeypatch, [
        {"yr": 2026, "model": "Camry", "trim": "XSE", "price": 34000, "vin": "NEW1"}])
    car = {"yr": 2022, "make": "Lexus", "model": "RX 350 F Sport", "trim": "", "vin": ""}
    out = mib._apply_scanner_pricing(car)
    assert out["vin"] == "2T2YZMDA9NC331574"
    assert out["price"] == 45280
    assert out["price_hi"] == 0


def test_apply_scanner_pricing_por_spec_ambiguo_no_da_precio(tmp_path, monkeypatch):
    # Dos usados con el mismo año+modelo en el scanner -> sin VIN no hay forma de
    # saber cuál es. Más seguro no dar ningún número que arriesgar el equivocado.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VINX1", yr="2022", model="RX", trim="350", internal_price=45000)
    _write_scanner_car(tmp_path, "VINX2", yr="2022", model="RX", trim="450", internal_price=52000)
    car = {"yr": 2022, "model": "RX 350 F Sport", "trim": "", "vin": ""}
    out = mib._apply_scanner_pricing(car)
    assert out.get("price", 0) == 0
    assert not out.get("vin")


def test_apply_scanner_pricing_por_spec_resuelve_modelo_con_nombre_distinto(tmp_path, monkeypatch):
    # Caso real Mercedes: el scanner guarda model="GLS-Class" pero el título del
    # anuncio (y el header de Marketplace) trae "GLS450 4MATIC AWD" — la
    # contención sobre el modelo corto no matchea. Se resuelve parseando el
    # título del propio listing del scanner (que es lo que generó el anuncio).
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "GLSVIN123", yr="2024", model="GLS-Class",
                       trim="GLS450 4MATIC", internal_price=72900,
                       title="2024 Mercedes-Benz GLS450 4MATIC AWD - Black")
    car = {"yr": 2024, "make": "Mercedes-Benz", "model": "GLS450 4MATIC AWD", "trim": "", "vin": ""}
    out = mib._apply_scanner_pricing(car)
    assert out["vin"] == "GLSVIN123"
    assert out["price"] == 72900


def test_apply_scanner_pricing_por_spec_raiz_distinta_no_matchea(tmp_path, monkeypatch):
    # La raíz del modelo debe distinguir: un GLS no debe resolverse contra un GLE
    # aunque compartan marca y año.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "GLEVIN", yr="2024", model="GLE-Class", trim="GLE350",
                       internal_price=60000, title="2024 Mercedes-Benz GLE350 4MATIC - Gray")
    car = {"yr": 2024, "make": "Mercedes-Benz", "model": "GLS450 4MATIC AWD", "trim": "", "vin": ""}
    out = mib._apply_scanner_pricing(dict(car))
    assert out == car


def test_apply_scanner_pricing_por_spec_no_colisiona_subfamilia_gr(tmp_path, monkeypatch):
    # BUG que cazó Sentry: un GR86 y un GR Corolla son autos DISTINTOS que
    # comparten el prefijo "GR". Reducir a la raíz "gr" les daba el mismo precio.
    # El bot NUNCA debe dar el precio de una unidad por otra.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "GRCOROLLA", yr="2024", model="GR Corolla", trim="Core",
                       internal_price=42000, title="2024 Toyota GR Corolla Core - Blue")
    car = {"yr": 2024, "make": "Toyota", "model": "GR86", "trim": "", "vin": ""}
    out = mib._apply_scanner_pricing(dict(car))
    assert out == car  # sin precio, sin VIN adoptado


def test_apply_scanner_pricing_por_spec_no_colisiona_prefijo_letra(tmp_path, monkeypatch):
    # Otra colisión que cazó Sentry: "C-HR" (Toyota) y "C 300" (Mercedes) NO deben
    # unirse por la letra "c".
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "CHRVIN", yr="2024", model="C-HR", trim="XLE",
                       internal_price=28000, title="2024 Toyota C-HR XLE - White")
    car = {"yr": 2024, "make": "Mercedes-Benz", "model": "C 300 4MATIC", "trim": "", "vin": ""}
    out = mib._apply_scanner_pricing(dict(car))
    assert out == car


def test_apply_scanner_pricing_por_spec_sin_match_no_toca_el_car(tmp_path, monkeypatch):
    # Carro normal (nuevo) sin VIN y sin unidad en el scanner -> sin cambios.
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "VINY", yr="2022", model="RX", trim="350", internal_price=45000)
    car = {"yr": 2026, "model": "Corolla", "trim": "", "vin": ""}
    out = mib._apply_scanner_pricing(dict(car))
    assert out == car


def test_apply_scanner_pricing_nuevo_con_vin_publico_no_se_resuelve_por_spec(tmp_path, monkeypatch):
    # Regresión: un carro NUEVO ya trae VIN + precio del API público. Aunque el
    # scanner tenga una unidad del mismo año+modelo (ej. un 2026 Sienna escaneado
    # sin precio), NO debe pisar el precio público del nuevo. La resolución por
    # spec es solo para carros SIN VIN (usados que no están en el público).
    _reset_scanner_cache(monkeypatch, tmp_path)
    _write_scanner_car(tmp_path, "SCANVIN", yr="2026", model="Sienna", trim="Limited")  # sin internal_price
    car = {"yr": 2026, "model": "Sienna", "vin": "PUBLICVIN", "price": 48000, "price_hi": 52000}
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


# ── _prioritize_threads: clientes sin respuesta nunca quedan mudos ─────────
# Bug real (16 ago 2026): un cliente preguntando por un Nissan Altima nunca
# recibió respuesta porque su thread dejó de estar entre los MAX_THREADS más
# recientes del sidebar y el bot solo procesaba esa ventana. Confirmado con
# Alejo en producción — "falta que atienda el bot a Jorge, pregunta por el
# altima".

def _t(thread_id, name="X"):
    return (f"/marketplace/t/{thread_id}", name, thread_id, 123)


def test_prioritize_threads_nunca_respondido_gana_el_cupo():
    # 4 threads "con cambios", cupo de 2 — el que nunca fue respondido
    # (thread_id no está en state) debe entrar aunque sea el más viejo.
    to_process = [_t("nuevo1"), _t("nuevo2"), _t("viejo_sin_respuesta"), _t("nuevo3")]
    state = {"nuevo1": "hash1", "nuevo2": "hash2", "nuevo3": "hash3"}  # ya se les respondió antes
    out = mib._prioritize_threads(to_process, state, max_threads=2)
    ids = [t[2] for t in out]
    assert "viejo_sin_respuesta" in ids
    assert len(out) == 2


def test_prioritize_threads_no_excede_max_threads():
    to_process = [_t(f"t{i}") for i in range(10)]
    out = mib._prioritize_threads(to_process, {}, max_threads=3)
    assert len(out) == 3


def test_prioritize_threads_dentro_del_cupo_no_trunca():
    to_process = [_t("a"), _t("b")]
    out = mib._prioritize_threads(to_process, {}, max_threads=5)
    assert len(out) == 2


def test_prioritize_threads_preserva_orden_relativo_dentro_de_cada_grupo():
    # Entre los nunca-respondidos, mantiene el orden original (más reciente primero).
    to_process = [_t("resp1"), _t("nunca1"), _t("nunca2"), _t("resp2")]
    state = {"resp1": "h", "resp2": "h"}
    out = mib._prioritize_threads(to_process, state, max_threads=4)
    ids = [t[2] for t in out]
    assert ids.index("nunca1") < ids.index("resp1")
    assert ids.index("nunca2") < ids.index("resp2")
