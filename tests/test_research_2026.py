"""Research findings are applied to the right cards with the user's numbers."""
import json
from pathlib import Path

from ecalc.calc.home import HomeInputs, home_design
from ecalc.calc.install_home import InstallInputs, build_home_install
from ecalc.guide import component_guide
from ecalc.guide.research_2026 import apply_research, legal_points_2026

FX = Path(__file__).parent / "fixtures" / "pvgis_kathmandu_1kwp.json"


def _build(mode, site="Jumla", pv_len=15.0):
    psh = [m["H(i)_d"] for m in json.loads(FX.read_text())["outputs"]["monthly"]["fixed"]]
    loads = [{"name": "Fridge", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True},
             {"name": "LED", "power_w": 10, "qty": 8, "hours_per_day": 6, "critical": True}]
    x = HomeInputs(loads=loads, monthly_psh=psh, mode=mode, outage_hours=4, holdover_days=2)
    d = home_design(x)
    ii = InstallInputs(site_name=site, len_array_to_inverter_m=pv_len)
    pkg = build_home_install(d, x, ii)
    return apply_research(component_guide(pkg, d, x, ii), pkg, x, ii), x


def _card(cards, start):
    return next(c for c in cards if c["name"].lower().startswith(start))


def test_cold_site_lithium_warning_and_earthing_spec():
    cards, _ = _build("hybrid_backup", "Jumla")
    bat = " ".join(_card(cards, "battery bank")["how_to_select"])
    assert "-15" in bat and "INDOORS" in bat and "SERIES" in bat
    earth = " ".join(_card(cards, "earthing")["how_to_select"])
    assert "TWO earth electrodes" in earth and "10 Ω" in earth


def test_second_spd_only_for_long_runs():
    long_cards, _ = _build("grid_tied", "Kathmandu", 15)
    short_cards, _ = _build("grid_tied", "Kathmandu", 6)
    spd = lambda cs: " ".join(next(c for c in cs if "surge protector" in c["name"].lower()
                                   and "dc" in c["name"].lower())["how_to_select"])
    assert "SECOND DC SPD" in spd(long_cards) and "SECOND DC SPD" not in spd(short_cards)


def test_legal_points_corrected():
    _, x = _build("hybrid_backup")
    text = " ".join(legal_points_2026(x))
    assert "no Nepali law requiring a licensed electrician" in text and "COMPULSORY" in text


def test_requirement_levels():
    from ecalc.guide.requirement import LAW, OPTIONAL, SAFETY, classify, requirement_table
    assert classify("NEA bidirectional meter", "grid_tied")[0] == LAW
    assert classify("NEA bidirectional meter", "off_grid")[0] == OPTIONAL
    assert classify("Battery fuse (DC)")[0] == SAFETY and classify("MC4 connector pairs")[0] == LAW
    assert classify("Monitoring Wi-Fi dongle")[0] == OPTIONAL
    parts = [r["Part"] for r in requirement_table("grid_tied")]
    assert "NEA approval + bidirectional meter" in parts and not any("Battery" in p for p in parts)
    assert any("charge controller" in r["Part"] for r in requirement_table("off_grid"))


def test_requirement_keyword_order():
    from ecalc.guide.requirement import LAW, SAFETY, classify
    assert classify("AC MCB (inverter output)", "grid_tied")[0] == SAFETY
    assert classify("Hybrid inverter (low-voltage battery)", "hybrid_backup")[0] == LAW
    assert classify("Off-grid inverter", "off_grid")[0] == SAFETY
    assert classify("Battery isolator / DC breaker", "hybrid_backup")[0] == SAFETY
