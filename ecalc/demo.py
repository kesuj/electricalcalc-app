"""Clearly labelled demonstration project built from real calculation code and a real,
bundled PVGIS response for Kathmandu. The client, loads and prices are invented sample inputs."""

from __future__ import annotations

import json
from pathlib import Path

from .calc import cable, fundamentals
from .calc.solar import SolarInputs, size_pv_system
from .solar_data import parse_pvgis

DEMO_PVGIS = Path(__file__).parent / "demo_data" / "pvgis_kathmandu_27deg_south.json"
DEMO_NOTE = ("DEMONSTRATION ONLY. Client, consumption, tariff and costs are illustrative sample inputs, not a real "
             "project or real quotation. Solar data is a real PVGIS v5.3 response for Kathmandu (27° tilt, south).")


def demo_results() -> list:
    res = parse_pvgis(json.loads(DEMO_PVGIS.read_text()), 27.7172, 85.324)
    pv = size_pv_system(SolarInputs(
        daily_consumption_kwh=18, panel_wp=550, panel_area_m2=2.58, resource=res, system_type="hybrid_battery",
        available_area_m2=60, tariff_per_kwh=12.0, currency="NPR", cost_per_kwp=95000,
        backup_kwh_per_day=6, autonomy_days=1, battery_dod_pct=90, battery_voltage_v=48, peak_load_kw=3.5,
        battery_cost_per_kwh=30000, location_label="Kathmandu, Nepal (demo)"))
    vd = cable.voltage_drop("single_phase", 230, 21.7, 35, 6, "copper", 70, 1.0, 0.0, limit_pct=3)
    vd.name = "Inverter AC output cable - voltage drop check"
    load = fundamentals.current_from_power(5.0, 230, 1.0, phases=1)
    load.name = "Inverter AC output current at 5 kW"
    return [pv, load, vd]


def load_demo_project(store) -> int:
    pid = store.create_project("DEMO - Health post rooftop solar (sample data)", client="Sample client (fictional)",
                               location="Kathmandu, Nepal", notes=DEMO_NOTE, is_demo=True)
    for r in demo_results():
        store.save_calculation(pid, "demo", r.name, r.to_dict())
    return pid
