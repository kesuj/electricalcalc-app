"""Book-method tab (Solar Farms): I-V model hand checks, helper maths and a headless render.

Book example (pp.113-116): 300 Wp module (Vmp 32, Imp 9.46, Voc 39.5, Isc 10, β_Voc −0.31, γ_Pmax −0.42),
SMA 900CP (1000 V, MPPT 596-850 V, 1400 A, 9 inputs), T_min 5 °C, T_cell,max 70 °C ->
Voc@5 °C = 41.95 V (book misprints 40.69), N_max (5 %) = 22, N_min (0.98 × 0.9) = 27 -> infeasible.
"""
import math
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ecalc.calc.iv import array_curve, iv_curve, module_at_temperature
from ecalc.calc.farm import Inverter, Module, book_string_design
from ui.book_farm import (insulation_row, noon_capture, step_status, string_fuse, string_voltage_drop,
                          voltage_ladder)

ROOT = Path(__file__).resolve().parent.parent
MOD = Module(wp=300, vmp=32.0, imp=9.46, voc=39.5, isc=10.0, beta_voc_pct=-0.31, gamma_pmax_pct=-0.42)
INV = Inverter(ac_kva=990, max_dc_kw=1010, v_dc_max=1000, v_mppt_min=596, v_mppt_max=850, i_dc_max=1400, dc_inputs=9)


def test_iv_curve_passes_datasheet_points():
    pts = iv_curve(isc=10.0, voc=39.5, imp=9.46, vmp=32.0, points=395)
    assert pts[0] == (0.0, pytest.approx(10.0))                       # Isc at V = 0
    v, i = min(pts, key=lambda p: abs(p[0] - 32.0))
    assert v == pytest.approx(32.0) and i == pytest.approx(9.46, rel=1e-3)   # (Vmp, Imp)
    assert pts[-1] == (pytest.approx(39.5), 0.0)                      # 0 A at Voc
    currents = [c for _, c in pts]
    assert all(a >= b for a, b in zip(currents, currents[1:]))        # monotonic


def test_temperature_and_array_scaling():
    m = module_at_temperature(39.5, 32.0, 10.0, 9.46, -0.31, -0.42, 5)
    assert m["voc"] == pytest.approx(41.949, abs=1e-3)
    assert m["vmp"] == pytest.approx(34.688, abs=1e-3)
    arr = array_curve([(10.0, 2.0)], 24, 140)
    assert arr == [(240.0, 280.0)]


def test_voltage_ladder_book_example():
    lad = voltage_ladder(MOD, INV, 5, 70)
    assert lad["voc_cold"] == pytest.approx(41.949, abs=1e-3)
    assert lad["voc_cold_margin"] == pytest.approx(44.046, abs=1e-3)
    assert lad["vmp_hot_margin"] == pytest.approx(25.952 * 0.98 * 0.9, abs=1e-3)
    assert lad["n_max"] == 22 and lad["n_min"] == 27


def test_noon_capture_and_tables():
    cap = noon_capture(27.7, 27.7)                       # tilt = latitude -> equinox sun hits square-on
    assert cap["Equinox (21 Mar / 23 Sep)"] == pytest.approx(1.0)
    assert cap["Winter solstice (21 Dec)"] == pytest.approx(math.cos(math.radians(23.45)))
    assert insulation_row(100) == 0 and insulation_row(300) == 1 and insulation_row(1200) == 2
    vd = string_voltage_drop(100, 9.46, 24, 32.0, 4.0)
    assert vd["vdrop_v"] == pytest.approx(2 * 100 * 9.46 * 0.0183 / 4)      # 8.656 V
    assert vd["vdrop_pct"] == pytest.approx(8.6559 / 768 * 100, rel=1e-3)
    assert string_fuse(10.0) == 15                       # 1.5 x 10 <= 15 <= 24


def test_step_status_infeasible_book_example():
    steps = step_status(book_string_design(MOD, INV, 5, 70))
    assert [ok for _, _, ok in steps] == [True, False, True, False, False]


def _script() -> str:
    return (f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
            "from ecalc.calc.farm import FarmInputs, Inverter, Module, book_string_design, farm_design, DEFAULT_LOSSES\n"
            "from ecalc.finance import cash_flow\nfrom ui.book_farm import book_farm_tab\n"
            "INV_V = __INV__\n"
            "mod = Module(wp=300, vmp=32.0, imp=9.46, voc=39.5, isc=10.0, beta_voc_pct=-0.31, gamma_pmax_pct=-0.42)\n"
            "inv = Inverter(ac_kva=990, max_dc_kw=1010, v_dc_max=INV_V, v_mppt_min=596, v_mppt_max=min(850, INV_V), "
            "i_dc_max=1400, dc_inputs=9)\n"
            "sr = book_string_design(mod, inv, t_cell_min=5, t_cell_max=70)\n"
            "fr = farm_design(FarmInputs(capacity_mwp=100, latitude=27.7, annual_psh=4.5, tilt_deg=27.7))\n"
            "cf = cash_flow(100e3 * 65000, fr.out('annual_mwh') * 1000, 5.3, years=25, om_per_year=6.5e7)\n"
            "out = {'name': 'Test', 'location': 'Kathmandu', 'lat': 27.7, 'mwp': 100, 'tmin': 5, 'tilt0': 27.7}\n"
            "book_farm_tab(out, fr, sr, mod, inv, dict(DEFAULT_LOSSES), cf, shade_free_hours=3)\n")


def _text(at) -> str:
    return " ".join(m.value for m in at.markdown) + " ".join(e.value for e in at.error)


def test_tab_renders_book_example_infeasible():
    at = AppTest.from_string(_script().replace("__INV__", "1000"), default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    text = _text(at)
    assert "41.95 V" in text and "**22**" in text and "**27**" in text
    assert any("Unsafe" in e.value or "cannot be completed" in e.value for e in at.error)


def test_tab_renders_feasible_1500v():
    at = AppTest.from_string(_script().replace("__INV__", "1500"), default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    text = _text(at)
    assert "Step 4 - power check" in text and not at.error
    assert "9 × 11" in text                          # 99 strings over 9 inputs
