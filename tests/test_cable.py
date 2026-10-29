import pytest

from ecalc.calc import ValidationError
from ecalc.calc import cable as c


def test_resistance_temperature_correction():
    # 4 mm2 Cu: 4.61 ohm/km at 20 C ; at 70 C x (1 + 0.00393*50) = 5.5159
    assert c.conductor_resistance_ohm_per_km("copper", 4, 70) == pytest.approx(5.5159, rel=1e-4)
    assert c.conductor_resistance_ohm_per_km("copper", 4, 20) == pytest.approx(4.61)


def test_single_phase_drop_hand_calc():
    # dV = 2 * 20 A * 0.030 km * 5.5159 = 6.619 V = 2.878 % of 230 V
    r = c.voltage_drop("single_phase", 230, 20, 30, 4, "copper", 70, 1.0, limit_pct=3)
    assert r.out("voltage_drop_v") == pytest.approx(6.619, rel=1e-3)
    assert r.out("voltage_drop_pct") == pytest.approx(2.878, rel=1e-3)
    assert r.outputs["within_limit"].value == "Yes"
    assert r.out("power_loss_w") == pytest.approx(2 * 20**2 * 5.5159 * 0.03, rel=1e-4)


def test_three_phase_drop_with_reactance_hand_calc():
    # R70 = 1.15*1.1965 = 1.37598 ; z = R*0.85 + 0.08*0.526783 = 1.21172 ohm/km
    # dV = sqrt3 * 50 * 0.1 * 1.21172 = 10.494 V -> 2.623 %
    r = c.voltage_drop("three_phase", 400, 50, 100, 16, "copper", 70, 0.85, 0.08)
    assert r.out("voltage_drop_v") == pytest.approx(10.494, rel=1e-3)
    assert r.out("voltage_drop_pct") == pytest.approx(2.6235, rel=1e-3)


def test_dc_drop_ignores_power_factor():
    r = c.voltage_drop("dc", 48, 30, 10, 6, "copper", 20, power_factor=0.5)
    assert r.out("voltage_drop_v") == pytest.approx(2 * 30 * 3.08 * 0.010, rel=1e-6)


def test_aluminium_and_limit_fail_warning():
    r = c.voltage_drop("single_phase", 230, 60, 80, 16, "aluminium", 70, 1.0, limit_pct=3)
    # R70 = 1.91 * 1.2015 = 2.29487 ; dV = 2*60*0.08*2.29487 = 22.03 V = 9.58 %
    assert r.out("voltage_drop_pct") == pytest.approx(9.579, rel=1e-3)
    assert r.outputs["within_limit"].value == "No"
    assert any("exceeds" in w for w in r.warnings)


def test_always_warns_ampacity_not_checked():
    r = c.voltage_drop("single_phase", 230, 10, 10, 2.5)
    assert any("ampacity" in w for w in r.warnings)


def test_large_conductor_zero_reactance_warning():
    r = c.voltage_drop("three_phase", 400, 150, 100, 70, power_factor=0.85)
    assert any("Reactance" in w for w in r.warnings)


def test_minimum_size_selection():
    r = c.minimum_size_for_drop("single_phase", 230, 20, 30, 3.0)
    assert r.out("min_size_mm2") == 4      # 2.5 mm2 gives 4.6 %, 4 mm2 gives 2.88 %
    table = r.tables["Size comparison"]
    assert table[0]["Size (mm²)"] == 0.75
    assert any("ONLY" in w for w in r.warnings)


def test_minimum_size_impossible():
    with pytest.raises(ValidationError):
        c.minimum_size_for_drop("single_phase", 230, 400, 2000, 1.0)


@pytest.mark.parametrize("kwargs", [
    {"system": "two_phase"}, {"size_mm2": 3}, {"material": "gold"}, {"current_a": 0}, {"length_m": -5},
    {"power_factor": 0}])
def test_invalid_inputs(kwargs):
    base = dict(system="single_phase", voltage_v=230, current_a=10, length_m=10, size_mm2=2.5, material="copper")
    base.update(kwargs)
    with pytest.raises(ValidationError):
        c.voltage_drop(**base)
