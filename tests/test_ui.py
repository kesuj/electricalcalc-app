"""Headless smoke test: every page renders without exceptions (Streamlit AppTest).
Each test uses a temporary data directory so the real database is never touched."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ecalc import config
from ecalc.storage import Store

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["solar", "pf_page", "cable", "report_page", "assistant", "docs", "settings", "usage", "help_page"]


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
    at = _app("report_page")
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
    """User types: 1-phase 230 V, 20 A, 30 m, copper 4 mm2 at 70 C, PF 1.0 -> hand calc 2.878 %."""
    at = _app("cable")
    at.run()
    assert any("Still empty" in i.value for i in at.info)      # nothing pre-filled, no result yet
    _by_label(at.selectbox, "System *").set_value("single_phase")
    _by_label(at.number_input, "Nominal voltage (V) *").set_value(230.0)
    _by_label(at.number_input, "Design current (A) *").set_value(20.0)
    _by_label(at.number_input, "One-way route length (m) *").set_value(30.0)
    _by_label(at.selectbox, "Conductor *").set_value("copper").run()
    _by_label(at.number_input, "Conductor temperature (°C) *").set_value(70.0)
    _by_label(at.number_input, "Power factor *").set_value(1.0)
    _by_label(at.selectbox, "Conductor size (mm²) *").set_value(4).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("2.878" in m.value for m in at.metric), [m.value for m in at.metric]


def test_public_demo_disables_uploads(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DEMO", True)
    at = _app("docs")
    at.run()
    assert not at.exception
    assert len(at.get("file_uploader")) == 0
    assert any("disabled" in i.value for i in at.info)


def _design_app():
    """Home page with PVGIS replaced by the saved Kathmandu responses (no network in tests)."""
    fx = ROOT / "tests" / "fixtures"
    script = (f"import sys, json\nsys.path.insert(0, {str(ROOT)!r})\n"
              "import streamlit as st\nst.cache_resource.clear()\n"
              "import ui.design as d\nfrom ecalc.solar_data import parse_pvgis\nfrom ecalc.profile import parse_drcalc\n"
              f"PV = json.load(open({str(fx / 'pvgis_kathmandu_1kwp.json')!r}))\n"
              f"DR = json.load(open({str(fx / 'pvgis_drcalc_kathmandu.json')!r}))\n"
              "d.fetch_pvgis = lambda lat, lon, *a, **k: parse_pvgis(PV, lat, lon)\n"
              "d.fetch_daily_profiles = lambda *a, **k: parse_drcalc(DR)\n"
              "d.design()\n")
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    return at


def _by_label(items, label):
    return next(x for x in items if x.label == label)


def _add_appliance(at, item, qty, hours=None, critical=False):
    _by_label(at.selectbox, "Appliance").set_value(item)
    _by_label(at.number_input, "How many?").set_value(qty)
    if hours is not None:
        _by_label(at.number_input, "Hours ON per day").set_value(hours)
    if critical:
        _by_label(at.checkbox, "Needed during power cuts").check()
    _by_label(at.button, "➕ Add to list").click().run()


def _common_answers(at, mode):
    _by_label(at.text_input, "Project name *").set_value("Test house")
    _by_label(at.selectbox, "Nearest place in Nepal *").set_value("Kathmandu - Bagmati Province")
    _by_label(at.radio, "What kind of roof? *").set_value("Flat roof - panels go on a metal frame")
    _by_label(at.radio, "Choose one *").set_value(mode).run()


def _install_answers(at, battery=True):
    _by_label(at.number_input, "Panels → inverter cable route (m) *").set_value(15.0)
    _by_label(at.number_input, "Inverter → main switchboard (m) *").set_value(8.0)
    if battery:
        _by_label(at.number_input, "Battery → inverter (m) *").set_value(2.0)
    _by_label(at.radio, "Where will the inverter be mounted? *").set_value("Indoors (dry, ventilated wall)")


def test_home_hybrid_with_bill_and_backup(temp_data):
    """Bill 250 units + backup fridge (150 W) & 8 LED (80 W) for 4 h -> battery usable 230/0.94*4/0.95 = 1.030 kWh."""
    at = _design_app()
    assert not at.exception, [e.value for e in at.exception]
    _common_answers(at, "Hybrid - lower my bill AND keep power during load-shedding")
    next(r for r in at.radio if r.key == "h_how").set_value("I have my NEA bill").run()
    _by_label(at.number_input, "Units used per month (kWh) *").set_value(250.0)
    _by_label(at.number_input, "Longest power cut on a normal day (hours) *").set_value(4.0).run()
    _add_appliance(at, "Refrigerator", 1)
    _add_appliance(at, "LED bulb", 8)
    _by_label(at.selectbox, "Your NEA meter *").set_value("Single-phase 15 A (most homes)")
    _install_answers(at)
    _by_label(at.button, "Calculate my solar system").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    text = at.success[0].value
    assert "solar panel" in text and "Battery:" in text and "NEA bill" in text
    inv_kw = at.session_state["home_out"]["inverter_kw"]
    assert inv_kw >= at.session_state["home_out"]["kwp"] / 1.2 - 1e-9     # hybrid inverter carries the whole array
    projects = Store(temp_data / "ecalc.db").list_projects()
    assert projects[0]["name"] == "Test house"
    out = at.session_state["home_out"]
    assert out["battery_usable_kwh"] == pytest.approx(230 / 0.94 * 4 / 0.95 / 1000, rel=1e-6)
    # recalculating the same project updates it instead of duplicating
    _by_label(at.button, "Calculate my solar system").click().run()
    assert len(Store(temp_data / "ecalc.db").list_projects()) == 1


def test_home_off_grid_with_appliances(temp_data):
    at = _design_app()
    _common_answers(at, "Off-grid - no NEA connection at the site")
    _add_appliance(at, "LED bulb", 6, 5.0)
    _add_appliance(at, "Laptop", 1, 4.0)
    _by_label(at.number_input, "Days the battery must last without sun *").set_value(2.0)
    _install_answers(at)
    _by_label(at.button, "Calculate my solar system").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert at.session_state["home_out"]["mode"] == "off_grid"
    pkg = at.session_state["home_out"]["pkg"]
    items = " ".join(r["Item"] for r in pkg.bom)
    for must in ("PV module", "attery", "harge controller", "nverter", "arth"):
        assert must in items, must
    titles = [e.label for e in at.expander]
    assert any("What to buy" in t for t in titles) and any("Step-by-step installation" in t for t in titles)
    assert not any("NEA" in r["Item"] and "meter" in r["Item"].lower() for r in pkg.bom)   # off-grid: no NEA meter


def test_home_lists_unanswered_questions():
    at = _design_app()
    _by_label(at.button, "Calculate my solar system").click().run()
    msg = at.error[0].value
    for q in ("Project name", "Nearest place", "Kind of roof", "System type", "Electricity use"):
        assert q in msg


def test_pf_page_meter_mode_shows_hand_calc():
    """User types 100 kW, 20000 kWh, 15000 kVArh -> PF 0.8; target 0.95 -> 42.13 kvar."""
    at = _app("pf_page")
    at.run()
    assert not at.exception and any("Still empty" in i.value for i in at.info)
    _by_label(at.number_input, "Maximum demand (kW) *").set_value(100.0)
    _by_label(at.number_input, "Active energy in the period (kWh) *").set_value(20000.0)
    _by_label(at.number_input, "Reactive energy in the period (kVArh) *").set_value(15000.0)
    _by_label(at.number_input, "Target PF *").set_value(0.95).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("0.800" in c.value for c in at.caption)
    assert any("42.13" in m.value for m in at.metric), [m.value for m in at.metric]


def test_solar_page_empty_then_hand_calc():
    """Peak sun hours 5, 20 % losses, 10 kWh/day, 550 Wp -> Y 1460, 2.5 kWp needed, 5 panels (hand calc)."""
    at = _app("solar")
    at.run()
    _by_label(at.button, "Calculate").click().run()
    assert "Please fill in" in at.error[0].value
    _by_label(at.radio, "Sunshine data *").set_value("Enter peak sun hours").run()
    _by_label(at.number_input, "Peak sun hours (kWh/m²/day) *").set_value(5.0)
    _by_label(at.number_input, "Total losses (%) - includes temperature *").set_value(20.0)
    _by_label(at.number_input, "Consumption (kWh/day) *").set_value(10.0)
    _by_label(at.radio, "System type *").set_value("Grid-tied")
    _by_label(at.number_input, "Cover % of consumption *").set_value(100.0)
    _by_label(at.number_input, "Panel rating (Wp) *").set_value(550.0)
    _by_label(at.number_input, "Panel area (m²) *").set_value(2.6)
    _by_label(at.number_input, "DC/AC ratio *").set_value(1.2)
    _by_label(at.button, "Calculate").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    vals = [m.value for m in at.metric]
    assert "5 panels" in vals and any(v.startswith("2.75") for v in vals), vals
