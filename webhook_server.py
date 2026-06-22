"""Webhook server — receives Facebook & Instagram DM + comment events."""
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import uuid

import requests as req_lib
from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv
from dm_bot import handle_message, handle_get_started, handle_marketplace_message, generate_reply
from comment_bot import handle_facebook_comment, handle_instagram_comment
from marketplace_agent import get_car_by_listing_id

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
            if not text:
                continue

            # Check if message came from a Marketplace listing
            listing_id = (
                event.get("referral", {}).get("product", {}).get("id") or
                message.get("referral", {}).get("product", {}).get("id")
            )
            if listing_id:
                car = get_car_by_listing_id(listing_id)
                if car:
                    handle_marketplace_message(sender_id, text, car, platform="facebook")
                    continue

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


# ── WEB CHAT ──────────────────────────────────────────────────────────────────
_web_conversations: dict[str, list] = {}

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

WEB_WELCOME = (
    "¡Hola! Soy el asistente de Alejo 👋 "
    "Tenemos más de 430 Toyotas disponibles en Hollywood Toyota, Florida. "
    "¿Qué modelo te interesa?"
)


@app.route("/web-chat", methods=["OPTIONS"])
def web_chat_preflight():
    """Handles CORS preflight requests from the browser widget."""
    return Response("", status=204, headers=_CORS_HEADERS)


