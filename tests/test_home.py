"""Home design (Boxwell method) - checked against the book's holiday-home worked example (§48-§89).

Book: 12 V DC loads 661 Wh/day (exact; book prints 662), peak 169 W; traction battery +5 % -> ~695 Wh;
London 38° tilt row, months Mar-Oct -> worst month Oct = 2.41 kWh/m²/day; MPPT 0.9 -> ~320 W;
cable (22 m, 14.08 A, 12 V) = 20.65 mm², 24 V = 5.16 mm², 48 V = 1.29 mm² (book misprints 1.63);
battery 695 Wh × 5 days ÷ 24 V ÷ 0.8 = 181 Ah.
This app divides by efficiencies (physically correct) where the book multiplies: 661/0.95 = 695.8 Wh.
"""
import json
from pathlib import Path

import pytest

from ecalc.calc import ValidationError
from ecalc.calc.home import HomeInputs, book_cable_mm2, home_design, lead_acid_cycles, power_analysis

LONDON_38 = [1.27, 2.04, 2.76, 3.67, 4.17, 4.20, 4.25, 4.16, 3.26, 2.41, 1.53, 1.05]
BOOK_LOADS = [("Living room light", 11, 5), ("Kitchen light", 11, 2), ("Hallway light", 8, 0.5),
              ("Bathroom light", 11, 1.5), ("Bedroom 1 light", 11, 1), ("Bedroom 2 light", 11, 1.5),
              ("Porch light", 8, 0.5), ("Small fridge", 12, 24), ("TV", 40, 4), ("Laptop", 40, 1),
              ("Phone charging", 5, 4), ("Phantom loads", 1, 24)]
LOADS = [{"name": n, "power_w": w, "qty": 1, "hours_per_day": h, "ac": False} for n, w, h in BOOK_LOADS]
MAR_OCT = list(range(3, 11))


def test_power_analysis_book_W1():
    pa = power_analysis(LOADS)
    assert pa["daily_wh"] == pytest.approx(661)
    assert pa["peak_w"] == pytest.approx(169)
    assert pa["dc_wh"] == pytest.approx(661) and pa["ac_wh"] == 0


def test_book_cable_formula_W8():
    assert book_cable_mm2(22, 169 / 12, 12) == pytest.approx(20.65, abs=0.01)
    assert book_cable_mm2(22, 169 / 24, 24) == pytest.approx(5.16, abs=0.01)
    assert book_cable_mm2(22, 169 / 48, 48) == pytest.approx(1.29, abs=0.01)   # book misprints 1.63


def test_off_grid_holiday_home_W2_W4_W5_W9():
    r = home_design(HomeInputs(loads=LOADS, monthly_psh=LONDON_38, mode="off_grid", months_required=MAR_OCT,
                               controller="MPPT", chemistry="Lead-acid tubular / traction", dod_pct=80,
                               holdover_days=5, system_voltage=24, panel_wp=80, panel_area_m2=0.6))
    assert r.out("design_wh") == pytest.approx(661 / 0.95)                         # 695.8 (book 695)
    assert r.out("design_psh") == pytest.approx(2.41)                              # worst required month = Oct
    assert r.out("array_w") == pytest.approx(661 / 0.95 / 2.41 / 0.9, rel=1e-6)    # 320.8 W (book 320)
    assert r.out("panel_count") == 5                                               # 320.8 W / 80 W rounds up
    assert r.out("battery_ah") == pytest.approx(661 / 0.95 * 5 / 24 / 0.8)         # 181.2 Ah (book 181.25)
    assert r.outputs["system_v"].value == 24
    assert r.out("battery_life_years") == pytest.approx(350 * 5 / 365)             # 350 cycles x 5 days


def test_pwm_needs_bigger_array_W5():
    a = home_design(HomeInputs(loads=LOADS, monthly_psh=LONDON_38, mode="off_grid", months_required=MAR_OCT,
                               controller="PWM", chemistry="Lead-acid tubular / traction", system_voltage=24))
    assert a.out("array_w") == pytest.approx(661 / 0.95 / 2.41 / 0.75, rel=1e-6)


