"""Solar farm construction package - hand-checked 10 MWp case near Nepalgunj (record low -0.3 °C).

Module 550 Wp: Voc 49.5, Vmp 41.6, Isc 14.0, Imp 13.2, β_Voc −0.25 %/°C, γ −0.29 %/°C.
Inverter 330 kVA, 1500 V, MPPT 500-1500 V, 390 A, 6 inputs, 450 kW DC max, 800 V AC.
Voc(−0.3) = 49.5 + 0.12375 × 25.3 = 52.631 → ×1.05 = 55.26 → N_max = floor(1500/55.26) = 27
Vmp(70) = 41.6 − 0.12064 × 45 = 36.171 → ×0.98×0.9 = 31.90 → N_min = 16 → 27 chosen
Strings = floor(390/14) = 27; DC = 27 × 27 × 0.55 = 400.95 kW ≤ 450.
Inverters = ceil(10000/400.95) = 25; strings 675; modules 18,225; 10.024 MWp.
Block = floor(3150/330) = 9 inverters → 3 blocks (9, 9, 7): 2970 → 3150 kVA; 2310 → 2500 kVA; 33 kV (> 3 MWp).
String inputs: ceil(27/6) = 5 per input → reverse 4 × 1.25 × 14 = 70 A > 30 A → fuses; 21 ≤ In ≤ 30 → 25 A.
String cable: CCC ≥ 25 A at 40 °C → 4 mm² (32 × 0.87 = 27.8 A); VD 2 × 13.2 × 0.06 × 5.516 / 1123.2 = 0.78 %.
LV AC: I = 330000/(√3 × 800) = 238.2 A → 1.25 × = 297.7 → 315 A breaker; 185 mm² 353 × 0.87 = 307 < 315
  → 240 mm² (361 A); VD √3 × 238.2 × 0.15 × 0.09022 / 800 = 0.70 % (VD alone needs 185 mm²).
MV per 3150 kVA at 33 kV: 3150000/(√3 × 33000) = 55.1 A.
Insulation: system voltage 49.5 × 27 × 1.25 = 1670.6 V > 500 → test 1000 V, ≥ 1 MΩ (Table 5.1).
"""
import pytest

from ecalc.calc import ValidationError
from ecalc.calc.farm import FarmInputs, Inverter, Module, book_string_design, farm_design
from ecalc.calc.install_farm import PackageInputs, build_farm_package, insulation_test_row

MOD = Module(wp=550, vmp=41.6, imp=13.2, voc=49.5, isc=14.0, beta_voc_pct=-0.25, gamma_pmax_pct=-0.29,
             efficiency_pct=21.3)
INV = Inverter(ac_kva=330, max_dc_kw=450, v_dc_max=1500, v_mppt_min=500, v_mppt_max=1500, i_dc_max=390, dc_inputs=6)
FI = FarmInputs(capacity_mwp=10, latitude=28.05, annual_psh=5.62, tilt_deg=28, table_slant_m=4.6,
                module_efficiency_pct=21.3)


def _pkg(**kw):
    sr = book_string_design(MOD, INV, t_cell_min=-0.3, t_cell_max=70)
    return build_farm_package(farm_design(FI), sr, MOD, INV, FI, PackageInputs(**kw))


def test_counts_and_blocks():
    p = _pkg()
    c = p.counts
    assert p.hierarchy["modules_per_string"] == 27 and p.hierarchy["strings_per_inverter"] == 27
    assert c["inverters"]["value"] == 25 and c["strings"]["value"] == 675 and c["modules"]["value"] == 18225
    assert c["mwp_actual"]["value"] == pytest.approx(10.024, abs=1e-3)
    assert c["blocks"]["value"] == 3 and c["mv_kv"]["value"] == 33.0
    assert [b["Transformer (kVA)"] for b in p.blocks] == [3150, 3150, 2500]
    assert p.blocks[0]["MV current (A)"] == pytest.approx(55.1, abs=0.1)
    assert c["tables"]["value"] == 338            # 18225 / (2 × 27) = 337.5 -> 338


def test_string_fuses_and_cables():
    p = _pkg()
    fuse = p.protection[0]
    assert "25 A" in fuse["Requirement"]
    s = p.cable_schedule[0]
    assert s["Protective device (A)"] == 25 and s["Size by current (mm²)"] == 4 and s["Selected"] == "4 mm² Cu"
    assert s["Voltage drop (%)"] == pytest.approx(0.78, abs=0.01)
    lv = p.cable_schedule[1]
    assert lv["Design current (A)"] == pytest.approx(238.2, abs=0.1) and lv["Protective device (A)"] == 315
    assert lv["Size by current (mm²)"] == 240 and lv["Size by voltage drop (mm²)"] == 185
    assert lv["Voltage drop (%)"] == pytest.approx(0.70, abs=0.01)


def test_insulation_table_rows():
    assert insulation_test_row(100)["test_v"] == 250
    assert insulation_test_row(400) == {"system_voltage_v": 400, "test_v": 500, "min_mohm": 1.0}
    assert _pkg().insulation_test["test_v"] == 1000
    assert _pkg().insulation_test["system_voltage_v"] == pytest.approx(1670.6, abs=0.1)


def test_small_plant_uses_11kv_and_central_combiners():
    fi = FarmInputs(capacity_mwp=2, latitude=28.05, annual_psh=5.62, tilt_deg=28)
    sr = book_string_design(MOD, INV, t_cell_min=-0.3)
    p = build_farm_package(farm_design(fi), sr, MOD, INV, fi, PackageInputs(inverter_type="central"))
    assert p.counts["mv_kv"]["value"] == 11.0
    # ceil(2000/400.95) = 5 inverters x 27 strings = 135 strings / 16 per combiner = 9 combiners
    assert p.counts["combiners"]["value"] == 9
    assert any(r["Level"].startswith("DC main") for r in p.cable_schedule)


def test_report_sections_and_lists():
    p = _pkg()
    secs = p.calc_results()
    assert len(secs) == 5 and "BOQ" in secs[3].tables
    assert any(r["Item"] == "String fuses gPV" for r in p.boq)
    assert p.sld["nodes"][0][0] == "pv" and len(p.sld["edges"]) == 7
    assert p.construction[0][0].startswith("1.") and len(p.commissioning) == 8
    assert all("verify" in r["Status"] for r in p.permits)
    assert "EPC" in p.note


def test_unsafe_string_rejected():
    inv = Inverter(ac_kva=330, max_dc_kw=450, v_dc_max=1000, v_mppt_min=900, v_mppt_max=1000, i_dc_max=390, dc_inputs=6)
    sr = book_string_design(MOD, inv, t_cell_min=-15)
    with pytest.raises(ValidationError):
        build_farm_package(farm_design(FI), sr, MOD, inv, FI)
