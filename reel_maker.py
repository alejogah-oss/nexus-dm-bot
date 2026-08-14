"""
Shot · Reel Maker — receta oficial de calidad para Reels NEXUS
================================================================
Pipeline: foto real → FB CDN → 2 clips Kling v3.0 Pro I2V (tomas distintas)
          → crossfade + textos cálidos con fade → Reel 9:16 ~9.5s

Estructura narrativa (3 actos — NO cambiar, es lo que funciona):
  0.0-3.0s  GANCHO emocional (2 líneas, blanco + rojo Toyota)
  3.2-6.5s  REVELACIÓN (modelo/celebración, rojo gigante)
  6.7-fin   CTA (954) 910-6671 + @tucarroconalejo fijo

Reglas de calidad:
  - SIEMPRE 2 clips con prompts distintos (push-in + órbita) → transición real
  - Prompts: personas "laughing/big joyful smiles/celebrating" — la alegría
    se pide explícita o Kling deja caras neutras
  - Textos cálidos y humanos, NUNCA fríos. Sin precios. Sin emojis (Impact
    no los renderiza)
  - Fuente Impact, borde negro 6px, rojo Toyota 0xEB0A1E para acentos
  - Música: se agrega desde la app IG (API no soporta borradores) —
    importar a Fotos para sync iPhone: ver import_to_photos()

Uso:
  venv/bin/python3 reel_maker.py                      # siguiente foto FIFO
  venv/bin/python3 reel_maker.py foto.jpg "COROLLA 2026"
"""
import os
import random
import subprocess
import sys
import time

import imageio_ffmpeg
import requests

MUAPI_BASE = "https://api.muapi.ai/api/v1"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FONT = os.path.join(os.path.dirname(__file__), "fonts/Anton-Regular.ttf")

# Variantes del clip de personas — Kling necesita una emoción explícita o deja
# caras neutras, pero rotar el gesto evita que todos los reels terminen igual
# (antes SIEMPRE era "laughing" → sensación repetitiva de carcajada forzada).
PROMPT_A_VARIANTS = [
    (
        "Camera slowly circling around the exact same people from the photo as they "
        "celebrate with warm genuine smiles, hugging next to their new Toyota "
        "with red bow in the background."
    ),
    (
        "Camera slowly circling around the exact same people from the photo as they "
        "proudly hold up the car keys together, warm content smiles, a quiet emotional "
        "moment next to their new Toyota with red bow in the background."
    ),
    (
        "Camera slowly circling around the exact same people from the photo as they "
        "share an excited high-five and joyful smiles next to their new Toyota "
        "with red bow in the background."
    ),
    (
        "Camera slowly circling around the exact same people from the photo as they "
        "embrace warmly with proud, happy smiles, admiring their new Toyota "
        "with red bow in the background."
    ),
]
PROMPT_A_SUFFIX = (
    " IMPORTANT: only the people already present in the photo — do not add, "
    "remove or replace any person, keep their faces and identities exactly "
    "consistent the entire shot. Warm golden light, confetti, heartwarming "
    "moment, cinematic commercial, no text"
)
PROMPT_B = (
    "Cinematic beauty shot of the brand new Toyota with its giant red bow, "
    "completely alone with no people in frame, slow elegant camera glide along "
    "the body, sparkling paint reflections, warm sunset glow, festive dealership "
    "atmosphere with balloons, premium car commercial style, no people, no text"
)


def _headers():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    return {"Content-Type": "application/json", "x-api-key": os.getenv("MUAPI_KEY")}


def _generate_clips(image_url: str) -> list[str]:
    """Lanza los 2 clips Kling en paralelo y espera ambos."""
    headers = _headers()
    reqs = {}
    prompt_a = random.choice(PROMPT_A_VARIANTS) + PROMPT_A_SUFFIX
    for tag, prompt in (("A", prompt_a), ("B", PROMPT_B)):
        r = requests.post(
            f"{MUAPI_BASE}/kling-v3.0-pro-image-to-video",
            json={"image_url": image_url, "prompt": prompt, "duration": 5},
            headers=headers, timeout=30,
        )
        r.raise_for_status()
        reqs[tag] = r.json().get("request_id") or r.json().get("id")
        print(f"  Reel · clip {tag} → {reqs[tag]}")

    done, deadline = {}, time.time() + 600
    while time.time() < deadline and len(done) < len(reqs):
        time.sleep(12)
        for tag, rid in reqs.items():
            if tag in done:
                continue
            res = requests.get(
                f"{MUAPI_BASE}/predictions/{rid}/result", headers=headers, timeout=15
            ).json()
            result = res.get("detail", res)
            status = str(result.get("status", "")).lower()
            if status in ("completed", "succeeded", "success"):
                url = (result.get("outputs") or [None])[0] or result.get("url")
                path = f"/tmp/nexus_reel_clip_{tag}_{int(time.time())}.mp4"
                open(path, "wb").write(requests.get(url, timeout=120).content)
                done[tag] = path
                print(f"  Reel · clip {tag} listo")
            elif status in ("failed", "error"):
                raise RuntimeError(f"Kling clip {tag} falló: {result.get('error')}")
    if len(done) < 2:
        raise TimeoutError("Kling: timeout generando clips")
    return [done["A"], done["B"]]


