import rescue_timing as rt


# ── next_scan_interval: cada revisión a un intervalo distinto ──────────────
# Alejo (29 ago 2026): "unas veces a 30 otras a 33 otras 37 otras 50, así de
# manera aleatoria que parezca humano... que no se repitan ni tenga un patrón".

def test_next_scan_interval_devuelve_un_valor_de_la_lista():
    assert rt.next_scan_interval(None) in rt.SCAN_MINUTES


def test_next_scan_interval_nunca_repite_el_anterior():
    for previous in rt.SCAN_MINUTES:
        for _ in range(50):
            assert rt.next_scan_interval(previous) != previous


def test_next_scan_interval_no_es_siempre_el_mismo():
    vistos = {rt.next_scan_interval(30) for _ in range(80)}
    assert len(vistos) > 1


# ── rescue_delay_minutes: la espera antes de escribirle al cliente ─────────
# Alejo: "la respuesta tampoco debe ser exacta a las 2 horas, puede estar
# entre un rango de 90 y 120 minutos... que no se repitan ni tenga un patrón".

def test_rescue_delay_siempre_entre_90_y_120_minutos():
    for _ in range(200):
        assert 90 <= rt.rescue_delay_minutes() <= 120


def test_rescue_delay_practicamente_nunca_se_repite():
    # Minutos con decimales, no enteros: con 31 enteros posibles los choques
    # serían constantes y dos clientes caerían en el mismo minuto.
    vistos = {rt.rescue_delay_minutes() for _ in range(100)}
    assert len(vistos) == 100


# ── shift_into_window: nadie recibe mensajes de madrugada ──────────────────
# Con espera sorteada, un cliente que escribe a las 11pm recibiría el rescate
# a la 1am. Ningún vendedor hace eso. Fuera de 8am-9pm el mensaje se guarda
# y sale a la mañana, a una hora también sorteada (8-10am).

from datetime import datetime


def test_dentro_de_la_ventana_no_se_mueve():
    momento = datetime(2026, 8, 29, 14, 37)
    assert rt.shift_into_window(momento) == momento


def test_madrugada_sale_esa_misma_manana():
    salida = rt.shift_into_window(datetime(2026, 8, 29, 1, 30))
    assert salida.date() == datetime(2026, 8, 29).date()
    assert 8 <= salida.hour < 10


def test_despues_de_las_9pm_sale_al_dia_siguiente():
    salida = rt.shift_into_window(datetime(2026, 8, 29, 22, 30))
    assert salida.date() == datetime(2026, 8, 30).date()
    assert 8 <= salida.hour < 10


def test_la_hora_de_salida_tampoco_es_siempre_la_misma():
    vistos = {rt.shift_into_window(datetime(2026, 8, 29, 3, 0)) for _ in range(50)}
    assert len(vistos) > 1


def test_nunca_devuelve_un_momento_anterior_al_pedido():
    for hora in range(24):
        momento = datetime(2026, 8, 29, hora, 15)
        assert rt.shift_into_window(momento) >= momento


# ── rescue_message: el texto aprobado por Alejo, ni una palabra más ────────
# El mensaje termina en el rango. NO lista carros: si no nombra unidades,
# el bot no puede inventarse ninguna.

def test_mensaje_es_el_aprobado():
    assert rt.rescue_message("Tacoma", 18000, 24000) == (
        "¿Qué tal, seguís pensando en la Tacoma? Si el precio no te cuadra, "
        "tengo otras opciones entre $18,000 y $24,000."
    )


def test_mensaje_no_nombra_ningun_carro_del_inventario():
    texto = rt.rescue_message("RAV4", 15500, 21000)
    assert "20" not in texto.replace("$15,500", "").replace("$21,000", "")


def test_sin_rango_no_hay_mensaje():
    assert rt.rescue_message("Tacoma", 0, 0) == ""
    assert rt.rescue_message("Tacoma", 18000, 0) == ""


def test_rango_invertido_no_manda_nada():
    # Si el rango quedó al revés en la tabla, callarse es mejor que decir
    # "entre $24,000 y $18,000".
    assert rt.rescue_message("Tacoma", 24000, 18000) == ""


def test_sin_modelo_no_hay_mensaje():
    assert rt.rescue_message("", 18000, 24000) == ""


# ── Idioma: el bot tiene REGLA ABSOLUTA de no cambiar de idioma ────────────
# dm_bot.py:23 — "detecta el idioma del PRIMER mensaje y mantén ESE idioma en
# TODOS tus mensajes siguientes". Un rescate en español a un cliente que
# venía en inglés rompe esa regla en el último mensaje de la conversación.

def test_detecta_espanol():
    assert rt.detect_language("¿Sigue disponible? ¿Cuál es el precio?") == "es"


def test_detecta_ingles():
    assert rt.detect_language("Is this still available? What's the price?") == "en"


def test_detecta_ingles_sin_signos_de_pregunta():
    assert rt.detect_language("I am interested in the truck, how much down") == "en"


def test_detecta_espanol_sin_acentos_ni_signos():
    assert rt.detect_language("hola, me interesa la camioneta, cuanto es el pago") == "es"


def test_texto_ambiguo_cae_en_espanol():
    # Ante la duda, español: es el idioma del mensaje que aprobó Alejo.
    assert rt.detect_language("ok") == "es"
    assert rt.detect_language("") == "es"


def test_mensaje_en_ingles_para_cliente_en_ingles():
    assert rt.rescue_message("Tacoma", 18000, 24000, lang="en") == (
        "Hey, are you still thinking about the Tacoma? If the price doesn't "
        "work for you, I have other options between $18,000 and $24,000."
    )


def test_el_mensaje_en_ingles_tambien_calla_sin_rango():
    assert rt.rescue_message("Tacoma", 0, 0, lang="en") == ""
