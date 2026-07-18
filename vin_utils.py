"""VIN: validación check digit ISO 3779 + decode NHTSA vPIC (gratis, sin key)."""
import requests

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"

_TRANSLIT = {**{str(d): d for d in range(10)},
             "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
             "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
             "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

def validate_vin(vin: str) -> bool:
    vin = vin.strip().upper()
    if len(vin) != 17 or any(c not in _TRANSLIT for c in vin):
        return False
    total = sum(_TRANSLIT[c] * w for c, w in zip(vin, _WEIGHTS))
    check = total % 11
    expected = "X" if check == 10 else str(check)
    return vin[8] == expected

# Confusiones típicas de OCR en placas de VIN (metal estampado, reflejos)
_OCR_CONFUSIONS = {"5": "S", "S": "5", "8": "B", "B": "8", "2": "Z", "Z": "2",
                   "6": "G", "G": "6", "0": "D", "D": "0", "1": "T", "T": "1"}

def clean_vin(raw: str) -> str:
    """Normaliza una lectura OCR: I→1, O→0, Q→0 (nunca existen en un VIN),
    descarta caracteres inválidos y, si sobra texto (ej. prefijo 'VIN:'),
    busca la ventana de 17 caracteres cuyo check digit valide."""
    up = raw.strip().upper().translate(str.maketrans({"I": "1", "O": "0", "Q": "0"}))
    s = "".join(c for c in up if c in _TRANSLIT)
    if len(s) <= 17:
        return s
    for i in range(len(s) - 16):
        window = s[i:i + 17]
        if validate_vin(window):
            return window
    return s[-17:]  # sin ventana válida: lo más probable es junk al inicio

def repair_vin(vin: str) -> str:
    """Si el check digit falla, prueba sustituciones únicas de confusión OCR.
    Devuelve el primer candidato válido, o el VIN original si ninguno valida."""
    if len(vin) != 17 or validate_vin(vin):
        return vin
    for i, c in enumerate(vin):
        alt = _OCR_CONFUSIONS.get(c)
        if alt:
            candidate = vin[:i] + alt + vin[i + 1:]
            if validate_vin(candidate):
                return candidate
    return vin

def decode_vin(vin: str) -> dict:
    r = requests.get(NHTSA_URL.format(vin=vin.strip().upper()), timeout=15)
    res = (r.json().get("Results") or [{}])[0]
    disp, cyl = res.get("DisplacementL", ""), res.get("EngineCylinders", "")
    engine = f"{float(disp):.1f}L {cyl}cyl" if disp and cyl else (disp or cyl or "")
    return {"yr": res.get("ModelYear", ""), "make": (res.get("Make") or "").title(),
            "model": res.get("Model", ""), "trim": res.get("Trim", ""),
            "engine": engine, "fuel": res.get("FuelTypePrimary", ""),
            "body": res.get("BodyClass", ""), "drive": res.get("DriveType", "")}
