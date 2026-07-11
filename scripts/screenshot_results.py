# -*- coding: utf-8 -*-
"""Screenshot der Ergebnisseite nach abgeschlossener Pipeline."""
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

def click_and_wait(page, label, post_wait=10000, timeout=10000):
    try:
        page.click("button:has-text('{}')".format(label), timeout=timeout)
        print("  OK: " + label)
        page.wait_for_timeout(post_wait)
        return True
    except Exception as e:
        print("  MISS: '{}' -> {}".format(label, str(e)[:80]))
        return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # Login
    print("=== Login ===")
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    page.fill("input[type='text']",     USERNAME)
    page.fill("input[type='password']", PASSWORD)
    page.click("button:has-text('Login')")
    page.wait_for_timeout(5000)

    # Schritte 1-5 durchlaufen
    print("Schritt 1 -> 2")
    click_and_wait(page, "Weiter zu Nutzung & Flächen →", post_wait=10000)

    print("Schritt 2 -> 3")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Weiter zum Funktionsgraph →", post_wait=10000)

    print("Schritt 3 -> 4")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Weiter zum Regelwerk →", post_wait=10000)

    print("Schritt 4 -> 5")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Weiter zu Projektzielen →", post_wait=10000)

    print("Schritt 5: Layouts generieren")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Layouts generieren", post_wait=3000)

    # Warte bis Pipeline fertig (kein "Pipeline läuft..." mehr sichtbar)
    print("Warte auf Pipeline-Abschluss (max 3 Min)...")
    try:
        page.wait_for_function(
            "() => !document.body.innerText.includes('Pipeline läuft')",
            timeout=180000
        )
        print("  Pipeline abgeschlossen!")
    except Exception:
        print("  Timeout - Ergebnis trotzdem screenshot")

    page.wait_for_timeout(3000)

    # Screenshots
    save(page, "08_ergebnisse_fertig")
    page.screenshot(path="scripts/ss_08_ergebnisse_full.png", full_page=True)
    print("  saved: scripts/ss_08_ergebnisse_full.png")

    # Nach unten scrollen und nochmals
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(2000)
    save(page, "09_ergebnisse_unten")

    browser.close()

print("\nFertig.")
