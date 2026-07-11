# -*- coding: utf-8 -*-
"""Vollstaendiger App-Durchlauf: Login -> alle Schritte -> Ergebnisse."""
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

def click_and_wait(page, label, post_wait=8000, timeout=10000):
    """Click button, then wait for Streamlit to rerender."""
    try:
        page.click("button:has-text('{}')".format(label), timeout=timeout)
        print("  OK: " + label)
        page.wait_for_timeout(post_wait)
        return True
    except Exception as e:
        print("  MISS: '{}' -> {}".format(label, str(e)[:100]))
        return False

def wait_for_step(page, step_num, timeout=15000):
    """Wait until sidebar shows step_num as active (triangle marker)."""
    try:
        # Wait for the sidebar step to show the arrow/active state
        page.wait_for_function(
            "() => document.body.innerText.includes('Schritt {}: ')".format(step_num),
            timeout=timeout
        )
        print("  On step {}".format(step_num))
        return True
    except Exception:
        print("  (step {} indicator timeout)".format(step_num))
        return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # ── Login ──────────────────────────────────────────────────────────────────
    print("=== Login ===")
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    page.fill("input[type='text']",     USERNAME)
    page.fill("input[type='password']", PASSWORD)
    page.click("button:has-text('Login')")
    page.wait_for_timeout(5000)
    save(page, "01_home")

    # ── Schritt 1 ─────────────────────────────────────────────────────────────
    print("\n=== Schritt 1: Grundstueck ===")
    save(page, "02_schritt1")
    click_and_wait(page, "Weiter zu Nutzung & Flächen →", post_wait=10000)
    save(page, "03_schritt2_eingabe")

    # ── Schritt 2 ─────────────────────────────────────────────────────────────
    print("\n=== Schritt 2: Eingabe ===")
    # Scroll to bottom to ensure button is visible
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Weiter zum Funktionsgraph →", post_wait=10000)
    save(page, "04_schritt3_funktionsgraph")

    # ── Schritt 3 ─────────────────────────────────────────────────────────────
    print("\n=== Schritt 3: Funktionsgraph ===")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Weiter zum Regelwerk →", post_wait=10000)
    save(page, "05_schritt4_regelwerk")

    # ── Schritt 4 ─────────────────────────────────────────────────────────────
    print("\n=== Schritt 4: Regelwerk ===")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Weiter zu Projektzielen →", post_wait=10000)
    save(page, "06_schritt5_projektziele")

    # ── Schritt 5: Generieren ─────────────────────────────────────────────────
    print("\n=== Schritt 5: Layouts generieren ===")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1000)
    click_and_wait(page, "Layouts generieren", post_wait=5000, timeout=10000)
    print("  Warte auf Pipeline (90s)...")
    page.wait_for_timeout(90000)
    save(page, "07_ergebnisse")
    page.screenshot(path="scripts/ss_07_ergebnisse_full.png", full_page=True)
    print("  saved: scripts/ss_07_ergebnisse_full.png")

    browser.close()

print("\nFertig.")
