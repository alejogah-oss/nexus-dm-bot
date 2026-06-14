"""Webhook server — receives Facebook & Instagram DM + comment events."""
import hashlib
import hmac
import json
import os

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from dm_bot import handle_message, handle_get_started
from comment_bot import handle_facebook_comment, handle_instagram_comment

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "nexus_alejo_2026")
APP_SECRET   = os.getenv("META_APP_SECRET", "")
PAGE_ID      = os.getenv("META_PAGE_ID", "")


def _verify_signature(payload: bytes, signature: str) -> bool:
    if not APP_SECRET or not signature:
        return True  # skip in dev mode
    expected = "sha256=" + hmac.new(
        APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── WEBHOOK VERIFICATION ─────────────────────────────────────────────────────
@app.get("/webhook")
def verify_webhook():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verificado por Meta")
        return challenge, 200
    return "Token inválido", 403


# ── FACEBOOK MESSENGER ────────────────────────────────────────────────────────
@app.post("/webhook")
def receive_webhook():
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(request.get_data(), signature):
        return "Firma inválida", 401

    data = request.json
    if not data:
        return "ok", 200

    for entry in data.get("entry", []):
        # Facebook Messenger
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            if not sender_id or sender_id == PAGE_ID:
                continue  # skip messages from the page itself

            # Get Started button tap
            postback = event.get("postback", {})
            if postback.get("payload") == "GET_STARTED":
                handle_get_started(sender_id, platform="facebook")
                continue

            message = event.get("message", {})
            text = message.get("text", "")
            if text:
                handle_message(sender_id, text, platform="facebook")

        # Instagram DMs + comentarios
        for change in entry.get("changes", []):
            field = change.get("field")
            value = change.get("value", {})

            # Instagram DMs
            if field == "messages":
                for msg in value.get("messages", []):
                    sender_id = msg.get("from", {}).get("id")
                    text = msg.get("text", {}).get("body", "")
                    if sender_id and text:
                        handle_message(sender_id, text, platform="instagram")

            # Instagram comentarios en posts/anuncios
            elif field == "comments":
                comment_id = value.get("id")
                username   = value.get("from", {}).get("username", "")
                text       = value.get("text", "")
                if comment_id and text:
                    handle_instagram_comment(comment_id, username, text)

            # Facebook comentarios en posts/anuncios
            elif field == "feed":
                item = value.get("item")
                verb = value.get("verb")
                if item == "comment" and verb == "add":
                    comment_id = value.get("comment_id", "")
                    from_name  = value.get("from", {}).get("name", "")
                    text       = value.get("message", "")
                    post_id    = value.get("post_id", "")
                    if comment_id and text:
                        handle_facebook_comment(comment_id, from_name, text, post_id)

            # Menciones de la página en comentarios de terceros
            elif field == "mention":
                comment_id = value.get("comment_id", "")
                from_name  = value.get("sender", {}).get("name", "")
                text       = value.get("message", "")
                post_id    = value.get("post_id", "")
                if comment_id and text:
                    print(f"[MENTION] {from_name}: {text[:60]}...")
                    handle_facebook_comment(comment_id, from_name, text, post_id)

    return "ok", 200


# ── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify({"status": "ok", "bot": "nexus-tucarroconalejo"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    print(f"🤖 NEXUS DM Bot corriendo en puerto {port}")
    print(f"   Webhook URL: https://TU-DOMINIO/webhook")
    print(f"   Verify Token: {VERIFY_TOKEN}")
    app.run(host="0.0.0.0", port=port, debug=False)
