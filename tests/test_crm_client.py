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
