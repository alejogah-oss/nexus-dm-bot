from unittest.mock import patch, MagicMock
import price_ranges


def _resp(status, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    return r


# ── get_range: el rango que Alejo definió, por VIN ─────────────────────────

def test_get_range_devuelve_el_rango_guardado():
    with patch("requests.get", return_value=_resp(200, {
            "vin": "5TFAX5GN1MX123456", "alt_price_low": 18000,
            "alt_price_high": 24000, "internal_price": 21500})):
        assert price_ranges.get_range("5TFAX5GN1MX123456") == (18000, 24000)


def test_get_range_sin_rango_para_ese_vin_devuelve_none():
    with patch("requests.get", return_value=_resp(404, {"error": "sin rango"})):
        assert price_ranges.get_range("5TFAX5GN1MX123456") is None


def test_get_range_con_crm_caido_devuelve_none_sin_reventar():
    # El bot no puede caerse porque el CRM no responda: sin rango, no rescata.
    with patch("requests.get", side_effect=OSError("connection refused")):
        assert price_ranges.get_range("5TFAX5GN1MX123456") is None


def test_get_range_sin_vin_no_llama_al_crm():
    with patch("requests.get") as mock_get:
        assert price_ranges.get_range("") is None
    mock_get.assert_not_called()


# ── claim_rescue: el candado de "una sola vez" ─────────────────────────────

def test_claim_rescue_primera_vez_devuelve_true():
    with patch("requests.post", return_value=_resp(200, {"claimed": True})):
        assert price_ranges.claim_rescue("t_1", "5TFAX5GN1MX123456", "Tacoma", "hola") is True


def test_claim_rescue_segunda_vez_devuelve_false():
    with patch("requests.post", return_value=_resp(200, {"claimed": False})):
        assert price_ranges.claim_rescue("t_1", "5TFAX5GN1MX123456", "Tacoma", "hola") is False


def test_claim_rescue_con_crm_caido_devuelve_false():
    # Fail-closed a propósito: si no podemos dejar constancia de que le
    # escribimos, NO le escribimos. Un lead sin rescatar es mejor que un
    # cliente recibiendo el mismo mensaje cada vez que el bot reinicia.
    with patch("requests.post", side_effect=OSError("timeout")):
        assert price_ranges.claim_rescue("t_1", "5TFAX5GN1MX123456", "Tacoma", "hola") is False


def test_claim_rescue_con_error_500_devuelve_false():
    with patch("requests.post", return_value=_resp(500, {"error": "boom"})):
        assert price_ranges.claim_rescue("t_1", "5TFAX5GN1MX123456", "Tacoma", "hola") is False


# ── save_range: el panel /admin guarda el rango en la tabla ────────────────
# Antes solo iba a listing.json, en el disco efímero de Render: Alejo cargaba
# el rango y se perdía en el siguiente despliegue.

def test_save_range_manda_el_rango_al_crm():
    with patch("requests.post", return_value=_resp(200, {"ok": True})) as mock_post:
        assert price_ranges.save_range("5tfax5gn1mx123456", 18000, 24000, 21500) is True
    enviado = mock_post.call_args.kwargs["json"]
    assert enviado["vin"] == "5TFAX5GN1MX123456"
    assert enviado["alt_price_low"] == 18000
    assert enviado["alt_price_high"] == 24000


def test_save_range_sin_rango_no_llama_al_crm():
    # Editar el precio público de un carro sin rango no debe crear filas vacías.
    with patch("requests.post") as mock_post:
        assert price_ranges.save_range("5TFAX5GN1MX123456", 0, 0, 0) is False
    mock_post.assert_not_called()


def test_save_range_con_crm_caido_devuelve_false_sin_reventar():
    # El panel /admin no puede romperse porque el CRM esté caído: el rango
    # igual queda en listing.json, solo que no se replicó.
    with patch("requests.post", side_effect=OSError("timeout")):
        assert price_ranges.save_range("5TFAX5GN1MX123456", 18000, 24000, 0) is False
