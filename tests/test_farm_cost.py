"""Farm cost model: totals are the sum of quantity x rate, plus soft costs and contingency."""
import pytest

from ecalc.calc.farm import FarmInputs, Inverter, Module, book_string_design, farm_design
from ecalc.calc.farm_cost import CONTINGENCY, RATES, SOFT, farm_cost
from ecalc.calc.install_farm import PackageInputs, build_farm_package
from ecalc.drawings import farm_sld_svg

MOD = Module(wp=550, vmp=41.6, imp=13.2, voc=49.5, isc=14.0, beta_voc_pct=-0.25, gamma_pmax_pct=-0.29, efficiency_pct=21.3)
INV = Inverter(ac_kva=100, max_dc_kw=150, v_dc_max=1100, v_mppt_min=200, v_mppt_max=1000, i_dc_max=260, dc_inputs=10)


def _pkg(mwp):
    fi = FarmInputs(capacity_mwp=mwp, latitude=28.05, annual_psh=5.62, tilt_deg=28.1, table_slant_m=4.6,
                    module_efficiency_pct=21.3)
    fr = farm_design(fi)
    sr = book_string_design(MOD, INV, t_cell_min=-0.3)
    return build_farm_package(fr, sr, MOD, INV, fi, PackageInputs(mv_kv=11, line_to_nea_km=2.0)), sr


def test_builds_to_requested_size():
    pkg, _ = _pkg(1.0)
    # ceil(1e6 / (19 x 550)) = ceil(95.7) = 96 strings -> 1824 modules? 96 x 19 = 1824 -> 1.0032 MWp
    assert pkg.counts["strings"]["value"] == 96 and pkg.counts["modules"]["value"] == 1824
    assert pkg.counts["inverters"]["value"] == 7                     # ceil(96 / 14)


def test_cost_totals_hand_check():
    pkg, _ = _pkg(1.0)
    r = farm_cost(pkg, 550, 100, 2.0)
    # module line: 1824 x 550 Wp x NPR 25 = 2.508 crore
    mod_row = r.tables["Cost breakdown"][0]
    assert mod_row["Central (NPR lakh)"] == pytest.approx(1824 * 550 * 25 / 1e5, abs=0.1)
    hard = sum(row["Central (NPR lakh)"] for row in r.tables["Cost breakdown"][:-2]) * 1e5
    total = hard * (1 + SOFT["central"]) * (1 + CONTINGENCY["central"])
    assert r.out("total_central_crore") * 1e7 == pytest.approx(total, rel=2e-3)
    assert r.out("total_low_crore") < r.out("total_central_crore") < r.out("total_high_crore")
    assert set(RATES) >= {"modules", "inverters", "transformer", "line"}


def test_small_plant_costs_more_per_kwp():
    small = farm_cost(_pkg(0.5)[0], 550, 100, 2.0)
    big = farm_cost(_pkg(1.0)[0], 550, 100, 2.0)
    assert small.out("per_kwp_central") > big.out("per_kwp_central")     # fixed line/switchgear costs


def test_farm_drawing_has_every_level():
    pkg, sr = _pkg(1.0)
    svg = farm_sld_svg(pkg, 19, sr.out("string_voc_cold_v"), 19 * 41.6, 550, 100)
    for s in ("STRINGS", "INVERTERS", "AC combiner", "transformer", "switchgear", "NEA revenue metering",
              "NEA substation", "Earth mesh"):
        assert s in svg, s
