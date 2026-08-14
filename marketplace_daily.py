"""
NEXUS Marketplace Daily — Wire + Ink
Genera el listing del día para Facebook Marketplace (individual seller).
Uso: python3 marketplace_daily.py
Resultado: foto en ~/Desktop/nexus_listing.jpg + prompt listo para Chrome Claude
"""
import os
import json
import base64
import requests
import anthropic
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

INVENTORY_URL  = "https://tucarroconalejo.com/api.php?action=list"
LOG_PATH       = os.path.join(os.path.dirname(__file__), "marketplace_daily_log.json")
PHOTO_PATH     = os.path.expanduser("~/Desktop/nexus_listing.jpg")
DAYS_COOLDOWN  = 30  # no repetir el mismo combo en 30 días

_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_INK_MARKETPLACE = """Eres Ink, copywriter de NEXUS para @tucarroconalejo.
Escribe la descripción de un listing de Facebook Marketplace para este vehículo Toyota.
El tono es de VENDEDOR INDIVIDUAL, no de dealer corporativo — cálido, directo, como Alejo hablando a un amigo.

REGLAS ABSOLUTAS DE FORMATO:
- Empieza DIRECTAMENTE con el gancho, sin ningún título, encabezado ni prefacio
- PROHIBIDO: #, *, **, guiones al inicio de línea, comillas de apertura, "LISTING", "MARKETPLACE", o cualquier etiqueta
- Solo texto limpio en párrafos separados por salto de línea
- Sin emojis excesivos

ESTRUCTURA:
Párrafo 1: Gancho emocional (1-2 oraciones que conecten con el carro)
Párrafo 2: 2-3 puntos clave (emoción/utilidad, no specs aburridos)
Párrafo 3: "El precio que ves en este anuncio es el down payment (inicial), que puede estar entre el 15% y el 25% del valor del vehículo dependiendo de tu crédito. Para más info escríbeme o llama al (954) 910-6671 — soy Alejo."
Párrafo 4: "Estoy en Hollywood, FL. Agendamos y te doy la dirección exacta."

LÍMITE: 150 palabras máximo."""


def _make_key(v: dict) -> str:
    return f"{v['yr']}|{v['model']}|{v['trim']}|{v['color']}"


def load_log() -> dict:
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"listings": [], "last_run": None}


def save_log(log: dict):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def _listed_keys_last_n_days(log: dict, days: int) -> set:
    cutoff = datetime.now() - timedelta(days=days)
    recent = set()
    for entry in log.get("listings", []):
        try:
            if datetime.fromisoformat(entry["date"]) > cutoff:
                recent.add(entry["key"])
        except Exception:
            pass
    return recent


