import json
import time
from unittest.mock import patch, mock_open, MagicMock

import pytest

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

@pytest.fixture(autouse=True)
def _pin_rate_limits(monkeypatch):
    # Los topes son configurables por env (default 20/8 en prod). Se fijan a
    # 5/3 para que los tests de esta sección sean deterministas.
    monkeypatch.setenv("COMMENT_MAX_PER_HOUR_GLOBAL", "5")
    monkeypatch.setenv("COMMENT_MAX_PER_HOUR_POST", "3")


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


# ── Redacción ───────────────────────────────────────────────────────────────

def test_comment_voice_tiene_el_telefono_correcto():
    # El número correcto de Alejo es (954) 910-6671 (ver .env ALEJO_PHONE,
    # nexus_agency.py). El 310 es una alucinación recurrente de Claude.
    assert "(954) 910-6671" in comment_bot.COMMENT_VOICE
    assert "310-6671" not in comment_bot.COMMENT_VOICE


def test_comment_voice_prohibe_precios():
    v = comment_bot.COMMENT_VOICE.lower()
    assert "nunca" in v and ("precio" in v or "mensualidad" in v or "tasa" in v)


def test_generate_private_reply_usa_haiku_y_recorta():
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("  ¡Claro! Te escribo por DM 🙌\n")):
        out = comment_bot.generate_private_reply("quiero un corolla", "COMPRA")
    assert out == "¡Claro! Te escribo por DM 🙌"


def test_generate_private_reply_corrige_telefono_alucinado():
    # Mismo guard que dm_bot.py:222 — si Haiku pone 310-6671, se corrige a 910-6671.
    with patch.object(comment_bot.client.messages, "create",
                      return_value=_mock_anthropic_text("Llama al (954) 310-6671 🙌")):
        out = comment_bot.generate_private_reply("hola", "COMPRA")
    assert "310-6671" not in out
    assert "910-6671" in out


def test_generate_private_reply_fallo_usa_texto_de_respaldo():
    with patch.object(comment_bot.client.messages, "create",
                      side_effect=RuntimeError("boom")):
        out = comment_bot.generate_private_reply("hola", "COMPRA")
    assert "DM" in out or "954" in out   # respaldo fijo, nunca vacío


# ── Envío (Graph API) ───────────────────────────────────────────────────────

def _mock_post_ok():
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"id": "reply_1"}
    return r


def test_send_private_reply_fb_llama_endpoint_private_replies():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        ok = comment_bot.send_private_reply("facebook", "c1", "hola")
    assert ok is True
    url = mp.call_args[0][0]
    assert url.endswith("/c1/private_replies")


def test_send_private_reply_ig_usa_messages_con_comment_id():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        with patch.object(comment_bot, "IG_USER_ID", "IG456"):
            ok = comment_bot.send_private_reply("instagram", "c1", "hola")
    assert ok is True
    url = mp.call_args[0][0]
    assert url.endswith("/IG456/messages")
    body = mp.call_args[1]["json"]
    assert body["recipient"] == {"comment_id": "c1"}
    assert body["message"] == {"text": "hola"}


def test_send_private_reply_ya_respondido_cuenta_como_exito():
    # Meta: (#10900) ya se envió una private reply para este comentario.
    r = MagicMock()
    r.status_code = 400
    r.json.return_value = {"error": {"code": 10900, "message": "already replied"}}
    with patch("comment_bot.requests.post", return_value=r):
        assert comment_bot.send_private_reply("facebook", "c1", "hola") is True


def test_send_private_reply_error_de_red_devuelve_false():
    with patch("comment_bot.requests.post", side_effect=comment_bot.requests.exceptions.Timeout()):
        assert comment_bot.send_private_reply("facebook", "c1", "hola") is False


def test_send_public_ack_fb():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        ok = comment_bot.send_public_ack("facebook", "c1")
    assert ok is True
    assert mp.call_args[0][0].endswith("/c1/comments")
    assert mp.call_args[1]["json"]["message"] == comment_bot.PUBLIC_ACK


def test_send_public_ack_ig_usa_replies():
    with patch("comment_bot.requests.post", return_value=_mock_post_ok()) as mp:
        ok = comment_bot.send_public_ack("instagram", "c1")
    assert ok is True
    assert mp.call_args[0][0].endswith("/c1/replies")


