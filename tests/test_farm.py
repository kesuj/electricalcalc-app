"""Solar farm - book worked examples (Neill et al., Solar Farms) with the book's errata corrected.

Book p.101: Germany 52.5° -> tilt 52.5°.   p.148: PR = 0.90x0.98x0.98x0.98x0.96x0.87 = 0.7075 (book 0.71).
p.81: 100 MWp x 4.5 PSH x 365 x 0.70 = 114,975 MWh; CF (DC) 13.1 %.
pp.113-116 (100 MWp, 300 Wp module, SMA 900CP): corrected physics -> NO feasible string length at 5 °C:
  Vmp(70) = 32 - 0.1344 x 45 = 25.952; x0.98 = 25.43; N_min (10 % margin) = ceil(596/(25.43x0.9)) = 27
  Voc(5)  = 39.5 + 0.12245 x 20 = 41.949; N_max (5 %) = floor(1000/44.05) = 22   -> infeasible
  no margins: N_min = ceil(596/25.43) = 24, N_max = floor(1000/41.95) = 23    -> infeasible (book chose 24: unsafe)
  strings = 1400/10 = 140 (Isc at STC, as the book).
Nepal row spacing (spec 3.6): lat 27.7, tilt 25, l 2.0 -> alpha 38.85, d = 2.862 m, GCR 0.699.
"""
import math

import pytest

from ecalc.calc import ValidationError
from ecalc.calc.farm import (BIGHA_M2, FarmInputs, Inverter, Module, ROPANI_M2, book_string_design, farm_design,
                             optimal_tilt, performance_ratio, row_spacing)

MOD = Module(wp=300, vmp=32.0, imp=9.46, voc=39.5, isc=10.0, beta_voc_pct=-0.31, gamma_pmax_pct=-0.42)
INV = Inverter(ac_kva=990, max_dc_kw=1010, v_dc_max=1000, v_mppt_min=596, v_mppt_max=850, i_dc_max=1400, dc_inputs=9)


def test_tilt_book_box_4_1():
    assert optimal_tilt(52.5) == 52.5
    assert optimal_tilt(5) == 10            # minimum 10° for self-cleaning


def test_pr_book_p148():
    losses = {"t": 10, "s": 2, "m": 2, "v": 2, "i": 4, "x": 13}
    assert performance_ratio(losses) == pytest.approx(0.70748, abs=1e-5)


def test_yield_book_p81():
    r = farm_design(FarmInputs(capacity_mwp=100, latitude=27.7, annual_psh=4.5, losses_pct={"all": 30}))
    assert r.out("annual_mwh") == pytest.approx(114_975)
    assert r.out("cf_dc_pct") == pytest.approx(13.125, abs=0.01)


def test_string_design_book_example_corrected():
    r = book_string_design(MOD, INV, t_cell_min=5, t_cell_max=70)
    assert r.out("vmp_hot_v") == pytest.approx(25.952)
    assert r.out("voc_cold_v") == pytest.approx(41.949, abs=1e-3)     # book misprints 40.69
    assert r.out("n_min") == 27 and r.out("n_max") == 22                # with margins
    assert r.out("n_min_raw") == 24 and r.out("n_max_raw") == 23        # without margins
    assert r.out("strings_max") == 140
    assert any("even without margins" in w for w in r.warnings)
    # the book's chosen 24-module string would reach 24 x 41.95 = 1006.8 V > 1000 V on a 5 °C morning
    assert r.out("string_voc_cold_v") == pytest.approx(24 * 41.949, abs=0.05)
    assert any("NOT safe" in w for w in r.warnings)


def test_string_design_feasible_1500v_case():
    inv = Inverter(ac_kva=990, max_dc_kw=1010, v_dc_max=1500, v_mppt_min=596, v_mppt_max=1300, i_dc_max=1400, dc_inputs=9)
    r = book_string_design(MOD, inv, t_cell_min=5)
    # N_max = floor(1500 / (41.949 x 1.05)) = floor(34.06) = 34; N_min 27 -> choose 34
    assert r.out("n_max") == 34 and r.out("modules_per_string") == 34
    # 34 x 140 x 300 W = 1428 kW > 1010 kW -> strings cut to floor(1010000 / (34 x 300)) = 99
    assert r.out("strings_used") == 99
    assert r.out("dc_kw_per_inverter") == pytest.approx(34 * 99 * 0.3)
    assert r.outputs["input_split"].value == "9 × 11"
    assert not any("NOT safe" in w for w in r.warnings)


def test_row_spacing_nepal():
    rs = row_spacing(27.7, 25, 2.0)
    assert rs["sun_altitude_deg"] == pytest.approx(38.85)
    assert rs["pitch_m"] == pytest.approx(2.862, abs=1e-3)
    assert rs["gcr"] == pytest.approx(0.699, abs=1e-3)


def test_land_units():
    r = farm_design(FarmInputs(capacity_mwp=1, latitude=27.7, annual_psh=5, tilt_deg=25, table_slant_m=2.0,
                               module_efficiency_pct=20, land_extra_pct=0, shade_free_hours=0))
    # module area 1e6 / (0.20 x 1000) = 5000 m²; ÷ GCR 0.6988 -> 7155 m²
    land_m2 = 5000 / row_spacing(27.7, 25, 2.0)["gcr"]
    assert r.out("land_ha") == pytest.approx(land_m2 / 1e4)
    assert r.out("land_bigha") == pytest.approx(land_m2 / BIGHA_M2)
    assert r.out("land_ropani") == pytest.approx(land_m2 / ROPANI_M2)


def test_invalid_farm():
    with pytest.raises(ValidationError):
        row_spacing(80, 30, 2)             # sun below horizon at solstice
    with pytest.raises(ValidationError):
        performance_ratio({"x": 70})


def test_shade_free_window_9_to_3_kathmandu():
    """Hand calc, lat 27.7, 21 Dec, 9 am (omega 45°): sin a = sin27.7 sin(-23.45) + cos27.7 cos23.45 cos45 = 0.3894
    -> a = 22.92°; cos g = (sin a sin phi - sin d)/(cos a cos phi) = 0.7099 -> shadow factor 0.7099/tan22.92 = 1.679."""
    rs = row_spacing(27.7, 25, 2.0, shade_free_hours=3)
    assert rs["sun_altitude_deg"] == pytest.approx(22.92, abs=0.02)
    assert rs["shadow_m"] == pytest.approx(2.0 * math.sin(math.radians(25)) * 1.679, rel=2e-3)
    assert rs["gcr"] < row_spacing(27.7, 25, 2.0)["gcr"]          # wider than the noon-only rule