def test_auto_voltage_uses_book_cable_rule():
    # 5 x 80 W = 400 W array, 22 m run: 12 V -> 33 A -> 24.4 mm² (> 6); 24 V -> 16.7 A -> 6.1 mm² (> 6);
    # 48 V -> 8.33 A -> 3.06 mm² -> 48 V chosen
    r = home_design(HomeInputs(loads=LOADS, monthly_psh=LONDON_38, mode="off_grid", months_required=MAR_OCT,
                               chemistry="Lead-acid tubular / traction", panel_wp=80, dc_cable_length_m=22))
    assert r.outputs["system_v"].value == 48
    assert r.out("dc_cable_mm2") == pytest.approx(22 * (400 / 48) * 0.04 / (48 / 20), rel=1e-6)


def test_hybrid_backup_nepal_outage_mode():
    # backup: fridge 150 W + 8 x 10 W LED (AC) = 230 W, 4 h cut, inverter 93 %, LiFePO4 eff 95 %, DoD 90 %
    loads = [{"name": "Fridge", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True},
             {"name": "LED", "power_w": 10, "qty": 8, "hours_per_day": 6, "critical": True},
             {"name": "Iron", "power_w": 1000, "qty": 1, "hours_per_day": 0.5}]
    r = home_design(HomeInputs(loads=loads, monthly_psh=[5.56] * 12, mode="hybrid_backup", outage_hours=4,
                               system_voltage=48))
    usable = 230 / 0.93 * 4 / 0.95
    assert r.out("battery_usable_wh") == pytest.approx(usable)
    assert r.out("battery_ah") == pytest.approx(usable / 48 / 0.9)
    # array 2480/0.93/5.56/0.9 = 533 W -> 1 x 550 W panel -> inverter = max(230 x 4/3, 550/1.2) = 458 W
    assert r.out("inverter_w") == pytest.approx(max(230 * 4 / 3, 550 / 1.2))
    assert any("surge" in w for w in r.warnings)
    # daily 1500 + 480 + 500 = 2480 Wh AC -> design 2480/0.93; annual-average sun 5.56
    assert r.out("array_w") == pytest.approx(2480 / 0.93 / 5.56 / 0.9)


def test_grid_tied_uses_annual_average_and_monthly_table():
    fx = json.loads((Path(__file__).parent / "fixtures" / "pvgis_kathmandu_1kwp.json").read_text())
    psh = [m["H(i)_d"] for m in fx["outputs"]["monthly"]["fixed"]]
    loads = [{"name": "House", "power_w": 1000, "qty": 1, "hours_per_day": 10}]
    r = home_design(HomeInputs(loads=loads, monthly_psh=psh, mode="grid_tied", temp_loss_pct=7.94))
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    avg = sum(p * d for p, d in zip(psh, days)) / 365
    assert r.out("design_psh") == pytest.approx(avg)
    assert r.out("array_w") == pytest.approx(10000 / 0.93 / avg / (0.9 * (1 - 0.0794)))
    assert len(r.tables["Monthly generation vs use"]) == 12
    assert "battery_ah" not in r.outputs


def test_lead_acid_cycle_table_interpolation():
    assert lead_acid_cycles(50) == 1000 and lead_acid_cycles(80) == 350
    assert lead_acid_cycles(65) == pytest.approx(675)


@pytest.mark.parametrize("bad", [dict(mode="island"), dict(monthly_psh=[5] * 11), dict(months_required=[])])
def test_invalid(bad):
    base = dict(loads=LOADS, monthly_psh=LONDON_38)
    base.update(bad)
    with pytest.raises(ValidationError):
        home_design(HomeInputs(**base))


def test_hybrid_requires_backup_loads():
    with pytest.raises(ValidationError, match="power cuts"):
        home_design(HomeInputs(loads=[{"name": "TV", "power_w": 60, "qty": 1, "hours_per_day": 4}],
                               monthly_psh=[5] * 12, mode="hybrid_backup"))


def test_roof_too_small_warns():
    r = home_design(HomeInputs(loads=[{"name": "House", "power_w": 1000, "qty": 1, "hours_per_day": 10}],
                               monthly_psh=[5.0] * 12, available_area_m2=5, panel_area_m2=2.58))
    assert "Only about 1 panel fit" in r.warnings[0]
