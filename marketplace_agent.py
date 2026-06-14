"""
NEXUS Marketplace Agent — Wire + Atlas
Syncs tucarroconalejo.com inventory → Facebook Catalog (Vehicles)
Catalog ID: 1137133291627950 | Weekly sync every Sunday 6am
"""
import os
import json
import base64
import tempfile
import requests
import anthropic
from datetime import datetime
from dotenv import load_dotenv
from meta_publisher import upload_image_to_facebook

load_dotenv()

CATALOG_ID    = "1137133291627950"
CATALOG_TOKEN = os.getenv("META_CATALOG_TOKEN")  # System User Token — add to Render env vars
GRAPH_BASE    = "https://graph.facebook.com/v19.0"
INVENTORY_URL = "https://tucarroconalejo.com/api.php?action=list"
LOG_PATH      = os.path.join(os.path.dirname(__file__), "marketplace_log.json")
DEALER_URL    = "https://tucarroconalejo.com/"
DEALER_ADDR   = {
    "addr1": "2200 N State Rd 7",
    "city": "Hollywood",
    "region": "FL",
    "postal_code": "33021",
    "country": "US",
}

_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_INK_PROMPT = """Eres Ink, copywriter de NEXUS para @tucarroconalejo.
Escribe la descripción de Marketplace para este vehículo Toyota.

TONO: Cálido, directo, como Alejo hablando a un amigo. No corporativo.
IDIOMA: Español natural de South Florida.
LÍMITE: 250 palabras máximo.

ESTRUCTURA:
1. Gancho emocional (1 oración) — qué hace sentir este carro
2. 2-3 puntos clave (emoción/utilidad, no specs aburridos)
3. Nota de precio: "El precio indicado es el down payment estimado, no el precio total del vehículo."
4. CTA: "¿Tienes preguntas? Escríbeme aquí o llama al (954) 310-6671 — soy Alejo y te atiendo personalmente."

REGLAS: NUNCA menciones precio total ni mensualidades. Sin Markdown. Solo texto limpio."""

_BODY_STYLE = {
    "4Runner": "SUV", "RAV4": "SUV", "Highlander": "SUV",
    "Grand Highlander": "SUV", "Sequoia": "SUV", "Corolla Cross": "SUV",
    "bZ": "SUV", "C-HR": "SUV", "Land Cruiser": "SUV",
    "Camry": "Sedan", "Corolla": "Sedan", "Crown": "Sedan",
    "Tacoma": "Truck", "Tundra": "Truck",
    "Sienna": "Minivan",
    "GR Supra": "Coupe", "GR86": "Coupe",
    "Prius": "Hatchback",
}

_FUEL = {"bZ": "electric", "Prius": "hybrid"}


def _body_style(model: str) -> str:
    for k, v in _BODY_STYLE.items():
        if k.lower() in model.lower():
            return v
    return "SUV"


def _fuel_type(model: str) -> str:
    for k, v in _FUEL.items():
        if k.lower() in model.lower():
            return v
    return "gasoline"


def _make_key(v: dict) -> str:
    return f"{v['yr']}|{v['model']}|{v['trim']}|{v['color']}"


def _upload_b64_image(b64_data: str) -> str | None:
    try:
        if "base64," in b64_data:
            b64_data = b64_data.split("base64,")[1]
        img_bytes = base64.b64decode(b64_data)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(img_bytes)
            tmp_path = f.name
        url = upload_image_to_facebook(tmp_path)
        os.unlink(tmp_path)
        return url
    except Exception as e:
        print(f"  ⚠️  Image error: {e}")
        return None


