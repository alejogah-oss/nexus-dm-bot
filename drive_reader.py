"""
Photo manager for nexus-automation.
Connects directly to Google Drive API — no desktop app required.
FIFO system: oldest photo first, cycles back when all used.
New photos uploaded to Drive take priority automatically.

SETUP (one-time):
  Share the nexus-fotos folder with:
  nexus-drive-reader@nexus-tucarroconalejo.iam.gserviceaccount.com
"""
import io
import os
import json
import subprocess
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

FOLDER_ID      = "1zZJ9Mm8v15bazCbsRNGrx4wirOFEbvFe"
SA_KEY_PATH    = os.path.join(os.path.dirname(__file__), "drive_service_account.json")
CACHE_DIR      = os.path.join(os.path.dirname(__file__), "fotos_cache")
FIFO_LOG       = os.path.join(CACHE_DIR, "_fifo_state.json")
SCOPES         = ["https://www.googleapis.com/auth/drive.readonly"]

# Folder "Fotos toyota" — fotos por modelo para ai_promo
PROMO_FOLDER_ID = "1uonwq5ZX-VXaBLSnu9sHNQmOXOR8beOK"
PROMO_SUBFOLDERS = {
    "corolla":           "19s9ou4sULakLZZZyKRoVsqPEievyUIxi",
    "corolla cross":     "18owBMKUXRLvdd6a1F6hF8x0qbM9JF0V9",
    "cross":             "18owBMKUXRLvdd6a1F6hF8x0qbM9JF0V9",
    "rav4":              "108LEG99X2Abyp7-IQRP2-IG3jGyJx5cX",
    "tacoma":            "10wK3CEwqhAcHDgguY-7Z9HETsOOezHc3",
    "tundra":            "1UhIFmmJuDsOroneAy5Vtl2Hz6v6QFXHf",
    "4runner":           "1TIfZDllf6DmcL6Lal2fq7WZvYyuleyn4",
    "grand highlander":  "1vGQ6szPE9SA4vpY7dTvGs6SWF6CO2zAY",
    "camry":             "1gEtfdLRSPe5Ga-CAJ1flg42K2PoN0LvZ",
    "highlander":        "17G2iJTbUu4ujN98yM3MWJ6wSog753lhs",
}

os.makedirs(CACHE_DIR, exist_ok=True)


def _drive_service():
    creds = service_account.Credentials.from_service_account_file(SA_KEY_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _list_drive_photos() -> list[dict]:
    """Returns list of photo files in nexus-fotos folder, oldest first."""
    try:
        service = _drive_service()
        results = service.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed=false and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/heic' or mimeType='image/heif' or mimeType='image/webp')",
            fields="files(id, name, createdTime, modifiedTime)",
            orderBy="createdTime asc",
            pageSize=50,
        ).execute()
        return results.get("files", [])
    except Exception as e:
        print(f"⚠️  Drive API error: {e}")
        return []


def _download_photo(file_id: str, filename: str) -> str | None:
    """Downloads a photo from Drive to local cache. Returns local path."""
    local_path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(local_path):
        return _ensure_jpg(local_path)
    try:
        service = _drive_service()
        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        with open(local_path, "wb") as f:
            f.write(buf.getvalue())
        print(f"   ☁️  Descargada desde Drive: {filename}")
        return _ensure_jpg(local_path)
    except Exception as e:
        print(f"⚠️  Error descargando {filename}: {e}")
        return None


def _load_fifo() -> dict:
    try:
        with open(FIFO_LOG, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"used": [], "last_new_photo": ""}


