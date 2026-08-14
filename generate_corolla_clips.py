import json, os, sys, time, urllib.request
sys.path.insert(0, "/Users/macbookpro/nexus-automation")
from meta_publisher import upload_image_to_facebook

MUAPI_KEY = None
with open("/Users/macbookpro/nexus-automation/.env") as f:
    for line in f:
        if line.startswith("MUAPI_KEY="):
            MUAPI_KEY = line.strip().split("=", 1)[1]
            break

BASE = "https://api.muapi.ai/api/v1"
OUT_DIR = "/Users/macbookpro/nexus-automation/test_output/corolla_familia/clips"
os.makedirs(OUT_DIR, exist_ok=True)

MOTION = ("Subtle natural motion: gentle breeze moves hair and clothing, warm sunlight flickers, "
          "genuine smile continues naturally, very slight cinematic camera push-in. Keep every "
          "person and the car exactly as shown, do not add, remove, or change anyone's identity, "
          "no distortion, no morphing.")

CLIPS = [
    ("01", "01_1968-1970_E10_v2_A.jpg", 4, MOTION),
    ("02", "02_1971-1974_E20_A.jpg", 4, MOTION),
    ("03", "03_1975-1979_E30-E50_A.jpg", 4, MOTION),
    ("04", "04_1980-1983_E70_A.jpg", 4, MOTION),
    ("05", "05_1984-1987_E80-AE86_A.jpg", 5, MOTION),
    ("06", "06_1988-1992_E90_A.jpg", 4, MOTION),
    ("07", "07_1993-1997_E100_v2_B.jpg", 4, MOTION),
    ("08", "08_1998-2002_E110_A.jpg", 4, MOTION),
    ("09", "09_2003-2008_E120-E130_v2_A.jpg", 4, MOTION),
    ("10", "10_2009-2013_E140-E150_A.jpg", 4, MOTION),
    ("11", "11_2014-2019_E160-E170_A.jpg", 4, MOTION),
    ("12", "12_2020-2026_E210_v2_B.jpg", 3, MOTION),
    ("13_family", "CLOSING_family_reveal_A.jpg", 5,
     "Camera slowly orbits around the family and the car, everyone laughing together with big "
     "genuine warm smiles, golden hour light. Keep all people and the car exactly as shown, do not "
     "add, remove, or change anyone's identity, no distortion, no morphing."),
    ("14_beauty", "CLOSING_beauty_shot.jpg", 4,
     "Camera slowly pushes in on the car with the red bow, warm sunlight glinting softly off the "
     "paint, gentle breeze in nearby leaves, cinematic. Keep the car exactly as shown, no distortion."),
]

SRC_DIR = "/Users/macbookpro/nexus-automation/test_output/corolla_familia"

def submit_kling(prompt, image_url, duration):
    body = json.dumps({
        "prompt": prompt, "image_url": image_url, "duration": duration, "generate_audio": False
    }).encode()
    req = urllib.request.Request(f"{BASE}/kling-v3.0-pro-image-to-video", data=body, method="POST",
                                  headers={"Authorization": f"Bearer {MUAPI_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def poll(request_id, max_wait=300):
    url = f"{BASE}/predictions/{request_id}/result"
    start = time.time()
    while time.time() - start < max_wait:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {MUAPI_KEY}"})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        if data.get("status") in ("completed", "failed", "error"):
            return data
        time.sleep(6)
    return {"status": "timeout"}

if __name__ == "__main__":
    for idx, fname, duration, prompt in CLIPS:
        local_path = os.path.join(SRC_DIR, fname)
        out_path = os.path.join(OUT_DIR, f"clip_{idx}.mp4")
        if os.path.exists(out_path):
            print(f"[{idx}] ya existe, saltando")
            continue
        print(f"[{idx}] subiendo {fname} a FB CDN...")
        img_url = upload_image_to_facebook(local_path)
        if not img_url:
            print(f"[{idx}] ERROR: no se pudo subir a FB CDN")
            continue
        print(f"[{idx}] enviando a Kling (duration={duration}s)...")
        resp = submit_kling(prompt, img_url, duration)
        request_id = resp.get("request_id") or resp.get("id")
        cost = resp.get("cost", {}).get("amount_usd")
        print(f"[{idx}] request_id={request_id} cost=${cost}")
        if not request_id:
            print(f"[{idx}] ERROR submit: {json.dumps(resp)[:300]}")
            continue
        result = poll(request_id)
        if result.get("status") != "completed":
            print(f"[{idx}] ERROR generacion: {json.dumps(result)[:400]}")
            continue
        outputs = result.get("outputs")
        video_url = outputs[0] if isinstance(outputs, list) and outputs else None
        if not video_url:
            print(f"[{idx}] ERROR: sin video url en resultado")
            continue
        urllib.request.urlretrieve(video_url, out_path)
        print(f"[{idx}] DONE -> {out_path}")
    print("TODOS LOS CLIPS PROCESADOS")
