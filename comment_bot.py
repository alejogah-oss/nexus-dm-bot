"""
Comment Bot — responde comentarios en posts y anuncios de @tucarroconalejo.
Cubre Facebook (feed) e Instagram (comments).

7 guardas en capas antes de responder (ver docs/superpowers/specs/2026-09-07-*):
  1. kill switch  2. identidad  3. solo top-level  4. dedupe
  5. rate limit   6. intención  7. backstop de Meta (1 private reply / comentario)

Incidente que motivó esto: 6 sep 2026, ~950 comentarios en loop porque no había
guarda de identidad y el bot se respondía a sí mismo.
"""
import json
import os
import time

import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

client            = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID           = os.getenv("META_PAGE_ID", "")
IG_USER_ID        = os.getenv("META_IG_USER_ID", "")
_OWN_IDS          = {i for i in (PAGE_ID, IG_USER_ID) if i}

GRAPH             = "https://graph.facebook.com/v19.0"
HANDLED_STORE     = os.path.join(os.path.dirname(__file__), "comments_handled.json")
PUBLIC_ACK        = "¡Te escribimos al DM! 🙌"
INTENT_ACTIONABLE = {"COMPRA", "PRECIO", "CREDITO"}
MAX_PER_HOUR_GLOBAL = 5
MAX_PER_HOUR_POST   = 3
PRIVATE_REPLY_WINDOW_DAYS = 7


def _enabled() -> bool:
    return os.getenv("COMMENT_BOT_ENABLED", "0") == "1"


def _dry_run() -> bool:
    return os.getenv("COMMENT_BOT_DRY_RUN", "0") == "1"


# ── Store ────────────────────────────────────────────────────────────────────

def _load_handled() -> dict:
    if not os.path.exists(HANDLED_STORE):
        return {}
    try:
        with open(HANDLED_STORE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_handled(store: dict) -> None:
    with open(HANDLED_STORE, "w") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