def fetch_unique_inventory() -> list[dict]:
    r = requests.get(INVENTORY_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    vehicles = r.json()["vehicles"]
    seen, unique = set(), []
    for v in vehicles:
        key = _make_key(v)
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def pick_vehicle(log: dict, vehicles: list[dict]) -> dict | None:
    recent = _listed_keys_last_n_days(log, DAYS_COOLDOWN)
    # Primero intenta con carros no listados recientemente
    for v in vehicles:
        if _make_key(v) not in recent:
            return v
    # Si todos pasaron por el ciclo, empieza de nuevo (el más antiguo primero)
    listings = sorted(log.get("listings", []), key=lambda x: x.get("date", ""))
    oldest_keys = [e["key"] for e in listings]
    for key in oldest_keys:
        for v in vehicles:
            if _make_key(v) == key:
                return v
    return vehicles[0] if vehicles else None


def generate_description(v: dict) -> str:
    down = round(v["price"] * 0.20 / 100) * 100
    prompt = (
        f"Vehículo: {v['yr']} Toyota {v['model']} {v['trim']}\n"
        f"Color: {v['color']}\n"
        f"MSRP: ${v['price']:,}\n"
        f"Down payment desde: ${down:,}\n"
        f"Tipo: {'Nuevo' if v.get('type') == 'new' else 'Usado'}\n"
        f"Millaje: {int(v.get('mileage') or 0):,} millas"
    )
    resp = _claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=350,
        system=_INK_MARKETPLACE,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def save_photo(v: dict) -> bool:
    img_data = v.get("img", "")
    if not img_data:
        return False
    try:
        if "base64," in img_data:
            img_data = img_data.split("base64,")[1]
        with open(PHOTO_PATH, "wb") as f:
            f.write(base64.b64decode(img_data))
        return True
    except Exception as e:
        print(f"  ⚠️  Error guardando foto: {e}")
        return False


def generate_chrome_prompt(v: dict, description: str) -> str:
    down = round(v["price"] * 0.20 / 100) * 100
    msrp = v["price"]
    has_photo = os.path.exists(PHOTO_PATH)
    photo_note = f"Sube la foto desde: {PHOTO_PATH}" if has_photo else "⚠️ No hay foto disponible — salta el paso de imagen"

    return f"""Necesito que publiques un listing en Facebook Marketplace. Estoy logueado en mi cuenta de Facebook.

PASOS:
1. Ve a: facebook.com/marketplace/create/vehicle
2. Selecciona la categoría "Vehículos" o "Cars & Trucks"
3. Llena los campos exactamente así:

   TÍTULO: {v['yr']} Toyota {v['model']} {v.get('trim','')} — {v['color']}
   PRECIO: {msrp}
   CONDICIÓN: New (Nuevo)
   AÑO: {v['yr']}
   MARCA: Toyota
   MODELO: {v['model']}
   MILLAJE: 0
   TRANSMISIÓN: Automatic
   COLOR EXTERIOR: {v['color']}
   UBICACIÓN: Hollywood, FL

4. En el campo de DESCRIPCIÓN pega exactamente esto:
---
{description}
---

5. {photo_note}

6. Haz clic en "Siguiente" y luego "Publicar"

7. Cuando el listing esté publicado, compárteme la URL (facebook.com/marketplace/item/...)

Datos adicionales del vehículo (por si los pide el formulario):
- VIN: {v.get('vin', 'disponible al contactar')}
- Down payment desde: ${down:,}
- Stock: {v.get('stock', 'N/A')}"""


def log_listing(log: dict, v: dict, description: str = ""):
    log.setdefault("listings", []).append({
        "date": datetime.now().isoformat(),
        "key": _make_key(v),
        "model": v["model"],
        "trim": v.get("trim", ""),
        "color": v["color"],
        "yr": v["yr"],
        "price": v["price"],
        "vin": v.get("vin", ""),
        "stock": v.get("stock", ""),
        "description": description,
    })
    log["last_run"] = datetime.now().isoformat()


def run(dry_run: bool = False):
    print("\n── NEXUS Marketplace Daily ─────────────────────")

    print("Cargando inventario...")
    vehicles = fetch_unique_inventory()
    print(f"  {len(vehicles)} vehículos únicos disponibles")

    log = load_log()
    recent = _listed_keys_last_n_days(log, DAYS_COOLDOWN)
    print(f"  {len(recent)} listados en los últimos {DAYS_COOLDOWN} días")

    vehicle = pick_vehicle(log, vehicles)
    if not vehicle:
        print("❌ No hay vehículos disponibles")
        return

    print(f"\n🚗 Carro del día: {vehicle['yr']} Toyota {vehicle['model']} {vehicle.get('trim','')} — {vehicle['color']}")
    print(f"   MSRP: ${vehicle['price']:,} | Down: ${round(vehicle['price'] * 0.20 / 100) * 100:,}")

    print("\n✍️  Ink generando descripción...")
    description = generate_description(vehicle)

    print("🖼️  Guardando foto en Desktop...")
    has_photo = save_photo(vehicle)
    print(f"   {'✅ Foto lista en ' + PHOTO_PATH if has_photo else '⚠️  Sin foto'}")

    prompt = generate_chrome_prompt(vehicle, description)

    print("\n" + "═" * 60)
    print("  PROMPT PARA CHROME CLAUDE — copia y pega todo esto:")
    print("═" * 60)
    print(prompt)
    print("═" * 60)

    if not dry_run:
        log_listing(log, vehicle, description)
        save_log(log)
        print(f"\n✅ Registrado en log. Próximo disponible: {len(vehicles) - len(recent) - 1} carros en fila.")
    else:
        print("\n[DRY RUN — no se guardó en log]")

    print("──────────────────────────────────────────────\n")
    return vehicle, description, prompt


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    run(dry_run=dry)
