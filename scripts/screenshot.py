"""Screenshot der Streamlit-App via Playwright — mit Login."""
import sys
from playwright.sync_api import sync_playwright

url      = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
outfile  = sys.argv[2] if len(sys.argv) > 2 else "scripts/screenshot.png"
username = sys.argv[3] if len(sys.argv) > 3 else "admin"
password = sys.argv[4] if len(sys.argv) > 4 else "Admin2024!"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Fill login form
    try:
        page.fill("input[type='text']",     username)
        page.fill("input[type='password']", password)
        # Streamlit Authenticator uses a button with text "Login"
        page.click("button:has-text('Login')")
        print("Login button clicked")
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"Login step error: {e}")

    # Screenshot after login attempt
    page.screenshot(path=outfile, full_page=False)
    page.screenshot(path=outfile.replace(".png", "_full.png"), full_page=True)
    browser.close()

print(f"Screenshot saved: {outfile}")
