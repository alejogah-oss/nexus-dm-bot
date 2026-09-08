from unittest.mock import patch
import webhook_server


def test_normaliza_evento_ig_comments():
    value = {
        "id": "IGC1",
        "from": {"id": "cliente789", "username": "juan"},
        "text": "quiero un corolla",
        "media": {"id": "MEDIA1"},
    }
    ev = webhook_server._comment_event("instagram", "comments", value)
    assert ev == {
        "platform": "instagram", "comment_id": "IGC1", "author_id": "cliente789",
        "text": "quiero un corolla", "post_id": "MEDIA1", "parent_id": "",
    }


def test_normaliza_evento_ig_comments_con_parent():
    value = {"id": "IGC2", "from": {"id": "x"}, "text": "hola",
             "media": {"id": "M1"}, "parent_id": "IGC1"}
    ev = webhook_server._comment_event("instagram", "comments", value)
    assert ev["parent_id"] == "IGC1"


def test_normaliza_evento_fb_feed():
    value = {"item": "comment", "verb": "add", "comment_id": "FBC1",
             "post_id": "POST1", "from": {"id": "PAGE?", "name": "Ana"},
             "message": "precio?"}
    ev = webhook_server._comment_event("facebook", "feed", value)
    assert ev == {
        "platform": "facebook", "comment_id": "FBC1", "author_id": "PAGE?",
        "text": "precio?", "post_id": "POST1", "parent_id": "",
    }


def test_normaliza_evento_fb_feed_ignora_no_comment():
    value = {"item": "reaction", "verb": "add"}
    assert webhook_server._comment_event("facebook", "feed", value) is None


def test_normaliza_evento_fb_mention_usa_sender():
    value = {"comment_id": "FBC9", "post_id": "POST9",
             "sender": {"id": "tercero", "name": "Luis"}, "message": "@pagina info"}
    ev = webhook_server._comment_event("facebook", "mention", value)
    assert ev["author_id"] == "tercero"
    assert ev["comment_id"] == "FBC9"


def test_webhook_no_rompe_si_handle_comment_explota():
    payload = {"object": "instagram", "entry": [{"changes": [
        {"field": "comments", "value": {"id": "C1", "from": {"id": "x"},
         "text": "hola", "media": {"id": "M1"}}}]}]}
    with webhook_server.app.test_client() as c:
        with patch("webhook_server.handle_comment", side_effect=RuntimeError("boom")):
            r = c.post("/webhook", json=payload)
    assert r.status_code == 200
