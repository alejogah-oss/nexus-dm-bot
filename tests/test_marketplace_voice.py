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
    # A pedido de Alejo (jul 24 2026): ahora hay DOS preguntas de calificación
    # antes del precio (financiar/cash + "para cuándo"), pero cada una debe
    # vivir en su propio paso/mensaje — nunca combinadas en un solo texto.
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("PRECIO — es señal de compra")
    assert idx != -1
    seccion_precio = p[idx:idx + 1200]

    idx_paso1 = seccion_precio.find("1. Financiar o cash")
    idx_paso2 = seccion_precio.find("2. Para cuándo lo necesita")
    idx_paso3 = seccion_precio.find("3. Con AMBAS respuestas")
    assert idx_paso1 != -1 and idx_paso2 != -1 and idx_paso3 != -1
    assert idx_paso1 < idx_paso2 < idx_paso3

    paso1 = seccion_precio[idx_paso1:idx_paso2]
    paso2 = seccion_precio[idx_paso2:idx_paso3]
    paso3 = seccion_precio[idx_paso3:idx_paso3 + 400]

    # Paso 1 pregunta SOLO financiar/cash, sin mencionar la segunda pregunta.
    assert "¿lo estás viendo para financiar o cash?" in paso1.lower()
    assert "para cuándo" not in paso1.lower()

    # Paso 2 pregunta SOLO la segunda calificación, sin repetir financiar/cash.
    assert "¿para cuándo la estarías necesitando?" in paso2.lower()
    assert "financiar o cash?" not in paso2.lower()

    # Paso 3 (donde por fin se da el precio) ya no lleva ninguna pregunta de
    # calificación — el pivot a horarios queda para el FLUJO DE AGENDAMIENTO.
    assert "financiar o cash?" not in paso3.lower()
    assert "¿para cuándo la estarías necesitando?" not in paso3.lower()
    assert "sin pregunta de calificación" in paso3.lower()
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" not in paso3


def test_precio_agrega_segunda_pregunta_de_calificacion_antes_de_cotizar():
    # Punto central del pedido de Alejo: no basta con financiar/cash, debe
    # haber una SEGUNDA pregunta de calificación real (timeline) antes de dar
    # cualquier número.
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "¿para cuándo la estarías necesitando?" in p.lower()
    idx = p.find("PRECIO — es señal de compra")
    assert idx != -1
    seccion_precio = p[idx:idx + 1200]
    assert "dos preguntas rápidas" in seccion_precio.lower()
    assert "no la repitas" in seccion_precio.lower() or "no repitas" in seccion_precio.lower()


def test_precio_no_gatea_el_rango_detras_del_numero_de_telefono():
    # El rango/ancla de precio se gatea SOLO con las 2 preguntas de
    # calificación (financiar/cash + para cuándo) — nunca con pedir el
    # teléfono. El teléfono sigue siendo parte aparte del FLUJO DE AGENDAMIENTO.
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("PRECIO — es señal de compra")
    assert idx != -1
    idx_fin = p.find("MENSUALIDAD — solo si pregunta")
    assert idx_fin != -1
    seccion_precio = p[idx:idx_fin]
    assert "número de teléfono" in seccion_precio.lower()
    assert "eso es aparte" in seccion_precio.lower()
    # Los pasos que preguntan (1 y 2) no deben pedir el teléfono como
    # condición para llegar al precio.
    idx_paso1 = seccion_precio.find("1. Financiar o cash")
    idx_paso3 = seccion_precio.find("3. Con AMBAS respuestas")
    pasos_1_2 = seccion_precio[idx_paso1:idx_paso3]
    assert "dame tu número" not in pasos_1_2.lower()
    assert "me dejas tu número" not in pasos_1_2.lower()


def test_precio_insistencia_sin_contestar_no_se_estonewallea():
    # Si el cliente reinsiste en el número sin contestar la calificación, el
    # bot debe ceder tras 1-2 reinsistencias — nunca un stonewall total.
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("PRECIO — es señal de compra")
    assert idx != -1
    seccion_precio = p[idx:idx + 1800]
    assert "reinsiste en el número sin contestar" in seccion_precio.lower()
    assert "no lo estonewalles" in seccion_precio.lower()
    assert "segunda reinsistencia dale el número" in seccion_precio.lower()


def test_precio_numero_exacto_sigue_requiriendo_visita():
    # El gate del número EXACTO / mensualidad (requiere pasar por el dealer)
    # es un comportamiento ya existente que NO debe tocarse con este cambio.
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("Si insiste en el número EXACTO")
    assert idx != -1
    sub_caso = p[idx:idx + 300]
    assert "se valida en minutos en persona" in sub_caso
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in sub_caso


def test_cierre_exige_un_intento_de_agendar_antes_de_despedirse():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "UN intento obligatorio de cierre suave" in p


def test_tiene_rama_para_decisor_ausente():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "DECISOR AUSENTE" in p
    assert "tráelo(a) también" in p


def test_decisor_ausente_cierra_con_horarios_concretos_no_pregunta_abierta():
    # Alineado con BOT_VOICE (commit b554137): la rama DECISOR AUSENTE debe
    # cerrar con el pivot de horarios concretos, no con una pregunta abierta
    # tipo "¿qué día les queda bien?".
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("DECISOR AUSENTE")
    assert idx != -1
    seccion = p[idx:idx + 700]
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in seccion
    assert "¿qué día les queda bien" not in seccion.lower()


def test_decisor_ausente_no_aplica_si_hay_despedida_o_rechazo():
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("DECISOR AUSENTE")
    assert idx != -1
    seccion = p[idx:idx + 1000]
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


def test_direccion_solo_tras_horario_y_numero_confirmados():
    # Alineado con BOT_VOICE: el gate de nombre/dirección del dealer requiere
    # AMBOS (horario confirmado Y número dado) — no basta con uno de los dos.
    # Debe matchear el AND de FLUJO DE AGENDAMIENTO paso 4 ("Con día + número").
    p = _marketplace_voice(CAR_CON_RANGO)
    idx = p.find("NUNCA menciones el nombre del asesor")
    assert idx != -1
    seccion = p[idx:idx + 200]
    assert "confirmado una cita y dado su número" in seccion
    assert "confirmado una cita o dado su número" not in seccion
