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
