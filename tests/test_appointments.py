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
