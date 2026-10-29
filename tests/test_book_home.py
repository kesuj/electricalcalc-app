"""📘 Book method tab (Home) and solar geometry - hand-checked values.

Kathmandu 27.7° N: noon sun on 21 Dec = 90 − 27.7 − 23.45 = 38.85°; equinox 90 − 27.7 = 62.3°;
21 Jun = 90 − |27.7 − 23.45| = 85.75°. 21 Dec 9 am (ω = −45°): sin α = 0.3894 -> α = 22.92°,
azimuth ≈ 44.8° east of south. Equinox day length = 12 h.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ecalc import config
from ecalc.calc.sun import (SOLSTICE_DEC, day_length_hours, declination, noon_altitude, solar_position, sun_path)

ROOT = Path(__file__).resolve().parent.parent


def test_declination_and_noon_heights():
    assert declination(SOLSTICE_DEC) == pytest.approx(-23.45, abs=0.01)
    assert noon_altitude(27.7, -23.45) == pytest.approx(38.85)
    assert noon_altitude(27.7, 0) == pytest.approx(62.3)
    assert noon_altitude(27.7, 23.45) == pytest.approx(85.75)


def test_solar_position_winter_9am():
    alt, az = solar_position(27.7, -23.45, -3)
    assert alt == pytest.approx(22.92, abs=0.02)
    assert az == pytest.approx(-44.8, abs=0.2)          # east of south in the morning
    alt_pm, az_pm = solar_position(27.7, -23.45, 3)
    assert alt_pm == pytest.approx(alt) and az_pm == pytest.approx(-az)


def test_day_length_and_path():
    assert day_length_hours(27.7, 0) == pytest.approx(12.0)
    assert day_length_hours(27.7, -23.45) < 12 < day_length_hours(27.7, 23.45)
    path = sun_path(27.7, SOLSTICE_DEC)
    assert all(p["Altitude"] > 0 for p in path)
    assert max(p["Altitude"] for p in path) == pytest.approx(38.85, abs=0.1)


@pytest.fixture
def temp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ecalc.db")
    return tmp_path


SCRIPT = '''
import sys, json
sys.path.insert(0, {root!r})
import streamlit as st
st.cache_resource.clear()
from ecalc.calc.home import HomeInputs, home_design
from ecalc.solar_data import parse_pvgis
import ui.book_home as bh
PV = json.load(open({fx!r}))
res = parse_pvgis(PV, 27.7172, 85.324)
bh.fetch_pvgis = lambda lat, lon, *a, **k: parse_pvgis(PV, lat, lon)
loads = [{{"name": "Fridge", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True}},
         {{"name": "LED", "power_w": 10, "qty": 8, "hours_per_day": 6, "critical": True}},
         {{"name": "Iron", "power_w": 1000, "qty": 1, "hours_per_day": 0.5}}]
x = HomeInputs(loads=loads, monthly_psh=res.monthly_irr_kwh_m2_day, mode="{mode}", outage_hours=4,
               temp_loss_pct=7.94, chemistry="{chem}", holdover_days=2)
r = home_design(x)
out = dict(result=r, inputs=x, mode="{mode}", lat=27.7172, lon=85.324, tilt=28.0, aspect=0.0, place="Kathmandu",
           monthly_psh=res.monthly_irr_kwh_m2_day, temp_loss_pct=7.94, res_details=res.details)
st.session_state["design_wh"] = r.out("design_wh")
bh.book_home_tab(out)
'''


@pytest.mark.parametrize("mode,chem", [("hybrid_backup", "LiFePO4 (lithium)"), ("off_grid", "Lead-acid tubular / traction"),
                                       ("grid_tied", "LiFePO4 (lithium)")])
def test_book_tab_renders_with_user_numbers(temp_data, mode, chem):
    script = SCRIPT.format(root=str(ROOT), fx=str(ROOT / "tests" / "fixtures" / "pvgis_kathmandu_1kwp.json"),
                           mode=mode, chem=chem)
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    design = at.session_state["design_wh"]
    assert any(f"= {design:,.0f} Wh/day" in c.value for c in at.code)       # user's number substituted
    assert any("Book formula (mm²)" in str(df.value.columns.tolist()) for df in at.dataframe)
    # load the 5-angle comparison (PVGIS mocked) and use the shading picker
    next(b for b in at.button if "Compare the 5 mounting angles" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    next(m for m in at.multiselect if m.label.startswith("Hours when")).set_value(["11 am-12", "12-1 pm"]).run()
    vals = [m.value for m in at.metric]
    assert "54 %" in vals and "28 %" in vals                                # 27+27 winter, 14+14 summer
