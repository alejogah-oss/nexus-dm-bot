"""Usados en el chat de la web y los DMs — dm_bot.BOT_VOICE + tablas de inventario.

Bug real (11 sep 2026): un cliente preguntó por un Jeep Wrangler usado y el bot
contestó "Jeep no manejamos — somos Toyota", cuando el Wrangler Rubicon 2026 SÍ
estaba en el inventario. Causa: la tabla que se le inyecta al prompt filtraba
`type == "new"`, así que el bot nunca supo que existían las 17 unidades usadas
(6 de ellas de otras marcas).

Regla de negocio (Alejo, 11 sep 2026): el número cargado de un usado por debajo
de $10.000 es el ENGANCHE, no el precio — el bot no puede decirlo. Ahí pide el
teléfono para mandar la info. Por encima de $10.000 sí es precio real y se da
como el bot de Marketplace. Los nuevos no cambian: todos tienen precio.
"""
import dm_bot


# ── Criterio nuevo/usado: el mismo de inventario.html (millaje, no `type`) ──
# const esNuevo = v => !v.mileage || v.mileage === '0' || v.mileage === 0;

def test_es_nuevo_por_millaje_no_por_type():
    assert dm_bot._es_nuevo({"mileage": 0, "type": "used"}) is True
    assert dm_bot._es_nuevo({"mileage": "0", "type": "used"}) is True
    assert dm_bot._es_nuevo({"mileage": "", "type": "new"}) is True
    assert dm_bot._es_nuevo({"mileage": None, "type": "new"}) is True
    assert dm_bot._es_nuevo({"mileage": "12,504", "type": "new"}) is False
    assert dm_bot._es_nuevo({"mileage": 22000, "type": "new"}) is False


# ── Tablas de inventario ────────────────────────────────────────────────────

NUEVO_LE = {"yr": 2026, "make": "Toyota", "model": "Corolla", "trim": "LE",
            "mileage": 0, "price": 22000, "type": "new"}
NUEVO_XSE = {"yr": 2026, "make": "Toyota", "model": "Corolla", "trim": "XSE",
             "mileage": "0", "price": 28000, "type": "new"}
USADO_JEEP = {"yr": 2026, "make": "Jeep", "model": "Wrangler", "trim": "Rubicon",
              "mileage": "12504", "price": 4000, "type": "used"}
USADO_CAMRY = {"yr": 2025, "make": "Toyota", "model": "Camry", "trim": "SE",
               "mileage": "2208", "price": 2000, "type": "used"}
USADO_CARO = {"yr": 2022, "make": "Toyota", "model": "Highlander", "trim": "L",
              "mileage": "93514", "price": 18500, "type": "used"}
# El caso Audi: sin millaje (la página lo pinta como NUEVO) pero con un precio
# que no es de carro nuevo. Alejo: "ese carro déjalo fuera".
AUDI_RARO = {"yr": 2025, "make": "Audi", "model": "A5", "trim": "",
             "mileage": 0, "price": 2000, "type": "new"}

TODOS = [NUEVO_LE, NUEVO_XSE, USADO_JEEP, USADO_CAMRY, USADO_CARO, AUDI_RARO]


def test_nuevos_conservan_su_rango_de_precio():
    precios, _ = dm_bot._build_inventory_tables(TODOS)
    assert "2026 Corolla: desde $22,000 hasta $28,000" in precios


def test_enganche_de_usado_nunca_aparece_como_precio():
    precios, sin_precio = dm_bot._build_inventory_tables(TODOS)
    todo = precios + sin_precio
    # $4,000 (Jeep) y $2,000 (Camry y Audi) son enganches: no pueden salir
    assert "$4,000" not in todo
    assert "$2,000" not in todo


def test_usado_sin_precio_aparece_listado_con_marca_y_millaje():
    # El bot tiene que poder confirmar que el Jeep existe — ese es el bug.
    _, sin_precio = dm_bot._build_inventory_tables(TODOS)
    assert "2026 Jeep Wrangler Rubicon" in sin_precio
    assert "12,504 millas" in sin_precio


def test_usado_sobre_10000_si_lleva_su_precio_real():
    precios, sin_precio = dm_bot._build_inventory_tables(TODOS)
    assert "2022 Toyota Highlander L" in precios
    assert "$18,500" in precios
    assert "Highlander" not in sin_precio


def test_vehiculo_sin_millaje_con_precio_bajo_queda_fuera_de_precios():
    precios, sin_precio = dm_bot._build_inventory_tables(TODOS)
    assert "A5" not in precios          # nunca se cotiza ese número
    assert "2025 Audi A5" in sin_precio  # pero el bot sabe que existe


def test_tablas_vacias_si_no_hay_inventario():
    precios, sin_precio = dm_bot._build_inventory_tables([])
    assert precios == "" and sin_precio == ""


# ── Reglas del prompt ───────────────────────────────────────────────────────

def _seccion_usados() -> str:
    # El encabezado, no las referencias cruzadas que otras secciones le hacen.
    idx = dm_bot.BOT_VOICE.find("USADOS Y OTRAS MARCAS — REGLA ABSOLUTA")
    assert idx != -1, "falta la sección USADOS Y OTRAS MARCAS en BOT_VOICE"
    fin = dm_bot.BOT_VOICE.find("\n\n", idx + 200)
    return dm_bot.BOT_VOICE[idx:fin if fin != -1 else len(dm_bot.BOT_VOICE)]


def test_prompt_prohibe_decir_que_solo_vendemos_toyota():
    seccion = _seccion_usados()
    assert "solo vendemos Toyota" in seccion
    assert "NUNCA" in seccion


def test_prompt_manda_pedir_el_telefono_cuando_el_usado_no_tiene_precio():
    seccion = _seccion_usados()
    assert "número" in seccion
    assert "[HOT LEAD]" in seccion


def test_prompt_prohibe_estimar_o_aproximar_el_precio_de_un_usado():
    seccion = _seccion_usados()
    for palabra in ("estimes", "rango", "desde"):
        assert palabra in seccion, f"la prohibición no cubre '{palabra}'"


def test_prompt_solo_habla_de_lo_listado():
    seccion = _seccion_usados()
    assert "listad" in seccion


def test_la_regla_vieja_de_no_dar_precios_de_usados_ya_no_esta_suelta():
    # Antes decía "no des números, invita a verlos en persona" sin pedir el
    # teléfono — esa salida dejaba ir al cliente sin dato de contacto.
    assert "invita a verlos en persona" not in dm_bot.BOT_VOICE
