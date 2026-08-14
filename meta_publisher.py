import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

PAGE_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("META_PAGE_ID")
IG_USER_ID = os.getenv("META_IG_USER_ID")

def upload_image_to_facebook(local_path: str) -> str:
    """Sube imagen a Facebook como foto no publicada y devuelve URL pública."""
    url = f"https://graph.facebook.com/{PAGE_ID}/photos"
    with open(local_path, "rb") as image_file:
        response = requests.post(url, data={
            "published": "false",
            "access_token": PAGE_TOKEN
        }, files={"source": image_file})

    result = response.json()
    if "id" not in result:
        print(f"Error subiendo imagen a Facebook: {result}")
        return None

    photo_id = result["id"]

    # Obtener URL pública de la foto
    photo_url_response = requests.get(
        f"https://graph.facebook.com/{photo_id}",
        params={"fields": "images", "access_token": PAGE_TOKEN}
    )
    photo_data = photo_url_response.json()

    if "images" in photo_data and len(photo_data["images"]) > 0:
        public_url = photo_data["images"][0]["source"]
        print(f"Imagen subida a Facebook. URL pública obtenida.")
        return public_url

    print(f"No se pudo obtener URL pública de la foto.")
    return None

def post_to_facebook(message: str, local_image_path: str = None) -> dict:
    if local_image_path:
        # Post con imagen
        url = f"https://graph.facebook.com/{PAGE_ID}/photos"
        with open(local_image_path, "rb") as image_file:
            response = requests.post(url, data={
                "caption": message,
                "access_token": PAGE_TOKEN
            }, files={"source": image_file})
    else:
        # Post solo texto
        url = f"https://graph.facebook.com/{PAGE_ID}/feed"
        response = requests.post(url, data={
            "message": message,
            "access_token": PAGE_TOKEN
        })

    result = response.json()
    if "id" in result:
        print(f"Facebook publicado. Post ID: {result['id']}")
    else:
        print(f"Error en Facebook: {result}")
    return result

def post_to_instagram(caption: str, image_url: str) -> dict:
    # Paso 1: crear contenedor
    container_response = requests.post(
        f"https://graph.facebook.com/{IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": PAGE_TOKEN
        }
    )
    container = container_response.json()

    if "id" not in container:
        print(f"Error al crear contenedor IG: {container}")
        return container

    creation_id = container["id"]

    # Paso 2: publicar con retry — IG necesita procesar la imagen antes de publicar
    for attempt in range(1, 4):
        if attempt > 1:
            print(f"Instagram retry {attempt}/3 — esperando 8s...")
            time.sleep(8)
        publish_response = requests.post(
            f"https://graph.facebook.com/{IG_USER_ID}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": PAGE_TOKEN
            }
        )
        result = publish_response.json()
        if "id" in result:
            print(f"Instagram publicado. Post ID: {result['id']}")
            return result
        error_code = result.get("error", {}).get("error_subcode")
        if error_code != 2207027:
            break

    print(f"Error en Instagram: {result}")
    return result

def upload_photo_fb_unpublished(local_path: str) -> str | None:
    """Sube foto a Facebook sin publicar. Retorna media_fbid para carousel."""
    url = f"https://graph.facebook.com/{PAGE_ID}/photos"
    with open(local_path, "rb") as f:
        r = requests.post(url, data={"published": "false", "access_token": PAGE_TOKEN},
                          files={"source": f})
    result = r.json()
    return result.get("id")


def post_carousel_to_facebook(message: str, local_paths: list[str]) -> dict:
    """Publica un post multi-foto en Facebook."""
    media_ids = []
    for p in local_paths:
        fid = upload_photo_fb_unpublished(p)
        if fid:
            media_ids.append({"media_fbid": fid})

    if not media_ids:
        return {"error": "no_media_uploaded"}

    url = f"https://graph.facebook.com/{PAGE_ID}/feed"
    r = requests.post(url, data={
        "message": message,
        "attached_media": str(media_ids).replace("'", '"'),
        "access_token": PAGE_TOKEN,
    })
    result = r.json()
    if "id" in result:
        print(f"Facebook carousel publicado. Post ID: {result['id']}")
    else:
        print(f"Error Facebook carousel: {result}")
    return result


def post_carousel_to_instagram(caption: str, image_urls: list[str]) -> dict:
    """Publica un carousel en Instagram. image_urls deben ser URLs públicas."""
    # Paso 1: crear contenedor por cada imagen
    child_ids = []
    for url in image_urls:
        r = requests.post(
            f"https://graph.facebook.com/{IG_USER_ID}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": PAGE_TOKEN}
        )
        cid = r.json().get("id")
        if cid:
            child_ids.append(cid)

    if not child_ids:
        return {"error": "no_carousel_children"}

    # Paso 2: crear contenedor carousel
    r2 = requests.post(
        f"https://graph.facebook.com/{IG_USER_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "caption": caption,
            "children": ",".join(child_ids),
            "access_token": PAGE_TOKEN,
        }
    )
    carousel_id = r2.json().get("id")
    if not carousel_id:
        print(f"Error creando carousel IG: {r2.json()}")
        return r2.json()

    # Paso 3: publicar con retry
    for attempt in range(1, 4):
        if attempt > 1:
            print(f"Instagram carousel retry {attempt}/3 — esperando 8s...")
            time.sleep(8)
        r3 = requests.post(
            f"https://graph.facebook.com/{IG_USER_ID}/media_publish",
            data={"creation_id": carousel_id, "access_token": PAGE_TOKEN}
        )
        result = r3.json()
        if "id" in result:
            print(f"Instagram carousel publicado. Post ID: {result['id']}")
            return result
        if result.get("error", {}).get("error_subcode") != 2207027:
            break

    print(f"Error publicando carousel IG: {result}")
    return result


def publish_carousel(facebook_text: str, instagram_caption: str, local_paths: list[str]) -> dict:
    """Publica carousel (3 slides) en Facebook e Instagram."""
    results = {}

    # Subir todas las fotos a Facebook para obtener URLs públicas para IG
    public_urls = []
    for p in local_paths:
        url = upload_image_to_facebook(p)
        if url:
            public_urls.append(url)

    # Facebook multi-foto
    print("Publicando carousel en Facebook...")
    results["facebook"] = post_carousel_to_facebook(facebook_text, local_paths)

    # Instagram carousel
    if public_urls:
        print("Publicando carousel en Instagram...")
        results["instagram"] = post_carousel_to_instagram(instagram_caption, public_urls)
    else:
        results["instagram"] = {"skipped": "no_public_urls"}

    return results


def publish_content(facebook_text: str, instagram_caption: str, local_image_path: str = None) -> dict:
    results = {}
    public_image_url = None

    if local_image_path:
        print("Subiendo imagen a Facebook como hosting...")
        public_image_url = upload_image_to_facebook(local_image_path)

    # Publicar en Facebook (con o sin imagen)
    print("Publicando en Facebook...")
    results["facebook"] = post_to_facebook(facebook_text, local_image_path)

    # Publicar en Instagram (requiere imagen)
    if public_image_url:
        print("Publicando en Instagram...")
        results["instagram"] = post_to_instagram(instagram_caption, public_image_url)
    else:
        print("Instagram omitido — no se generó imagen.")
        results["instagram"] = {"skipped": "No image available"}

    return results
