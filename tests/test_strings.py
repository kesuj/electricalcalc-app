"""String sizing - hand calculation:
Voc 49.5, Vmp 41.6, Isc 14, beta -0.25 %/C, Tmin -5, Tmax 40, NOCT 45; inverter 1100 V, MPPT 200-1000 V.
Voc,max = 49.5 x 1.075 = 53.2125 -> 1100/53.21 = 20.67 -> N_max 20 (Vmp,cold 44.72 -> 1000/44.72 = 22.4)
Tcell,max = 40 + 25/800 x 1000 = 71.25; Vmp,hot = 41.6 x (1 - 0.0025 x 46.25) = 36.79 -> 200/36.79 = 5.44 -> N_min 6
Fuse: 3 strings -> reverse 2 x 1.25 x 14 = 35 A > 30 A module rating -> needed; 1.5x14=21 <= In <= min(33.6, 30) -> 25 A
"""
import pytest

from ecalc.calc import ValidationError
from ecalc.calc.strings import string_sizing

BASE = dict(voc=49.5, vmp=41.6, isc=14.0, beta_voc_pct=-0.25, t_amb_min=-5, t_amb_max=40,
            v_dc_max=1100, mppt_min=200, mppt_max=1000)


def test_string_limits_hand_calc():
    r = string_sizing(**BASE)
    assert r.out("voc_max_v") == pytest.approx(53.2125)
    assert r.out("tcell_max_c") == pytest.approx(71.25)
    assert r.out("vmp_hot_v") == pytest.approx(36.79, abs=0.01)
    assert r.out("n_max") == 20 and r.out("n_min") == 6


def test_fuse_rules():
    r = string_sizing(**BASE, strings_in_parallel=3, module_max_fuse_a=30, mppt_max_current_a=32, imp=13.2)
    assert r.out("reverse_current_a") == pytest.approx(35.0)
    assert r.outputs["fuse_needed"].value == "Yes"
    assert r.out("fuse_rating_a") == 25
    assert r.out("strings_per_mppt") == 2          # floor(32 / 13.2)
    r2 = string_sizing(**BASE, strings_in_parallel=2, module_max_fuse_a=30)
    assert r2.outputs["fuse_needed"].value == "No"  # 1 x 17.5 A < 30 A


def test_colder_site_allows_fewer_modules():
    # Jumla-like -15 C: Voc,max = 49.5 x 1.1 = 54.45 -> 1100/54.45 = 20.2 -> still 20; at -30 C: 49.5x1.1375=56.31 -> 19
    assert string_sizing(**dict(BASE, t_amb_min=-30)).out("n_max") == 19


@pytest.mark.parametrize("bad", [dict(vmp=50), dict(beta_voc_pct=0.3), dict(t_amb_max=-10), dict(mppt_max=1200)])
def test_invalid(bad):
    with pytest.raises(ValidationError):
        string_sizing(**dict(BASE, **bad))
