from unittest.mock import patch, Mock
from vin_utils import validate_vin, decode_vin, clean_vin, repair_vin

def test_validate_vin_ok():
    assert validate_vin("1HGCM82633A004352") is True   # check digit válido conocido

def test_validate_vin_bad_check_digit():
    assert validate_vin("1HGCM82633A004353") is False

def test_validate_vin_bad_length_or_chars():
    assert validate_vin("ABC") is False
    assert validate_vin("1HGCM82633A00435I") is False  # I no es válido en VIN

def test_clean_vin_normaliza_ocr():
    # I/O/Q nunca existen en un VIN — se traducen, no se descartan (no pierde posiciones)
    assert clean_vin("1HGCM82633A0O4352") == "1HGCM82633A004352"
    assert clean_vin("vin: 1hgcm82633a004352.") == "1HGCM82633A004352"

def test_repair_vin_corrige_confusion_unica():
    assert repair_vin("1HGCMB2633A004352") == "1HGCM82633A004352"  # B leída por 8
    assert repair_vin("1HGCM82633A0043S2") == "1HGCM82633A004352"  # S leída por 5

def test_repair_vin_no_toca_validos_ni_irreparables():
    assert repair_vin("1HGCM82633A004352") == "1HGCM82633A004352"
    assert repair_vin("AAAAAAAAAAAAAAAAA") == "AAAAAAAAAAAAAAAAA"

def test_decode_vin_parses_nhtsa():
    fake = {"Results": [{"ModelYear": "2021", "Make": "TOYOTA", "Model": "Corolla",
                         "Trim": "SE", "DisplacementL": "2.0", "EngineCylinders": "4",
                         "FuelTypePrimary": "Gasoline", "BodyClass": "Sedan",
                         "DriveType": "FWD"}]}
    with patch("vin_utils.requests.get", return_value=Mock(json=lambda: fake, status_code=200)):
        d = decode_vin("1HGCM82633A004352")
    assert d["yr"] == "2021" and d["model"] == "Corolla" and d["trim"] == "SE"
    assert d["engine"] == "2.0L 4cyl"
