from dm_bot import BOT_VOICE


def test_numero_se_pide_despues_de_horario_no_antes():
    # El pivot a horarios concretos (paso 2 de FLUJO GENERAL) debe venir
    # ANTES de pedir el número (paso 3) — nunca al revés.
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in BOT_VOICE
    idx_horarios = BOT_VOICE.index("Tengo espacio hoy en la tarde o mañana en la mañana")
    idx_numero = BOT_VOICE.index('"Perfecto, ¿me das tu número para coordinarte mejor?"')
    assert idx_horarios < idx_numero


def test_numero_no_se_pide_inmediatamente_despues_del_precio():
    # La sección PRECIO (donde se ancla el rango) no debe contener la
    # pregunta de número — eso vive únicamente en FLUJO GENERAL paso 3,
    # después de que el cliente confirme un horario.
    idx = BOT_VOICE.find("PRECIO — es señal de compra")
    assert idx != -1
    idx_fin = BOT_VOICE.find("MENSUALIDAD — solo si pregunta")
    assert idx_fin != -1
    seccion_precio = BOT_VOICE[idx:idx_fin]
    assert "¿me das tu número para coordinarte mejor?" not in seccion_precio.lower()
    assert "número de teléfono" in seccion_precio.lower()
    assert "eso es aparte" in seccion_precio.lower()


def test_precio_califica_en_dos_pasos_antes_de_cotizar():
    # Igual que en _marketplace_voice: financiar/cash primero, "para cuándo"
    # después, cada uno como única pregunta de su propio mensaje, y solo
    # entonces se da el número — sin pregunta de calificación adjunta.
    idx = BOT_VOICE.find("PRECIO — es señal de compra")
    assert idx != -1
    seccion_precio = BOT_VOICE[idx:idx + 1400]

    idx_paso1 = seccion_precio.find("1. Financiar o cash")
    idx_paso2 = seccion_precio.find("2. Para cuándo lo necesita")
    idx_paso3 = seccion_precio.find("3. Con AMBAS respuestas")
    assert idx_paso1 != -1 and idx_paso2 != -1 and idx_paso3 != -1
    assert idx_paso1 < idx_paso2 < idx_paso3

    paso1 = seccion_precio[idx_paso1:idx_paso2]
    paso2 = seccion_precio[idx_paso2:idx_paso3]
    paso3 = seccion_precio[idx_paso3:idx_paso3 + 400]

    assert "¿lo estás viendo para financiar o cash?" in paso1.lower()
    assert "para cuándo" not in paso1.lower()

    assert "¿para cuándo la estarías necesitando?" in paso2.lower()
    assert "financiar o cash?" not in paso2.lower()

    assert "financiar o cash?" not in paso3.lower()
    assert "¿para cuándo la estarías necesitando?" not in paso3.lower()
    assert "sin pregunta de calificación" in paso3.lower()
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" not in paso3


def test_precio_tiene_valvula_de_escape_ante_reinsistencia():
    idx = BOT_VOICE.find("PRECIO — es señal de compra")
    assert idx != -1
    seccion_precio = BOT_VOICE[idx:idx + 1800]
    assert "reinsiste en el número sin contestar" in seccion_precio.lower()
    assert "no lo estonewalles" in seccion_precio.lower()
    assert "segunda reinsistencia dale el número" in seccion_precio.lower()


def test_precio_numero_exacto_sigue_requiriendo_visita():
    idx = BOT_VOICE.find("Si insiste en el número EXACTO")
    assert idx != -1
    sub_caso = BOT_VOICE[idx:idx + 300]
    assert "se valida en minutos en persona" in sub_caso
    assert "Tengo espacio hoy en la tarde o mañana en la mañana" in sub_caso


def test_tiene_rama_para_decisor_ausente():
    assert "DECISOR AUSENTE" in BOT_VOICE
    assert "tráelo(a) también" in BOT_VOICE


def test_decisor_ausente_no_aplica_si_hay_despedida_o_rechazo():
    idx = BOT_VOICE.find("DECISOR AUSENTE")
    assert idx != -1
    seccion = BOT_VOICE[idx:idx + 1000]
    assert "RECHAZOS" in seccion
    assert "CIERRE DE CONVERSACIÓN" in seccion
    assert "salida educada" in seccion


def test_tiene_rama_para_carfax_historial():
    assert "HISTORIAL / CARFAX" in BOT_VOICE


def test_carfax_no_es_deflexion_pura():
    idx = BOT_VOICE.find("HISTORIAL / CARFAX")
    assert idx != -1
    seccion = BOT_VOICE[idx:idx + 500]
    assert "accidentes" in seccion.lower()
    assert "dueños" in seccion.lower()
    assert "NUNCA inventes" in seccion


def test_cierre_exige_un_intento_de_agendar_antes_de_despedirse():
    assert "UN intento obligatorio de cierre suave" in BOT_VOICE


def test_rechazo_2_no_pide_numero_como_disfraz_de_insistencia():
    idx = BOT_VOICE.find("RECHAZOS — si no quiere venir")
    assert idx != -1
    seccion = BOT_VOICE[idx:idx + 400]
    assert "NO pidas el número" in seccion
    assert "CIERRE DE CONVERSACIÓN" in seccion


def test_direccion_solo_tras_horario_y_numero_confirmados():
    idx = BOT_VOICE.find("DEALER Y DIRECCIÓN")
    assert idx != -1
    seccion = BOT_VOICE[idx:idx + 400]
    assert "confirmado un horario y dado su número" in seccion
