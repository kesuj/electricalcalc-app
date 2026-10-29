"""Wiring drawings: valid SVG, right number of panels/batteries, key numbers present, Latin-1 text,
and they embed in a PDF (fpdf2) without error."""

import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fpdf import FPDF

from ecalc.calc.home import HomeInputs, home_design
from ecalc.calc.install_home import InstallInputs, build_home_install
from ecalc.drawings import (battery_bank_svg, earthing_svg, inverter_terminals_svg, panel_strings_svg,
                            system_overview_svg)

NS = "{http://www.w3.org/2000/svg}"
FX = Path(__file__).parent / "fixtures" / "pvgis_kathmandu_1kwp.json"


def _root(svg):
    return ET.fromstring(svg)


def _ids(svg, prefix):
    return [e.get("id") for e in _root(svg).iter(f"{NS}rect") if (e.get("id") or "").startswith(prefix)]


def _text(svg):
    return " ".join(t.text or "" for t in _root(svg).iter(f"{NS}text"))


def _pdf_ok(svg):
    pdf = FPDF()
    pdf.add_page()
    pdf.image(io.BytesIO(svg.encode("utf-8")), x=10, y=10, w=180)
    assert bytes(pdf.output()).startswith(b"%PDF")


def _latin1(svg):
    _text(svg).encode("latin-1")      # raises if a character cannot be drawn with the PDF core font


@pytest.mark.parametrize("ns,np_", [(4, 1), (6, 2), (12, 3)])
def test_panel_strings(ns, np_):
    svg = panel_strings_svg(ns, np_, "550 W", 52.75 * ns, 41.6 * ns, 14.0, 4, fuse_a=25 if np_ >= 3 else None)
    assert len(_ids(svg, "panel_")) == ns * np_
    t = _text(svg)
    assert f"{ns} x 41.6 V = {41.6 * ns:.0f} V" in t and "14.0 A" in t and f"{52.75 * ns:.0f} V" in t
    if np_ > 1:
        assert f"{np_} x 14.0 A = {np_ * 14.0:.1f} A" in t
    if np_ >= 3:
        assert "25 A" in t
    _latin1(svg)
    _pdf_ok(svg)


@pytest.mark.parametrize("ns,np_", [(1, 1), (4, 2), (2, 3)])
def test_battery_bank(ns, np_):
    svg = battery_bank_svg(ns, np_, "LiFePO4 48 V 100 Ah", 48, 4.8 * np_, 25, 63)
    assert len(_ids(svg, "battery_")) == ns * np_
    t = _text(svg)
    assert "48 V" in t and "63 A" in t and "25 mm2" in t
    if np_ > 1:
        assert "FIRST string" in t and "LAST string" in t     # diagonal take-off (book 107)
    _latin1(svg)
    _pdf_ok(svg)


def _pkg(mode):
    psh = [m["H(i)_d"] for m in json.loads(FX.read_text())["outputs"]["monthly"]["fixed"]]
    loads = [{"name": "Fridge", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True},
             {"name": "LED", "power_w": 10, "qty": 10, "hours_per_day": 6, "critical": True},
             {"name": "TV", "power_w": 60, "qty": 1, "hours_per_day": 5}]
    x = HomeInputs(loads=loads, monthly_psh=psh, mode=mode, outage_hours=4, holdover_days=2, temp_loss_pct=7.9)
    return build_home_install(home_design(x), x, InstallInputs(site_name="Kathmandu"))


@pytest.mark.parametrize("mode", ["grid_tied", "hybrid_backup", "off_grid"])
def test_system_overview_and_earthing(mode):
    pkg = _pkg(mode)
    svg = system_overview_svg(mode, pkg)
    t = _text(svg)
    assert "Solar panels" in t and "Earth electrode" in t
    assert ("NEA bidirectional meter" in t) == (mode != "off_grid")
    assert ("Battery bank" in t) == (mode != "grid_tied")
    assert ("charge controller" in t) == (mode == "off_grid")
    pv = next(r for r in pkg.cable_schedule if r["Circuit"].startswith("PV string"))
    assert f"{pv['Chosen (mm²)']} mm2" in t
    _latin1(svg)
    _pdf_ok(svg)
    e = earthing_svg(pkg)
    assert "16 mm2" in _text(e) and "Earth rod" in _text(e)
    _latin1(e)
    _pdf_ok(e)


@pytest.mark.parametrize("mode,must", [("grid_tied", ["PV1+", "L", "N", "PE"]),
                                       ("hybrid_backup", ["BAT+", "GRID in", "LOAD / BACKUP"]),
                                       ("off_grid", ["BAT+", "MPPT charge controller", "PV+"])])
def test_inverter_terminals(mode, must):
    svg = inverter_terminals_svg(mode)
    t = _text(svg)
    for m in must:
        assert m in t
    assert "manual" in t
    _latin1(svg)
    _pdf_ok(svg)
