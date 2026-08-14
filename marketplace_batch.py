"""
NEXUS Marketplace Batch — Publica el siguiente vehículo en orden del CSV
Uso:
  python3 marketplace_batch.py           # publica el siguiente en la cola
  python3 marketplace_batch.py --dry     # muestra qué publicaría sin hacerlo
  python3 marketplace_batch.py --status  # muestra estado de la cola
"""
import io
import csv
import json
import sys
import subprocess
import requests
from pathlib import Path
from datetime import datetime

from marketplace_daily import (
    LOG_PATH, PHOTO_PATH, fetch_unique_inventory,
    generate_description, save_photo, load_log, save_log,
    log_listing, _make_key,
)

CSV_URL = "https://bot.tucarroconalejo.com/feed/vehicles.csv"


def fetch_csv_order() -> list[str]:
    """Retorna los keys únicos del inventario en el orden exacto del CSV."""
    r = requests.get(CSV_URL, timeout=15)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text.lstrip("﻿")))
    seen, order = set(), []
    for row in reader:
        key = f"{row['year']}|{row['model']}|{row.get('trim', '').strip()}|{row['exterior_color'].strip()}"
        if key not in seen:
            seen.add(key)
            order.append(key)
    return order


def pick_next(log: dict, vehicles: list[dict], csv_order: list[str]) -> dict | None:
    """Primer vehículo del CSV sin listing_url confirmada en el log."""
    published = {l["key"] for l in log.get("listings", []) if l.get("listing_url")}
    by_key = {_make_key(v): v for v in vehicles}

    for key in csv_order:
        if key not in published and key in by_key:
            return by_key[key]

    # Todos publicados → reiniciar desde el primero del CSV
    print("  ♻️  Ciclo completo — reiniciando desde el principio")
    for key in csv_order:
        if key in by_key:
            return by_key[key]
    return None


def show_status(log: dict, csv_order: list[str]):
    published = {l["key"] for l in log.get("listings", []) if l.get("listing_url")}
    prepared  = {l["key"] for l in log.get("listings", []) if not l.get("listing_url")}
    total = len(csv_order)
    done  = len(published)

    print(f"\n── Cola Marketplace ({done}/{total} publicados) ──────────────────")
    for i, key in enumerate(csv_order[:30]):
        if key in published:
            icon = "✅"
        elif key in prepared:
            icon = "🕐"  # en log pero sin URL
        else:
            icon = "  "
        print(f"  {icon} [{i+1:3}] {key}")
    if total > 30:
        print(f"  ... y {total - 30} más")
    print("──────────────────────────────────────────────\n")


def run(dry_run: bool = False, status_only: bool = False):
    print("\n── NEXUS Marketplace Batch ─────────────────────")

    print("  Cargando inventario JSON...")
    vehicles = fetch_unique_inventory()
    print(f"  {len(vehicles)} vehículos únicos")

    print("  Cargando orden del CSV...")
    csv_order = fetch_csv_order()
    print(f"  {len(csv_order)} en CSV")

    log = load_log()
    published_count = sum(1 for l in log.get("listings", []) if l.get("listing_url"))
    print(f"  {published_count} publicados con URL")

    if status_only:
        show_status(log, csv_order)
        return

    # Revisar si el último entry ya está preparado (sin URL)
    listings = log.get("listings", [])
    last = listings[-1] if listings else None
    last_is_pending = last and not last.get("listing_url")

    if last_is_pending:
        # Reusar el vehículo ya preparado en el log
        pending_key = last["key"]
        print(f"\n  🕐 Retomando vehículo pendiente: {pending_key}")
        by_key = {_make_key(v): v for v in vehicles}
        v = by_key.get(pending_key)
        if v:
            v["down_payment"] = last.get("down_payment") or round(v["price"] * 0.20 / 100) * 100
            v["title"]        = last.get("title") or f"{v['yr']} Toyota {v['model']} {v.get('trim', '')} — {v['color']}"
            v["description"]  = last.get("description") or generate_description(v)
            # Actualizar descripción en log si faltaba
            if not last.get("description"):
                log["listings"][-1]["description"] = v["description"]
                save_log(log)
    else:
        v = pick_next(log, vehicles, csv_order)
        if not v:
            print("❌ No hay vehículos disponibles en el inventario")
            return
        v["down_payment"] = round(v["price"] * 0.20 / 100) * 100
        v["title"]        = f"{v['yr']} Toyota {v['model']} {v.get('trim', '')} — {v['color']}"

    print(f"\n🚗 {v['title']}")
    print(f"   MSRP: ${v['price']:,} | Down: ${v['down_payment']:,}")

    # Generar descripción si no existe
    if not v.get("description"):
        print("  ✍️  Generando descripción con Ink...")
        v["description"] = generate_description(v)

    # Guardar foto en Desktop
    print("  🖼️  Guardando foto del vehículo...")
    if not save_photo(v):
        print("  ⚠️  Sin foto — el poster continuará sin imagen")
    else:
        print(f"  ✅ Foto lista: {PHOTO_PATH}")

    if dry_run:
        print("\n── [DRY RUN] ───────────────────────────────────")
        print(f"Título:       {v['title']}")
        print(f"Precio (down): ${v['down_payment']:,}")
        print(f"Key del log:  {_make_key(v)}")
        print(f"\nDescripción:\n{v.get('description', '')}")
        print("──────────────────────────────────────────────\n")
        return

    # Agregar al log si es un vehículo nuevo (no el pendiente)
    if not last_is_pending:
        log_listing(log, v, v["description"])
        save_log(log)
        print("  ✅ Registrado en log")

    # Publicar
    print("\n  Iniciando marketplace_poster.py...")
    result = subprocess.run(
        [sys.executable, "marketplace_poster.py"],
        cwd=str(Path(__file__).parent),
    )
    if result.returncode == 0:
        print("✅ Publicación completada")
    else:
        print(f"⚠️  Poster salió con código {result.returncode}")

    print("──────────────────────────────────────────────\n")


if __name__ == "__main__":
    dry    = "--dry"    in sys.argv
    status = "--status" in sys.argv
    run(dry_run=dry, status_only=status)
