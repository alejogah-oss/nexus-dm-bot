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


class _FakePage:
    def __init__(self, url, pass_visible=False):
        self.url = url
        self._pass_visible = pass_visible
    def locator(self, sel): return _FakeLocator(self._pass_visible)


async def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def test_muro_de_login_por_url_da_mensaje_claro():
    """Antes decía 'no se encontró el formulario', que manda a buscar el
    problema en el DOM cuando en realidad la sesión de FB se cayó."""
    import asyncio, pytest
    page = _FakePage("https://www.facebook.com/login/?next=...")
    with pytest.raises(RuntimeError, match="refresh_fb_session"):
        asyncio.run(marketplace_poster.assert_logged_in(page))


def test_muro_de_login_por_campo_de_password():
    import asyncio, pytest
    page = _FakePage("https://www.facebook.com/marketplace/create/vehicle",
                     pass_visible=True)
    with pytest.raises(RuntimeError, match="refresh_fb_session"):
        asyncio.run(marketplace_poster.assert_logged_in(page))


def test_sesion_viva_no_levanta_nada():
    import asyncio
    page = _FakePage("https://www.facebook.com/marketplace/create/vehicle")
    asyncio.run(marketplace_poster.assert_logged_in(page))


def test_usa_el_perfil_del_login_por_terminal_si_existe(tmp_path, monkeypatch):
    """El login por terminal (refresh_fb_session.py) deja este perfil con la
    sesión viva. Reusarlo es lo que evita que FB pida login en cada publicada."""
    import asyncio
    perfil = tmp_path / ".fb_playwright_profile_poster"
    perfil.mkdir()
    monkeypatch.setattr(marketplace_poster, "SESSION_PROFILES", [perfil])
    llamadas = {}

    class _Ctx:
        pages = []
        async def close(self): pass

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
