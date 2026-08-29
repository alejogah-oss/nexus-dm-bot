from datetime import datetime, timedelta
import rescue_queue as rq


CAR = {"vin": "5TFAX5GN1MX123456", "model": "Tacoma", "yr": 2022}
MEDIODIA = datetime(2026, 8, 29, 12, 0)


# ── schedule: al contestar el bot, arranca el reloj del rescate ────────────

def test_schedule_deja_el_rescate_entre_90_y_120_minutos_despues():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    vence = datetime.fromisoformat(state["rescue_t_1"]["due_at"])
    assert MEDIODIA + timedelta(minutes=90) <= vence <= MEDIODIA + timedelta(minutes=120)


def test_schedule_guarda_el_carro_para_armar_el_mensaje():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    assert state["rescue_t_1"]["vin"] == "5TFAX5GN1MX123456"
    assert state["rescue_t_1"]["model"] == "Tacoma"


def test_schedule_de_noche_corre_el_rescate_a_la_manana():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=datetime(2026, 8, 29, 23, 30))
    vence = datetime.fromisoformat(state["rescue_t_1"]["due_at"])
    assert vence.date() == datetime(2026, 8, 30).date()
    assert 8 <= vence.hour < 10


def test_schedule_otra_vez_reinicia_el_reloj():
    # El bot solo contesta cuando el cliente escribió: si vuelve a contestar,
    # el silencio empieza de cero.
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    primero = state["rescue_t_1"]["due_at"]
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA + timedelta(hours=1))
    assert state["rescue_t_1"]["due_at"] > primero


def test_schedule_sin_vin_no_encola_nada():
    # Sin VIN no hay rango, y sin rango no hay mensaje que mandar.
    state = {}
    rq.schedule(state, "t_1", {"model": "Tacoma", "vin": ""}, ahora=MEDIODIA)
    assert state == {}


# ── due: a quién le toca ahora ────────────────────────────────────────────

def test_due_no_devuelve_nada_antes_de_tiempo():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    assert rq.due(state, ahora=MEDIODIA + timedelta(minutes=80)) == []


def test_due_devuelve_el_thread_cuando_se_cumple_el_plazo():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    assert rq.due(state, ahora=MEDIODIA + timedelta(minutes=125)) == ["t_1"]


def test_due_ignora_los_que_ya_se_rescataron():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    rq.mark_done(state, "t_1")
    assert rq.due(state, ahora=MEDIODIA + timedelta(hours=5)) == []


def test_due_no_se_cae_con_una_fecha_corrupta():
    # El estado es un JSON en disco; si queda a medio escribir, el bot no
    # puede morirse: se salta esa entrada.
    state = {"rescue_t_1": {"due_at": "no-es-una-fecha", "vin": "X", "model": "Y"}}
    assert rq.due(state, ahora=MEDIODIA) == []


# ── cancel: el cliente contestó, ya no hay nada que rescatar ───────────────

def test_cancel_saca_el_rescate_de_la_cola():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    rq.cancel(state, "t_1")
    assert rq.due(state, ahora=MEDIODIA + timedelta(hours=5)) == []


def test_cancel_de_un_thread_que_no_existe_no_revienta():
    rq.cancel({}, "t_desconocido")


# ── build_message: qué se le diría a este cliente ──────────────────────────
from unittest.mock import patch


def test_build_message_usa_el_rango_que_alejo_definio_para_ese_vin():
    entry = {"vin": "5TFAX5GN1MX123456", "model": "Tacoma"}
    with patch("price_ranges.get_range", return_value=(18000, 24000)):
        assert rq.build_message(entry) == (
            "¿Qué tal, seguís pensando en la Tacoma? Si el precio no te cuadra, "
            "tengo otras opciones entre $18,000 y $24,000."
        )


def test_build_message_sin_rango_cargado_no_dice_nada():
    # Alejo no le puso rango a ese carro: el bot se calla en vez de inventar.
    entry = {"vin": "5TFAX5GN1MX123456", "model": "Tacoma"}
    with patch("price_ranges.get_range", return_value=None):
        assert rq.build_message(entry) == ""


def test_build_message_sin_modelo_no_dice_nada():
    entry = {"vin": "5TFAX5GN1MX123456", "model": ""}
    with patch("price_ranges.get_range", return_value=(18000, 24000)):
        assert rq.build_message(entry) == ""


# ── El interruptor: nada sale hasta que Alejo lo prenda ────────────────────

def test_por_defecto_el_envio_esta_apagado():
    with patch.dict("os.environ", {}, clear=True):
        assert rq.sending_enabled() is False


def test_se_prende_con_la_variable_en_1():
    with patch.dict("os.environ", {"RESCUE_ENABLED": "1"}):
        assert rq.sending_enabled() is True


def test_cualquier_otro_valor_lo_deja_apagado():
    for valor in ("0", "", "si", "true", "yes"):
        with patch.dict("os.environ", {"RESCUE_ENABLED": valor}):
            assert rq.sending_enabled() is False, valor


# ── should_check_now: cada cuánto revisa la cola ──────────────────────────
# Alejo: "unas veces a 30 otras a 33 otras 37 otras 50". El bot ya revisa el
# buzón cada 4-9 minutos; el chequeo de rescates va montado encima, pero con
# su propio reloj sorteado.

def test_la_primera_vez_revisa_de_una():
    state = {}
    assert rq.should_check_now(state, ahora=1000.0) is True


def test_despues_de_revisar_no_vuelve_a_revisar_enseguida():
    state = {}
    rq.should_check_now(state, ahora=1000.0)
    assert rq.should_check_now(state, ahora=1000.0 + 29 * 60) is False


def test_vuelve_a_revisar_pasado_el_intervalo_sorteado():
    state = {}
    rq.should_check_now(state, ahora=1000.0)
    assert rq.should_check_now(state, ahora=1000.0 + 51 * 60) is True


def test_el_intervalo_nunca_se_repite_dos_veces_seguidas():
    state = {}
    ahora = 1000.0
    anterior = None
    for _ in range(30):
        rq.should_check_now(state, ahora=ahora)
        actual = state["last_rescue_interval"]
        assert actual != anterior
        anterior = actual
        ahora += 60 * 60


def test_las_llaves_de_control_no_se_confunden_con_rescates():
    # Las llaves internas viven en el mismo estado que los rescates: si due()
    # las leyera como threads, el bot intentaría escribirle a "next_check".
    state = {}
    rq.should_check_now(state, ahora=1000.0)
    assert rq.due(state, ahora=datetime(2030, 1, 1)) == []


# ── El rescate hereda el idioma de la conversación ────────────────────────

def test_schedule_guarda_el_idioma():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA, lang="en")
    assert state["rescue_t_1"]["lang"] == "en"


def test_schedule_sin_idioma_asume_espanol():
    state = {}
    rq.schedule(state, "t_1", CAR, ahora=MEDIODIA)
    assert state["rescue_t_1"]["lang"] == "es"


def test_build_message_respeta_el_ingles_de_la_conversacion():
    entry = {"vin": "5TFAX5GN1MX123456", "model": "Tacoma", "lang": "en"}
    with patch("price_ranges.get_range", return_value=(18000, 24000)):
        assert rq.build_message(entry).startswith("Hey, are you still thinking")


def test_build_message_de_una_entrada_vieja_sin_idioma_usa_espanol():
    # Rescates encolados antes de este cambio no tienen la llave "lang".
    entry = {"vin": "5TFAX5GN1MX123456", "model": "Tacoma"}
    with patch("price_ranges.get_range", return_value=(18000, 24000)):
        assert rq.build_message(entry).startswith("¿Qué tal")
