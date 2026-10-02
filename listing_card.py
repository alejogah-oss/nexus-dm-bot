# listing_card.py
"""Ficha del carro para WhatsApp, recortada del texto del anuncio del scanner.

El anuncio (listing.json → description) trae una mitad en inglés y otra en
español separadas por "— En Español —" o "— In English —" (el orden varía).
La ficha conserva lo que describe el carro y quita lo que vende o desvía:
la frase de gancho, el teléfono, la invitación a escribir por Marketplace y
la línea "Ref:". Nunca ve internal_price: solo recibe el texto público.
"""
import re

_SEP = re.compile(r"^\s*—\s*(En Español|In English)\s*—\s*$", re.M)
_PHONE = re.compile(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_DROP = re.compile(r"(📞|marketplace|escr[ií]beme|message me|call/text|^ref:)", re.I)
_MONEY = re.compile(r"(enganche|down payment|financ)", re.I)


def _half_lang(text: str) -> str:
    return "es" if re.search(r"\b(millas|enganche|motor|gasolina|financiamiento)\b", text, re.I) else "en"


def _clean(half: str) -> str:
    lines = [l.strip() for l in half.strip().splitlines() if l.strip()]
    if not lines or not any(l.startswith("✅") for l in lines):
        return ""
    if not lines[0].startswith("✅"):
        lines = lines[1:]                      # frase de gancho
    out, title = [], None
    for l in lines:
        if _DROP.search(l) or _PHONE.search(l):
            continue
        if l.startswith("✅") and title is None:
            title = l[1:].strip()
            continue
        if not l.startswith(("✅", "📍")) and _MONEY.search(l):
            l = "💵 " + l
        out.append(l)
    return "\n".join([f"🚙 {title}"] + out)


def build_card(description: str) -> dict:
    card = {"es": "", "en": ""}
    if not description:
        return card
    parts = _SEP.split(description)
    if len(parts) == 1:
        card[_half_lang(parts[0])] = _clean(parts[0])
        return card
    first, marker, second = parts[0], parts[1], parts[2]
    second_lang = "es" if marker == "En Español" else "en"
    first_lang = "en" if second_lang == "es" else "es"
    card[first_lang] = _clean(first)
    card[second_lang] = _clean(second)
    return card
