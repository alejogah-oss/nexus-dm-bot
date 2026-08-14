"""
create_catalog_tca.py

Create a vehicle catalog in BM 1551722759597838 ("Tu Carro con Alejo")
by:
1. Opening the New Catalog form
2. Changing Business Portfolio dropdown to "Tu Carro con Alejo"
3. Selecting "Vehicles" catalog type
4. Naming it "Inventario TCA"
5. Clicking Next to complete the creation

Once the catalog exists in BM 1551722759597838, the shop wizard
for that BM will show page 765862069934682 (Tucarro-con-Alejo).
"""
import sys, time
sys.path.insert(0, "/Users/macbookpro/nexus-automation")
from playwright.sync_api import sync_playwright
from fb_session import create_context

BIZ_PAGE     = "1551722759597838"   # Tu Carro con Alejo BM
BIZ_CATALOG  = "1975334699886381"   # Tucarroconalejo BM (has existing catalog)
TARGET_PAGE  = "765862069934682"
CATALOG_NAME = "Inventario TCA"
CSV_FEED_URL = "https://bot.tucarroconalejo.com/feed/vehicles.csv"

NEW_CATALOG_URL = f"https://business.facebook.com/products/catalogs/new/?business_id={BIZ_PAGE}"


def ss(page, name):
    path = f"/Users/macbookpro/nexus-automation/{name}.png"
    page.screenshot(path=path)
    print(f"  📸 {name}.png", flush=True)


def body_text(page):
    return page.inner_text("body")


def click_by_text(page, text, role=None):
    """Click first visible element matching text."""
    r = page.evaluate(f"""
        () => {{
            const txt = {repr(text)};
            const els = [...document.querySelectorAll('*')]
                .filter(e => e.textContent.trim() === txt && e.offsetParent);
            if (!els.length) {{
                const els2 = [...document.querySelectorAll('*')]
                    .filter(e => e.textContent.trim().includes(txt) && e.offsetParent);
                if (!els2.length) return 'not found';
                els2[0].click();
                return 'clicked (contains): ' + els2[0].tagName;
            }}
            els[0].click();
            return 'clicked: ' + els[0].tagName;
        }}
    """)
    return r


