r"""Capture UI screenshots of a running local app (dev tool). Uses the installed Microsoft Edge.
Usage: .venv\Scripts\python scripts\screenshots.py  (app must be running on 127.0.0.1:8501)"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8501"
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
PAGES = {"1_plan.png": "", "2_solar.png": "solar", "3_cable.png": "cable", "4_reports.png": "reports",
         "5_pf.png": "pf-correction", "6_settings.png": "settings"}

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    page = b.new_page(viewport={"width": 1400, "height": 2000})
    errors = 0
    for name, path in PAGES.items():
        page.goto(f"{BASE}/{path}")
        page.wait_for_selector("h1", timeout=30000)
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / name, full_page=True)
        errors += page.locator("[data-testid='stException']").count()
    b.close()
print("saved to", OUT, "| pages with exceptions:", errors)