def fetch_unique_inventory() -> list[dict]:
    """Fetch API and deduplicate by model/trim/color — one vehicle per combo."""
    r = requests.get(INVENTORY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    vehicles = r.json()["vehicles"]
    seen, unique = set(), []
    for v in vehicles:
        key = _make_key(v)
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def generate_description(v: dict) -> str:
    prompt = (
        f"Vehículo: {v['yr']} Toyota {v['model']} {v['trim']}\n"
        f"Color: {v['color']}\n"
        f"Down payment estimado: ${round(v['price'] * 0.20):,}\n"
        f"Tipo: {'Nuevo' if v.get('type') == 'new' else 'Usado'}"
    )
    resp = _claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=_INK_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _publish_to_catalog(v: dict, description: str, img_url: str | None) -> str | None:
    down_payment_cents = round(v["price"] * 0.20) * 100
    title = f"{v['yr']} Toyota {v['model']} {v['trim']} — {v['color']}"

    data = {
        "availability":     "in stock",
        "condition":        "new",
        "currency":         "USD",
        "description":      description,
        "make":             "Toyota",
        "model":            v["model"],
        "title":            title,
        "trim":             v.get("trim", ""),
        "year":             str(v["yr"]),
        "exterior_color":   v["color"],
        "price":            str(down_payment_cents),
        "state_of_vehicle": "new",
        "vehicle_type":     "car_truck",
        "vin":              v.get("vin", ""),
        "url":              DEALER_URL,
        "mileage":          json.dumps({"value": 0, "unit": "MI"}),
        "body_style":       _body_style(v["model"]),
        "fuel_type":        _fuel_type(v["model"]),
        "transmission":     "automatic",
        "address":          json.dumps(DEALER_ADDR),
    }
    if img_url:
        data["image_url[0]"] = img_url

    resp = requests.post(
        f"{GRAPH_BASE}/{CATALOG_ID}/vehicles",
        params={"access_token": CATALOG_TOKEN},
        data=data,
        timeout=30,
    )
    result = resp.json()
    if "id" in result:
        return result["id"]
    print(f"  ⚠️  Catalog error: {result}")
    return None


def _update_price(listing_id: str, down_payment_cents: int):
    requests.post(
        f"{GRAPH_BASE}/{listing_id}",
        params={"access_token": CATALOG_TOKEN},
        data={"price": str(down_payment_cents)},
        timeout=15,
    )


def mark_sold(listing_id: str):
    requests.post(
        f"{GRAPH_BASE}/{listing_id}",
        params={"access_token": CATALOG_TOKEN},
        data={"availability": "out of stock"},
        timeout=15,
    )


def load_log() -> dict:
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_sync": None, "by_listing_id": {}, "by_key": {}}


def save_log(log: dict):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def get_car_by_listing_id(listing_id: str) -> dict | None:
    """Used by webhook_server to get car context from a Marketplace referral."""
    log = load_log()
    return log["by_listing_id"].get(listing_id)


def sync():
    """
    Weekly sync — publishes new combos, updates prices, marks sold.
    Triggered every Sunday at 6am from main.py scheduler.
    """
    print("\n── NEXUS Marketplace Sync ─────────────────────")
    log = load_log()

    current_vehicles = fetch_unique_inventory()
    current_keys = {_make_key(v): v for v in current_vehicles}

    published = updated = sold_count = errors = 0

    for key, v in current_keys.items():
        down_payment = round(v["price"] * 0.20)

        if key not in log["by_key"]:
            print(f"  + {key}")
            description = generate_description(v)
            img_url = _upload_b64_image(v["img"]) if v.get("img") else None
            listing_id = _publish_to_catalog(v, description, img_url)
            if listing_id:
                log["by_key"][key] = listing_id
                log["by_listing_id"][listing_id] = {
                    "key": key,
                    "model": v["model"],
                    "trim": v.get("trim", ""),
                    "color": v["color"],
                    "yr": v["yr"],
                    "price": v["price"],
                    "down_payment": down_payment,
                    "vin": v.get("vin", ""),
                    "status": "active",
                }
                published += 1
            else:
                errors += 1
        else:
            listing_id = log["by_key"][key]
            stored = log["by_listing_id"].get(listing_id, {})
            if stored.get("price") != v["price"]:
                print(f"  ↑ Price: {key} ${stored.get('price', 0):,} → ${v['price']:,}")
                _update_price(listing_id, down_payment * 100)
                stored["price"] = v["price"]
                stored["down_payment"] = down_payment
                log["by_listing_id"][listing_id] = stored
                updated += 1

    for listing_id, info in log["by_listing_id"].items():
        if info.get("status") == "active" and info["key"] not in current_keys:
            print(f"  ✗ Sold: {info['key']}")
            mark_sold(listing_id)
            info["status"] = "sold"
            sold_count += 1

    log["last_sync"] = datetime.now().isoformat()
    save_log(log)

    print(f"  ✅ +{published} nuevos | ↑{updated} actualizados | ✗{sold_count} vendidos | ⚠️{errors} errores")
    print("──────────────────────────────────────────────")
    return {"published": published, "updated": updated, "sold": sold_count, "errors": errors}


if __name__ == "__main__":
    sync()
