"""Handler de lead ads (formulario instantáneo de Meta) — webhook_server.handle_leadgen.

No toca la red: se mockean la Graph API, el CRM y el aviso de Pulse.
"""
import sys, os, types, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import webhook_server as ws


LEAD_RESPONSE = {
    "created_time": "2026-09-13T16:09:11+0000",
    "id": "111",
    "ad_id": "120255566743020348",
    "form_id": "28422664124061710",
    "campaign_id": "120255675582210348",
    "campaign_name": "TEAM CARS - Leads - Dos Opciones bZ/Prius - Sep2026",
    "adset_name": "AS - Weekend Sab-Dom $30d",
    "ad_name": "IMG_6435 v1",
    "field_data": [
        {"name": "full_name", "values": ["Candida Zeledon"]},
        {"name": "phone_number", "values": ["+17862942144"]},
    ],
}


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, str(payload)
    def json(self):
        return self._p


@pytest.fixture
def capturado(monkeypatch):
    out = {"crm": [], "pulse": [], "get": []}
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(ws, "send_to_crm", lambda lead, notes="": out["crm"].append((lead, notes)))
    monkeypatch.setattr(ws, "pulse_notify", lambda event, detail: out["pulse"].append((event, detail)))
    def fake_get(url, params=None, timeout=None):
        out["get"].append(url)
        return FakeResp(LEAD_RESPONSE)
    monkeypatch.setattr(ws.req_lib, "get", fake_get)
    monkeypatch.setattr(ws, "_is_retry", lambda mid: False)
    return out


def test_crea_el_lead_con_nombre_y_telefono_normalizado(capturado):
    ws.handle_leadgen({"leadgen_id": "111"})
    assert len(capturado["crm"]) == 1
    lead, notes = capturado["crm"][0]
    assert lead["first_name"] == "Candida"
    assert lead["last_name"] == "Zeledon"
    # E.164 de Meta -> 10 dígitos, como el resto de la columna phone del CRM
    assert lead["phone"] == "7862942144"
    assert "Dejó sus datos en un anuncio de Meta" in notes
    assert "IDs:" not in notes and "Conjunto:" not in notes


def test_marca_el_canal_ads(capturado):
    ws.handle_leadgen({"leadgen_id": "111"})
    lead, _ = capturado["crm"][0]
    assert lead["source"] == "ads"


def test_se_asigna_a_luisa(capturado):
    ws.handle_leadgen({"leadgen_id": "111"})
    lead, _ = capturado["crm"][0]
    assert lead["agent_code"] == "LUISA"


def test_avisa_por_pulse(capturado):
    ws.handle_leadgen({"leadgen_id": "111"})
    assert capturado["pulse"] and capturado["pulse"][0][0] == "LEAD_ADS"
    assert "Candida Zeledon" in capturado["pulse"][0][1]


def test_reintento_de_meta_no_duplica(capturado, monkeypatch):
    monkeypatch.setattr(ws, "_is_retry", lambda mid: True)
    ws.handle_leadgen({"leadgen_id": "111"})
    assert capturado["crm"] == []


def test_evento_sin_leadgen_id_no_revienta(capturado):
    ws.handle_leadgen({})
    assert capturado["crm"] == []


def test_si_la_graph_api_falla_no_crea_lead(capturado, monkeypatch):
    monkeypatch.setattr(ws.req_lib, "get",
                        lambda url, params=None, timeout=None: FakeResp({"error": "x"}, 400))
    ws.handle_leadgen({"leadgen_id": "111"})
    assert capturado["crm"] == []


def test_respuestas_extra_del_formulario_van_a_la_nota(capturado, monkeypatch):
    payload = dict(LEAD_RESPONSE)
    payload["field_data"] = LEAD_RESPONSE["field_data"] + [
        {"name": "¿para_qué_necesitas_el_carro?", "values": ["Para trabajar"]}
    ]
    monkeypatch.setattr(ws.req_lib, "get",
                        lambda url, params=None, timeout=None: FakeResp(payload))
    ws.handle_leadgen({"leadgen_id": "111"})
    _, notes = capturado["crm"][0]
    assert "Para trabajar" in notes


def test_pide_los_campos_de_campana(capturado, monkeypatch):
    pedidos = []
    def fake_get(url, params=None, timeout=None):
        pedidos.append(params["fields"])
        return FakeResp(LEAD_RESPONSE)
    monkeypatch.setattr(ws.req_lib, "get", fake_get)
    ws.handle_leadgen({"leadgen_id": "111"})
    for campo in ("campaign_id", "campaign_name", "adset_name", "ad_name"):
        assert campo in pedidos[0].split(",")


def test_manda_la_campana_al_crm(capturado):
    ws.handle_leadgen({"leadgen_id": "111"})
    lead, _ = capturado["crm"][0]
    assert lead["ad_campaign_id"] == "120255675582210348"
    assert lead["ad_campaign_name"] == "TEAM CARS - Leads - Dos Opciones bZ/Prius - Sep2026"


def test_los_datos_tecnicos_viajan_en_el_payload_no_en_la_nota(capturado):
    ws.handle_leadgen({"leadgen_id": "111"})
    lead, notes = capturado["crm"][0]
    assert lead["channel"] == "ads"
    assert lead["meta_ad_id"] == "120255566743020348"
    assert lead["meta_form_id"] == "28422664124061710"
    assert lead["meta_adset_name"] == "AS - Weekend Sab-Dom $30d"
    assert lead["meta_ad_name"] == "IMG_6435 v1"
    assert "120255566743020348" not in notes
    assert "$30d" not in notes


def test_lead_sin_campana_se_crea_igual(capturado, monkeypatch):
    sin = {k: v for k, v in LEAD_RESPONSE.items()
           if k not in ("campaign_id", "campaign_name", "adset_name", "ad_name")}
    monkeypatch.setattr(ws.req_lib, "get", lambda url, params=None, timeout=None: FakeResp(sin))
    ws.handle_leadgen({"leadgen_id": "111"})
    lead, notes = capturado["crm"][0]
    assert lead["ad_campaign_id"] is None
    assert lead["ad_campaign_name"] is None
    assert lead["first_name"] == "Candida"
    assert "Dejó sus datos" in notes


def test_campaign_id_numerico_viaja_como_string(capturado, monkeypatch):
    num = dict(LEAD_RESPONSE, campaign_id=120255675582210348)
    monkeypatch.setattr(ws.req_lib, "get", lambda url, params=None, timeout=None: FakeResp(num))
    ws.handle_leadgen({"leadgen_id": "111"})
    lead, _ = capturado["crm"][0]
    assert lead["ad_campaign_id"] == "120255675582210348"
