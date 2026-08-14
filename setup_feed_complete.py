"""
setup_feed_complete.py
Full flow: Data sources → Add URL feed → Confirm settings → Upload
Commerce Manager Catalog ID: 1000973389316119
"""
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from fb_session import load_cookies
import time, sys

CAT_ID = "1000973389316119"
BIZ_ID = "1975334699886381"
CSV_FEED = "https://bot.tucarroconalejo.com/feed/vehicles.csv"
ADD_URL = f"https://business.facebook.com/commerce/catalogs/{CAT_ID}/data_sources/add/?business_id={BIZ_ID}"


def log(msg):
    print(msg, flush=True)


def dismiss_overlays(page):
    for name in ["Close", "Done", "Not now", "Dismiss"]:
        try:
            page.get_by_role("button", name=name, exact=True).click(timeout=1500)
            page.wait_for_timeout(600)
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    except Exception:
        pass


def wait_and_click(page, selector_fn, label, timeout=10000):
    """Wait for element to be enabled, then click."""
    try:
        el = selector_fn()
        el.wait_for(state="visible", timeout=timeout)
        page.wait_for_timeout(300)
        el.click(timeout=timeout)
        log(f"  ✅ {label}")
        return True
    except Exception as e:
        log(f"  ⚠️ {label}: {e}")
        return False


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        slow_mo=500,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
    )
    load_cookies(ctx)
    page = ctx.new_page()

    # ── STEP 1: Navigate to Add data source ──────────────────────────────────
    log(f"\n[1] Navegando a Add data source...")
    page.goto(ADD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    dismiss_overlays(page)
    page.screenshot(path="feed_s1_add.png")
    log(f"    URL: {page.url}")

    # ── STEP 2: Click "Data File" ─────────────────────────────────────────────
    log(f"\n[2] Seleccionando 'Data File'...")
    page.wait_for_timeout(1000)
    try:
        page.locator('text="Data File"').first.click(timeout=6000)
        log("    ✅ Data File seleccionado")
    except Exception as e:
        log(f"    ⚠️ {e}")
    page.wait_for_timeout(1500)
    page.screenshot(path="feed_s2_datafile.png")

    # ── STEP 3: Click "Next" (after Data File) ───────────────────────────────
    log(f"\n[3] Click Next (Data File)...")
    page.wait_for_timeout(500)
    try:
        # Wait for Next to be enabled
        page.wait_for_function(
            "() => { const btns = [...document.querySelectorAll('[role=\"button\"]')]; "
            "return btns.some(b => b.textContent.trim() === 'Next' && b.getAttribute('aria-disabled') !== 'true'); }",
            timeout=8000
        )
        page.evaluate(
            "() => { const btns = [...document.querySelectorAll('[role=\"button\"]')]; "
            "const n = btns.find(b => b.textContent.trim() === 'Next' && b.getAttribute('aria-disabled') !== 'true'); "
            "if (n) n.click(); }"
        )
        page.wait_for_timeout(3000)
        log(f"    ✅ Next → {page.url}")
    except Exception as e:
        log(f"    ⚠️ {e}")
    page.screenshot(path="feed_s3_next1.png")

    # ── STEP 4: Select "Use a URL or Google Sheets" if not already ───────────
    log(f"\n[4] Asegurando 'Use a URL or Google Sheets'...")
    try:
        radio = page.locator('text="Use a URL or Google Sheets"').first
        if radio.is_visible(timeout=4000):
            radio.click(timeout=4000)
            page.wait_for_timeout(1200)
            log("    ✅ URL option seleccionada")
    except Exception as e:
        log(f"    ℹ️ {e}")
    page.screenshot(path="feed_s4_url_option.png")

    # ── STEP 5: Fill URL with React event triggers ────────────────────────────
    log(f"\n[5] Llenando URL del feed...")
    page.wait_for_timeout(800)

    # Find the URL input
    url_input = None
    all_inputs = page.locator('input').all()
    for inp in all_inputs:
        try:
            if inp.is_visible(timeout=500):
                ph = inp.get_attribute("placeholder") or ""
                log(f"    Input: placeholder='{ph}'")
                url_input = inp
                break
        except Exception:
            pass

    if url_input:
        url_input.click()
        page.wait_for_timeout(300)
        # Select all and clear
        url_input.press("Meta+a")
        page.wait_for_timeout(200)
        url_input.press("Backspace")
        page.wait_for_timeout(200)
        # Type URL
        url_input.type(CSV_FEED, delay=15)
        page.wait_for_timeout(600)
        url_input.dispatch_event("input")
        url_input.dispatch_event("change")
        page.wait_for_timeout(600)
        val = url_input.input_value()
        log(f"    Input value: {val}")
    else:
        log("    ⚠️ No input found")

    page.screenshot(path="feed_s5_url_filled.png")

    # ── STEP 6: Wait for Next to enable, then click ───────────────────────────
    log(f"\n[6] Esperando que Next se habilite...")
    try:
        page.wait_for_function(
            "() => { const btns = [...document.querySelectorAll('[role=\"button\"]')]; "
            "return btns.some(b => b.textContent.trim() === 'Next' && b.getAttribute('aria-disabled') !== 'true'); }",
            timeout=12000
        )
        next_info = page.evaluate(
            "() => { const b = [...document.querySelectorAll('[role=\"button\"]')]"
            ".find(x => x.textContent.trim() === 'Next'); "
            "return b ? {disabled: b.getAttribute('aria-disabled'), text: b.textContent.trim()} : null; }"
        )
        log(f"    Next state: {next_info}")

        page.evaluate(
            "() => { const btns = [...document.querySelectorAll('[role=\"button\"]')]; "
            "const n = btns.find(b => b.textContent.trim() === 'Next' && b.getAttribute('aria-disabled') !== 'true'); "
            "if (n) n.click(); }"
        )
        log("    ✅ Next clickeado")
        page.wait_for_timeout(6000)
    except Exception as e:
        log(f"    ⚠️ {e}")

    page.screenshot(path="feed_s6_after_next2.png")
    log(f"    URL: {page.url}")

    # ── STEP 7: Handle "Confirm settings" modal ───────────────────────────────
    log(f"\n[7] Buscando modal 'Confirm settings'...")
    page.wait_for_timeout(3000)
    body_text = page.evaluate("() => document.body.innerText")
    log(f"    Contenido: {body_text[:400]}")
    page.screenshot(path="feed_s7_modal.png")

    # Check if modal appeared
    has_confirm = "Confirm settings" in body_text or "confirm" in body_text.lower()
    has_upload = "Upload" in body_text
    log(f"    'Confirm settings' en página: {has_confirm}")
    log(f"    'Upload' en página: {has_upload}")

    # ── STEP 8: Set USD currency ──────────────────────────────────────────────
    if has_confirm or has_upload:
        log(f"\n[8] Configurando moneda USD...")
        # Look for currency selector
        try:
            # Try finding a select or combobox for currency
            currency_selectors = [
                page.get_by_label("Default currency", exact=False),
                page.locator('select').filter(has_text="currency"),
                page.locator('[role="combobox"]').filter(has_text="Select"),
            ]
            for cs in currency_selectors:
                try:
                    if cs.first.is_visible(timeout=2000):
                        cs.first.click(timeout=3000)
                        page.wait_for_timeout(1000)
                        # Try to find USD option
                        for opt_text in ["USD", "US Dollar", "United States Dollar"]:
                            try:
                                page.get_by_role("option", name=opt_text, exact=False).first.click(timeout=2000)
                                log(f"    ✅ USD seleccionado ({opt_text})")
                                page.wait_for_timeout(800)
                                break
                            except Exception:
                                pass
                        break
                except Exception:
                    pass
        except Exception as e:
            log(f"    ℹ️ Currency: {e}")

        page.screenshot(path="feed_s8_currency.png")

        # ── STEP 9: Click Upload ──────────────────────────────────────────────
        log(f"\n[9] Clickeando Upload...")
        page.wait_for_timeout(800)
        try:
            # Try Upload button
            page.wait_for_function(
                "() => { const btns = [...document.querySelectorAll('[role=\"button\"]')]; "
                "return btns.some(b => (b.textContent.trim() === 'Upload' || b.textContent.includes('Upload')) "
                "&& b.getAttribute('aria-disabled') !== 'true'); }",
                timeout=6000
            )
            page.evaluate(
                "() => { const btns = [...document.querySelectorAll('[role=\"button\"]')]; "
                "const u = btns.find(b => (b.textContent.trim() === 'Upload' || b.textContent.includes('Upload')) "
                "&& b.getAttribute('aria-disabled') !== 'true'); "
                "if (u) { u.click(); return u.textContent; } return 'not found'; }"
            )
            page.wait_for_timeout(10000)
            log(f"    ✅ Upload clickeado")
        except Exception as e:
            log(f"    ⚠️ Upload: {e}")

        page.screenshot(path="feed_s9_uploading.png")
        log(f"    URL: {page.url}")
        body_final = page.evaluate("() => document.body.innerText.slice(0, 800)")
        log(f"    Resultado:\n{body_final}")

        # Wait to see result
        page.wait_for_timeout(8000)
        page.screenshot(path="feed_s10_final.png")
        log(f"    URL FINAL: {page.url}")
        log(page.evaluate("() => document.body.innerText.slice(0, 800)"))
    else:
        log("\n    ⚠️ Modal no encontrado - revisar feed_s7_modal.png")

    log("\n\n⏳ Browser abierto 3 minutos para inspección...")
    time.sleep(180)
    browser.close()
    log("✅ DONE")
