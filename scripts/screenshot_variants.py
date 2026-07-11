# -*- coding: utf-8 -*-
"""Screenshots aller Layout-Grundrisse (scrollt tiefer)."""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"
USERNAME = "admin"
PASSWORD = "Admin2024!"

def save(page, name):
    path = "scripts/ss_{}.png".format(name)
    page.screenshot(path=path, full_page=False)
    print("  saved: " + path)

def scroll_st(page, y=0):
    page.evaluate("""(y) => {
        const main = document.querySelector('[data-testid="stMain"]');
        if (main) main.scrollTop = y;
    }""", y)
    page.wait_for_timeout(700)

def click_wait(page, label, wait=10000, timeout=10000):
    try:
        page.click("button:has-text('{}')".format(label), timeout=timeout)
        page.wait_for_timeout(wait)
        return True
    except:
        return False

def click_tab(page, text):
    for sel in ["[data-testid='stTab']:has-text('{}')", "button[role='tab']:has-text('{}')"]:
        try:
            page.click(sel.format(text), timeout=6000)
            page.wait_for_timeout(2000)
            return True
        except:
            pass
    return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    page.fill("input[type='text']", USERNAME)
    page.fill("input[type='password']", PASSWORD)
    page.click("button:has-text('Login')")
    page.wait_for_timeout(5000)

    click_wait(page, "Weiter zu Nutzung & Flächen →")
    scroll_st(page, 99999); click_wait(page, "Weiter zum Funktionsgraph →")
    scroll_st(page, 99999); click_wait(page, "Weiter zum Regelwerk →")
    scroll_st(page, 99999); click_wait(page, "Weiter zu Projektzielen →")
    scroll_st(page, 99999); click_wait(page, "Layouts generieren", wait=3000)

    print("Warte auf Pipeline...")
    try:
        page.wait_for_function(
            "() => !document.body.innerText.includes('Pipeline läuft')",
            timeout=180000
        )
    except:
        pass
    page.wait_for_timeout(3000)
    print("Fertig.")

    # Variante A: scroll to layout image (weiter unten als bisher)
    for tab, name in [("Variante A", "A"), ("Variante B", "B"), ("Variante C", "C")]:
        if tab != "Variante A":
            click_tab(page, tab)
        # Grundriss ist ~1800-2200px tief
        scroll_st(page, 1900)
        save(page, "grundriss_{}".format(name))

    browser.close()
print("Fertig.")
