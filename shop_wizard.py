"""
shop_wizard.py — Commerce Manager Shop Setup Wizard
UI actualizada: el selector de plataforma es ahora un DROPDOWN, no radio buttons.
"""
import sys, time
sys.path.insert(0, "/Users/macbookpro/nexus-automation")
from playwright.sync_api import sync_playwright
from fb_session import create_context

BIZ_ID      = "1975334699886381"   # Tucarroconalejo BM (catálogo + Alejo asignado a página 765862069934682)
TARGET_PAGE = "765862069934682"    # Tucarro-con-Alejo

WIZARD_URL = (
    f"https://business.facebook.com/commerce/onboarding/"
    f"?source=COMMERCE_MANAGER_LAUNCHPAD_CREATE_SHOP_BUTTON"
    f"&business_id={BIZ_ID}"
)


def ss(page, name):
    path = f"/Users/macbookpro/nexus-automation/{name}.png"
    page.screenshot(path=path)
    print(f"  📸 {name}.png", flush=True)


def body_text(page):
    return page.inner_text("body")


def wait_body(page, text, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if text.lower() in body_text(page).lower():
            return True
        time.sleep(1)
    return False


with sync_playwright() as p:
    ctx = create_context(p)
    print("  ✅ Contexto cargado", flush=True)
    pg = ctx.new_page()

    # ── 1. Abrir wizard ───────────────────────────────────────────────────────
    print(f"\n[1] Abriendo wizard BM {BIZ_ID}...", flush=True)
    pg.goto(WIZARD_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    ss(pg, "w01_home")

    # ── 2. Click "Create shop" ────────────────────────────────────────────────
    print(f"\n[2] Clickeando Create shop...", flush=True)
    pg.get_by_role("button", name="Create shop").first.click(timeout=15000)
    print(f"  ✅ Create shop clickeado", flush=True)
    time.sleep(5)
    ss(pg, "w02_modal")
    print(f"  Body: {body_text(pg)[:200]}", flush=True)

    # ── 3. Handle platform modal — now a DROPDOWN ─────────────────────────────
    print(f"\n[3] Manejando modal de plataforma (dropdown)...", flush=True)

    # Step 3a: Click the "Select platform" combobox — match by text containing "platform"
    open_r = pg.evaluate("""
        () => {
            // Find ALL comboboxes and pick the one whose text contains "platform"
            const combos = [...document.querySelectorAll('[role="combobox"]')]
                .filter(e => e.offsetParent);

            const platform = combos.find(
                e => e.textContent.replace(/​/g, '').trim().toLowerCase().includes('platform')
            );

            if (platform) {
                platform.click();
                return `clicked: "${platform.textContent.replace(/​/g, '').trim()}"`;
            }

            // Fallback: click the LAST combobox (Select platform is usually the last one in modal)
            if (combos.length >= 1) {
                const last = combos[combos.length - 1];
                last.click();
                return `clicked last combobox: "${last.textContent.replace(/​/g, '').trim()}"`;
            }

            return `no comboboxes found; total=${
                document.querySelectorAll('[role="combobox"]').length
            }`;
        }
    """)
    print(f"  Abriendo dropdown: {open_r}", flush=True)
    time.sleep(3)  # wait for dropdown to open and options to render
    ss(pg, "w03a_dropdown_open")

    # Step 3b: List all options (visible + hidden, since listbox might use display:none initially)
    opts = pg.evaluate("""
        () => {
            const selectors = ['[role="option"]', '[role="listitem"]', 'li[id]'];
            for (const sel of selectors) {
                const items = [...document.querySelectorAll(sel)]
                    .map(e => e.textContent.trim())
                    .filter(t => t.length > 0 && t.length < 100);
                if (items.length) return {sel, items};
            }
            return {sel: 'none', items: []};
        }
    """)
    print(f"  Opciones: {opts}", flush=True)

    # Step 3c: Click "I don't use these platforms"
    sel_r = pg.evaluate("""
        () => {
            const kws = ["I don't use these platforms", "don't use", "No uso estas", "None of"];
            // Try visible options first, then any
            for (const visible of [true, false]) {
                for (const kw of kws) {
                    const opt = [...document.querySelectorAll('[role="option"], li')]
                        .find(e => e.textContent.trim().toLowerCase().includes(kw.toLowerCase())
                                   && (!visible || e.offsetParent));
                    if (opt) {
                        opt.click();
                        return `clicked (visible=${!!opt.offsetParent}): "${opt.textContent.trim()}"`;
                    }
                }
            }
            // Last resort: click the LAST option (usually "I don't use these platforms" or "None")
            const allOpts = [...document.querySelectorAll('[role="option"]')];
            if (allOpts.length) {
                allOpts[allOpts.length - 1].click();
                return `clicked LAST option: "${allOpts[allOpts.length-1].textContent.trim()}"`;
            }
            return `not found; all options: ${
                JSON.stringify([...document.querySelectorAll('[role="option"]')]
                    .map(e => e.textContent.trim()))
            }`;
        }
    """)
    print(f"  Selección: {sel_r}", flush=True)
    time.sleep(2)
    ss(pg, "w03b_option_selected")

    # ── 4. Click Next ─────────────────────────────────────────────────────────
    print(f"\n[4] Clickeando Next...", flush=True)
    # Facebook uses both <button> and [role="button"] — check both, match by text includes "Next"
    next_info = pg.evaluate("""
        () => {
            const all = [...document.querySelectorAll('button, [role="button"]')]
                .filter(b => b.offsetParent && b.textContent.trim().replace(/​/g,'').includes('Next'));
            return all.map(b => ({
                text: b.textContent.trim().replace(/​/g,''),
                disabled: b.disabled || b.getAttribute('aria-disabled') === 'true',
                rect: {x: Math.round(b.getBoundingClientRect().x),
                       y: Math.round(b.getBoundingClientRect().y)}
            }));
        }
    """)
    print(f"  Next buttons: {next_info}", flush=True)

    if next_info and not next_info[0].get("disabled"):
        rx = next_info[0]["rect"]["x"] + 20
        ry = next_info[0]["rect"]["y"] + 10
        pg.mouse.click(rx, ry)
        print(f"  ✅ Next clickeado en ({rx},{ry})", flush=True)
    else:
        print(f"  ⚠️ Next no encontrado o disabled — forzando via JS...", flush=True)
        r = pg.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button, [role="button"]')]
                    .find(b => b.offsetParent && b.textContent.trim().replace(/​/g,'').includes('Next'));
                if (!btn) {
                    const all = [...document.querySelectorAll('button, [role="button"]')]
                        .filter(b => b.offsetParent)
                        .map(b => b.textContent.trim().slice(0,30));
                    return `not found; visible buttons: ${JSON.stringify(all)}`;
                }
                btn.click();
                return `force-clicked: "${btn.textContent.trim()}" disabled=${btn.disabled}`;
            }
        """)
        print(f"  → {r}", flush=True)

    time.sleep(4)
    ss(pg, "w04_after_next")
    b4 = body_text(pg)
    print(f"  Texto post-Next: {b4[:400]}", flush=True)

    # ── 5. Sales Channel — buscar página 765862069934682 ─────────────────────
    print(f"\n[5] Esperando Sales Channel...", flush=True)
    found_sc = wait_body(pg, "Sales channel", 15)
    time.sleep(3)
    ss(pg, "w05_sales_channel")
    b5 = body_text(pg)
    print(f"  Sales Channel found={found_sc}", flush=True)
    print(f"  Body completo:\n{b5[:3000]}", flush=True)

    if TARGET_PAGE in b5:
        print(f"\n  ✅✅✅ PAGE {TARGET_PAGE} VISIBLE EN WIZARD!", flush=True)
        # Click "Select" button near the target page
        sel = pg.evaluate(f"""
            () => {{
                const allEls = [...document.querySelectorAll('*')];
                const pageEl = allEls.find(e =>
                    e.textContent.includes('{TARGET_PAGE}') &&
                    e.childElementCount < 5 && e.offsetParent
                );
                if (!pageEl) return 'page element not found';

                // Walk up to find row container, then find Select button
                let el = pageEl;
                for (let i = 0; i < 10; i++) {{
                    const btns = el.querySelectorAll &&
                        [...el.querySelectorAll('button, [role="button"]')]
                        .filter(b => b.textContent.trim() === 'Select' && b.offsetParent);
                    if (btns && btns.length) {{
                        btns[0].click();
                        return 'clicked Select near page';
                    }}
                    el = el.parentElement;
                    if (!el) break;
                }}
                return 'Select button not found near page element';
            }}
        """)
        print(f"  → {sel}", flush=True)
        time.sleep(3)
        ss(pg, "w05b_page_selected")

        # Click Next to go to Catalog step
        pg.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button')]
                    .find(b => b.textContent.trim() === 'Next' && b.offsetParent && !b.disabled);
                if (btn) btn.click();
            }
        """)
        time.sleep(4)
        ss(pg, "w06_catalog")
        b6 = body_text(pg)
        print(f"\n[6] Catalog step:\n{b6[:1500]}", flush=True)
    else:
        print(f"\n  ⚠️ Page {TARGET_PAGE} NO aparece en wizard", flush=True)
        # List what pages DO appear
        lines = [l.strip() for l in b5.split('\n') if l.strip()]
        page_lines = [l for l in lines if any(x in l for x in ['Page:', '701', '767', '765', 'Tucarro', 'Car-sales'])]
        print(f"  Páginas visibles: {page_lines[:15]}", flush=True)

    print("\n⏳ Browser abierto 10 min", flush=True)
    time.sleep(600)
    ctx.close()
