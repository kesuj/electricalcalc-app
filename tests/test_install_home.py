"""Home installation package - hand-checked numbers.

Module defaults: Voc 49.5, Vmp 41.6, Isc 14, Imp 13.2, beta -0.25 %/°C, NOCT 45. Kathmandu -3.5 / 36.6 °C:
  Voc cold = 49.5 × (1 + 0.0025 × 28.5) = 53.027 V;  Vmp cold = 44.564 V
  T_cell,max = 36.6 + 31.25 = 67.85 °C;  Vmp hot = 41.6 × (1 − 0.0025 × 42.85) = 37.144 V
Hybrid (500 V, MPPT 125-425 V, 18 A/MPPT): N_max = floor(min(9.43, 9.54)) = 9, N_min = ceil(3.37) = 4
"""
import pytest

from ecalc.calc import ValidationError
from ecalc.calc.home import HomeInputs, home_design
from ecalc.calc.install_home import InstallInputs, build_home_install

PSH = [5.0] * 12


def _hybrid():
    loads = [{"name": "Fridge", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True},
             {"name": "LED", "power_w": 10, "qty": 8, "hours_per_day": 6, "critical": True},
             {"name": "Iron", "power_w": 1000, "qty": 1, "hours_per_day": 0.5},
             {"name": "Base load", "power_w": 500, "qty": 1, "hours_per_day": 10}]
    x = HomeInputs(loads=loads, monthly_psh=PSH, mode="hybrid_backup", outage_hours=4, system_voltage=48)
    return x, home_design(x)


def test_hybrid_strings_battery_cables():
    x, d = _hybrid()
    # 7480 Wh / 0.93 / 5 / 0.9 = 1787 W -> 4 panels of 550 W
    assert d.out("panel_count") == 4
    pk = build_home_install(d, x, InstallInputs(site_name="Kathmandu"))
    st = pk.strings
    assert st["n_max"] == 9 and st["n_min"] == 4
    assert st["modules_per_string"] == 4 and st["strings"] == 1
    assert st["string_voc_cold_v"] == pytest.approx(4 * 53.027, abs=0.01)
    assert st["string_fuses"] is None                            # one string: no fuses
    # inverter max(230 x 4/3, 2200/1.2) = 1833 W -> 2 kW standard size
    inv = next(r for r in pk.bom if r["Item"].startswith("Hybrid inverter"))
    assert inv["Specification"].startswith("2 kW")
    # battery current: discharge 2000/(48 x 0.93) = 44.8 A, charge 2200/48 = 45.83 A -> fuse 1.25 x 45.83 = 57.3 -> 63 A
    bat = next(r for r in pk.cable_schedule if r["Circuit"].startswith("Battery cable"))
    assert bat["Design current (A)"] == pytest.approx(45.8, abs=0.05)
    assert bat["Protective device (A)"] == 63
    # current rule at 36.6 °C (x0.87): 10 mm² 49.6 A < 63, 16 mm² 66.1 A -> 16; voltage drop 1 % over 2 m -> 10 mm²
    assert bat["Size for current (mm²)"] == 16 and bat["Size for voltage drop (mm²)"] == 10
    assert bat["Chosen (mm²)"] == 16                              # chosen = max of the two rules
    # AC: 2000/230 = 8.70 A -> MCB 16 A -> 2.5 mm² (1.5 mm² carries only 15.2 A at 36.6 °C)
    ac = next(r for r in pk.cable_schedule if r["Circuit"] == "Inverter AC output")
    assert ac["Protective device (A)"] == 16 and ac["Chosen (mm²)"] == 2.5
    assert st["battery_series"] == 1 and st["battery_parallel"] == 1


def test_bom_categories_by_system_type():
    x, d = _hybrid()
    items = " | ".join(r["Item"] for r in build_home_install(d, x, InstallInputs()).bom)
    for must in ("Solar PV module", "Mounting structure", "PV cable", "MC4", "DC isolator", "DC surge", "Hybrid inverter",
                 "Battery", "Battery fuse", "Battery isolator", "AC MCB", "RCD", "AC surge", "Backup distribution board",
                 "changeover", "Earth electrode", "Earth cable", "Warning labels", "NEA bidirectional"):
        assert must in items, must

    g = HomeInputs(loads=[{"name": "House", "power_w": 1000, "qty": 1, "hours_per_day": 10}], monthly_psh=PSH)
    gi = " | ".join(r["Item"] for r in build_home_install(home_design(g), g, InstallInputs()).bom)
    assert "Grid-tied (on-grid) inverter" in gi and "NEA bidirectional" in gi
    assert "Battery" not in gi                                    # grid-tied has no battery rows


def test_off_grid_controller_and_no_meter():
    loads = [{"name": "LED", "power_w": 10, "qty": 6, "hours_per_day": 5},
             {"name": "Laptop", "power_w": 60, "qty": 1, "hours_per_day": 4}]
    x = HomeInputs(loads=loads, monthly_psh=PSH, mode="off_grid")
    d = home_design(x)
    assert d.outputs["system_v"].value == 24
    pk = build_home_install(d, x, InstallInputs(site_name="Kathmandu"))
    items = " | ".join(r["Item"] for r in pk.bom)
    assert "MPPT charge controller" in items and "Off-grid inverter" in items
    assert "NEA" not in items                                     # off-grid: no NEA meter
    ctrl = next(r for r in pk.bom if r["Item"] == "MPPT charge controller")
    assert ctrl["Specification"].startswith("30 A")              # 550 W / 24 V x 1.25 = 28.6 -> 30 A
    # 150 V controller: N_max = floor(min(150/53.03, 145.5/44.56)) = 2
    assert pk.strings["n_max"] == 2


def test_string_fuses_when_three_strings():
    x = HomeInputs(loads=[{"name": "House", "power_w": 1100, "qty": 1, "hours_per_day": 10}], monthly_psh=PSH,
                   mode="off_grid", system_voltage=48)
    d = home_design(x)
    assert d.out("panel_count") == 6
    pk = build_home_install(d, x, InstallInputs(site_name="Kathmandu"))
    # 2 in series x 3 parallel; reverse current 2 x 1.25 x 14 = 35 A > 25 A module fuse -> 25 A gPV fuses
    assert pk.strings["modules_per_string"] == 2 and pk.strings["strings"] == 3
    assert pk.strings["string_fuses"] == 25
    assert any(r["Item"].startswith("PV string fuse") for r in pk.bom)


def test_package_sections_and_expected_values():
    x, d = _hybrid()
    pk = build_home_install(d, x, InstallInputs(site_name="Kathmandu"))
    titles = [t for t, _ in pk.steps]
    assert any("safety" in t.lower() for t in titles) and any("AC connection" in t for t in titles)
    assert any("Switch on" in t for t in titles) and any("battery" in t.lower() for t in titles)
    voc_row = next(r for r in pk.tests_table if r["Test"].startswith("String 1 open-circuit"))
    assert "198 V" in voc_row["Expected"]                          # 4 x 49.5 = 198 V at 25 °C
    assert pk.maintenance and pk.troubleshooting and pk.safety
    ids = {n["id"] for n in pk.sld["nodes"]}
    assert {"pv", "dciso", "inv", "bat", "batp", "earth", "grid"} <= ids
    assert all(e["from"] in ids and e["to"] in ids for e in pk.sld["edges"])


def test_bad_datasheet_rejected():
    x, d = _hybrid()
    with pytest.raises(ValidationError):
        build_home_install(d, x, InstallInputs(vmp=60))