# ── Orquestador handle_comment ──────────────────────────────────────────────

def _event(**over):
    ev = {"platform": "instagram", "comment_id": "c1", "author_id": "cliente789",
          "text": "quiero un corolla", "post_id": "p1", "parent_id": ""}
    ev.update(over)
    return ev


@patch("comment_bot.requests.post")
def test_handle_comment_kill_switch_apagado(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "0")
    assert comment_bot.handle_comment(_event()) == "skipped:disabled"
    mp.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_ignora_comentario_propio_LOOP_REGRESSION(mp, monkeypatch):
    # REGRESIÓN DEL INCIDENTE 6 sep 2026: un comentario cuyo autor es nuestra
    # propia cuenta IG NUNCA debe procesarse. Sin esto el bot se responde a sí
    # mismo y entra en loop (fueron ~950 comentarios).
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_OWN_IDS", {"IG456"}):
        res = comment_bot.handle_comment(_event(author_id="IG456"))
    assert res == "skipped:identity"
    mp.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_ignora_respuesta_anidada(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    res = comment_bot.handle_comment(_event(parent_id="c0"))
    assert res == "skipped:reply"
    mp.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_dedupe(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", return_value={"c1": {"ts": 1}}):
        res = comment_bot.handle_comment(_event())
    assert res == "skipped:dedupe"
    mp.assert_not_called()


@patch("comment_bot.pulse_notify")
@patch("comment_bot.requests.post")
def test_handle_comment_rate_limit_avisa_a_pulse(mp, mpulse, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=True):
        res = comment_bot.handle_comment(_event())
    assert res == "skipped:ratelimit"
    mp.assert_not_called()
    mpulse.assert_called_once()


@patch("comment_bot.requests.post")
def test_handle_comment_felicitacion_no_responde_pero_se_registra(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    saved = {}
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="POSITIVO"), \
         patch.object(comment_bot, "_save_handled", side_effect=lambda s: saved.update(s)):
        res = comment_bot.handle_comment(_event(text="bonito carro!"))
    assert res == "skipped:intent"
    mp.assert_not_called()
    assert saved["c1"]["actions"] == []


@patch("comment_bot.requests.post")
def test_handle_comment_error_de_clasificacion_no_responde(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="ERROR"):
        res = comment_bot.handle_comment(_event())
    assert res == "skipped:classify_error"
    mp.assert_not_called()


def test_handle_comment_intencion_compra_responde_privado_y_publico(monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    saved = {}
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="COMPRA"), \
         patch.object(comment_bot, "generate_private_reply", return_value="Te escribo 🙌"), \
         patch.object(comment_bot, "send_private_reply", return_value=True) as sp, \
         patch.object(comment_bot, "send_public_ack", return_value=True) as pa, \
         patch.object(comment_bot, "_save_handled", side_effect=lambda s: saved.update(s)):
        res = comment_bot.handle_comment(_event())
    assert res == "replied"
    sp.assert_called_once_with("instagram", "c1", "Te escribo 🙌")
    pa.assert_called_once_with("instagram", "c1")
    assert saved["c1"]["intent"] == "COMPRA"
    assert saved["c1"]["actions"] == ["private_instagram", "public_instagram"]


def test_handle_comment_dry_run_no_postea(monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    monkeypatch.setenv("COMMENT_BOT_DRY_RUN", "1")
    with patch.object(comment_bot, "_load_handled", return_value={}), \
         patch.object(comment_bot, "rate_limited", return_value=False), \
         patch.object(comment_bot, "classify_intent", return_value="COMPRA"), \
         patch.object(comment_bot, "send_private_reply") as sp, \
         patch.object(comment_bot, "send_public_ack") as pa, \
         patch.object(comment_bot, "_save_handled") as sv:
        res = comment_bot.handle_comment(_event())
    assert res == "dryrun:would_reply:COMPRA"
    sp.assert_not_called()
    pa.assert_not_called()
    sv.assert_not_called()


@patch("comment_bot.requests.post")
def test_handle_comment_nunca_lanza_excepcion(mp, monkeypatch):
    monkeypatch.setenv("COMMENT_BOT_ENABLED", "1")
    with patch.object(comment_bot, "_load_handled", side_effect=RuntimeError("disco lleno")):
        res = comment_bot.handle_comment(_event())
    assert res.startswith("error:")
