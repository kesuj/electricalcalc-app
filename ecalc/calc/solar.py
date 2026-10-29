"""Module B - solar PV preliminary sizing (grid-tied and battery-supported).

Keeps the distinctions explicit:
  energy (kWh)  vs  power (kW / kWp)
  battery nominal capacity (kWh, Ah)  vs  usable capacity (kWh)
  PV DC capacity (kWp)  vs  inverter AC rating (kW)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


@dataclass
class SolarResource:
    """Specific yield of 1 kWp. Either from PVGIS (losses already applied) or from user PSH."""
    annual_kwh_per_kwp: float
    source: str
    monthly_kwh_per_kwp: list[float] = field(default_factory=list)
    losses_included: bool = True
    details: dict = field(default_factory=dict)

    @classmethod
    def from_peak_sun_hours(cls, psh: float, losses_pct: float) -> "SolarResource":
        psh = require_range("Peak sun hours", psh, 0.5, 9)
        losses = require_range("System losses", losses_pct, 0, 50)
        pr = 1 - losses / 100
        return cls(annual_kwh_per_kwp=psh * 365 * pr,
                   source=f"User-entered average of {psh:g} peak sun hours/day (kWh/m²/day on the array plane) "
                          f"with {losses:g}% system losses",
                   losses_included=True,
                   details={"psh": psh, "performance_ratio": pr})


@dataclass
class SolarInputs:
    daily_consumption_kwh: float
    panel_wp: float
    panel_area_m2: float
    resource: SolarResource
    system_type: str = "grid_tied"           # grid_tied | hybrid_battery
    target_offset_pct: float = 100.0
    available_area_m2: float | None = None
    dc_ac_ratio: float = 1.2
    tariff_per_kwh: float | None = None
    export_rate_per_kwh: float = 0.0
    currency: str = "NPR"
    cost_per_kwp: float | None = None
    peak_load_kw: float | None = None
    backup_kwh_per_day: float | None = None
    autonomy_days: float = 1.0
    battery_dod_pct: float = 80.0
    battery_inverter_eff_pct: float = 95.0
    battery_voltage_v: float = 48.0
    battery_cost_per_kwh: float | None = None
    location_label: str = ""


def size_pv_system(inp: SolarInputs) -> CalcResult:
    daily = require_positive("Daily consumption", inp.daily_consumption_kwh)
    wp = require_range("Panel rating", inp.panel_wp, 50, 1000)
    area_panel = require_range("Panel area", inp.panel_area_m2, 0.3, 4)
    offset = require_range("Target offset", inp.target_offset_pct, 1, 200)
    ratio = require_range("DC/AC ratio", inp.dc_ac_ratio, 0.8, 1.6)
    if inp.system_type not in ("grid_tied", "hybrid_battery"):
        raise ValidationError("System type must be 'grid_tied' or 'hybrid_battery'.")
    y = require_positive("Specific yield", inp.resource.annual_kwh_per_kwp)

    warnings: list[str] = []
    assumptions = [
        f"Solar resource: {inp.resource.source}.",
        "Annual energy balance only - hourly mismatch between generation and consumption is not modelled.",
        f"Inverter AC rating = PV DC capacity / DC-to-AC ratio of {ratio:g} (design choice; verify with the "
        "inverter manufacturer's string-sizing tool).",
        "Panel count rounded up; array layout, row spacing, shading and roof setbacks are not modelled.",
    ]
    annual_demand = daily * 365
    kwp_required = annual_demand * offset / 100 / y
    n_panels = math.ceil(kwp_required * 1000 / wp)
    area_limited = False
    if inp.available_area_m2 is not None:
        avail = require_positive("Available area", inp.available_area_m2)
        max_panels = int(avail // area_panel)
        if max_panels < 1:
            raise ValidationError("Available area is smaller than one panel.")
        if n_panels > max_panels:
            area_limited = True
            warnings.append(f"Area limits the array to {max_panels} panels ({max_panels * wp / 1000:.2f} kWp); "
                            f"{n_panels} were needed for the {offset:g}% target.")
            n_panels = max_panels
        assumptions.append("Available area is net usable module area (no allowance for spacing/access added).")
    kwp = n_panels * wp / 1000
    annual_gen = kwp * y
    inverter_kw = kwp / ratio

    outputs: dict[str, Q] = {
        "annual_demand_kwh": Q(annual_demand, "kWh/yr", "Annual consumption (energy)"),
        "kwp_required": Q(kwp_required, "kWp", "PV capacity needed for target (power, DC)"),
        "panel_count": Q(n_panels, "panels", f"Panels of {wp:g} Wp"),
        "pv_kwp": Q(kwp, "kWp", "Installed PV capacity (power, DC)"),
        "array_area_m2": Q(n_panels * area_panel, "m²", "Module area"),
        "specific_yield": Q(y, "kWh/kWp/yr", "Specific yield"),
        "annual_generation_kwh": Q(annual_gen, "kWh/yr", "Estimated annual generation (energy, AC)"),
        "solar_fraction_pct": Q(min(annual_gen / annual_demand, 10) * 100, "%", "Generation / consumption"),
        "inverter_ac_kw": Q(inverter_kw, "kW", "Preliminary inverter AC rating (power)"),
    }
    equations = ["E_demand = daily kWh × 365",
                 "P_PV,required = E_demand × offset / Y   (Y = specific yield, kWh/kWp/yr)",
                 "N_panels = ceil(P_PV × 1000 / Wp_panel)",
                 "E_gen = P_PV,installed × Y",
                 "P_inverter,AC = P_PV / (DC:AC ratio)"]
    tables = {}
    if inp.resource.monthly_kwh_per_kwp:
        tables["Monthly generation estimate"] = [
            {"Month": m, "kWh/kWp": round(v, 1), "Generation (kWh)": round(v * kwp, 0),
             "Consumption (kWh)": round(daily * d, 0)}
            for m, v, d in zip(MONTHS, inp.resource.monthly_kwh_per_kwp, DAYS_IN_MONTH)]

    # ---- battery (hybrid) ---------------------------------------------------------
    battery_kwh_nominal = None
    if inp.system_type == "hybrid_battery":
        backup = require_positive("Backup energy per day", inp.backup_kwh_per_day)
        days = require_range("Days of autonomy", inp.autonomy_days, 0.1, 7)
        dod = require_range("Battery depth of discharge", inp.battery_dod_pct, 10, 100)
        eff = require_range("Battery-to-AC efficiency", inp.battery_inverter_eff_pct, 50, 100)
        vbat = require_range("Battery bank voltage", inp.battery_voltage_v, 12, 1000)
        usable = backup * days
        battery_kwh_nominal = usable / (dod / 100) / (eff / 100)
        outputs.update({
            "battery_usable_kwh": Q(usable, "kWh", "Required usable battery energy"),
            "battery_nominal_kwh": Q(battery_kwh_nominal, "kWh", "Required nominal battery capacity"),
            "battery_ah": Q(battery_kwh_nominal * 1000 / vbat, "Ah", f"Nominal capacity at {vbat:g} V"),
        })
        equations += ["E_usable = backup kWh/day × autonomy days",
                      "E_nominal = E_usable / (DoD × η_battery→AC)",
                      "Ah = E_nominal × 1000 / V_bank"]
        assumptions += [f"Usable battery energy limited by {dod:g}% depth of discharge (check battery warranty).",
                        f"{eff:g}% battery-to-AC conversion efficiency.",
                        "Battery ageing, temperature derating and recharge time are not included."]
        if inp.peak_load_kw:
            pk = require_positive("Peak load", inp.peak_load_kw)
            if inverter_kw < pk:
                outputs["inverter_ac_kw"] = Q(pk, "kW", "Preliminary inverter AC rating (power, set by peak load)")
                warnings.append(f"Inverter rating raised to the {pk:g} kW peak simultaneous load for backup operation.")
            warnings.append("Motor/compressor start-up surge is not checked; confirm inverter surge rating.")
        else:
            warnings.append("Peak simultaneous load not entered - inverter continuous rating for backup "
                            "operation is not verified.")

    # ---- economics ---------------------------------------------------------------
    if inp.tariff_per_kwh is not None:
        tariff = require_positive("Tariff", inp.tariff_per_kwh, allow_zero=True)
        export = require_positive("Export rate", inp.export_rate_per_kwh, allow_zero=True)
        offset_kwh = min(annual_gen, annual_demand)
        excess = max(annual_gen - annual_demand, 0)
        savings = offset_kwh * tariff + excess * export
        outputs["annual_savings"] = Q(savings, f"{inp.currency}/yr", "Estimated annual bill saving")
        equations.append("Saving = min(E_gen, E_demand) × tariff + max(E_gen − E_demand, 0) × export rate")
        assumptions.append(f"Flat tariff of {tariff:g} {inp.currency}/kWh with annual net metering; tariff "
                           "slabs, demand charges, taxes, escalation and degradation are not included.")
        capex = None
        if inp.cost_per_kwp is not None:
            capex = require_positive("Installed cost per kWp", inp.cost_per_kwp) * kwp
            if battery_kwh_nominal and inp.battery_cost_per_kwh:
                capex += require_positive("Battery cost per kWh", inp.battery_cost_per_kwh) * battery_kwh_nominal
            elif battery_kwh_nominal:
                warnings.append("Battery cost not entered - payback excludes battery cost.")
            outputs["capex"] = Q(capex, inp.currency, "Estimated installed cost (user-entered unit costs)")
            if savings > 0:
                outputs["simple_payback_years"] = Q(capex / savings, "years", "Simple payback")
                equations.append("Simple payback = capital cost / annual saving")
        else:
            warnings.append("Installed cost per kWp not entered - payback not calculated.")
    else:
        warnings.append("Electricity tariff not entered - savings and payback not calculated.")

    if offset > 100 and not area_limited:
        warnings.append("Target exceeds 100% of consumption; confirm export is permitted and paid.")
    warnings.append("Preliminary estimate for feasibility only. Final design requires site survey, shading "
                    "analysis, structural check and verification against local codes by a qualified engineer.")

    bom = [{"Item": "PV modules", "Specification": f"{wp:g} Wp, ~{area_panel:g} m² each (user-entered)",
            "Quantity": n_panels, "Note": "Confirm model datasheet"},
           {"Item": "Inverter" if inp.system_type == "grid_tied" else "Hybrid inverter",
            "Specification": f"≈ {outputs['inverter_ac_kw'].value:.2f} kW AC", "Quantity": "1 (or split)",
            "Note": "Check MPPT voltage window vs string design"}]
    if battery_kwh_nominal:
        bom.append({"Item": "Battery bank", "Specification": f"≈ {battery_kwh_nominal:.1f} kWh nominal @ "
                    f"{inp.battery_voltage_v:g} V", "Quantity": "as per module size", "Note": "Chemistry/DoD per datasheet"})
    for item in ("Mounting structure", "DC cables & connectors", "DC isolator / fuses", "AC breaker & isolator",
                 "Surge protection (DC/AC)", "Earthing system", "Energy meter (net/bi-directional)"):
        bom.append({"Item": item, "Specification": "To be sized in detailed design", "Quantity": "-", "Note": ""})
    tables["Preliminary bill of materials"] = bom

    extra_inputs: dict[str, Q] = {}
    if inp.tariff_per_kwh is not None:
        extra_inputs["export_rate"] = Q(inp.export_rate_per_kwh, f"{inp.currency}/kWh", "Export rate")
    if inp.cost_per_kwp is not None:
        extra_inputs["cost_per_kwp"] = Q(inp.cost_per_kwp, f"{inp.currency}/kWp", "Installed cost per kWp")
    if inp.system_type == "hybrid_battery":
        extra_inputs.update({
            "backup_kwh_per_day": Q(inp.backup_kwh_per_day, "kWh/day", "Backup energy required"),
            "autonomy_days": Q(inp.autonomy_days, "days", "Days of autonomy"),
            "battery_dod_pct": Q(inp.battery_dod_pct, "%", "Battery depth of discharge"),
            "battery_inverter_eff_pct": Q(inp.battery_inverter_eff_pct, "%", "Battery-to-AC efficiency"),
            "battery_voltage_v": Q(inp.battery_voltage_v, "V", "Battery bank voltage")})
        if inp.peak_load_kw:
            extra_inputs["peak_load_kw"] = Q(inp.peak_load_kw, "kW", "Peak simultaneous load")
        if inp.battery_cost_per_kwh:
            extra_inputs["battery_cost_per_kwh"] = Q(inp.battery_cost_per_kwh, f"{inp.currency}/kWh", "Battery cost")
    return CalcResult(
        name=f"Solar PV preliminary sizing ({'grid-tied' if inp.system_type == 'grid_tied' else 'hybrid with battery'})",
        inputs={"location": Q(inp.location_label or "not specified", "", "Location"),
                "daily_consumption_kwh": Q(daily, "kWh/day", "Average daily consumption"),
                "target_offset_pct": Q(offset, "%", "Target share of consumption"),
                "panel_wp": Q(wp, "Wp", "Panel rating"), "panel_area_m2": Q(area_panel, "m²", "Panel area"),
                "dc_ac_ratio": Q(ratio, "", "DC/AC ratio"),
                **({"available_area_m2": Q(inp.available_area_m2, "m²", "Available area")} if inp.available_area_m2 else {}),
                **({"tariff": Q(inp.tariff_per_kwh, f"{inp.currency}/kWh", "Tariff")} if inp.tariff_per_kwh is not None else {}),
                **extra_inputs},
        outputs=outputs, equations=equations, assumptions=assumptions, warnings=warnings,
        references=["PVGIS (JRC, European Commission), https://re.jrc.ec.europa.eu/pvg_tools/"]
        if inp.resource.source.startswith("PVGIS") else [],
        tables=tables,
    )
