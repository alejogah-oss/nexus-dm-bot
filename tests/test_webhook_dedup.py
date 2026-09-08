"""Dedup de reintentos de Meta — incidente 8 sep 2026 (dos respuestas al mismo DM).

Meta reenvía el mismo evento si el handler (síncrono, llama a Claude) no responde
200 a tiempo. Sin dedup por message-id, cada reenvío genera otra respuesta.
"""
from unittest.mock import patch

import pytest

import webhook_server


@pytest.fixture(autouse=True)
def _tmp_seen(tmp_path):
    # Aísla el store de disco y el de memoria entre tests.
    with patch.object(webhook_server, "_SEEN_FILE", str(tmp_path / "seen.json")):
        webhook_server._seen_msgs.clear()
        yield
        webhook_server._seen_msgs.clear()


def _fb_payload(mid, text="quiero un corolla"):
    return {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "USER123"},
                "recipient": {"id": "PAGE1"},
                "message": {"mid": mid, "text": text},
            }],
        }],
    }


def _ig_payload(mid, text="hola"):
    return {
        "object": "instagram",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {"messages": [{
                    "from": {"id": "IGUSER"}, "mid": mid,
                    "text": {"body": text},
                }]},
            }],
        }],
    }


def test_fb_mensaje_repetido_solo_responde_una_vez():
    with webhook_server.app.test_client() as c:
        with patch("webhook_server.handle_message") as hm, \
             patch("webhook_server._verify_signature", return_value=True):
            c.post("/webhook", json=_fb_payload("m_abc"))
            c.post("/webhook", json=_fb_payload("m_abc"))   # reintento de Meta
    assert hm.call_count == 1


def test_fb_mensajes_distintos_responden_cada_uno():
    with webhook_server.app.test_client() as c:
        with patch("webhook_server.handle_message") as hm, \
             patch("webhook_server._verify_signature", return_value=True):
            c.post("/webhook", json=_fb_payload("m_1"))
            c.post("/webhook", json=_fb_payload("m_2"))
    assert hm.call_count == 2


def test_ig_mensaje_repetido_solo_responde_una_vez():
    with webhook_server.app.test_client() as c:
        with patch("webhook_server.handle_message") as hm, \
             patch("webhook_server._verify_signature", return_value=True):
            c.post("/webhook", json=_ig_payload("ig_x"))
            c.post("/webhook", json=_ig_payload("ig_x"))
    assert hm.call_count == 1


def test_sin_mid_no_deduplica():
    # Si Meta no manda mid, no hay con qué deduplicar — se procesa (no se pierde).
    assert webhook_server._is_retry(None) is False
    assert webhook_server._is_retry("") is False


def test_dedup_sobrevive_reinicio_via_disco():
    webhook_server._is_retry("persisted_1")
    webhook_server._seen_msgs.clear()          # simula reinicio del worker
    assert webhook_server._is_retry("persisted_1") is True
