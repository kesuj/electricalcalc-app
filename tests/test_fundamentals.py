"""Expected values below were calculated by hand (see TESTING.md) - never edited to make code pass."""

import math

import pytest

from ecalc.calc import ValidationError
from ecalc.calc import fundamentals as f


def test_ohms_law_solves_each_unknown():
    assert f.ohms_law(voltage_v=230, resistance_ohm=46).out("current_a") == pytest.approx(5.0)
    assert f.ohms_law(current_a=5, resistance_ohm=46).out("voltage_v") == pytest.approx(230)
    r = f.ohms_law(voltage_v=230, current_a=5)
    assert r.out("resistance_ohm") == pytest.approx(46)
    assert r.out("power_w") == pytest.approx(1150)


@pytest.mark.parametrize("kwargs", [{}, {"voltage_v": 1}, {"voltage_v": 1, "current_a": 1, "resistance_ohm": 1}])
def test_ohms_law_requires_exactly_two(kwargs):
    with pytest.raises(ValidationError):
        f.ohms_law(**kwargs)


def test_ohms_law_rejects_negative_and_nan():
    with pytest.raises(ValidationError):
        f.ohms_law(voltage_v=-230, current_a=5)
    with pytest.raises(ValidationError):
        f.ohms_law(voltage_v=float("nan"), current_a=5)


def test_three_phase_power_hand_calc():
    # S = sqrt3 * 400 * 10 = 6928.2 VA ; P = 0.8 S ; Q = 0.6 S
    r = f.ac_power(400, 10, 0.8, phases=3)
    assert r.out("apparent_power_kva") == pytest.approx(6.92820, rel=1e-5)
    assert r.out("real_power_kw") == pytest.approx(5.54256, rel=1e-5)
    assert r.out("reactive_power_kvar") == pytest.approx(4.15692, rel=1e-5)
    assert r.out("phase_angle_deg") == pytest.approx(36.8699, rel=1e-5)


def test_single_phase_power_and_power_triangle():
    r = f.ac_power(230, 10, 0.9, phases=1, lagging=False)
    s, p, q = r.out("apparent_power_kva"), r.out("real_power_kw"), r.out("reactive_power_kvar")
    assert s == pytest.approx(2.3)
    assert p == pytest.approx(2.07)
    assert q < 0  # leading
    assert math.hypot(p, q) == pytest.approx(s)


def test_invalid_power_factor_and_phase_count():
    with pytest.raises(ValidationError):
        f.ac_power(230, 10, 1.2)
    with pytest.raises(ValidationError):
        f.ac_power(230, 10, 0.9, phases=2)


def test_current_from_power_three_phase():
    # I = 15000 / (sqrt3 * 400 * 0.85) = 25.47 A
    assert f.current_from_power(15, 400, 0.85, phases=3).out("current_a") == pytest.approx(25.4726, rel=1e-4)


def test_pf_correction_textbook_example():
    # 100 kW, 0.70 -> 0.95: Qc = 100 (1.020204 - 0.328684) = 69.152 kvar
    r = f.pf_correction(100, 0.70, 0.95, voltage_ll_v=400, frequency_hz=50, connection="delta")
    assert r.out("capacitor_kvar") == pytest.approx(69.152, rel=1e-4)
    # C = 69152 / (3 * 2*pi*50 * 400^2) = 458.6 uF per phase (delta)
    assert r.out("capacitance_per_phase_uf") == pytest.approx(458.6, rel=1e-3)
    star = f.pf_correction(100, 0.70, 0.95, voltage_ll_v=400, connection="star")
    assert star.out("capacitance_per_phase_uf") == pytest.approx(3 * 458.6, rel=1e-3)


def test_pf_correction_target_must_be_higher():
    with pytest.raises(ValidationError):
        f.pf_correction(100, 0.95, 0.9)


def test_energy_cost():
    r = f.energy_cost(2, 8, 30, tariff_per_kwh=12)
    assert r.out("energy_kwh") == pytest.approx(480)
    assert r.out("cost") == pytest.approx(5760)
    with pytest.raises(ValidationError):
        f.energy_cost(2, 25)


def test_unit_conversions():
    assert f.HP_TO_KW * 10 == pytest.approx(7.457, rel=1e-4)
    assert f.awg_to_mm2(10) == pytest.approx(5.261, rel=1e-3)   # published 5.26 mm2
    assert f.awg_to_mm2(12) == pytest.approx(3.309, rel=1e-3)   # published 3.31 mm2
    assert f.kcmil_to_mm2(250) == pytest.approx(126.68, rel=1e-4)
    with pytest.raises(ValidationError):
        f.awg_to_mm2(50)