with sync_playwright() as p:
    ctx = create_context(p)
    print("  ✅ Contexto cargado", flush=True)
    pg = ctx.new_page()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Open New Catalog form
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n[1] Abriendo New Catalog form para BM {BIZ_PAGE}...", flush=True)
    pg.goto(NEW_CATALOG_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    ss(pg, "nc_01_form")
    print(f"  URL: {pg.url}", flush=True)
    t = body_text(pg)
    print(f"  Texto:\n{t[:800]}", flush=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Click "Product type" dropdown — look for Vehicles option
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n[2] Abriendo dropdown de tipo de producto...", flush=True)

    # Scan all dropdown-like elements
    dropdowns = pg.evaluate("""
        () => {
            return [...document.querySelectorAll('[role="option"], [role="listbox"], select, [aria-haspopup="listbox"]')]
                .filter(e => e.offsetParent)
                .map(e => ({tag: e.tagName, role: e.getAttribute('role'), text: e.textContent.trim().slice(0, 80)}));
        }
    """)
    print(f"  Dropdowns visibles: {dropdowns}", flush=True)

    # Click the product type dropdown (first dropdown on form)
    r = pg.evaluate("""
        () => {
            // Look for the first dropdown that seems to be for product type
            const triggers = [...document.querySelectorAll('[aria-haspopup], [aria-expanded], select')]
                .filter(e => e.offsetParent);
            if (!triggers.length) return 'no dropdown found';
            triggers[0].click();
            return `clicked: ${triggers[0].tagName} text="${triggers[0].textContent.trim().slice(0, 50)}"`;
        }
    """)
    print(f"  → {r}", flush=True)
    time.sleep(2)
    ss(pg, "nc_02_dropdown_open")

    # List all visible options
    options = pg.evaluate("""
        () => [...document.querySelectorAll('[role="option"]')]
            .filter(e => e.offsetParent)
            .map(e => e.textContent.trim())
    """)
    print(f"  Opciones: {options}", flush=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Select "Vehicles" if available, otherwise "Online products"
    # ─────────────────────────────────────────────────────────────────────────
    vehicle_keywords = ['Vehicles', 'vehicles', 'Auto', 'Autos', 'Cars', 'Vehicle']
    selected_type = None
    for kw in vehicle_keywords:
        r = pg.evaluate(f"""
            () => {{
                const opt = [...document.querySelectorAll('[role="option"]')]
                    .find(e => e.textContent.trim().toLowerCase().includes({repr(kw.lower())}) && e.offsetParent);
                if (!opt) return 'not found';
                opt.click();
                return 'clicked: ' + opt.textContent.trim();
            }}
        """)
        if 'clicked' in r:
            selected_type = r
            break

    if not selected_type:
        print(f"  ⚠️ No 'Vehicles' option — cerrando dropdown y usando 'Online products'", flush=True)
        pg.keyboard.press("Escape")
        time.sleep(1)
    else:
        print(f"  ✅ {selected_type}", flush=True)

    time.sleep(2)
    ss(pg, "nc_03_type_selected")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Change Business Portfolio to "Tu Carro con Alejo"
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n[4] Cambiando Business Portfolio a 'Tu Carro con Alejo'...", flush=True)

    # Find the Business Portfolio dropdown
    biz_portfolio_r = pg.evaluate("""
        () => {
            // Find element containing "Business portfolio" label or "Tucarroconalejo"
            const section = [...document.querySelectorAll('*')]
                .find(e => e.textContent.trim() === 'Business portfolio' && e.offsetParent);
            if (!section) return {found: false, note: 'Business portfolio label not found'};

            // Look for a dropdown trigger in or near that section
            let parent = section.parentElement;
            for (let i = 0; i < 5; i++) {
                const triggers = parent.querySelectorAll('[aria-haspopup], [role="combobox"], select');
                if (triggers.length) {
                    triggers[0].click();
                    return {found: true, action: `clicked dropdown: ${triggers[0].tagName}`};
                }
                parent = parent.parentElement;
                if (!parent) break;
            }
            return {found: true, note: 'no trigger found near label'};
        }
    """)
    print(f"  Business portfolio dropdown: {biz_portfolio_r}", flush=True)
    time.sleep(2)

    # Also try clicking "Tucarroconalejo" text directly (it might be a dropdown trigger)
    r2 = pg.evaluate("""
        () => {
            const el = [...document.querySelectorAll('*')]
                .find(e => e.textContent.trim() === 'Tucarroconalejo' && e.offsetParent);
            if (!el) return 'Tucarroconalejo not found';
            el.click();
            return 'clicked Tucarroconalejo: ' + el.tagName;
        }
    """)
    print(f"  Click Tucarroconalejo: {r2}", flush=True)
    time.sleep(2)
    ss(pg, "nc_04_biz_dropdown")

    # List options in dropdown
    biz_options = pg.evaluate("""
        () => [...document.querySelectorAll('[role="option"], [role="menuitem"]')]
            .filter(e => e.offsetParent)
            .map(e => e.textContent.trim())
    """)
    print(f"  Opciones de negocio: {biz_options}", flush=True)

    # Select "Tu Carro con Alejo"
    r3 = pg.evaluate("""
        () => {
            const keywords = ['Tu Carro con Alejo', 'Tu carro con alejo', 'tca', '1551'];
            for (const kw of keywords) {
                const opt = [...document.querySelectorAll('[role="option"], [role="menuitem"], li')]
                    .find(e => e.textContent.trim().toLowerCase().includes(kw.toLowerCase()) && e.offsetParent);
                if (opt) {
                    opt.click();
                    return 'clicked: ' + opt.textContent.trim();
                }
            }
            return 'Tu Carro con Alejo option not found';
        }
    """)
    print(f"  Selección: {r3}", flush=True)
    time.sleep(2)
    ss(pg, "nc_05_biz_selected")
    t5 = body_text(pg)
    print(f"  Estado: {t5[:500]}", flush=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Set catalog name
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n[5] Poniendo nombre '{CATALOG_NAME}'...", flush=True)

    # Find the Name input
    name_r = pg.evaluate(f"""
        () => {{
            // Find input near "Name" label
            const inputs = [...document.querySelectorAll('input[type="text"], input:not([type])')];
            for (const inp of inputs) {{
                if (inp.offsetParent) {{
                    inp.focus();
                    inp.value = '';
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return 'focused: ' + (inp.placeholder || inp.name || inp.id);
                }}
            }}
            return 'no input found';
        }}
    """)
    print(f"  Input: {name_r}", flush=True)

    pg.keyboard.type(CATALOG_NAME)
    time.sleep(1)
    ss(pg, "nc_06_name_set")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Click Next
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n[6] Clickeando Next...", flush=True)
    r_next = pg.evaluate("""
        () => {
            const btn = [...document.querySelectorAll('button, [role="button"]')]
                .find(b => b.textContent.trim() === 'Next' && b.offsetParent && !b.disabled);
            if (!btn) return 'Next not found or disabled';
            btn.click();
            return 'clicked Next';
        }
    """)
    print(f"  → {r_next}", flush=True)
    time.sleep(5)
    ss(pg, "nc_07_after_next")
    print(f"  URL: {pg.url}", flush=True)
    t7 = body_text(pg)
    print(f"  Texto:\n{t7[:2000]}", flush=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 7. If catalog created — check what BM it's in
    # ─────────────────────────────────────────────────────────────────────────
    print(f"\n[7] Verificando resultado...", flush=True)
    time.sleep(3)
    print(f"  URL final: {pg.url}", flush=True)
    tf = body_text(pg)
    print(f"  Texto final:\n{tf[:2000]}", flush=True)
    ss(pg, "nc_08_final")

    # Extract new catalog ID from URL if available
    import re
    catalog_ids = re.findall(r'/catalogs/(\d+)', pg.url)
    if catalog_ids:
        print(f"\n  ✅ CATALOG ID EXTRAIDO: {catalog_ids}", flush=True)
    else:
        print(f"  ⚠️ Catalog ID not found in URL", flush=True)

    print("\n⏳ Browser abierto 10 min", flush=True)
    time.sleep(600)
    ctx.close()