def _save_fifo(state: dict):
    with open(FIFO_LOG, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_next_photo() -> str | None:
    """
    Lógica:
    1. Consulta Drive → ordena por fecha de creación (más antigua primero)
    2. Usa la foto más antigua que nunca se haya usado
    3. Cada foto se usa UNA sola vez — sin repetición
    4. Todas usadas → alerta y aborta | Sin Drive → cache local
    """
    photos = _list_drive_photos()

    if not photos:
        print("⚠️  No hay fotos en Drive. Usando cache local si existe.")
        return _fallback_local()

    state = _load_fifo()
    used  = set(state.get("used", []))

    unused = sorted(
        [p for p in photos if p["name"] not in used],
        key=lambda p: p["createdTime"],
    )
    if not unused:
        print("🔴 ALERTA: todas las fotos de Drive ya se usaron — Alejo debe subir fotos nuevas.")
        return None

    chosen = unused[0]
    path = _download_photo(chosen["id"], chosen["name"])
    if path:
        state["last_used"] = chosen["name"]
        state["used"] = list(used | {chosen["name"]})
        _save_fifo(state)
        print(f"📸 Foto más antigua sin usar: {chosen['name']}")
        _check_photo_stock(len(unused) - 1)
        return path

    return _fallback_local()


def _check_photo_stock(remaining: int):
    """Alerta proactiva: al ritmo de ~7 fotos/semana, <10 fotos = <1.5 semanas."""
    if remaining >= 10:
        return
    import subprocess
    msg = (f"Quedan solo {remaining} fotos sin usar en Drive — "
           "sube fotos nuevas de entregas esta semana")
    print(f"⚠️  STOCK DE FOTOS BAJO: {msg}")
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{msg}" with title "NEXUS · Fotos" sound name "Basso"'],
        check=False, capture_output=True,
    )


def _fallback_local() -> str | None:
    """Last resort: use any photo in local cache."""
    photos = [
        os.path.join(CACHE_DIR, f)
        for f in os.listdir(CACHE_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png")) and not f.startswith("_")
        and os.path.getsize(os.path.join(CACHE_DIR, f)) > 10000
    ]
    if photos:
        chosen = sorted(photos, key=os.path.getmtime)[0]
        print(f"📸 Fallback local: {os.path.basename(chosen)}")
        return chosen
    return None


def _ensure_jpg(path: str) -> str:
    """Converts HEIC/HEIF to JPEG using macOS sips if needed."""
    if path.lower().endswith((".heic", ".heif")):
        out = path.rsplit(".", 1)[0] + "_conv.jpg"
        if not os.path.exists(out):
            subprocess.run(
                ["sips", "-s", "format", "jpeg", path, "--out", out],
                capture_output=True
            )
        return out if os.path.exists(out) else path
    return path


# Backwards-compatible alias
def get_latest_photo_path() -> str | None:
    return get_next_photo()


def get_promo_photo(model: str) -> str | None:
    """FIFO por modelo — misma lógica que get_next_photo pero con carpeta por modelo."""
    model_key = model.lower().strip()
    folder_id = PROMO_SUBFOLDERS.get(model_key)

    if not folder_id:
        for key, fid in PROMO_SUBFOLDERS.items():
            if key in model_key or model_key in key:
                folder_id = fid
                break

    if not folder_id:
        folder_id = PROMO_FOLDER_ID

    fifo_key = f"promo_{model_key.replace(' ', '_')}"
    fifo_log = os.path.join(CACHE_DIR, f"_fifo_{fifo_key}.json")

    def _load():
        try:
            with open(fifo_log, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"used": [], "last_used": ""}

    def _save(state):
        with open(fifo_log, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    try:
        service = _drive_service()
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType contains 'image/'",
            fields="files(id, name, createdTime)",
            orderBy="createdTime asc",
            pageSize=100,
        ).execute()
        photos = results.get("files", [])
        if not photos:
            return None

        state = _load()
        last_used = state.get("last_used", "")
        used = set(state.get("used", []))

        # Foto más reciente — si es nueva, úsala primero
        newest = sorted(photos, key=lambda p: p["createdTime"], reverse=True)[0]
        if newest["name"] != last_used:
            path = _download_photo(newest["id"], newest["name"])
            if path:
                state["last_used"] = newest["name"]
                state["used"] = list(used | {newest["name"]})
                _save(state)
                print(f"📸 Nueva foto promo ({model}): {newest['name']}")
                return _ensure_jpg(path)

        # FIFO: foto más antigua no usada
        unused = [p for p in photos if p["name"] not in used]
        if not unused:
            print(f"📸 Ciclo completo promo ({model}) — reiniciando")
            state["used"] = []
            _save(state)
            unused = photos

        chosen = unused[0]
        path = _download_photo(chosen["id"], chosen["name"])
        if path:
            state["last_used"] = chosen["name"]
            state["used"] = list(set(state.get("used", [])) | {chosen["name"]})
            _save(state)
            print(f"📸 Foto promo FIFO ({model}): {chosen['name']}")
            return _ensure_jpg(path)

    except Exception as e:
        print(f"⚠️  get_promo_photo error: {e}")
    return None
