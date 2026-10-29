r"""Capture UI screenshots of a running local app (dev tool). Uses the installed Microsoft Edge.
Usage: .venv\Scripts\python scripts\screenshots.py  (app must be running on 127.0.0.1:8501)"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8501"
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)


def wait(page):
    page.wait_for_selector("h1", timeout=30000)
    page.wait_for_timeout(1500)


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    page = b.new_page(viewport={"width": 1400, "height": 2600})
    page.goto(BASE); wait(page)
    page.screenshot(path=OUT / "1_home.png", full_page=True)

    page.goto(f"{BASE}/solar"); wait(page)
    page.get_by_role("button", name="Get solar data from PVGIS").click()
    page.wait_for_selector("text=Specific yield", timeout=60000)
    page.get_by_role("button", name="Calculate").click()
    page.wait_for_selector("text=3. Results", timeout=30000); page.wait_for_timeout(1500)
    page.screenshot(path=OUT / "2_solar.png", full_page=True)

    page.goto(f"{BASE}/cable"); wait(page)
    page.screenshot(path=OUT / "3_cable.png", full_page=True)

    page.goto(f"{BASE}/reports"); wait(page)
    page.screenshot(path=OUT / "4_reports.png", full_page=True)

    page.goto(f"{BASE}/settings"); wait(page)
    page.screenshot(path=OUT / "5_settings.png", full_page=True)
    errs = page.locator("[data-testid='stException']").count()
    b.close()
print("saved to", OUT, "| exceptions on last page:", errs)
