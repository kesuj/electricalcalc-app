"""Solar farm page - headless run with the bundled Kathmandu PVGIS response (no network).

Hand checks (Kathmandu, 10 MWp, record low -3.5 °C, default 550 Wp module / 330 kVA 1500 V inverter):
  sun hours = Σ H(i)_d × days / 365 from the fixture; PR = Π(1 − loss) with PVGIS temperature 7.94 % and
  reflection 2.57 % plus the default losses; energy = 10 × sun hours × 365 × PR.
  Voc(-3.5) = 49.5 + (-0.0025 × 49.5)(-28.5) = 53.027 V; × 1.05 = 55.68 → 1500/55.68 = 26.9 → 26 per string
  Vmp(70) = 41.6 − 0.0029 × 41.6 × 45 = 36.17; × 0.98 × 0.9 = 31.90 → 500/31.90 = 15.7 → min 16
  strings = floor(390/14) = 27; DC per inverter = 26 × 27 × 0.55 = 386.1 kW; inverters = ceil(10000/386.1) = 26
"""
import json
import math
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ecalc import config, solar_data
from ecalc.calc.farm import DEFAULT_LOSSES, performance_ratio
from ecalc.solar_data import parse_pvgis
from ecalc.storage import Store

ROOT = Path(__file__).resolve().parent.parent
FIX = json.loads((Path(__file__).parent / "fixtures" / "pvgis_kathmandu_1kwp.json").read_text())
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


@pytest.fixture(autouse=True)
def temp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ecalc.db")
    monkeypatch.setattr(solar_data, "fetch_pvgis", lambda lat, lon, *a, **k: parse_pvgis(FIX, lat, lon))
    return tmp_path


def _app() -> AppTest:
    script = (f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
              "import streamlit as st\nst.cache_resource.clear()\nfrom ui.farm import farm\nfarm()\n")
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    return at


def _by(items, label):
    return next(x for x in items if x.label == label)


def _metric(at, label):
    return _by(at.metric, label).value


def test_farm_page_renders_empty():
    at = _app()
    assert not at.exception, [e.value for e in at.exception]
    _by(at.button, "Calculate the solar farm").click().run()
    msg = at.error[0].value
    for q in ("Project name", "Nearest place", "Plant size"):
        assert q in msg


def test_farm_full_run_hand_checked(temp_data):
    at = _app()
    _by(at.text_input, "Project name *").set_value("Test 10 MW")
    _by(at.selectbox, "Nearest place *").set_value("Kathmandu - Bagmati Province").run()
    assert _by(at.number_input, "Record low temperature (°C)").value == -3.5     # pre-filled from DHM table
    _by(at.number_input, "Plant size (MWp of panels) *").set_value(10.0)
    _by(at.button, "Calculate the solar farm").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]

    psh = sum(m["H(i)_d"] * d for m, d in zip(FIX["outputs"]["monthly"]["fixed"], DAYS)) / 365
    losses = dict(DEFAULT_LOSSES, **{"Temperature": 7.94, "Reflection (angle of incidence)": 2.57})
    pr = performance_ratio(losses)
    mwh = 10 * psh * 365 * pr
    assert _metric(at, "Energy per year (P50)") == f"{mwh:,.0f} MWh"
    assert _metric(at, "Performance ratio") == f"{pr:.3f}"
    assert _metric(at, "Energy per year (P90)") == f"{mwh * (1 - 1.282 * 0.05):,.0f} MWh"
    # strings & inverters
    assert _metric(at, "Chosen modules per string") == "26 modules"
    assert _metric(at, "Strings per inverter (after power check)") == "27 strings"
    assert _metric(at, "Number of inverters") == f"{math.ceil(10000 / (26 * 27 * 0.55))} inverters"
    # money: build cost 10 MW × Rs 65,000/kW = Rs 65 crore
    assert _metric(at, "Build cost") == "Rs 65.0 crore"
    # report + save
    _by(at.button, "💾 Save to My projects").click().run()
    assert not at.exception
    projects = Store(temp_data / "ecalc.db").list_projects()
    assert projects and projects[0]["name"] == "Test 10 MW" and projects[0]["n_calcs"] == 3


def test_unsafe_inverter_is_flagged():
    at = _app()
    _by(at.text_input, "Project name *").set_value("Cold site")
    _by(at.selectbox, "Nearest place *").set_value("Jumla - Karnali Province").run()
    _by(at.number_input, "Plant size (MWp of panels) *").set_value(5.0)
    _by(at.number_input, "Max DC voltage (V)").set_value(1000.0)
    _by(at.number_input, "MPPT max (V)").set_value(1000.0)
    _by(at.number_input, "MPPT min (V)").set_value(900.0)
    _by(at.button, "Calculate the solar farm").click().run()
    assert not at.exception, [e.value for e in at.exception]
    # Jumla -15 °C: Voc = 49.5 × (1 + 0.0025 × 40) = 54.45 V × 1.05 → max 17; min ceil(900/31.90) = 29 → unsafe
    assert any("does not give a safe string length" in e.value for e in at.error)
