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
        return [{"name": "c_user"}, {"name": "xs"}]   # cookies viejas, siempre ahí


class _FakePage:
    """entra_tras=N: al N-ésimo chequeo Facebook deja de mostrar el muro."""
    def __init__(self, url, pass_visible=False, entra_tras=0):
        self.url = url
        self._pass_visible = pass_visible
        self._entra_tras = entra_tras
        self.consultas = 0
        self.context = _FakeContext(self)
    def locator(self, sel):
        self.consultas += 1
        if self._entra_tras and self.consultas >= self._entra_tras:
            self.url = "https://www.facebook.com/"
            return _FakeLocator(False)
        return _FakeLocator(self._pass_visible)


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
    # Facebook muestra el formulario de entrar sobre la propia URL del form.
    page = _FakePage("https://www.facebook.com/marketplace/create/vehicle",
                     pass_visible=True, entra_tras=3)
    asyncio.run(marketplace_poster.ensure_logged_in(page, segundos=10))
    assert page.consultas >= 3


def test_cookies_viejas_no_cuentan_como_sesion_viva():
    """c_user y xs siguen en el perfil aunque estén vencidas. Si nos guiáramos
    por ellas daríamos el login por bueno con la pantalla de entrar delante, y
    el bot reportaría 'no se encontró el formulario'."""
    import asyncio, pytest
    page = _FakePage("https://www.facebook.com/login/", pass_visible=True)  # nunca entra
    with pytest.raises(RuntimeError, match="no se completó el login"):
        asyncio.run(marketplace_poster.ensure_logged_in(page, segundos=3))


def test_si_nadie_entra_cancela_con_mensaje_claro():
    import asyncio, pytest
    page = _FakePage("https://www.facebook.com/login/", pass_visible=True)
    with pytest.raises(RuntimeError, match="no se completó el login"):
        asyncio.run(marketplace_poster.ensure_logged_in(page, segundos=2))


def test_perfil_de_sesion_es_estable_no_el_mas_reciente(tmp_path, monkeypatch):
    """Si cambiara de perfil entre corridas, el login se guardaría en uno y la
    publicada siguiente abriría el otro — y FB lo pediría de nuevo."""
    import os, time
    a = tmp_path / "poster"; a.mkdir()
    b = tmp_path / "otro";   b.mkdir()
    os.utime(b, (time.time() + 500, time.time() + 500))   # b es más reciente
    monkeypatch.setattr(marketplace_poster, "SESSION_CHANNEL", "")
    monkeypatch.setattr(marketplace_poster, "SESSION_PROFILES", [a, b])
    assert marketplace_poster.session_profile() == a
    assert marketplace_poster.session_profile() == a


def test_sin_ningun_perfil_devuelve_el_del_poster_para_crearlo(tmp_path, monkeypatch):
    a = tmp_path / "poster"
    monkeypatch.setattr(marketplace_poster, "SESSION_CHANNEL", "")
    monkeypatch.setattr(marketplace_poster, "SESSION_PROFILES", [a, tmp_path / "otro"])
    assert marketplace_poster.session_profile() == a


def test_usa_el_perfil_del_login_por_terminal_si_existe(tmp_path, monkeypatch):
    """El login por terminal (refresh_fb_session.py) deja este perfil con la
    sesión viva. Reusarlo es lo que evita que FB pida login en cada publicada."""
    import asyncio
    perfil = tmp_path / ".fb_playwright_profile_poster"
    perfil.mkdir()
    monkeypatch.setattr(marketplace_poster, "SESSION_CHANNEL", "")
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


def test_con_chrome_real_no_pisamos_el_user_agent(monkeypatch, tmp_path):
    """Declarar Chrome/120 mientras el binario va por la 148 contradice los
    client hints y Facebook lo lee como bot justo al loguearse. Con el Chrome
    de verdad dejamos su UA en paz."""
    import asyncio
    monkeypatch.setattr(marketplace_poster, "SESSION_CHANNEL", "chrome")
    monkeypatch.setattr(marketplace_poster, "load_session_cookies", lambda *a, **k: [])
    monkeypatch.setattr(marketplace_poster.Path, "home", staticmethod(lambda: tmp_path))
    visto = {}

    class _Ctx:
        pages = []
        async def close(self): pass
        async def add_cookies(self, c): pass

    class _Chromium:
        async def launch_persistent_context(self, user_data_dir, **kw):
            visto.update(kw); visto["dir"] = user_data_dir
            return _Ctx()

    class _P:
        chromium = _Chromium()

    asyncio.run(marketplace_poster.open_session_context(_P()))
    assert visto["channel"] == "chrome"
    assert "user_agent" not in visto            # el UA real de Chrome, sin tocar
    assert visto["dir"].endswith(".fb_playwright_profile_chrome")   # perfil aparte


def test_chrome_real_es_el_default_si_esta_instalado(monkeypatch, tmp_path):
    """El panel lanza el poster como subproceso: nadie va a acordarse de
    exportar FB_BROWSER_CHANNEL. Si Chrome está, se usa Chrome."""
    monkeypatch.delenv("FB_BROWSER_CHANNEL", raising=False)
    monkeypatch.setattr(marketplace_poster, "CHROME_APP", tmp_path / "hay")
    (tmp_path / "hay").mkdir()
    assert marketplace_poster._canal_por_defecto() == "chrome"

    monkeypatch.setattr(marketplace_poster, "CHROME_APP", tmp_path / "no_hay")
    assert marketplace_poster._canal_por_defecto() == ""


def test_se_puede_forzar_el_chromium_de_playwright(monkeypatch):
    monkeypatch.setenv("FB_BROWSER_CHANNEL", "")
    assert marketplace_poster._canal_por_defecto() == ""
