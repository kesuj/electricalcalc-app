"""Load schedule and full-project workflow. Expected values calculated by hand:

Loads: LED 12 W x20 x6 h = 1.44 kWh; fans 75 W x6 x8 h = 3.6; fridge 150 W x1 x10 h = 1.5;
computers 120 W x4 x8 h = 3.84; pump 750 W x1 x1.5 h = 1.125  -> 11.505 kWh/day, 2.07 kW connected,
max demand @0.8 = 1.656 kW; critical (LED, fridge, computers) = 6.78 kWh/day, 0.87 kW.
Hybrid, PSH 5, 20 % losses: Y = 1460; kWp = 11.505*365/1460 = 2.876 -> 6 x 550 Wp = 3.3 kWp;
inverter 3.3/1.2 = 2.75 kW; battery nominal 6.78/0.8/0.95 = 8.921 kWh.
AC current 2750/230 = 11.957 A; 20 m @3 %: 1.5 mm2 gives 3.01 % (fail), 2.5 mm2 gives 1.84 % -> 2.5 mm2.
DC current 2750/(48*0.95) = 60.31 A; 3 m @1 %: 16 mm2 gives 1.04 % (fail), 25 mm2 gives 0.656 % -> 25 mm2.
"""

import pytest

from ecalc.calc import ValidationError
from ecalc.calc.loads import load_schedule
from ecalc.calc.solar import SolarResource
from ecalc.workflow import ProjectDesign, battery_dc_current, plain_summary, run_full_design, summary

LOADS = [
    {"name": "LED", "power_w": 12, "qty": 20, "hours_per_day": 6, "critical": True, "motor": False},
    {"name": "Fans", "power_w": 75, "qty": 6, "hours_per_day": 8, "critical": False, "motor": True},
    {"name": "Fridge", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True},
    {"name": "Computers", "power_w": 120, "qty": 4, "hours_per_day": 8, "critical": True, "motor": False},
    {"name": "Pump", "power_w": 750, "qty": 1, "hours_per_day": 1.5, "critical": False, "motor": True},
    {"name": "", "power_w": None, "qty": 1, "hours_per_day": None},  # blank editor row is ignored
]


def test_load_schedule_hand_calc():
    r = load_schedule(LOADS, 0.8)
    assert r.out("daily_kwh") == pytest.approx(11.505)
    assert r.out("connected_kw") == pytest.approx(2.07)
    assert r.out("max_demand_kw") == pytest.approx(1.656)
    assert r.out("critical_kwh") == pytest.approx(6.78)
    assert r.out("critical_kw") == pytest.approx(0.87)
    assert r.tables["Load schedule"][-1]["Load"] == "TOTAL"
    assert any("surge" in w for w in r.warnings)


@pytest.mark.parametrize("rows", [[], [{"name": "x", "power_w": -5, "qty": 1, "hours_per_day": 2}],
                                  [{"name": "x", "power_w": 100, "qty": 1, "hours_per_day": 30}],
                                  [{"name": "x", "power_w": 100, "qty": 1, "hours_per_day": None}]])
def test_load_schedule_invalid(rows):
    with pytest.raises(ValidationError):
        load_schedule(rows)


def _design(**kw):
    base = dict(resource=SolarResource.from_peak_sun_hours(5, 20), loads=LOADS, coincidence_factor=0.8,
                system_type="hybrid_battery", panel_wp=550, panel_area_m2=2.6, battery_voltage_v=48,
                battery_dod_pct=80, supply_phases=1, supply_voltage_v=230, ac_cable_length_m=20,
                ac_drop_limit_pct=3, dc_cable_length_m=3, dc_drop_limit_pct=1)
    base.update(kw)
    return ProjectDesign(**base)


def test_full_hybrid_design_hand_calc():
    res = run_full_design(_design())
    names = [r.name for r in res]
    assert names[0] == "Load schedule" and len(res) == 6
    pv, inv, ac, dci, dc = res[1], res[2], res[3], res[4], res[5]
    assert pv.out("panel_count") == 6 and pv.out("pv_kwp") == pytest.approx(3.3)
    assert pv.out("inverter_ac_kw") == pytest.approx(2.75)
    assert pv.out("battery_usable_kwh") == pytest.approx(6.78)       # from critical loads
    assert pv.out("battery_nominal_kwh") == pytest.approx(8.9211, rel=1e-4)
    assert inv.out("current_a") == pytest.approx(11.957, rel=1e-4)
    assert ac.out("min_size_mm2") == 2.5 and ac.out("voltage_drop_pct") == pytest.approx(1.843, rel=1e-3)
    assert dci.out("dc_current_a") == pytest.approx(60.307, rel=1e-4)
    assert dc.out("min_size_mm2") == 25 and dc.out("voltage_drop_pct") == pytest.approx(0.656, rel=1e-3)
    s = summary(res)
    assert "Battery" in s and "AC cable (VD only)" in s


