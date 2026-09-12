"""La marca que se publica al sitio NUNCA se defaultea a Toyota.

Este fix ya se hizo una vez (`70afaf2`, 16 ago 2026) y se perdió: el commit
`5291d97` ("sincroniza el repo con lo que ya corre en el Pro") reescribió
site_publisher.py con la versión vieja del Pro y devolvió el
`data.get("make") or "Toyota"`. Consecuencia real en el inventario de
producción: 4 trade-ins quedaron guardados como Toyota — el Altima (Nissan),
el ES 350 y el RX 350 (Lexus) y el GLS450 (Mercedes-Benz) — y el chat de la
web los nombraba "Toyota Altima" porque la página repite lo que hay en la base.

Este test es la guarda para que no vuelva a pasar en un tercer merge.
"""
from unittest.mock import patch

import site_publisher


def _payload(data, tmp_path):
    return site_publisher.build_payload(data, tmp_path)


def test_usa_la_marca_que_trae_el_scanner(tmp_path):
    p = _payload({"vin": "1N4BL4DV6SN303115", "make": "Nissan", "model": "Altima"}, tmp_path)
    assert p["make"] == "Nissan"


def test_sin_marca_la_decodifica_del_vin_en_vez_de_asumir_toyota(tmp_path):
    with patch("vin_utils.decode_vin", return_value={"make": "Mercedes-Benz"}):
        p = _payload({"vin": "4JGFF5KE6RB185778", "model": "GLS-Class"}, tmp_path)
    assert p["make"] == "Mercedes-Benz"


def test_sin_marca_y_sin_vin_queda_vacia_nunca_toyota(tmp_path):
    p = _payload({"model": "Altima"}, tmp_path)
    assert p["make"] == ""


def test_si_falla_el_decode_queda_vacia_nunca_toyota(tmp_path):
    with patch("vin_utils.decode_vin", side_effect=RuntimeError("NHTSA caído")):
        p = _payload({"vin": "1N4BL4DV6SN303115", "model": "Altima"}, tmp_path)
    assert p["make"] == ""


def test_no_queda_ningun_default_a_toyota_en_el_codigo():
    import inspect
    fuente = inspect.getsource(site_publisher.build_payload)
    assert '"Toyota"' not in fuente and "'Toyota'" not in fuente
