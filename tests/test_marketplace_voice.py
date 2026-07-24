from dm_bot import _marketplace_voice

CAR_CON_RANGO = {"yr": 2026, "model": "Camry", "trim": "LE", "color": "White",
                  "price": 28000, "price_hi": 35000, "vin": "1FAKE"}
CAR_UN_SOLO_TRIM = {"yr": 2026, "model": "GR Supra", "trim": "3.0", "color": "Red",
                     "price": 58000, "price_hi": 0, "vin": "2FAKE"}


def test_ofrece_dos_horarios_concretos_no_pregunta_abierta():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in p
    assert "¿Para cuándo te queda fácil venir?" not in p


def test_cierre_exige_un_intento_de_agendar_antes_de_despedirse():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "UN intento obligatorio de cierre suave" in p


def test_tiene_rama_para_decisor_ausente():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "DECISOR AUSENTE" in p
    assert "tráelo(a) también" in p


def test_tiene_rama_para_carfax_historial():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "HISTORIAL / CARFAX" in p


def test_un_solo_trim_aclara_que_no_hay_rango():
    p = _marketplace_voice(CAR_UN_SOLO_TRIM)
    assert "no hay rango porque solo tenemos esta versión" in p


def test_usados_da_valor_antes_de_pedir_whatsapp():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "Sí manejamos usados en ese rango" in p
