"""
setup_feed_v5.py — Commerce Manager CSV Feed Setup
Fix: waits for "Review data file" page (field mapping), then clicks Next to finish
"""
from playwright.sync_api import sync_playwright
from fb_session import load_cookies
import time

CAT_ID = "1000973389316119"
BIZ_ID = "1975334699886381"
CSV_FEED = "https://bot.tucarroconalejo.com/feed/vehicles.csv"
ADD_URL = f"https://business.facebook.com/commerce/catalogs/{CAT_ID}/data_sources/add/?business_id={BIZ_ID}"
SOURCES_URL = f"https://business.facebook.com/commerce/catalogs/{CAT_ID}/data_sources/?business_id={BIZ_ID}"


def log(msg): print(msg, flush=True)


def js_click_next(page):
    return page.evaluate("""
        () => {
            const btn = [...document.querySelectorAll('[role="button"]')]
                .find(b => b.textContent.trim() === 'Next' &&
                      b.getAttribute('aria-disabled') !== 'true');
            if (btn) { btn.click(); return 'ok'; }
            return null;
        }
    """)


def react_fill_url(page, value):
    return page.evaluate("""
        (val) => {
            const inp = [...document.querySelectorAll('input')]
                .find(el => el.type !== 'radio' && el.type !== 'hidden' &&
                      el.type !== 'checkbox' && el.offsetParent !== null);
            if (!inp) return { error: 'no input' };
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(inp, val);
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            inp.focus();
            return { type: inp.type, placeholder: inp.placeholder, value: inp.value };
        }
    """, value)


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False, slow_mo=400,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
    )
    load_cookies(ctx)
    page = ctx.new_page()

    # ── CHECK: does a data source already exist? ──────────────────────────────
    log("\n[0] Verificando si ya existe data source...")
    page.goto(SOURCES_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    ds_body = page.evaluate("() => document.body.innerText")
    page.screenshot(path="v5_s0_sources.png")
    log(f"    URL: {page.url}")

    has_feed = any(kw in ds_body for kw in ["vehicles.csv", "tucarroconalejo.com/feed", "New data feed"])
    log(f"    Feed existente: {has_feed}")

    if has_feed:
        log("    ✅ Feed ya está configurado!")
        log(f"    Contenido:\n{ds_body[:600]}")
        page.screenshot(path="v5_feed_exists.png")
        log("\n⏳ Browser abierto 2 min...")
        time.sleep(120)
        browser.close()
        exit(0)

    # ── FULL FLOW ─────────────────────────────────────────────────────────────
    log("\n[1] Navegando a Add data source...")
    page.goto(ADD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    for name in ["Close", "Done", "Not now"]:
        try: page.get_by_role("button", name=name, exact=True).click(timeout=1500)
        except: pass
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    log("[2] Data File...")
    page.locator('text="Data File"').first.click(timeout=6000)
    page.wait_for_timeout(1200)

    log("[3] Next 1...")
    page.wait_for_function(
        "() => [...document.querySelectorAll('[role=\"button\"]')]"
        ".some(b => b.textContent.trim() === 'Next' && b.getAttribute('aria-disabled') !== 'true')",
        timeout=8000)
    js_click_next(page)
    page.wait_for_timeout(3500)
    log(f"    → {page.url}")

    log("[4] URL option...")
    try:
        page.locator('text="Use a URL or Google Sheets"').first.click(timeout=5000)
        page.wait_for_timeout(1000)
    except: pass

    log("[5] Llenando URL (React setter)...")
    page.wait_for_timeout(500)
    r = react_fill_url(page, CSV_FEED)
    log(f"    → {r}")
    page.wait_for_timeout(800)
    page.screenshot(path="v5_s5_url.png")

    log("[6] Esperando Next habilitado...")
    page.wait_for_function(
        "() => [...document.querySelectorAll('[role=\"button\"]')]"
        ".some(b => b.textContent.trim() === 'Next' && b.getAttribute('aria-disabled') !== 'true')",
        timeout=10000)
    log("    ✅ Next habilitado")
    js_click_next(page)
    page.screenshot(path="v5_s6_next_clicked.png")

    # ── WAIT: either "Confirm settings" OR "Review data file" ─────────────────
    log("\n[7] Esperando confirmación o Review (hasta 90s)...")
    try:
        page.wait_for_function(
            "() => { const t = document.body.innerText; "
            "return t.includes('Confirm settings') || t.includes('Review data file') || "
            "t.includes('Make sure that the fields'); }",
            timeout=90000
        )
        body = page.evaluate("() => document.body.innerText")
        page.screenshot(path="v5_s7_review.png")
        log(f"    ✅ Página detectada")

        if "Review data file" in body or "Make sure that the fields" in body:
            log("    → Estado: 'Review data file' (mapeo de campos)")
            log(f"    Contenido:\n{body[max(0,body.find('Make sure')):max(0,body.find('Make sure'))+300]}")

            # Just click Next — field mapping is optional
            page.wait_for_timeout(1500)
            log("\n[8] Click Next en 'Review data file'...")
            result = js_click_next(page)
            log(f"    Click result: {result}")
            page.wait_for_timeout(10000)
            page.screenshot(path="v5_s8_after_review.png")
            log(f"    URL: {page.url}")
            body2 = page.evaluate("() => document.body.innerText")
            log(f"\n    Contenido:\n{body2[:800]}")

            # Check if there's another Next or a Done/Finish button
            final_btns = page.evaluate("""
                () => [...document.querySelectorAll('[role="button"]')]
                    .filter(b => b.offsetParent !== null)
                    .map(b => b.textContent.trim())
                    .filter(t => t.length > 0)
            """)
            log(f"    Botones visibles: {final_btns}")

            # Click Done/Finish/Save if available
            for btn_name in ["Done", "Finish", "Save", "Close"]:
                try:
                    result = page.evaluate(f"""
                        () => {{
                            const btn = [...document.querySelectorAll('[role="button"]')]
                                .find(b => b.textContent.trim() === '{btn_name}' &&
                                      b.getAttribute('aria-disabled') !== 'true');
                            if (btn) {{ btn.click(); return 'clicked {btn_name}'; }}
                            return null;
                        }}
                    """)
                    if result:
                        log(f"    ✅ {result}")
                        page.wait_for_timeout(5000)
                        break
                except: pass

            page.screenshot(path="v5_s9_final.png")
            log(f"    URL FINAL: {page.url}")

        elif "Confirm settings" in body:
            log("    → Estado: 'Confirm settings' (modal)")
            # Set USD and click Upload
            try:
                combo = page.locator('[role="combobox"]').first
                if combo.is_visible(timeout=2000):
                    combo.click()
                    page.wait_for_timeout(800)
                    page.locator('[role="option"]').filter(has_text="USD").first.click(timeout=3000)
                    log("    ✅ USD")
            except: pass

            upload = page.evaluate("""
                () => {
                    const btn = [...document.querySelectorAll('[role="button"]')]
                        .find(b => b.textContent.trim() === 'Upload' &&
                              b.getAttribute('aria-disabled') !== 'true');
                    if (btn) { btn.click(); return 'ok'; }
                    return null;
                }
            """)
            log(f"    Upload: {upload}")
            page.wait_for_timeout(15000)
            page.screenshot(path="v5_s9_final.png")

    except Exception as e:
        log(f"    ⚠️ Timeout: {e}")
        page.screenshot(path="v5_timeout.png")
        log(page.evaluate("() => document.body.innerText.slice(0, 500)"))

    # Final state check
    log("\n[FINAL] Verificando data sources...")
    page.goto(SOURCES_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    page.screenshot(path="v5_final_sources.png")
    final = page.evaluate("() => document.body.innerText")
    log(f"    URL: {page.url}")
    log(f"    {final[:600]}")

    log("\n✅ DONE — Browser abierto 3 min para inspección")
    time.sleep(180)
    browser.close()
