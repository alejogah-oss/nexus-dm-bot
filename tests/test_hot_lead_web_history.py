"""El HOT LEAD del chat web: la firma tiene que aguantar al llamador.

Bug de producción (11 sep 2026): `webhook_server.web_chat` llama
`notify_alejo_hot_lead(..., history=_web_conversations[session_id])`, pero la firma
de `dm_bot.notify_alejo_hot_lead` había vuelto a quedar sin ese parámetro
(lo agregó `ae47c62` y lo revirtió `d7ea8ee`). Resultado: cada cliente que daba su
teléfono en el chat de la web recibía un HTTP 500 justo en el momento de capturar
el lead. Estuvo oculto porque Render llevaba días sin poder desplegar.

El chat web NO vive en `_conversations`, así que sin `history` explícito el lead
llegaría al CRM sin conversación.
"""
import inspect
from unittest.mock import patch

import dm_bot


def test_acepta_history_explicito():
    params = inspect.signature(dm_bot.notify_alejo_hot_lead).parameters
    assert "history" in params, "el chat web lo pasa por keyword; sin esto revienta con TypeError"


def test_el_history_del_canal_web_es_el_que_llega_al_crm():
    conversacion = [{"role": "user", "content": "954-555-0134"}]
    with patch.object(dm_bot, "push_hot_lead") as push, \
         patch.object(dm_bot, "save_note", return_value={"changed": False}), \
         patch.object(dm_bot, "log_event"):
        dm_bot.notify_alejo_hot_lead("sess-web-1", "web", "954-555-0134", history=conversacion)
    assert push.call_args.args[2] is conversacion


def test_sin_history_sigue_usando_el_de_los_dms():
    dm_bot._conversations["dm-123"] = [{"role": "user", "content": "hola"}]
    try:
        with patch.object(dm_bot, "push_hot_lead") as push, \
             patch.object(dm_bot, "save_note", return_value={"changed": False}), \
             patch.object(dm_bot, "log_event"):
            dm_bot.notify_alejo_hot_lead("dm-123", "instagram", "hola")
        assert push.call_args.args[2] == [{"role": "user", "content": "hola"}]
    finally:
        dm_bot._conversations.pop("dm-123", None)


def test_la_llamada_real_de_webhook_server_es_compatible():
    # Ata el llamador a la firma: si uno de los dos cambia, esto falla en tests
    # y no en producción con un 500 en la cara del cliente.
    fuente = inspect.getsource(__import__("webhook_server").web_chat)
    assert "notify_alejo_hot_lead(" in fuente
    llamada = fuente[fuente.index("notify_alejo_hot_lead("):]
    llamada = llamada[:llamada.index(")") + 1]
    kwargs = {"history": []} if "history=" in llamada else {}
    inspect.signature(dm_bot.notify_alejo_hot_lead).bind("sid", "web", "msg", **kwargs)
