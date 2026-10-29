"""Full project design: one set of project inputs -> every relevant calculation, in report order.

Order: load schedule (optional) -> solar PV sizing -> inverter AC output current -> AC cable
voltage drop -> battery DC current + cable (hybrid only).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .calc import cable, fundamentals
from .calc.loads import load_schedule
from .calc.result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range
from .calc.solar import SolarInputs, SolarResource, size_pv_system


@dataclass
class ProjectDesign:
    resource: SolarResource
    location_label: str = ""
    # demand: either a load list or a monthly bill figure
    loads: list[dict] = field(default_factory=list)
    diversity_factor: float = 0.8
    monthly_kwh: float | None = None
    peak_load_kw: float | None = None
    backup_kwh_per_day: float | None = None
    # system
    system_type: str = "grid_tied"
    panel_wp: float = 550
    panel_area_m2: float = 2.58
    available_area_m2: float | None = None
    target_offset_pct: float = 100
    dc_ac_ratio: float = 1.2
    battery_voltage_v: float = 48
    battery_dod_pct: float = 80
    autonomy_days: float = 1
    # economics
    currency: str = "NPR"
    tariff_per_kwh: float | None = None
    export_rate_per_kwh: float = 0
    cost_per_kwp: float | None = None
    battery_cost_per_kwh: float | None = None
    # cables
    supply_phases: int = 1
    supply_voltage_v: float = 230
    ac_cable_length_m: float = 20
    ac_drop_limit_pct: float = 3
    dc_cable_length_m: float = 3
    dc_drop_limit_pct: float = 1
    conductor: str = "copper"
    conductor_temp_c: float = 70


def battery_dc_current(inverter_kw: float, battery_voltage_v: float, efficiency_pct: float = 95) -> CalcResult:
    p = require_positive("Inverter power", inverter_kw)
    v = require_positive("Battery voltage", battery_voltage_v)
    eff = require_range("Inverter efficiency", efficiency_pct, 50, 100)
    i = p * 1000 / (v * eff / 100)
    return CalcResult(
        name="Battery DC current at full inverter output",
        inputs={"inverter_kw": Q(p, "kW", "Inverter AC output"), "battery_voltage_v": Q(v, "V", "Battery bank voltage"),
                "efficiency_pct": Q(eff, "%", "Inverter efficiency (DC→AC)")},
        outputs={"dc_current_a": Q(i, "A", "Battery-side DC current")},
        equations=["I_DC = P_AC / (V_bat × η)"],
        assumptions=["Nominal battery voltage; at low state of charge the voltage is lower and the current higher."],
        warnings=["Battery fuse/breaker and cable rating must follow the battery and inverter manufacturers' instructions."],
    )


def run_full_design(d: ProjectDesign) -> list[CalcResult]:
    results: list[CalcResult] = []
    peak_kw, backup = d.peak_load_kw, d.backup_kwh_per_day
    if d.loads:
        ls = load_schedule(d.loads, d.diversity_factor)
        results.append(ls)
        daily = ls.out("daily_kwh")
        peak_kw = peak_kw or ls.out("max_demand_kw")
        if backup is None and ls.out("critical_kwh") > 0:
            backup = ls.out("critical_kwh")
    elif d.monthly_kwh:
        daily = require_positive("Monthly consumption", d.monthly_kwh) * 12 / 365
    else:
        raise ValidationError("Enter either a load list or the monthly consumption from the electricity bill.")
    if daily <= 0:
        raise ValidationError("Daily consumption must be greater than zero.")

    hybrid = d.system_type == "hybrid_battery"
    if hybrid and not backup:
        raise ValidationError("For a hybrid system, mark critical loads in the load list or enter the backup energy per day.")
    pv = size_pv_system(SolarInputs(
        daily_consumption_kwh=daily, panel_wp=d.panel_wp, panel_area_m2=d.panel_area_m2, resource=d.resource,
        system_type=d.system_type, target_offset_pct=d.target_offset_pct, available_area_m2=d.available_area_m2,
        dc_ac_ratio=d.dc_ac_ratio, tariff_per_kwh=d.tariff_per_kwh, export_rate_per_kwh=d.export_rate_per_kwh,
        currency=d.currency, cost_per_kwp=d.cost_per_kwp, peak_load_kw=peak_kw if hybrid else None,
        backup_kwh_per_day=backup if hybrid else None, autonomy_days=d.autonomy_days,
        battery_dod_pct=d.battery_dod_pct, battery_voltage_v=d.battery_voltage_v,
        battery_cost_per_kwh=d.battery_cost_per_kwh, location_label=d.location_label))
    results.append(pv)

    inv_kw = pv.out("inverter_ac_kw")
    if d.supply_phases not in (1, 3):
        raise ValidationError("Supply must be single-phase or three-phase.")
    cur = fundamentals.current_from_power(inv_kw, d.supply_voltage_v, 1.0, d.supply_phases)
    cur.name = "Inverter AC output current (at rated output, PF 1.0)"
    cur.assumptions.append("Inverter operating at rated output and unity power factor.")
    results.append(cur)

    system = "three_phase" if d.supply_phases == 3 else "single_phase"
    ac = cable.minimum_size_for_drop(system, d.supply_voltage_v, cur.out("current_a"), d.ac_cable_length_m,
                                     d.ac_drop_limit_pct, d.conductor, d.conductor_temp_c, 1.0)
    ac.name = "Inverter-to-main-board AC cable (voltage-drop sizing)"
    results.append(ac)

    if hybrid:
        dc_i = battery_dc_current(inv_kw, d.battery_voltage_v)
        results.append(dc_i)
        dc = cable.minimum_size_for_drop("dc", d.battery_voltage_v, dc_i.out("dc_current_a"), d.dc_cable_length_m,
                                         d.dc_drop_limit_pct, d.conductor, d.conductor_temp_c)
        dc.name = "Battery-to-inverter DC cable (voltage-drop sizing)"
        results.append(dc)
    return results


def summary(results: list[CalcResult]) -> dict[str, str]:
    """Headline numbers for the dashboard."""
    out: dict[str, str] = {}
    for r in results:
        o = r.outputs
        if r.name == "Load schedule":
            out["Daily energy"] = f"{o['daily_kwh'].value:,.1f} kWh/day"
            out["Maximum demand"] = f"{o['max_demand_kw'].value:,.2f} kW"
        elif r.name.startswith("Solar PV"):
            out["PV array"] = f"{o['pv_kwp'].value:,.2f} kWp ({o['panel_count'].value} panels)"
            out["Annual generation"] = f"{o['annual_generation_kwh'].value:,.0f} kWh/yr"
            out["Inverter"] = f"{o['inverter_ac_kw'].value:,.2f} kW AC"
            if "battery_nominal_kwh" in o:
                out["Battery"] = (f"{o['battery_nominal_kwh'].value:,.1f} kWh "
                                  f"({o['battery_usable_kwh'].value:,.1f} usable)")
            if "annual_savings" in o:
                out["Annual saving"] = f"{o['annual_savings'].value:,.0f} {o['annual_savings'].unit}"
            if "simple_payback_years" in o:
                out["Simple payback"] = f"{o['simple_payback_years'].value:,.1f} years"
        elif r.name.startswith("Inverter-to-main-board"):
            out["AC cable (VD only)"] = f"{o['min_size_mm2'].value:g} mm² ({o['voltage_drop_pct'].value:.2f}%)"
        elif r.name.startswith("Battery-to-inverter"):
            out["Battery cable (VD only)"] = f"{o['min_size_mm2'].value:g} mm² ({o['voltage_drop_pct'].value:.2f}%)"
    return out
