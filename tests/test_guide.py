"""Component guide: right cards per system type, the user's own numbers inside, nothing empty, no brands."""
import json
from pathlib import Path

import pytest

from ecalc.calc.home import HomeInputs, home_design
from ecalc.calc.install_home import InstallInputs, build_home_install
from ecalc.guide import component_guide, legal_and_safety_stop_points, series_parallel_explainer, skills

FX = json.loads((Path(__file__).parent / "fixtures" / "pvgis_kathmandu_1kwp.json").read_text())
PSH = [m["H(i)_d"] for m in FX["outputs"]["monthly"]["fixed"]]
LOADS = [{"name": "Fridge", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True},
         {"name": "LED", "power_w": 10, "qty": 10, "hours_per_day": 6, "critical": True},
         {"name": "TV", "power_w": 60, "qty": 1, "hours_per_day": 5}]
BRANDS = ["jinko", "longi", "trina", "ja solar", "canadian solar", "deye", "growatt", "huawei", "victron", "pylontech",
          "luminous", "exide", "waaree", "su-kam", "microtek", "schneider", "abb ", "havells", "legrand", "sma "]


def build(mode):
    x = HomeInputs(loads=LOADS, monthly_psh=PSH, mode=mode, outage_hours=4, holdover_days=2, temp_loss_pct=7.9)
    r = home_design(x)
    ii = InstallInputs(site_name="Kathmandu")
    return build_home_install(r, x, ii), r, x, ii


def names(cards):
    return [c["name"] for c in cards]


def all_text(obj) -> str:
    if isinstance(obj, dict):
        return " ".join(all_text(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(all_text(v) for v in obj)
    return str(obj)


@pytest.mark.parametrize("mode", ["grid_tied", "hybrid_backup", "off_grid"])
def test_cards_complete_and_without_brands(mode):
    pkg, r, x, ii = build(mode)
    cards = component_guide(pkg, r, x, ii)
    for c in cards:
        for key in ("name", "what_it_does", "types", "best_for_you", "how_to_select", "buying_checklist",
                    "how_to_connect", "mistakes", "ref"):
            assert c[key], (c["name"], key)
        for row in c["types"]:
            assert set(row) == {"Type", "How it works", "Good", "Bad", "Best for"}
    text = all_text(cards).lower() + all_text(skills(pkg, x)).lower()
    for b in BRANDS:
        assert b not in text, b


def test_mode_appropriate_cards():
    g = names(component_guide(*build("grid_tied")))
    h = names(component_guide(*build("hybrid_backup")))
    o = names(component_guide(*build("off_grid")))
    assert "Battery bank" not in g and "Battery bank" in h and "Battery bank" in o
    assert not any("NEA" in n for n in o) and any("NEA" in n for n in g) and any("NEA" in n for n in h)
    assert any("Charge controller" in n for n in o) and not any("Charge controller" in n for n in g + h)
    assert any("changeover" in n.lower() for n in h) and not any("changeover" in n.lower() for n in g + o)


def test_users_numbers_appear():
    pkg, r, x, ii = build("hybrid_backup")
    cards = {c["name"]: c for c in component_guide(pkg, r, x, ii)}
    cold = f"{pkg.strings['string_voc_cold_v']:,.0f} V"
    assert any(cold in s for s in cards["DC isolator / DC breaker (panel side)"]["how_to_select"])
    bat = next(c for c in pkg.cable_schedule if c["Circuit"].startswith("Battery cable"))
    sel = " ".join(cards["Battery cables, lugs, fuse and isolator"]["how_to_select"])
    assert f"{bat['Chosen (mm²)']} mm²" in sel and f"Fuse {bat['Protective device (A)']} A" in sel
    assert f"{pkg.strings['modules_per_string']} in series" in cards["Solar panels (PV modules)"]["series_or_parallel"]


def test_series_parallel_and_skills():
    pkg, r, x, ii = build("off_grid")
    sp = series_parallel_explainer(pkg)
    assert "voltages add" in sp["rule"] and "batteries" in sp
    assert f"{pkg.strings['battery_parallel']} in parallel" in sp["batteries"]
    titles = [s["title"] for s in skills(pkg, x)]
    assert any("multimeter" in t.lower() for t in titles) and any("battery" in t.lower() for t in titles)
    inv = next(s for s in skills(pkg, x) if s["title"].startswith("Setting up"))
    assert any("3.6 V per cell" in st for st in inv["steps"])            # NEPQA HVD cap stated for lithium
    g_pkg, _, gx, _ = build("grid_tied")
    assert not any("battery" in s["title"].lower() for s in skills(g_pkg, gx))


def test_stop_points_honest():
    _, _, gx, _ = build("grid_tied")
    pts = " ".join(legal_and_safety_stop_points(gx))
    assert "licensed electrician" in pts and "NEA" in pts
    _, _, ox, _ = build("off_grid")
    assert not any("net metering" in p for p in legal_and_safety_stop_points(ox))
