"""Headless smoke test: every page renders without exceptions (Streamlit AppTest).
Each test uses a temporary data directory so the real database is never touched."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ecalc import config
from ecalc.storage import Store

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["home", "solar", "electrical", "cable", "report_page", "assistant", "docs", "settings", "usage", "help_page"]


def _app(page: str) -> AppTest:
    script = (f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
              "import streamlit as st\nst.cache_resource.clear()\n"
              f"from ui import pages\npages.{page}()\n")
    return AppTest.from_string(script, default_timeout=60)


@pytest.fixture(autouse=True)
def temp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ecalc.db")
    return tmp_path


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    at = _app(page)
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_demo_project_flow(temp_data):
    at = _app("home")
    at.run()
    next(b for b in at.button if "demonstration" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    projects = Store(temp_data / "ecalc.db").list_projects()
    assert projects and projects[0]["is_demo"] and projects[0]["n_calcs"] == 3
    # The reports page must render with the demo project and offer the PDF download
    at = _app("report_page")
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_cable_page_shows_hand_calc_value():
    at = _app("cable")
    at.run()
    # defaults: 1-phase 230 V, 20 A, 30 m, 4 mm2 Cu at 70 C; with PF = 1.0 the hand calc gives 2.878 %
    next(n for n in at.number_input if n.label == "Power factor").set_value(1.0).run()
    assert any("2.878" in m.value for m in at.metric), [m.value for m in at.metric]


def test_public_demo_disables_uploads(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DEMO", True)
    at = _app("docs")
    at.run()
    assert not at.exception
    assert len(at.get("file_uploader")) == 0
    assert any("disabled" in i.value for i in at.info)


def test_design_page_full_run_with_user_loads(temp_data):
    """Enter a project through the real page (peak-sun-hours mode, no network) and get all results + report."""
    script = (f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
              "import streamlit as st\nst.cache_resource.clear()\n"
              "from ui.design import design\ndesign()\n")
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.text_input[0].set_value("Test clinic")
    next(r for r in at.radio if r.label == "Solar data").set_value("I know the peak sun hours")
    at.run()
    next(b for b in at.button if b.label == "Fill example loads").click().run()
    next(r for r in at.radio if r.label == "System type").set_value("Hybrid (with battery backup)").run()
    next(b for b in at.button if b.label == "Calculate everything").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    labels = [m.label for m in at.metric]
    for k in ("Daily energy", "PV array", "Inverter", "Battery", "AC cable (VD only)", "Battery cable (VD only)"):
        assert k in labels, labels
    projects = Store(temp_data / "ecalc.db").list_projects()
    assert projects[0]["name"] == "Test clinic" and projects[0]["n_calcs"] == 6
