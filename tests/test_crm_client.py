import json
from unittest.mock import patch, mock_open
import crm_client


def test_push_hot_lead_ya_enviado_no_reenvia_ni_notifica():
    # Fix ago 2026 (pedido de Alejo): un lead ya registrado NO debe volver a
    # disparar WhatsApp en cada mensaje siguiente de la conversación — antes
    # mandaba "🔄 ACTUALIZACIÓN DE LEAD" sin límite, y como el criterio de
    # [HOT LEAD] en el prompt es amplio (teléfono, financiamiento, "quiere
    # venir"), terminaba mandando muchos mensajes por el mismo cliente.
    activity_data = json.dumps({"sender123": {"crm_sent": True}})
    with patch("builtins.open", mock_open(read_data=activity_data)):
        result = crm_client.push_hot_lead("sender123", "marketplace_personal", [])
    assert result == {"ok": True, "skipped": True}


def test_push_hot_lead_ya_enviado_no_llama_pulse_notify():
    activity_data = json.dumps({"sender123": {"crm_sent": True}})
    with patch("builtins.open", mock_open(read_data=activity_data)):
        with patch("pulse.pulse_notify") as mock_notify:
            crm_client.push_hot_lead("sender123", "marketplace_personal", [])
    mock_notify.assert_not_called()


# ── _clean_sender_name: nombre real de Marketplace como respaldo confiable ──
# Bug real (17 ago 2026): fetch_user_profile() solo reconoce platform
# "facebook"/"instagram" — para Marketplace ("marketplace_personal") nunca
# devuelve nada, así que el único nombre posible venía de que la IA lo
# adivinara del texto del chat. El bot YA tiene el nombre real (el que
# muestra el sidebar de Messenger, ej. "Kimonia · 2025 Nissan Altima") pero
# nunca se lo pasaba a push_hot_lead.

def test_clean_sender_name_separa_nombre_del_listing():
    assert crm_client._clean_sender_name("Kimonia · 2025 Nissan Altima") == "Kimonia"


def test_clean_sender_name_sin_separador_devuelve_tal_cual():
    assert crm_client._clean_sender_name("Jorge") == "Jorge"


def test_clean_sender_name_id_numerico_se_descarta():
    # El sidebar a veces da el ID del thread en vez del nombre — no es un
    # nombre real, no debe guardarse como si lo fuera.
    assert crm_client._clean_sender_name("1027487763443921") == ""


def test_clean_sender_name_vacio():
    assert crm_client._clean_sender_name("") == ""


# ── push_hot_lead: usa sender_name como respaldo, y "falta nombre" solo avisa una vez ──

def test_push_hot_lead_usa_sender_name_si_la_ia_no_encuentra_nombre(tmp_path, monkeypatch):
    fake_module = tmp_path / "crm_client.py"
    fake_module.write_text("")
    monkeypatch.setattr(crm_client, "__file__", str(fake_module))

    with patch("crm_client.fetch_user_profile", return_value={}), \
         patch("crm_client.extract_lead_data", return_value={"source_platform": "marketplace_personal"}), \
         patch("crm_client._build_crm_note", return_value="nota") as mock_note, \
         patch("crm_client.send_to_crm", return_value={"success": True, "lead_id": 1}) as mock_send, \
         patch("notes.analyze_buyer", return_value=None), \
         patch("pulse.pulse_notify") as mock_notify:
        result = crm_client.push_hot_lead("sender999", "marketplace_personal", [],
                                           sender_name="Kimonia · 2025 Nissan Altima")

    assert mock_send.called  # sí llegó a crear el lead (no se saltó por "falta nombre")
    # el nombre usado para la nota del CRM viene de sender_name, no quedó vacío
    assert mock_note.call_args[0][2] == "Kimonia"
    assert result.get("success") is True
    assert mock_notify.called  # WhatsApp del HOT LEAD normal (una vez, ya cubierto por otro test)


def test_push_hot_lead_falta_nombre_avisa_una_sola_vez(tmp_path, monkeypatch):
    # __file__ apunta a un módulo real dentro de tmp_path para que
    # leads_activity.json se lea/escriba ahí — sin tocar el archivo real ni
    # necesitar mockear open() a mano en cada round-trip.
    fake_module = tmp_path / "crm_client.py"
    fake_module.write_text("")
    monkeypatch.setattr(crm_client, "__file__", str(fake_module))

    with patch("crm_client.fetch_user_profile", return_value={}), \
         patch("crm_client.extract_lead_data", return_value={"source_platform": "marketplace_personal"}), \
         patch("pulse.pulse_notify") as mock_notify:
        # Primera vez: sin sender_name, no hay forma de sacar nombre -> avisa
        result1 = crm_client.push_hot_lead("sender777", "marketplace_personal", [])
        assert result1["reason"] == "incomplete_data"
        assert mock_notify.call_count == 1

        # Segunda vez, mismo cliente, sigue sin nombre -> NO vuelve a avisar
        result2 = crm_client.push_hot_lead("sender777", "marketplace_personal", [])
        assert result2["reason"] == "incomplete_data"
        assert mock_notify.call_count == 1  # sigue en 1, no subió a 2

    saved = json.loads((tmp_path / "leads_activity.json").read_text())
    assert saved["sender777"]["incomplete_alert_sent"] is True
