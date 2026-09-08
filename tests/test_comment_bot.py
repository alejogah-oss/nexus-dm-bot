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


# ── Guarda 5: rate limit ────────────────────────────────────────────────────

def _store_con_respuestas(n_global, post_id="pX", n_post=0, edad_seg=60):
    """Genera un store con n_global respuestas recientes (actions no vacío),
    de las cuales n_post son en post_id."""
    now = time.time()
    store = {}
    for i in range(n_global):
        store[f"g{i}"] = {"ts": now - edad_seg, "post_id": "otro",
                          "actions": ["private_ig"]}
    for i in range(n_post):
        store[f"p{i}"] = {"ts": now - edad_seg, "post_id": post_id,
                          "actions": ["private_ig"]}
    return store


def test_rate_limit_global_alcanzado():
    store = _store_con_respuestas(5)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is True


def test_rate_limit_global_no_alcanzado():
    store = _store_con_respuestas(4)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is False


def test_rate_limit_por_post_alcanzado():
    store = _store_con_respuestas(0, post_id="pX", n_post=3)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is True


def test_rate_limit_ignora_respuestas_viejas():
    # Respuestas de hace más de 1 hora no cuentan.
    store = _store_con_respuestas(10, edad_seg=3700)
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is False


def test_rate_limit_ignora_entradas_sin_accion():
    # Comentarios evaluados pero no respondidos (actions vacío) no cuentan.
    now = time.time()
    store = {f"s{i}": {"ts": now - 60, "post_id": "pX", "actions": []}
             for i in range(10)}
    with patch.object(comment_bot, "_load_handled", return_value=store):
        assert comment_bot.rate_limited("pX") is False


# ── Guarda 6: intención ─────────────────────────────────────────────────────

def _mock_anthropic_text(texto):
    resp = MagicMock()
    resp.content = [MagicMock(text=texto)]
    return resp


def test_classify_intent_normaliza_a_mayusculas_y_recorta():
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("  compra\n")):
        assert comment_bot.classify_intent("quiero un corolla") == "COMPRA"


def test_classify_intent_valor_desconocido_cae_a_otro():
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("no sé qué es")):
        assert comment_bot.classify_intent("hola") == "OTRO"


def test_classify_intent_error_de_api_devuelve_error():
    # Falla cerrado: si Haiku falla, la clasificación devuelve "ERROR" y el
    # orquestador NO responde.
    with patch.object(comment_bot.client.messages, "create",
                      side_effect=RuntimeError("timeout")):
        assert comment_bot.classify_intent("hola") == "ERROR"
