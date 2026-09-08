import json
import time
from unittest.mock import patch, mock_open, MagicMock

import comment_bot


# ── Store: comments_handled.json ──────────────────────────────────────────────

def test_load_handled_store_inexistente_devuelve_dict_vacio():
    with patch("os.path.exists", return_value=False):
        assert comment_bot._load_handled() == {}


def test_load_handled_store_corrupto_devuelve_dict_vacio():
    # Un JSON roto no debe crashear el webhook — se ignora y se sigue.
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data="{ roto")):
            assert comment_bot._load_handled() == {}


def test_save_y_load_roundtrip(tmp_path):
    store_file = tmp_path / "comments_handled.json"
    with patch.object(comment_bot, "HANDLED_STORE", str(store_file)):
        comment_bot._save_handled({"c1": {"ts": 123, "actions": []}})
        assert comment_bot._load_handled() == {"c1": {"ts": 123, "actions": []}}


# ── Guarda 2: identidad ──────────────────────────────────────────────────────

def test_is_own_author_page_id():
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123", "IG456"}):
        assert comment_bot.is_own_author("PAGE123") is True


def test_is_own_author_ig_id():
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123", "IG456"}):
        assert comment_bot.is_own_author("IG456") is True


def test_is_own_author_tercero():
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123", "IG456"}):
        assert comment_bot.is_own_author("cliente789") is False


def test_is_own_author_vacio_es_falso():
    # author_id "" (Meta lo omitió) no debe contar como propio.
    with patch.object(comment_bot, "_OWN_IDS", {"PAGE123"}):
        assert comment_bot.is_own_author("") is False


# ── Guarda 3: solo top-level ─────────────────────────────────────────────────

def test_is_reply_con_parent_id():
    ev = {"comment_id": "c2", "parent_id": "c1", "post_id": "p1"}
    assert comment_bot.is_reply(ev) is True


def test_is_reply_sin_parent_id():
    ev = {"comment_id": "c1", "parent_id": "", "post_id": "p1"}
    assert comment_bot.is_reply(ev) is False


def test_is_reply_parent_igual_al_post_no_es_reply():
    # Algunos payloads de FB ponen parent_id == post_id para comentarios top-level.
    ev = {"comment_id": "c1", "parent_id": "p1", "post_id": "p1"}
    assert comment_bot.is_reply(ev) is False


# ── Guarda 4: dedupe ────────────────────────────────────────────────────────

def test_already_handled_true():
    with patch.object(comment_bot, "_load_handled", return_value={"c1": {"ts": 1}}):
        assert comment_bot.already_handled("c1") is True


def test_already_handled_false():
    with patch.object(comment_bot, "_load_handled", return_value={}):
        assert comment_bot.already_handled("c1") is False
