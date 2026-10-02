# tests/test_listing_card.py
from listing_card import build_card

IS_EN_ES = """Looking for a sporty sedan that still feels brand new? This 2025 Lexus IS 350 F Sport is barely broken in and ready to go.
✅ 2025 Lexus IS 350 F Sport
✅ 3.5L 6cyl engine
✅ 24,720 miles
✅ White
Down payment from $2,000, building credit is welcome too - financing available.
📍 Hollywood, Florida.
Message me here on Marketplace or call/text me directly, Alejo, at 📞 (954) 910-6671. No middlemen, no call centers - just me.

— En Español —
¿Buscas un sedán deportivo que se sienta como nuevo? Este 2025 Lexus IS 350 F Sport apenas tiene millas y está listo para rodar.
✅ 2025 Lexus IS 350 F Sport
✅ Motor 3.5L 6cil
✅ 24,720 millas
✅ Blanco
Enganche desde $2,000, crédito en construcción también aplica - financiamiento disponible.
📍 Hollywood, Florida.
Escríbeme por Marketplace o llámame directo a mí, Alejo, al 📞 (954) 910-6671. Sin intermediarios, sin call center - solo yo.

Ref: 4478S508"""

Q5_ES_EN = """Si andas buscando una SUV de lujo con tracción total y ese toque deportivo del S Line, esta Q5 está lista para ti.
✅ 2025 Audi Q5 S Line quattro Premium
✅ 38,817 millas

Enganche desde $4,500, crédito en construcción también aplica.
📍 Hollywood, Florida.
📞 Escríbeme por Marketplace o llama directo al (954) 910-6671 — hablas conmigo, sin intermediarios ni call center.

— In English —

If you're looking for a luxury SUV with all-wheel drive and that sporty S Line touch, this Q5 is ready for you.
✅ 2025 Audi Q5 S Line quattro Premium
✅ 38,817 miles

Down payment from $4,500, building credit also welcome.
📍 Hollywood, Florida.
📞 Message me on Marketplace or call direct at (954) 910-6671 — you talk to me, no middlemen, no call center.

Ref: 2399S202"""

TUNDRA_PRICE = """Barely broken in — this Tundra still has that new-truck feel.
✅ 2026 Toyota Tundra Limited Appearance, Platinum
✅ 5,629 miles
✅ Price: $59,516
Financing available, building credit is welcome too.
📍 Hollywood, Florida.
📞 (954) 910-6671 — message me here on Marketplace or call direct, no middleman, just me."""


def test_separa_idiomas_en_primero():
    c = build_card(IS_EN_ES)
    assert c["es"].startswith("🚙 2025 Lexus IS 350 F Sport")
    assert c["en"].startswith("🚙 2025 Lexus IS 350 F Sport")
    assert "24,720 millas" in c["es"] and "24,720 miles" in c["en"]


def test_separa_idiomas_es_primero():
    c = build_card(Q5_ES_EN)
    assert "38,817 millas" in c["es"] and "38,817 miles" in c["en"]
    assert "millas" not in c["en"]


def test_quita_frase_de_venta_telefono_marketplace_y_ref():
    for card in build_card(IS_EN_ES).values():
        assert "910-6671" not in card and "📞" not in card
        assert "Marketplace" not in card
        assert "Ref:" not in card
        assert "barely broken in" not in card.lower() and "Buscas" not in card


def test_conserva_enganche_con_icono_y_ciudad():
    c = build_card(IS_EN_ES)
    assert "💵 Enganche desde $2,000" in c["es"]
    assert "💵 Down payment from $2,000" in c["en"]
    assert "📍 Hollywood, Florida." in c["es"]


def test_titulo_no_se_repite_como_linea_check():
    c = build_card(IS_EN_ES)["es"]
    assert c.count("2025 Lexus IS 350 F Sport") == 1
    assert "✅ 2025 Lexus" not in c


def test_un_solo_idioma_deja_el_otro_vacio():
    c = build_card(TUNDRA_PRICE)
    assert c["es"] == ""
    assert c["en"].startswith("🚙 2026 Toyota Tundra")
    assert "✅ Price: $59,516" in c["en"]       # precio público del anuncio: se conserva


def test_texto_vacio_o_sin_checks():
    assert build_card("") == {"es": "", "en": ""}
    assert build_card("Solo una frase sin formato.") == {"es": "", "en": ""}
