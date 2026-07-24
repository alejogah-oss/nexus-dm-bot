import json
from unittest.mock import patch, MagicMock

import appointments


def test_has_open_appointment_true_si_pending(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "abc", "status": "pending"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("abc") is True


def test_has_open_appointment_true_si_confirmed(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "abc", "status": "confirmed"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("abc") is True


def test_has_open_appointment_false_si_cancelada(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "abc", "status": "cancelled"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("abc") is False


def test_has_open_appointment_false_si_no_existe(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text("[]")
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))
    assert appointments._has_open_appointment("xyz") is False


def test_extract_appointment_no_llama_a_claude_si_ya_hay_cita_abierta(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text(json.dumps([{"customer_id": "cust1", "status": "pending"}]))
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))

    with patch.object(appointments._claude.messages, "create") as mock_create:
        result = appointments.extract_appointment_from_conversation(
            history=[{"role": "user", "content": "puedo ir el sábado"}],
            car={"yr": 2026, "model": "Camry", "trim": "", "color": ""},
            sender_id="cust1",
            platform="marketplace",
        )

    assert result is None
    mock_create.assert_not_called()


def test_extract_appointment_si_llama_a_claude_cuando_no_hay_cita_abierta(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text("[]")
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text='{"fecha": null, "hora": null, "nombre": null, "telefono": null}')]

    with patch.object(appointments._claude.messages, "create", return_value=fake_response) as mock_create:
        result = appointments.extract_appointment_from_conversation(
            history=[{"role": "user", "content": "hola"}],
            car={"yr": 2026, "model": "Camry", "trim": "", "color": ""},
            sender_id="cust2",
            platform="marketplace",
        )

    assert result is None
    mock_create.assert_called_once()


def test_extract_appointment_crea_cita_cuando_hay_fecha_real(tmp_path, monkeypatch):
    f = tmp_path / "appts.json"
    f.write_text("[]")
    monkeypatch.setattr(appointments, "APPOINTMENTS_FILE", str(f))

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text=(
        '{"fecha": "2026-07-30", "hora": "3pm", '
        '"nombre": "Maria Lopez", "telefono": "3055551234"}'
    ))]

    car = {"yr": 2026, "model": "Camry", "trim": "XLE", "color": "Blanco"}

    with patch.object(appointments._claude.messages, "create", return_value=fake_response) as mock_create, \
         patch.object(appointments, "pulse_notify") as mock_notify:
        result = appointments.extract_appointment_from_conversation(
            history=[{"role": "user", "content": "puedo ir el 2026-07-30 a las 3pm"}],
            car=car,
            sender_id="cust3",
            platform="marketplace",
        )

    mock_create.assert_called_once()
    mock_notify.assert_called_once()

    assert result is not None
    assert result["date_preference"] == "2026-07-30"
    assert result["time_preference"] == "3pm"
    assert result["customer_name"] == "Maria Lopez"
    assert result["customer_phone"] == "3055551234"
    assert result["customer_id"] == "cust3"
    assert result["platform"] == "marketplace"
    assert result["car"] == "2026 Toyota Camry XLE Blanco"
    assert result["status"] == "pending"

    saved = json.loads(f.read_text())
    assert len(saved) == 1
    assert saved[0]["id"] == result["id"]
    assert saved[0]["date_preference"] == "2026-07-30"
