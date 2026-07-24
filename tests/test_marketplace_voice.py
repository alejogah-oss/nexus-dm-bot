from dm_bot import _marketplace_voice

CAR_CON_RANGO = {"yr": 2026, "model": "Camry", "trim": "LE", "color": "White",
                  "price": 28000, "price_hi": 35000, "vin": "1FAKE"}
CAR_UN_SOLO_TRIM = {"yr": 2026, "model": "GR Supra", "trim": "3.0", "color": "Red",
                     "price": 58000, "price_hi": 0, "vin": "2FAKE"}


def test_ofrece_dos_horarios_concretos_no_pregunta_abierta():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in p
    assert "¿Para cuándo te queda fácil venir?" not in p
    assert "para cuándo te queda fácil venir" not in p.lower()


def test_insistencia_numero_exacto_usa_horarios_concretos():
    p = _marketplace_voice(CAR_CON_RANGO)
    # El sub-caso de "insiste en el número EXACTO" debe usar el mismo patrón
    # de horarios concretos que el resto de la función, no una pregunta abierta.
    idx = p.find("Si insiste en el número EXACTO")
    assert idx != -1
    sub_caso = p[idx:idx + 250]
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in sub_caso
    assert "te queda fácil venir" not in sub_caso.lower()


def test_precio_no_hace_dos_preguntas_en_un_mismo_mensaje():
    p = _marketplace_voice(CAR_CON_RANGO)
    # regla_precio (usada en la respuesta de precio) debe cerrar SOLO con
    # financiar/cash — los horarios van en el turno siguiente, no en el mismo
    # bloque de instrucción de precio.
    idx = p.find("PRECIO — es señal de compra")
    assert idx != -1
    seccion_precio = p[idx:idx + 400]
    assert seccion_precio.count("¿Lo estás viendo para financiar o cash?") == 1
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" not in seccion_precio
    assert "los horarios de cita van en el turno siguiente" in seccion_precio


def test_cierre_exige_un_intento_de_agendar_antes_de_despedirse():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "UN intento obligatorio de cierre suave" in p


def test_tiene_rama_para_decisor_ausente():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "DECISOR AUSENTE" in p
    assert "tráelo(a) también" in p


def test_decisor_ausente_no_aplica_si_hay_despedida_o_rechazo():
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("DECISOR AUSENTE")
    assert idx != -1
    seccion = p[idx:idx + 900]
    assert "RECHAZOS" in seccion
    assert "CIERRE DE CONVERSACIÓN" in seccion
    assert "salida educada" in seccion or "NO es señal de compra" in seccion


def test_tiene_rama_para_carfax_historial():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "HISTORIAL / CARFAX" in p


def test_carfax_no_es_deflexion_pura():
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("HISTORIAL / CARFAX")
    assert idx != -1
    seccion = p[idx:idx + 500]
    # Debe nombrar puntualmente lo que el cliente pidió (accidentes, dueños,
    # título), no solo decir "te lo mostramos cuando vengas".
    assert "accidentes" in seccion.lower()
    assert "dueños" in seccion.lower()
    assert "NUNCA inventes" in seccion


def test_rechazo_2_no_pide_numero_como_disfraz_de_insistencia():
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("RECHAZOS:")
    assert idx != -1
    seccion = p[idx:idx + 400]
    assert "pide número antes de despedirte" not in seccion
    assert "NO pidas el número" in seccion
    assert "CIERRE DE CONVERSACIÓN" in seccion


def test_un_solo_trim_aclara_que_no_hay_rango():
    p = _marketplace_voice(CAR_UN_SOLO_TRIM)
    assert "no hay rango porque solo tenemos esta versión" in p


def test_usados_da_valor_antes_de_pedir_whatsapp():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "Sí manejamos usados en ese rango" in p
