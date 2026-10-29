"""Browser build: PVGIS answers come from the baked file (real PVGIS results), never invented."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
import offline_pvgis  # noqa: E402

URL = "https://re.jrc.ec.europa.eu/api/v5_3/"


def test_nearest_site_and_angle_are_named():
    d = offline_pvgis.get(URL + "PVcalc", {"lat": 28.3, "lon": 84.1, "angle": 30, "aspect": -30, "loss": 14})
    db = d.json()["inputs"]["meteo_data"]["radiation_db"]
    assert "Pokhara" in db and "km from your point" in db


def test_loss_scales_energy_exactly():
    p = {"lat": 27.7172, "lon": 85.324, "angle": 25, "aspect": 0}
    e14 = offline_pvgis.get(URL + "PVcalc", p | {"loss": 14}).json()["outputs"]["totals"]["fixed"]["E_y"]
    e20 = offline_pvgis.get(URL + "PVcalc", p | {"loss": 20}).json()["outputs"]["totals"]["fixed"]["E_y"]
    assert e20 == pytest.approx(e14 * 0.80 / 0.86)


def test_every_site_has_every_roof_option():
    data = offline_pvgis._data()
    assert len(data) == 27
    for s in data.values():
        keys = set(s["pv"])
        assert {f"{t}|{a}" for t in (15, 25, 35) for a in (0, -45, 45, -90, 90, 180)} <= keys
        assert set(s["dr"]) == keys


def test_daily_profile_shape():
    d = offline_pvgis.get(URL + "DRcalc", {"lat": 26.45, "lon": 87.27, "angle": 25, "aspect": 0}).json()
    rows = d["outputs"]["daily_profile"]
    assert {r["month"] for r in rows} == set(range(1, 13)) and max(r["G(i)"] for r in rows) > 500
