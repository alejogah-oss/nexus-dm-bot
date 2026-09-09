"""Diagnóstico de un solo tiro: ¿le llega al bot el rango que Alejo carga en el scanner?
Solo lee. No toca Facebook, no escribe nada, no manda mensajes.
Correr en el Mac Pro:  cd ~/nexus-automation && venv/bin/python3 check_scanner_pipe.py
"""
import json, os, subprocess, sys
from pathlib import Path

def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception: return "?"

print("=" * 62)
print(" 1. RAMA QUE CORRE ESTA MÁQUINA")
print("=" * 62)
print("   rama:", sh("git branch --show-current") or "(desconocida)")
print("   commit:", sh("git log --oneline -1") or "(desconocido)")

print("\n" + "=" * 62)
print(" 2. ¿EXISTE EL CÓDIGO QUE LEE EL RANGO DEL SCANNER?")
print("=" * 62)
src = Path("marketplace_inbox_bot.py")
if not src.is_file():
    print("   ✗ no encuentro marketplace_inbox_bot.py — ¿estás en ~/nexus-automation?")
    sys.exit(1)
txt = src.read_text()
for fn in ("_apply_scanner_pricing", "_get_scanner_inventory", "_resolve_scanner_by_ref_code"):
    n = txt.count(fn)
    print(f"   {'✓' if n else '✗'} {fn}: {n} referencias")
if "_apply_scanner_pricing" not in txt:
    print("\n   >>> CAUSA ENCONTRADA: esta máquina corre una versión SIN el precio")
    print("       del scanner. El rango nunca puede llegar al bot. Hay que")
    print("       desplegar la rama que lo tiene ANTES de tocar el prompt.")

print("\n" + "=" * 62)
print(" 3. ¿EL BOT ENCUENTRA LA CARPETA DEL SCANNER?")
print("=" * 62)
inv = os.environ.get("INVENTORY_DIR", str(Path.cwd() / "inventario"))
root = Path(inv)
print(f"   INVENTORY_DIR = {inv}")
print(f"   ¿existe?      = {root.exists()}")
listings = []
if root.exists():
    for d in root.iterdir():
        lj = d / "listing.json"
        if lj.is_file():
            try: listings.append(json.loads(lj.read_text()))
            except Exception: pass
print(f"   listing.json encontrados: {len(listings)}")
if root.exists() and not listings:
    print("\n   >>> La carpeta existe pero está vacía: el bot lee 0 carros.")
elif not root.exists():
    print("\n   >>> CAUSA ENCONTRADA: la carpeta NO existe donde el bot la busca.")
    print("       El código falla en silencio (solo imprime) y sigue sin precio.")
    print("       Fix: exportar INVENTORY_DIR apuntando a donde escribe el scanner.")

print("\n" + "=" * 62)
print(" 4. ¿QUÉ CARROS TIENEN RANGO CARGADO?")
print("=" * 62)
con = [x for x in listings if (x.get("alt_price_low") or 0) and (x.get("alt_price_high") or 0)]
print(f"   con rango (alt_price_low y high): {len(con)} de {len(listings)}")
print(f"   con internal_price:              {len([x for x in listings if (x.get('internal_price') or 0)])}")
if con:
    print("\n   primeros 10 con rango:")
    for x in con[:10]:
        print(f"     {str(x.get('yr','?')):<5} {str(x.get('model',''))[:22]:<22} "
              f"${x.get('alt_price_low'):>7,} - ${x.get('alt_price_high'):>7,}  "
              f"interno=${x.get('internal_price') or 0:,}  ref={x.get('ref_code') or '(sin código)'}")
lex = [x for x in listings if "lexus" in json.dumps(x).lower() or "es 350" in str(x.get("model","")).lower()]
print(f"\n   unidades que mencionan Lexus / ES 350: {len(lex)}")
for x in lex[:5]:
    print(f"     {x.get('yr')} {x.get('model')} — rango "
          f"${x.get('alt_price_low') or 0:,}-${x.get('alt_price_high') or 0:,} | vin={x.get('vin')}")
print("\n" + "=" * 62)
