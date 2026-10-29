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
    coincidence_factor: float = 1.0
    monthly_kwh: float | None = None
    peak_load_kw: float | None = None
    backup_kwh_per_day: float | None = None   # engineer input; otherwise derived from outage hours
    outage_hours: float | None = None         # layman input: hours of power cut per day to cover
    backup_loads: list[dict] = field(default_factory=list)  # bill mode: appliances needed during power cuts
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
    ac_cable_length_m: float | None = None   # None = cable check skipped
    ac_drop_limit_pct: float | None = None
    dc_cable_length_m: float | None = None
    dc_drop_limit_pct: float | None = None
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
        ls = load_schedule(d.loads, d.coincidence_factor)
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
    if hybrid and d.backup_kwh_per_day is None and d.outage_hours:
        hours = require_range("Power-cut hours per day", d.outage_hours, 0.5, 24)
        if d.loads:
            crit_kw = results[0].out("critical_kw")
        else:
            if not any(r.get("name") or r.get("power_w") for r in d.backup_loads):
                raise ValidationError("Choose at least one appliance that must work during power cuts.")
            bl = load_schedule([dict(r, critical=True, hours_per_day=hours) for r in d.backup_loads])
            bl.name = "Backup loads (needed during power cuts)"
            results.append(bl)
            crit_kw = bl.out("connected_kw")
            peak_kw = peak_kw or crit_kw
        if crit_kw <= 0:
            raise ValidationError("Choose at least one appliance that must work during power cuts.")
        backup = crit_kw * hours
    if hybrid and not backup:
        raise ValidationError("For a backup (battery) system, choose the appliances needed during power cuts "
                              "and the hours of power cut per day.")
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
    if d.ac_cable_length_m:
        if not d.ac_drop_limit_pct:
            raise ValidationError("Enter the AC voltage-drop limit (%) for the inverter cable.")
        ac = cable.minimum_size_for_drop(system, d.supply_voltage_v, cur.out("current_a"), d.ac_cable_length_m,
                                         d.ac_drop_limit_pct, d.conductor, d.conductor_temp_c, 1.0)
        ac.name = "Inverter-to-main-board AC cable (voltage-drop sizing)"
        results.append(ac)
    else:
        cur.warnings.append("Inverter AC cable not checked: cable length was not entered.")

    if hybrid:
        dc_i = battery_dc_current(inv_kw, d.battery_voltage_v)
        results.append(dc_i)
        if d.dc_cable_length_m:
            if not d.dc_drop_limit_pct:
                raise ValidationError("Enter the DC voltage-drop limit (%) for the battery cable.")
            dc = cable.minimum_size_for_drop("dc", d.battery_voltage_v, dc_i.out("dc_current_a"), d.dc_cable_length_m,
                                             d.dc_drop_limit_pct, d.conductor, d.conductor_temp_c)
            dc.name = "Battery-to-inverter DC cable (voltage-drop sizing)"
            results.append(dc)
        else:
            dc_i.warnings.append("Battery DC cable not checked: cable length was not entered.")
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


def plain_summary(results: list[CalcResult]) -> list[str]:
    """The design in plain words for a non-engineer (all numbers come from the calculations)."""
    lines: list[str] = []
    pv = next((r for r in results if r.name.startswith("Solar PV")), None)
    if pv is None:
        return lines
    o = pv.outputs
    n = o["panel_count"].value
    lines.append(f"You need {n} solar panel{'s' if n != 1 else ''} of {pv.inputs['panel_wp'].value:g} W each "
                 f"({o['pv_kwp'].value:.2f} kW in total), needing about {o['array_area_m2'].value:.0f} m² of roof.")
    gen = o["annual_generation_kwh"].value
    lines.append(f"They should produce about {gen:,.0f} units (kWh) a year - about {gen / 12:,.0f} units a month on "
                 f"average, less in the monsoon and more in spring - which is about "
                 f"{min(o['solar_fraction_pct'].value, 999):.0f}% of the electricity you use.")
    lines.append(f"Inverter (the box that turns solar power into normal household power): about "
                 f"{o['inverter_ac_kw'].value:.1f} kW.")
    if "battery_nominal_kwh" in o:
        lines.append(f"Battery: about {o['battery_nominal_kwh'].value:.1f} kWh in total, of which "
                     f"{o['battery_usable_kwh'].value:.1f} kWh can be used during power cuts.")
    if "annual_savings" in o:
        lines.append(f"Estimated saving on electricity bills: about {o['annual_savings'].value:,.0f} "
                     f"{o['annual_savings'].unit.split('/')[0]} per year.")
    if "simple_payback_years" in o:
        lines.append(f"The system would pay for itself in about {o['simple_payback_years'].value:.1f} years.")
    for r in results:
        if r.name.startswith("Inverter-to-main-board"):
            lines.append(f"Cable from inverter to main switchboard: at least {r.out('min_size_mm2'):g} mm² "
                         f"{r.inputs['material'].value} (by voltage drop).")
        if r.name.startswith("Battery-to-inverter"):
            lines.append(f"Battery cable: at least {r.out('min_size_mm2'):g} mm² {r.inputs['material'].value} "
                         f"(by voltage drop).")
    lines.append("This is a first estimate. A qualified electrical engineer must check it, the site and the "
                 "equipment before anything is bought or installed.")
    return lines
