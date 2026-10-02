"""Reglas del prompt de Marketplace (_marketplace_voice).

Rediseño oct 2026 (pedido de Alejo): solo el 8% de las conversaciones dejaba el
teléfono. El bot vuelve a concentrarse en la CITA, da el precio después de UNA
pregunta de apertura, no pregunta "¿financiar o cash?" como paso obligatorio,
acepta llamadas, y pide el número a cambio de más fotos/info. Estos tests
fijan esas decisiones y las reglas viejas que siguen vigentes.
"""
from dm_bot import _marketplace_voice

CAR_CON_RANGO = {"yr": 2026, "model": "Camry", "trim": "LE", "color": "White",
                  "price": 28000, "price_hi": 35000, "vin": "1FAKE"}
CAR_UN_SOLO_TRIM = {"yr": 2026, "model": "GR Supra", "trim": "3.0", "color": "Red",
                     "price": 58000, "price_hi": 0, "vin": "2FAKE"}
CAR_SIN_PRECIO = {"yr": 2026, "model": "Corolla", "trim": "LE", "color": "Blue",
                  "price": 0, "price_hi": 0, "vin": "3FAKE"}


def _seccion(p: str, titulo: str, largo: int = 900) -> str:
    idx = p.find(titulo)
    assert idx != -1, f"falta la sección {titulo!r}"
    return p[idx:idx + largo]


# ── Decisiones de oct 2026 ────────────────────────────────────────────────────

def test_apertura_hace_una_pregunta_antes_del_precio():
    p = _marketplace_voice(CAR_CON_RANGO)
    apertura = _seccion(p, "1. APERTURA", 1400)
    assert "¿Lo buscas para ya o estás mirando opciones?" in apertura
    assert "NO des el precio todavía" in apertura


def test_apertura_no_pregunta_lo_que_el_cliente_ya_contesto():
    apertura = _seccion(_marketplace_voice(CAR_CON_RANGO), "1. APERTURA", 1400)
    assert "Excepciones" in apertura
    assert "enganche" in apertura          # "¿es el total o el enganche?" se contesta de una
    assert "no le preguntes lo que ya contestó" in apertura


def test_precio_sale_en_el_siguiente_mensaje_sin_segundo_gate():
    paso2 = _seccion(_marketplace_voice(CAR_CON_RANGO), "2. PRECIO", 700)
    assert "dalo ya" in paso2
    assert "Nunca preguntes financiar/cash como paso obligatorio" in paso2


def test_ya_no_pregunta_financiar_o_cash():
    for car in (CAR_CON_RANGO, CAR_UN_SOLO_TRIM, CAR_SIN_PRECIO):
        p = _marketplace_voice(car).lower()
        assert "¿lo estás viendo para financiar o cash?" not in p
        assert "are you looking to finance or pay cash" not in p


def test_despues_del_precio_la_pregunta_empuja_a_la_cita():
    cierre = _seccion(_marketplace_voice(CAR_CON_RANGO), "3. CIERRE TRAS PRECIO", 700)
    assert "¿Te gustaría pasar a verlo esta semana?" in cierre
    assert "hoy en la tarde o mañana en la mañana" in cierre


def test_acepta_llamadas_y_nunca_da_un_numero_nuestro():
    p = _marketplace_voice(CAR_CON_RANGO)
    llamadas = _seccion(p, "LLAMADAS / HABLAR CON ALGUIEN", 500)
    assert "¿a qué número te llamamos?" in llamadas
    assert "NUNCA des un número nuestro" in llamadas
    assert "don't take calls" not in p.lower()


def test_si_preguntan_si_es_bot_ofrece_la_llamada():
    bot = _seccion(_marketplace_voice(CAR_CON_RANGO), "SI PREGUNTA SI ERES BOT", 300)
    assert "LLAMADAS" in bot


def test_numero_a_cambio_de_fotos_e_info():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "¿A qué número te mando más fotos y la info completa?" in p


def test_no_promete_inmediatez_que_nadie_cumple():
    p = _marketplace_voice(CAR_CON_RANGO)
    cierre = _seccion(p, "5. CIERRE TRAS NÚMERO", 700)
    assert "Listo, un asesor te contacta hoy." in cierre
    assert "8:00pm hora de Florida" in cierre
    assert "mañana temprano" in cierre
    assert "[HOT LEAD]" in cierre
    voz = _seccion(p, "VOZ:", 900)
    assert "ahorita mismo" in voz and "NUNCA prometas inmediatez" in voz


def test_textos_cortos_una_pregunta():
    voz = _seccion(_marketplace_voice(CAR_CON_RANGO), "VOZ:", 600)
    assert "Máximo 2 frases cortas" in voz
    assert "35 es el tope absoluto" in voz
    assert "UNA sola pregunta por mensaje" in voz


def test_formulario_facredit_solo_si_no_quiere_dar_el_numero():
    mens = _seccion(_marketplace_voice(CAR_CON_RANGO), "MENSUALIDAD", 700)
    assert "SOLO si insiste en la cuota Y de plano no quiere dar su número" in mens
    assert "?lang=en" in mens