def test_grid_tied_from_bill_three_phase():
    res = run_full_design(_design(loads=[], monthly_kwh=900, system_type="grid_tied", supply_phases=3,
                                  supply_voltage_v=400))
    assert [r.name.split(" ")[0] for r in res] == ["Solar", "Inverter", "Inverter-to-main-board"]
    daily = 900 * 12 / 365
    assert res[0].out("kwp_required") == pytest.approx(daily * 365 / 1460)


def test_design_requires_demand_and_backup():
    with pytest.raises(ValidationError, match="load list or the monthly"):
        run_full_design(_design(loads=[]))
    no_crit = [dict(r, critical=False) for r in LOADS]
    with pytest.raises(ValidationError, match="power cuts"):
        run_full_design(_design(loads=no_crit))


def test_battery_dc_current():
    assert battery_dc_current(5, 48, 95).out("dc_current_a") == pytest.approx(109.65, rel=1e-4)


def test_coincidence_factor_is_inverse_of_diversity_and_warns_for_small_lists():
    r = load_schedule(LOADS, 0.8)
    assert r.out("max_demand_kw") == pytest.approx(2.07 * 0.8)
    assert any("1.25" in a for a in r.assumptions)          # equivalent diversity factor 1/0.8
    assert any("undersize the inverter" in w for w in r.warnings)
    full = load_schedule(LOADS)                             # default 1.0: no undersizing warning
    assert full.out("max_demand_kw") == pytest.approx(2.07)
    assert not any("undersize" in w for w in full.warnings)


def test_cable_checks_skipped_when_length_not_entered():
    res = run_full_design(_design(ac_cable_length_m=None, dc_cable_length_m=None))
    names = [r.name for r in res]
    assert not any("cable (voltage-drop" in n for n in names)
    assert any("not checked" in w for r in res for w in r.warnings)
    with pytest.raises(ValidationError, match="AC voltage-drop limit"):
        run_full_design(_design(ac_drop_limit_pct=None))


def test_backup_from_outage_hours_with_load_list():
    # critical kW = 0.87 (LED 0.24 + fridge 0.15 + computers 0.48); 4 h cuts -> 3.48 kWh; nominal 3.48/0.8/0.95
    pv = run_full_design(_design(outage_hours=4))[1]
    assert pv.out("battery_usable_kwh") == pytest.approx(3.48)
    assert pv.out("battery_nominal_kwh") == pytest.approx(4.5789, rel=1e-4)


def test_backup_from_outage_hours_with_bill():
    # backup loads: 10 x 10 W + 150 W = 0.25 kW; 4 h -> 1.0 kWh usable; nominal 1.0/0.8/0.95 = 1.3158 kWh
    bl = [{"name": "LED bulb", "power_w": 10, "qty": 10}, {"name": "Fridge", "power_w": 150, "qty": 1}]
    res = run_full_design(_design(loads=[], monthly_kwh=300, outage_hours=4, backup_loads=bl))
    assert res[0].name.startswith("Backup loads") and res[0].out("connected_kw") == pytest.approx(0.25)
    pv = res[1]
    assert pv.out("battery_usable_kwh") == pytest.approx(1.0)
    assert pv.out("battery_nominal_kwh") == pytest.approx(1.3158, rel=1e-4)
    with pytest.raises(ValidationError, match="power cuts"):
        run_full_design(_design(loads=[], monthly_kwh=300, outage_hours=4, backup_loads=[]))


def test_plain_summary_uses_calculated_numbers():
    res = run_full_design(_design(tariff_per_kwh=12, cost_per_kwp=100000))
    text = " ".join(plain_summary(res))
    assert "6 solar panels" in text and "3.30 kW" in text and "8.9 kWh" in text
    assert "pay for itself" in text and "qualified electrical engineer" in text