def _drawtext(text: str, size: int, color: str, y: int, alpha: str) -> str:
    return (
        f"drawtext=fontfile={FONT}:text='{text}':fontsize={size}:fontcolor={color}:"
        f"borderw=6:bordercolor=black:x=(w-text_w)/2:y={y}:alpha='{alpha}'"
    )


def _compose(clip_a: str, clip_b: str, hook1: str, hook2: str,
             reveal1: str, reveal2: str, out: str) -> str:
    """Crossfade A→B + textos en 3 actos con fade in/out."""
    fade1 = r"if(lt(t\,0.4)\,t/0.4\,if(lt(t\,2.6)\,1\,max(0\,(3-t)/0.4)))"
    fade2 = r"if(lt(t\,3.2)\,0\,if(lt(t\,3.6)\,(t-3.2)/0.4\,if(lt(t\,6.1)\,1\,max(0\,(6.5-t)/0.4))))"
    fade3 = r"if(lt(t\,6.7)\,0\,if(lt(t\,7.1)\,(t-6.7)/0.4\,1))"
    filt = (
        "[0:v]scale=-2:1920,crop=1080:1920:'(iw-1080)/2':0,setsar=1[a];"
        "[1:v]scale=-2:1920,crop=1080:1920:'(iw-1080)/2':0,setsar=1[b];"
        "[a][b]xfade=transition=fade:duration=0.6:offset=4.4[v0];"
        "[v0]"
        + ",".join([
            _drawtext(hook1, 78, "white", 270, fade1),
            _drawtext(hook2, 78, "0xEB0A1E", 370, fade1),
            _drawtext(reveal1, 78, "white", 270, fade2),
            _drawtext(reveal2, 100, "0xEB0A1E", 370, fade2),
            _drawtext("TU TAMBIEN PUEDES", 72, "white", 1400, fade3),
            _drawtext("ESCRIBEME (954) 910-6671", 68, "0xEB0A1E", 1500, fade3),
            _drawtext("@tucarroconalejo", 44, "white", 1720, "1"),
        ])
        + "[vout]"
    )
    script = f"/tmp/nexus_reel_filter_{int(time.time())}.txt"
    open(script, "w").write(filt)
    subprocess.run(
        [FFMPEG, "-y", "-i", clip_a, "-i", clip_b,
         "-filter_complex_script", script, "-map", "[vout]",
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", out],
        check=True, capture_output=True,
    )
    return out


def import_to_photos(path: str):
    """Importa a Fotos → sync iCloud → Alejo agrega música trending en IG app.

    Fotos suele estar cerrada cuando corre el scheduler — el arranque en frío
    puede tardar más que el timeout default de Apple Events (error -1712).
    "with timeout of" evita que ese arranque lento se reporte como fallo.
    """
    subprocess.run(["open", "-a", "Photos"], check=False, capture_output=True)
    result = subprocess.run([
        "osascript", "-e",
        'with timeout of 180 seconds\n'
        f'set f to POSIX file "{path}"\n'
        'tell application "Photos" to import f skip check duplicates yes\n'
        'end timeout',
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Import a Fotos falló: {result.stderr.strip()}")


def make_reel(photo_path: str, model_line: str = "TOYOTA NUEVO",
              hook1: str = "PENSABAN QUE", hook2: str = "NO SE PODIA...",
              reveal1: str = "HOY ESTRENAN SU") -> str:
    """Foto real → Reel 9:16 con la receta de calidad oficial."""
    from meta_publisher import upload_image_to_facebook
    print(f"  Reel · subiendo {os.path.basename(photo_path)} a FB CDN...")
    url = upload_image_to_facebook(photo_path)
    if not url:
        raise RuntimeError("FB CDN upload falló")
    clip_a, clip_b = _generate_clips(url)
    out = f"/tmp/nexus_reel_{int(time.time())}.mp4"
    _compose(clip_a, clip_b, hook1, hook2, reveal1, model_line, out)
    print(f"  Reel · LISTO: {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        photo, model = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "TOYOTA NUEVO")
    else:
        from drive_reader import get_next_photo
        photo = get_next_photo()
        model = sys.argv[2] if len(sys.argv) > 2 else "TOYOTA NUEVO"
        if not photo:
            sys.exit("Sin fotos disponibles")
    reel = make_reel(photo, model_line=model)
    import_to_photos(reel)
    print(f"Importado a Fotos — listo para IG con música: {reel}")