def test_despedida_intenta_quedarse_con_el_numero_una_vez():
    p = _marketplace_voice(CAR_CON_RANGO)
    cierre = _seccion(p, "CIERRE DE CONVERSACIÓN:", 700)
    assert "UN intento suave" in cierre
    assert "fotos" in cierre
    assert "es el 2do rechazo" in cierre      # tras el 2do rechazo ya no se insiste


# ── Precio y enganche ─────────────────────────────────────────────────────────

def test_el_numero_del_anuncio_es_el_enganche_nunca_el_total():
    # Bug cazado al reproducir conversaciones reales (oct 2026): sin esta línea
    # el bot le decía al cliente que el número del anuncio era el precio total.
    p = _marketplace_voice(dict(CAR_CON_RANGO, down_payment=2000))
    assert "El anuncio muestra $2,000: ese número es el ENGANCHE estimado, nunca el precio total." in p
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "es el ENGANCHE estimado, nunca el precio total" in p


def test_rango_y_trim_unico():
    assert "desde $28,000 hasta $35,000" in _marketplace_voice(CAR_CON_RANGO)
    assert "(único trim en stock)" in _marketplace_voice(CAR_UN_SOLO_TRIM)


def test_sin_precio_nunca_inventa_y_pide_el_numero():
    p = _marketplace_voice(CAR_SIN_PRECIO)
    assert "PROHIBIDO inventar un número" in p
    assert "pide el número para mandarle el precio y fotos" in p


def test_negociacion_nunca_se_cierra_por_chat():
    assert "nunca cierres un número por chat" in _marketplace_voice(CAR_CON_RANGO)


def test_alt_options_ausente_por_defecto_y_presente_con_texto():
    assert "SI ESTE CARRO NO LE CUADRA" not in _marketplace_voice(CAR_CON_RANGO)
    car = dict(CAR_CON_RANGO, alt_options_text="- 2018 Corolla LE: $12,000\n- 2019 Camry LE: $15,500")
    bloque = _seccion(_marketplace_voice(car), "SI ESTE CARRO NO LE CUADRA", 700)
    assert "2018 Corolla LE: $12,000" in bloque and "2019 Camry LE: $15,500" in bloque
    assert "sin inventar datos" in bloque


# ── Reglas viejas que siguen vigentes ─────────────────────────────────────────

def test_nunca_da_la_direccion_en_el_chat():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "2200 n state rd" not in p.lower()
    assert "Nunca nombre del asesor, del dealer, ni dirección en el chat." in p


def test_credito_bajo_pregunta_por_enganche():
    credito = _seccion(_marketplace_voice(CAR_CON_RANGO), "CRÉDITO BAJO", 500)
    assert "crédito malo" in credito and "enganche" in credito


def test_usados_nunca_dan_precio_en_el_chat():
    usados = _seccion(_marketplace_voice(CAR_CON_RANGO), "USADOS / EL LISTING NO ES LO QUE BUSCA", 900)
    assert "NUNCA des precios ni disponibilidad de usados en el chat" in usados
    assert "NÚMERO A CAMBIO DE FOTOS/INFO" in usados


def test_carfax_nunca_inventa():
    carfax = _seccion(_marketplace_voice(CAR_CON_RANGO), "CARFAX / HISTORIAL", 500)
    assert "NUNCA inventes si tuvo accidentes o dueños anteriores" in carfax


def test_decisor_ausente():
    dec = _seccion(_marketplace_voice(CAR_CON_RANGO), "DECISOR AUSENTE", 500)
    assert "tráelo(a) también" in dec
    assert "RECHAZO" in dec          # si viene con despedida no es señal de compra


def test_rechazos_segundo_rechazo_cierra():
    rech = _seccion(_marketplace_voice(CAR_CON_RANGO), "RECHAZOS:", 300)
    assert "2do rechazo, no insistas más" in rech
    assert "[SHOWROOM_DECLINED]" in rech


def test_horario_propuesto_por_el_cliente_manda():
    hor = _seccion(_marketplace_voice(CAR_CON_RANGO), "HORARIO PROPUESTO POR EL CLIENTE — por encima", 700)
    assert "nunca le ofrezcas \"hoy o mañana\"" in hor


def test_realismo_de_horario():
    real = _seccion(_marketplace_voice(CAR_CON_RANGO), "REALISMO DE HORARIO:", 600)
    assert "Pasadas las 5:00pm hora de Florida" in real
    assert "lejos del Sur de Florida" in real
    assert "acéptalo con calidez" in real


def test_luisa():
    luisa = _seccion(_marketplace_voice(CAR_CON_RANGO), "SI PREGUNTAN POR LUISA", 800)
    assert "nunca digas que eres ella" in luisa
    assert "Luisa te llama" in luisa


def test_idioma_y_marcadores_silenciosos():
    p = _marketplace_voice(CAR_CON_RANGO)
    assert "IDIOMA" in p
    assert "[HOT LEAD] siempre que el cliente dé su número" in p
    assert "nunca mencionados al cliente" in p
