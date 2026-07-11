# -*- coding: utf-8 -*-
"""Screenshots der Layout-Bilder in Schritt 6 - scrollt Streamlit-Container."""
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

def scroll_st(page, y):
    """Scroll the Streamlit main block container."""
    page.evaluate("""(y) => {
        // Try Streamlit's main scrollable area
        const main = document.querySelector('[data-testid="stMain"]');
        if (main) { main.scrollTop = y; return; }
        // Fallback: first scrollable div
        const divs = document.querySelectorAll('div');
        for (const d of divs) {
            if (d.scrollHeight > d.clientHeight + 50) {
                d.scrollTop = y;
                break;
            }
        }
    }""", y)
    page.wait_for_timeout(800)

def click_wait(page, label, wait=10000, timeout=10000):
    try:
        page.click("button:has-text('{}')".format(label), timeout=timeout)
        print("  OK: " + label)
        page.wait_for_timeout(wait)
        return True
    except Exception as e:
        print("  MISS: {}".format(str(e)[:60]))
        return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Login + alle Schritte
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    page.fill("input[type='text']", USERNAME)
    page.fill("input[type='password']", PASSWORD)
    page.click("button:has-text('Login')")
    page.wait_for_timeout(5000)

    click_wait(page, "Weiter zu Nutzung & Flächen →")
    scroll_st(page, 99999)
    click_wait(page, "Weiter zum Funktionsgraph →")
    scroll_st(page, 99999)
    click_wait(page, "Weiter zum Regelwerk →")
    scroll_st(page, 99999)
    click_wait(page, "Weiter zu Projektzielen →")
    scroll_st(page, 99999)
    click_wait(page, "Layouts generieren", wait=3000)

    print("Warte auf Pipeline...")
    try:
        page.wait_for_function(
            "() => !document.body.innerText.includes('Pipeline läuft')",
            timeout=180000
        )
    except Exception:
        print("  Timeout")
    page.wait_for_timeout(3000)
    print("Pipeline fertig.")

    # Finde Scrollhoehe des Streamlit-Containers
    info = page.evaluate("""() => {
        const main = document.querySelector('[data-testid="stMain"]');
        if (!main) return {h: document.documentElement.scrollHeight, tag: 'document'};
        return {h: main.scrollHeight, tag: 'stMain'};
    }""")
    print("  Container: {} scrollHeight={}px".format(info['tag'], info['h']))

    # Screenshottsektion: 0, 900, 1800, 2700, 3600, 4500 px
    for i, y in enumerate(range(0, max(info['h'], 4500) + 1, 900)):
        scroll_st(page, y)
        path = "scripts/ss_result_{:02d}.png".format(i)
        page.screenshot(path=path, full_page=False)
        print("  saved: {} (scroll={}px)".format(path, y))
        if i >= 7:  # max 8 screenshots
            break

    browser.close()
print("\nFertig.")
