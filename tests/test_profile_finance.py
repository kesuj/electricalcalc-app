"""Hourly simulation and finance - expected values worked by hand."""

import json
from pathlib import Path

import pytest

from ecalc.calc import ValidationError
from ecalc.finance import cash_flow
from ecalc.profile import LOAD_SHAPES, parse_drcalc, shape_kw, simulate_day

FIX = Path(__file__).parent / "fixtures" / "pvgis_drcalc_kathmandu.json"


def test_parse_drcalc_shifts_to_nepal_time():
    prof = parse_drcalc(json.loads(FIX.read_text()))
    assert sorted(prof) == list(range(1, 13)) and all(len(v) == 24 for v in prof.values())
    jan = prof[1]
    peak_hour = max(range(24), key=lambda h: jan[h])
    assert 11 <= peak_hour <= 13          # solar noon in Kathmandu ~12:15 NPT
    assert jan[0] == 0 and jan[23] == 0   # dark at midnight local time


def test_load_shapes_conserve_energy():
    for name in LOAD_SHAPES:
        assert sum(shape_kw(10, name)) == pytest.approx(10)


def test_simulate_day_energy_balance_hand_case():
    # Square sun: 1000 W/m2 for hours 10-13 (4 h). 1 kWp, 4 kWh/kWp/day -> 1 kW for 4 h.
    g = [0] * 24
    for h in range(10, 14):
        g[h] = 1000
    load = [0.5] * 24                       # 12 kWh/day
    d = simulate_day(g, 1.0, 4.0, load, outage_start=18, outage_hours=4, battery_usable_kwh=3.0, critical_kw=0.5)
    assert d.totals["pv_kwh"] == pytest.approx(4.0)
    # PV hours: 0.5 kW surplus x 4 h = 2 kWh -> battery already full -> exported
    assert d.totals["export_kwh"] == pytest.approx(2.0)
    # outage 18-21: 0.5 kW x 4 h = 2 kWh from a 3 kWh battery -> nothing unserved, 1 kWh left
    assert d.totals["unserved_kwh"] == pytest.approx(0.0)
    assert d.soc_kwh[21] == pytest.approx(1.0)
    # grid supplies the other 16 non-PV, non-outage hours: 16 x 0.5 = 8 kWh
    assert d.totals["import_kwh"] == pytest.approx(8.0)


def test_simulate_day_battery_too_small():
    g = [0] * 24
    load = [1.0] * 24
    d = simulate_day(g, 1.0, 0.0, load, outage_start=19, outage_hours=3, battery_usable_kwh=1.0)
    assert d.totals["unserved_kwh"] == pytest.approx(2.0)   # 3 kWh needed, 1 kWh available


def test_simulate_validation():
    with pytest.raises(ValidationError):
        simulate_day([0] * 23, 1, 1, [0] * 24)


def test_cash_flow_hand_case():
    # capex 100,000; 1,000 kWh x 20/kWh = 20,000/yr, no degradation/escalation/O&M -> payback 5.0 y
    cf = cash_flow(100_000, 1000, 20, years=10, degradation_pct=0, discount_rate_pct=0)
    assert cf.simple_payback_years == pytest.approx(5.0)
    assert cf.npv == pytest.approx(100_000)                   # 10 x 20,000 - 100,000 at r = 0
    assert cf.lcoe == pytest.approx(10.0)                     # 100,000 / 10,000 kWh
    # IRR for -100k then 10 x 20k is 15.10 % (annuity factor 5.0 at 15.10 %)
    assert cash_flow(100_000, 1000, 20, years=10, degradation_pct=0).irr_pct == pytest.approx(15.10, abs=0.02)


def test_cash_flow_discounting_and_degradation():
    cf = cash_flow(100_000, 1000, 20, years=2, degradation_pct=5, discount_rate_pct=10)
    # year 2 energy 950 kWh; discounted energy = 1000/1.1 + 950/1.21 = 909.09 + 785.12 = 1694.21
    assert cf.rows[1]["Energy (kWh)"] == 950
    assert cf.lcoe == pytest.approx(100_000 / 1694.21, rel=1e-4)
    assert cf.simple_payback_years is None                    # ~38k income never repays 100k in 2 years


def test_negative_escalation_allowed():
    cf = cash_flow(100_000, 1000, 20, years=2, degradation_pct=0, price_escalation_pct=-10, discount_rate_pct=0)
    assert cf.rows[1]["Income"] == 18000


def test_grid_tied_pv_off_during_outage():
    g = [0] * 24
    for h in range(10, 14):
        g[h] = 1000
    d = simulate_day(g, 1.0, 4.0, [0.5] * 24, outage_start=10, outage_hours=2, pv_in_outage=False)
    assert d.pv_kw[10] == 0 and d.pv_kw[11] == 0 and d.pv_kw[12] == pytest.approx(1.0)
    assert d.totals["unserved_kwh"] == pytest.approx(1.0)        # 2 h x 0.5 kW with no grid and no PV
