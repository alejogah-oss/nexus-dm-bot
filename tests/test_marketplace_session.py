import json
import marketplace_poster


def test_storage_state_con_origins_devuelve_solo_cookies(tmp_path):
    """El archivo que escribe refresh_fb_session.py trae 'origins' con el
    localStorage de facebook.com. Pasárselo a new_context(storage_state=...)
    obliga a Playwright a navegar a https://www.facebook.com para restaurarlo,
    y ahí revienta con 'Execution context was destroyed'. Solo cookies."""
    f = tmp_path / "fb_session.json"
    f.write_text(json.dumps({
        "cookies": [{"name": "c_user", "value": "123", "domain": ".facebook.com", "path": "/"}],
        "origins": [{"origin": "https://www.facebook.com",
                     "localStorage": [{"name": "Session", "value": "x"}]}],
    }))
    cookies = marketplace_poster.load_session_cookies(f)
    assert cookies == [{"name": "c_user", "value": "123", "domain": ".facebook.com", "path": "/"}]


def test_lista_plana_de_cookies_tambien_sirve(tmp_path):
    """fb_session.py / refresh_mp_session.py guardan una lista pelada de
    cookies, no un storage_state. Los dos formatos tienen que funcionar."""
    f = tmp_path / "mp_session.json"
    f.write_text(json.dumps([{"name": "xs", "value": "abc", "domain": ".facebook.com", "path": "/"}]))
    assert marketplace_poster.load_session_cookies(f) == [
        {"name": "xs", "value": "abc", "domain": ".facebook.com", "path": "/"}]


def test_sin_archivo_no_explota(tmp_path):
    assert marketplace_poster.load_session_cookies(tmp_path / "no_existe.json") == []


class _FakeLocator:
    def __init__(self, visible): self._v = visible
    @property
    def first(self): return self
    async def is_visible(self, timeout=None): return self._v


class _FakeContext:
    def __init__(self, page): self._page = page
    async def cookies(self):
        self._page.consultas += 1
        if self._page._cookies_tras and self._page.consultas >= self._page._cookies_tras:
            return [{"name": "c_user"}, {"name": "xs"}]
        return [{"name": "datr"}]


class _FakePage:
    def __init__(self, url, pass_visible=False, cookies_tras=0):
        self.url = url
        self._pass_visible = pass_visible
        self._cookies_tras = cookies_tras
        self.consultas = 0
        self.context = _FakeContext(self)
    def locator(self, sel): return _FakeLocator(self._pass_visible)


async def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def test_detecta_muro_de_login_por_url():
    import asyncio
    page = _FakePage("https://www.facebook.com/login/?next=...")
    assert asyncio.run(marketplace_poster.hay_muro_de_login(page)) is True


def test_detecta_muro_de_login_por_campo_de_password():
    import asyncio
    page = _FakePage("https://www.facebook.com/marketplace/create/vehicle",
                     pass_visible=True)
    assert asyncio.run(marketplace_poster.hay_muro_de_login(page)) is True


def test_sesion_viva_no_espera_nada():
    import asyncio
    page = _FakePage("https://www.facebook.com/marketplace/create/vehicle")
    assert asyncio.run(marketplace_poster.hay_muro_de_login(page)) is False
    asyncio.run(marketplace_poster.ensure_logged_in(page))   # no bloquea


def test_espera_a_que_alejo_entre_a_mano_y_sigue():
    """Antes abortaba. Ahora espera el login en esa ventana — y como el perfil
    es persistente, es la única vez que lo va a pedir."""
    import asyncio
    page = _FakePage("https://www.facebook.com/login/", cookies_tras=2)
    asyncio.run(marketplace_poster.ensure_logged_in(page, segundos=10))
    assert page.consultas >= 2


def test_si_nadie_entra_cancela_con_mensaje_claro():
    import asyncio, pytest
    page = _FakePage("https://www.facebook.com/login/")   # nunca aparece c_user
    with pytest.raises(RuntimeError, match="no se completó el login"):
        asyncio.run(marketplace_poster.ensure_logged_in(page, segundos=2))


def test_perfil_de_sesion_es_estable_no_el_mas_reciente(tmp_path, monkeypatch):
    """Si cambiara de perfil entre corridas, el login se guardaría en uno y la
    publicada siguiente abriría el otro — y FB lo pediría de nuevo."""
    import os, time
    a = tmp_path / "poster"; a.mkdir()
    b = tmp_path / "otro";   b.mkdir()
    os.utime(b, (time.time() + 500, time.time() + 500))   # b es más reciente
    monkeypatch.setattr(marketplace_poster, "SESSION_PROFILES", [a, b])
    assert marketplace_poster.session_profile() == a
    assert marketplace_poster.session_profile() == a


def test_sin_ningun_perfil_devuelve_el_del_poster_para_crearlo(tmp_path, monkeypatch):
    a = tmp_path / "poster"
    monkeypatch.setattr(marketplace_poster, "SESSION_PROFILES", [a, tmp_path / "otro"])
    assert marketplace_poster.session_profile() == a


def test_usa_el_perfil_del_login_por_terminal_si_existe(tmp_path, monkeypatch):
    """El login por terminal (refresh_fb_session.py) deja este perfil con la
    sesión viva. Reusarlo es lo que evita que FB pida login en cada publicada."""
    import asyncio
    perfil = tmp_path / ".fb_playwright_profile_poster"
    perfil.mkdir()
    monkeypatch.setattr(marketplace_poster, "SESSION_PROFILES", [perfil])
    monkeypatch.setattr(marketplace_poster, "load_session_cookies", lambda *a, **k: [])
    llamadas = {}

    class _Ctx:
        pages = []
        async def close(self): pass
        async def add_cookies(self, c): pass

    class _Chromium:
        async def launch_persistent_context(self, user_data_dir, **kw):
            llamadas["persistent"] = (user_data_dir, kw)
            return _Ctx()
        async def launch(self, **kw):
            llamadas["launch"] = kw
            raise AssertionError("no debería abrir un Chromium limpio")

    class _P:
        chromium = _Chromium()

    asyncio.run(marketplace_poster.open_session_context(_P()))
    user_data_dir, kw = llamadas["persistent"]
    assert user_data_dir == str(perfil)
    assert "Chrome/120.0.0.0" in kw["user_agent"]          # mismo UA del login
    assert "--disable-blink-features=AutomationControlled" in kw["args"]
