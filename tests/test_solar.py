import json
from pathlib import Path

import pytest

from ecalc.calc import ValidationError
from ecalc.calc.solar import SolarInputs, SolarResource, size_pv_system
from ecalc.solar_data import PVGISError, default_aspect, fetch_pvgis, parse_pvgis

FIXTURE = Path(__file__).parent / "fixtures" / "pvgis_kathmandu_1kwp.json"


def psh_resource(psh=5.0, losses=20.0):
    return SolarResource.from_peak_sun_hours(psh, losses)


def test_grid_tied_hand_calc():
    # Y = 5 * 365 * 0.8 = 1460 kWh/kWp ; demand 3650 ; need 2.5 kWp ; 550 Wp -> 5 panels = 2.75 kWp
    r = size_pv_system(SolarInputs(daily_consumption_kwh=10, panel_wp=550, panel_area_m2=2.6,
                                   resource=psh_resource(), tariff_per_kwh=12, cost_per_kwp=100000))
    assert r.out("specific_yield") == pytest.approx(1460)
    assert r.out("kwp_required") == pytest.approx(2.5)
    assert r.out("panel_count") == 5
    assert r.out("pv_kwp") == pytest.approx(2.75)
    assert r.out("annual_generation_kwh") == pytest.approx(4015)
    assert r.out("inverter_ac_kw") == pytest.approx(2.75 / 1.2)
    # saving: min(4015, 3650)*12 + excess*0 = 43800 ; capex 275000 ; payback 6.28 y
    assert r.out("annual_savings") == pytest.approx(43800)
    assert r.out("simple_payback_years") == pytest.approx(275000 / 43800)
    assert "Preliminary bill of materials" in r.tables


def test_area_limit_caps_panels_and_warns():
    r = size_pv_system(SolarInputs(daily_consumption_kwh=10, panel_wp=550, panel_area_m2=2.6,
                                   resource=psh_resource(), available_area_m2=8))
    assert r.out("panel_count") == 3
    assert any("Area limits" in w for w in r.warnings)


def test_missing_tariff_and_cost_are_flagged_not_invented():
    r = size_pv_system(SolarInputs(daily_consumption_kwh=10, panel_wp=550, panel_area_m2=2.6, resource=psh_resource()))
    assert "annual_savings" not in r.outputs and "simple_payback_years" not in r.outputs
    assert any("tariff not entered" in w for w in r.warnings)


def test_hybrid_battery_energy_distinctions():
    # usable = 5 kWh * 1 day ; nominal = 5 / 0.8 / 0.95 = 6.579 kWh ; Ah @48 V = 137.06
    r = size_pv_system(SolarInputs(daily_consumption_kwh=10, panel_wp=550, panel_area_m2=2.6, resource=psh_resource(),
                                   system_type="hybrid_battery", backup_kwh_per_day=5, peak_load_kw=4))
    assert r.out("battery_usable_kwh") == pytest.approx(5)
    assert r.out("battery_nominal_kwh") == pytest.approx(6.5789, rel=1e-4)
    assert r.out("battery_ah") == pytest.approx(137.06, rel=1e-4)
    assert r.out("inverter_ac_kw") == pytest.approx(4)   # raised to peak load
    assert r.outputs["battery_nominal_kwh"].unit == "kWh" and r.outputs["pv_kwp"].unit == "kWp"


def test_hybrid_requires_backup_energy():
    with pytest.raises(ValidationError):
        size_pv_system(SolarInputs(daily_consumption_kwh=10, panel_wp=550, panel_area_m2=2.6,
                                   resource=psh_resource(), system_type="hybrid_battery"))


@pytest.mark.parametrize("kw", [{"daily_consumption_kwh": 0}, {"panel_wp": 5}, {"system_type": "offgrid"},
                                {"dc_ac_ratio": 3}])
def test_invalid_inputs(kw):
    base = dict(daily_consumption_kwh=10, panel_wp=550, panel_area_m2=2.6, resource=psh_resource())
    base.update(kw)
    with pytest.raises(ValidationError):
        size_pv_system(SolarInputs(**base))


def test_peak_sun_hours_validation():
    with pytest.raises(ValidationError):
        SolarResource.from_peak_sun_hours(15, 14)


def test_parse_real_pvgis_fixture():
    res = parse_pvgis(json.loads(FIXTURE.read_text()), 27.7172, 85.324)
    assert res.annual_kwh_per_kwp == pytest.approx(1426.64)
    assert len(res.monthly_kwh_per_kwp) == 12
    # independent consistency check: monthly values must sum to the annual value (rounding < 0.5 %)
    assert sum(res.monthly_kwh_per_kwp) == pytest.approx(1426.64, rel=5e-3)
    assert res.source.startswith("PVGIS") and "ERA5" in res.source


def test_pvgis_based_sizing_produces_monthly_table():
    res = parse_pvgis(json.loads(FIXTURE.read_text()), 27.7172, 85.324)
    r = size_pv_system(SolarInputs(daily_consumption_kwh=15, panel_wp=550, panel_area_m2=2.58, resource=res))
    # 15*365 / 1426.64 = 3.838 kWp -> 7 panels -> 3.85 kWp
    assert r.out("kwp_required") == pytest.approx(3.8376, rel=1e-4)
    assert r.out("panel_count") == 7
    assert len(r.tables["Monthly generation estimate"]) == 12
    assert any("PVGIS" in ref for ref in r.references)


def test_parse_rejects_malformed():
    with pytest.raises(PVGISError):
        parse_pvgis({"outputs": {}}, 0, 0)


def test_default_aspect_hemisphere():
    assert default_aspect(27.7) == 0 and default_aspect(-33.9) == 180


def test_fetch_pvgis_network_failure(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(PVGISError, match="Could not reach PVGIS"):
        fetch_pvgis(27.7, 85.3, 27)


def test_fetch_pvgis_uses_cache(monkeypatch):
    data = json.loads(FIXTURE.read_text())

    class Cache:
        def __init__(self): self.store = {}
        def get_pvgis(self, k): return self.store.get(k)
        def put_pvgis(self, k, v): self.store[k] = v

    class Resp:
        status_code = 200
        def json(self): return data
    calls = []
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1) or Resp())
    cache = Cache()
    fetch_pvgis(27.7172, 85.324, 27, cache=cache)
    fetch_pvgis(27.7172, 85.324, 27, cache=cache)
    assert len(calls) == 1