@app.route("/web-chat", methods=["POST"])
def web_chat():
    """
    Chat endpoint for the website widget.

    Request  JSON: { "message": str, "session_id": str }
    Response JSON: { "reply": str, "session_id": str }
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    session_id = (data.get("session_id") or "").strip()

    if not message:
        resp = jsonify({"error": "message is required"})
        resp.headers.update(_CORS_HEADERS)
        return resp, 400

    if not session_id:
        session_id = str(uuid.uuid4())

    history = _web_conversations.get(session_id, [])

    # First message in this session — prepend a silent welcome context so the
    # AI knows it's talking to a web visitor (not a DM)
    if not history:
        history = [
            {
                "role": "user",
                "content": "[Sistema: El usuario está chateando desde el sitio web tucarroconalejo.com]",
            },
            {"role": "assistant", "content": WEB_WELCOME},
        ]

    reply, is_hot = generate_reply(history, message)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    _web_conversations[session_id] = history[-20:]  # keep last 10 exchanges

    if is_hot:
        print(
            f"[WEB-CHAT] HOT LEAD — session={session_id[:12]}... | msg={message[:80]}"
        )

    resp = jsonify({"reply": reply, "session_id": session_id})
    resp.headers.update(_CORS_HEADERS)
    return resp, 200


# ── VEHICLE FEED ──────────────────────────────────────────────────────────────
_INVENTORY_URL = "https://tucarroconalejo.com/api.php?action=list"
_DEALER = {"addr1": "2200 N State Rd 7", "city": "Hollywood",
           "region": "FL", "postal_code": "33021", "country": "US"}
_LAT, _LNG = "26.0219", "-80.1942"
_BODY_STYLES = {
    "4Runner": "SUV", "RAV4": "SUV", "Highlander": "SUV",
    "Grand Highlander": "SUV", "Sequoia": "SUV", "Corolla Cross": "SUV",
    "bZ": "SUV", "C-HR": "SUV", "Land Cruiser": "SUV",
    "Camry": "SEDAN", "Corolla": "SEDAN", "Crown": "SEDAN",
    "Tacoma": "PICKUP", "Tundra": "PICKUP",
    "Sienna": "MINIVAN", "GR Supra": "COUPE", "GR86": "COUPE",
    "Prius": "HATCHBACK",
}


def _body_style(model):
    for k, v in _BODY_STYLES.items():
        if k.lower() in model.lower():
            return v
    return "SUV"


def _fuel_type(model):
    m = model.lower()
    if "bz" in m or "electric" in m:
        return "ELECTRIC"
    if "plug-in hybrid" in m:
        return "PLUG_IN_HYBRID"
    if "hybrid" in m:
        return "HYBRID"
    return "GASOLINE"


def _load_model_descriptions() -> dict:
    path = os.path.join(os.path.dirname(__file__), "model_descriptions.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_MODEL_DESCRIPTIONS = _load_model_descriptions()


def _get_model_description(model: str) -> str | None:
    if model in _MODEL_DESCRIPTIONS:
        return _MODEL_DESCRIPTIONS[model]
    ml = model.lower()
    for key, desc in _MODEL_DESCRIPTIONS.items():
        kl = key.lower()
        if ml.startswith(kl) or kl.startswith(ml):
            return desc
    return None


# Cache en memoria — evita descargar 430 vehículos por cada imagen solicitada
_inventory_cache: list = []
_inventory_cache_ts: float = 0.0
_INVENTORY_CACHE_TTL = 300  # 5 minutos


def _fetch_all_inventory() -> list:
    """Returns every vehicle from the API with 5-minute in-memory cache."""
    global _inventory_cache, _inventory_cache_ts
    import time
    if _inventory_cache and (time.time() - _inventory_cache_ts) < _INVENTORY_CACHE_TTL:
        return _inventory_cache
    r = req_lib.get(_INVENTORY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    _inventory_cache = r.json()["vehicles"]
    _inventory_cache_ts = time.time()
    return _inventory_cache


def _fetch_unique_inventory():
    """Returns one vehicle per yr/model/trim/color combo — used for social posts."""
    vehicles = _fetch_all_inventory()
    seen, unique = set(), []
    for v in vehicles:
        key = f"{v['yr']}|{v['model']}|{v.get('trim','')}|{v['color']}"
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


@app.get("/feed/image/<vehicle_id>")
def vehicle_image(vehicle_id):
    """Sirve la foto de un vehículo como JPEG desde el inventario."""
    try:
        vehicles = _fetch_all_inventory()
        vehicle = next(
            (v for v in vehicles
             if v.get("vin") == vehicle_id or v.get("stock") == vehicle_id),
            None,
        )
        if not vehicle:
            return "Vehicle not found", 404
        img_data = vehicle.get("img", "")
        if not img_data:
            return "No image", 404
        if "base64," in img_data:
            img_data = img_data.split("base64,")[1]
        resp = Response(base64.b64decode(img_data), mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "public, max-age=86400"  # browser cachea 24h
        return resp
    except Exception as e:
        return f"Error: {e}", 500


@app.get("/feed/vehicles.csv")
def vehicles_csv():
    """Genera el CSV de inventario para Facebook Vehicle Catalog."""
    try:
        vehicles = _fetch_unique_inventory()
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow([
            "id", "title", "description", "availability", "condition",
            "price", "image_link", "link", "body_style", "make", "model",
            "year", "state_of_vehicle", "mileage.unit", "mileage.value",
            "address.addr1", "address.city", "address.region",
            "address.postal_code", "address.country",
            "latitude", "longitude", "exterior_color", "trim",
            "fuel_type", "transmission",
        ])
        for v in vehicles:
            vid = v.get("vin") or v.get("stock", "")
            if not vid:
                continue
            down = round(v["price"] * 0.20 / 100) * 100
            raw_model = v["model"]
            model = raw_model if raw_model.lower() != "toyota" else v.get("trim", "")
            trim = v.get("trim", "") if raw_model.lower() != "toyota" else ""
            title = f"{v['yr']} Toyota {model} {trim} - {v['color']}".strip()
            desc = _get_model_description(model) or (
                f"{v['yr']} Toyota {model} {trim} en {v['color']}. "
                f"Vehiculo nuevo disponible en Hollywood Toyota, FL. "
                f"El precio indicado es el down payment estimado (15%-25% del valor total segun tu credito). "
                f"Escribeme o llama al (954) 310-6671 - soy Alejo, te atiendo personalmente."
            )
            w.writerow([
                f"{vid}-2026", title, desc, "IN STOCK", "NEW",
                f"{v['price']} USD",
                f"https://bot.tucarroconalejo.com/feed/image/{vid}",
                f"https://tucarroconalejo.com/?stock={vid}",
                _body_style(model), "Toyota", model,
                v["yr"], "NEW", "MI", 0,
                _DEALER["addr1"], _DEALER["city"], _DEALER["region"],
                _DEALER["postal_code"], _DEALER["country"],
                _LAT, _LNG, v["color"], trim,
                _fuel_type(model), "AUTOMATIC",
            ])
        return Response(
            output.getvalue().encode("utf-8"),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=vehicles.csv"},
        )
    except Exception as e:
        return f"Error generando CSV: {e}", 500


def _keep_alive():
    """Pinga /health cada 10 minutos para evitar que Render duerma el servicio."""
    import threading, time
    def _ping():
        while True:
            time.sleep(600)
            try:
                req_lib.get("https://bot.tucarroconalejo.com/health", timeout=10)
            except Exception:
                pass
    t = threading.Thread(target=_ping, daemon=True)
    t.start()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    _keep_alive()
    print(f"🤖 NEXUS DM Bot corriendo en puerto {port}")
    print(f"   Webhook URL: https://TU-DOMINIO/webhook")
    print(f"   Verify Token: {VERIFY_TOKEN}")
    app.run(host="0.0.0.0", port=port, debug=False)
