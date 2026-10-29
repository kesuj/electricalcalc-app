"""Home solar design following the step order of Boxwell, *Solar Electricity Handbook* (2012):
power analysis -> inefficiencies -> solar resource (worst month or annual) -> array -> system voltage
-> battery -> controller -> inverter -> cables. Method from the book; data is modern and site-specific
(PVGIS monthly in-plane irradiation for the Nepal site, current battery chemistry values, NPR costs).

Book section numbers are given as § references. Where the book gives no rule (payback, controller
margin, outage-hours battery mode) the rule used is marked [modern/derived].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
SYSTEM_VOLTAGES = (12, 24, 48)
BOOK_REF = "Boxwell, Solar Electricity Handbook (2012)"

# Battery chemistry defaults. Lead-acid figures are the book's (§50, §89). LiFePO4 is not in the 2012 book:
# current datasheet values (e.g. Pylontech US5000: 95 % DoD, >6000 cycles); the app uses a more
# conservative 90 % DoD by default.
CHEMISTRY = {
    "LiFePO4 (lithium)": {"dod": 90.0, "eff": 95.0, "cycles": 6000, "life_years": 12},
    "Lead-acid tubular / traction": {"dod": 50.0, "eff": 95.0, "cycles": 1000, "life_years": 8},
    "Lead-acid gel / leisure": {"dod": 50.0, "eff": 90.0, "cycles": 1000, "life_years": 4},
}
LEAD_ACID_CYCLES = {20: 1600, 40: 1200, 50: 1000, 80: 350}   # §89 cycle-life table


@dataclass
class HomeInputs:
    loads: list[dict]                       # name, power_w, qty, hours_per_day, ac (bool), critical, motor
    monthly_psh: list[float]                # in-plane irradiation kWh/m²/day per month (PVGIS H(i)_d)
    mode: str = "grid_tied"                 # grid_tied | hybrid_backup | off_grid
    months_required: list[int] = field(default_factory=lambda: list(range(1, 13)))
    phantom_w: float = 0.0                  # standby loads, §48
    controller: str = "MPPT"                # MPPT | PWM  (§58: 0.90 / 0.75)
    temp_loss_pct: float = 0.0              # site temperature loss (PVGIS) - replaces the book's ×1.4 rule
    shade_loss_pct: float = 0.0             # §69 / §145
    panel_wp: float = 550.0
    panel_area_m2: float = 2.58
    inverter_eff_pct: float = 93.0
    chemistry: str = "LiFePO4 (lithium)"
    dod_pct: float | None = None
    holdover_days: float = 3.0              # off-grid (§89: 3-5 days)
    outage_hours: float = 4.0               # hybrid backup (Nepal power cuts) [modern/derived]
    system_voltage: int | None = None       # None = choose by the book's cable rule (§85)
    dc_cable_length_m: float = 3.0          # longest low-voltage run (one way)
    max_cable_mm2: float = 6.0              # §85: above this, go up a voltage
    available_area_m2: float | None = None  # roof space; warns if the array does not fit


def power_analysis(loads: list[dict], phantom_w: float = 0.0) -> dict:
    """§48: daily Wh = Σ W × h; peak = Σ W of everything on at once."""
    rows, ac_wh, dc_wh, peak, crit_w, crit_ac_w, motors = [], 0.0, 0.0, 0.0, 0.0, 0.0, []
    for i, r in enumerate(loads, 1):
        name = str(r.get("name") or "").strip()
        if not name and not r.get("power_w"):
            continue
        label = name or f"Row {i}"
        w = require_positive(f"{label}: power", r.get("power_w"))
        n = require_positive(f"{label}: quantity", r.get("qty") or 0)
        h = require_range(f"{label}: hours per day", r.get("hours_per_day") if r.get("hours_per_day") is not None else -1, 0, 24)
        ac = r.get("ac", True) is not False
        wh = w * n * h
        if ac:
            ac_wh += wh
        else:
            dc_wh += wh
        peak += w * n
        if r.get("critical"):
            crit_w += w * n
            crit_ac_w += w * n if ac else 0
        if r.get("motor"):
            motors.append(label)
        rows.append({"Appliance": label, "W": w, "Qty": n, "Hours/day": h, "Wh/day": round(wh, 1),
                     "Supply": "AC 230 V" if ac else "DC", "Backup": "Yes" if r.get("critical") else "",
                     "Motor": "Yes" if r.get("motor") else ""})
    if not rows:
        raise ValidationError("Add at least one appliance.")
    ph = require_positive("Standby (phantom) load", phantom_w, allow_zero=True)
    if ph:
        rows.append({"Appliance": "Standby / phantom loads", "W": ph, "Qty": 1, "Hours/day": 24, "Wh/day": ph * 24,
                     "Supply": "AC 230 V", "Backup": "", "Motor": ""})
        ac_wh += ph * 24
        peak += ph
    return {"rows": rows, "ac_wh": ac_wh, "dc_wh": dc_wh, "daily_wh": ac_wh + dc_wh, "peak_w": peak,
            "critical_w": crit_w, "critical_ac_w": crit_ac_w, "motors": motors}


def book_cable_mm2(length_m: float, current_a: float, voltage_v: float) -> float:
    """§87: CSA = (L × I × 0.04) / (V / 20)  - equivalent to a 5 % drop with copper, L one-way."""
    return length_m * current_a * 0.04 / (voltage_v / 20)


def lead_acid_cycles(dod_pct: float) -> float:
    pts = sorted(LEAD_ACID_CYCLES.items())
    if dod_pct <= pts[0][0]:
        return pts[0][1]
    for (d0, c0), (d1, c1) in zip(pts, pts[1:]):
        if dod_pct <= d1:
            return c0 + (c1 - c0) * (dod_pct - d0) / (d1 - d0)
    return pts[-1][1]


def home_design(x: HomeInputs) -> CalcResult:
    if x.mode not in ("grid_tied", "hybrid_backup", "off_grid"):
        raise ValidationError("Mode must be grid-tied, hybrid backup or off-grid.")
    if len(x.monthly_psh) != 12:
        raise ValidationError("Monthly sunshine data must have 12 values.")
    psh = [require_positive(f"Sunshine {m}", v) for m, v in zip(MONTHS, x.monthly_psh)]
    req = sorted({int(m) for m in x.months_required})
    if not req or not all(1 <= m <= 12 for m in req):
        raise ValidationError("Choose at least one month the system must cover.")
    eta_pp = 0.90 if x.controller == "MPPT" else 0.75
    temp = require_range("Temperature loss", x.temp_loss_pct, 0, 40) / 100
    shade = require_range("Shading loss", x.shade_loss_pct, 0, 80) / 100
    inv = require_range("Inverter efficiency", x.inverter_eff_pct, 50, 100) / 100
    wp = require_range("Panel rating", x.panel_wp, 5, 1000)
    chem = CHEMISTRY.get(x.chemistry)
    if chem is None:
        raise ValidationError("Unknown battery chemistry.")
    dod = require_range("Depth of discharge", x.dod_pct if x.dod_pct is not None else chem["dod"], 10, 100) / 100
    beff = chem["eff"] / 100

    # 1-2. power analysis and inefficiencies (§48, §50). Physically correct division form.
    pa = power_analysis(x.loads, x.phantom_w)
    battery_based = x.mode == "off_grid"
    design_wh = pa["dc_wh"] + pa["ac_wh"] / inv
    if battery_based:
        design_wh /= beff
    equations = ["Daily Wh = Σ (W × qty × hours)  (§48)",
                 "Design Wh = DC Wh + AC Wh ÷ η_inverter" + (" ; then ÷ η_battery" if battery_based else "") + "  (§50)"]

    # 3. solar resource (§56): worst required month (off-grid) or annual average (grid-tied/hybrid, §46)
    if x.mode == "off_grid":
        worst_m = min(req, key=lambda m: psh[m - 1])
        design_psh = psh[worst_m - 1]
        basis = f"worst required month ({MONTHS[worst_m - 1]})"
    else:
        design_psh = sum(p * d for p, d in zip(psh, DAYS)) / 365
        basis = "annual average"
    # 4. array (§56, §58, §59 + shading §145)
    derate = eta_pp * (1 - temp) * (1 - shade)
    array_w = design_wh / design_psh / derate
    n_panels = math.ceil(array_w / wp)
    installed_w = n_panels * wp
    equations += [f"Array W = Design Wh ÷ sun hours ({basis}) ÷ (η_controller × (1 − temperature loss) × (1 − shading))  (§56-§59)",
                  "Panels = ceil(Array W ÷ panel Wp)"]

    outputs = {
        "daily_wh": Q(pa["daily_wh"], "Wh/day", "Appliance energy per day"),
        "design_wh": Q(design_wh, "Wh/day", "Energy the solar must supply per day (after losses)"),
        "peak_w": Q(pa["peak_w"], "W", "Everything switched on at once"),
        "design_psh": Q(design_psh, "kWh/m²/day", f"Sun hours used ({basis})"),
        "array_w": Q(array_w, "W", "Solar array needed"),
        "panel_count": Q(n_panels, "panels", f"Panels of {wp:g} W"),
        "installed_w": Q(installed_w, "W", "Installed solar array"),
        "array_area_m2": Q(n_panels * x.panel_area_m2, "m²", "Roof area for panels"),
    }
    warnings, tables = [], {"Appliance list (power analysis)": pa["rows"]}
    if x.available_area_m2:
        fit = math.floor(require_positive("Roof space", x.available_area_m2) / x.panel_area_m2)
        if fit < n_panels:
            warnings.insert(0, f"Only about {fit} panel{'s' if fit != 1 else ''} fit on {x.available_area_m2:g} m² of roof, but {n_panels} are "
                               "needed. Use higher-wattage panels, a second roof, or accept a smaller system.")

    # 5. system voltage + 7. battery (§85-§89) for battery-based modes
    if x.mode in ("off_grid", "hybrid_backup"):
        if x.mode == "off_grid":
            store_wh = design_wh * require_range("Days of autonomy", x.holdover_days, 0.5, 10)
            bat_load_w = pa["peak_w"]
            equations.append("Battery Wh = Design Wh × days of autonomy  (§89)")
        else:
            if pa["critical_w"] <= 0:
                raise ValidationError("Tick the appliances that must run during power cuts.")
            hrs = require_range("Power-cut hours", x.outage_hours, 0.5, 24)
            store_wh = (pa["critical_w"] - pa["critical_ac_w"] + pa["critical_ac_w"] / inv) * hrs / beff
            bat_load_w = pa["critical_w"]
            equations.append("Battery Wh = backup appliances W (÷ η_inverter for AC) × power-cut hours ÷ η_battery  [modern/derived]")
        inv_w_needed = bat_load_w * 4 / 3
        if x.mode == "hybrid_backup":   # a hybrid inverter also converts all the solar power (DC:AC 1.2)
            inv_w_needed = max(inv_w_needed, installed_w / 1.2)
        if x.system_voltage:
            v_sys = int(x.system_voltage)
            if v_sys not in SYSTEM_VOLTAGES:
                raise ValidationError("System voltage must be 12, 24 or 48 V.")
        else:
            v_sys = 48
            for v in SYSTEM_VOLTAGES:
                i_max = max(bat_load_w / v, installed_w / v)
                if book_cable_mm2(x.dc_cable_length_m, i_max, v) <= x.max_cable_mm2 and not (v == 12 and inv_w_needed > 3000):
                    v_sys = v
                    break
        i_load, i_array = bat_load_w / v_sys, installed_w / v_sys
        cable = book_cable_mm2(x.dc_cable_length_m, max(i_load, i_array), v_sys)
        ah = store_wh / v_sys / dod
        outputs.update({
            "system_v": Q(v_sys, "V", "Battery / system voltage"),
            "battery_usable_wh": Q(store_wh, "Wh", "Energy the battery must deliver"),
            "battery_ah": Q(ah, "Ah", f"Battery capacity at {v_sys} V"),
            "battery_kwh_nominal": Q(ah * v_sys / 1000, "kWh", "Battery nominal capacity"),
            "controller_a": Q(i_array * 1.25, "A", "Charge controller rating (array current × 1.25)"),
            "dc_cable_mm2": Q(cable, "mm²", "Battery/array cable by the book's formula (5 % drop)"),
        })
        equations += ["Battery Ah = Battery Wh ÷ system V ÷ depth of discharge  (§89)",
                      "Current = W ÷ system V  (§86);  Cable mm² = L × I × 0.04 ÷ (V ÷ 20)  (§87)",
                      "System V: lowest of 12/24/48 V keeping that cable ≤ 6 mm²  (§85); 12 V only up to ~3 kW  (§91)",
                      "Controller A = array W ÷ system V × 1.25  [modern margin - the book gives none, §90]"]
        if x.chemistry.startswith("Lead"):
            cyc = lead_acid_cycles(dod * 100)
            days_per_cycle = x.holdover_days if x.mode == "off_grid" else 1
            life = min(cyc * days_per_cycle / 365, chem["life_years"])
            outputs["battery_life_years"] = Q(life, "years", "Estimated battery life")
            equations.append("Lead-acid life = cycles at this DoD × days per cycle, capped by float life  (§89)")
        else:
            outputs["battery_life_years"] = Q(min(chem["cycles"] / 365, chem["life_years"]), "years",
                                              "Estimated battery life (one cycle per day, capped)")
        if cable > x.max_cable_mm2:
            warnings.append(f"Even at {v_sys} V the battery/array cable is {cable:.1f} mm² - shorten the run or use a "
                            "higher-voltage (HV) battery system.")
    else:
        inv_w_needed = installed_w / 1.2  # grid-tied: inverter follows the array (DC/AC 1.2)
        equations.append("Grid-tied inverter ≈ installed array ÷ 1.2 (DC:AC ratio)  [modern]")

    outputs["inverter_w"] = Q(inv_w_needed, "W", "Inverter continuous rating")
    if x.mode == "off_grid":
        equations.append("Inverter W ≥ 4/3 × appliances running at once  (§91)")
    elif x.mode == "hybrid_backup":
        equations.append("Inverter W ≥ max(4/3 × backup appliances (§91), installed array ÷ 1.2)  [modern]")
    if pa["motors"]:
        warnings.append(f"Motor loads ({', '.join(pa['motors'])}) need a high start-up surge rating - check the "
                        "inverter's surge (peak) rating against the appliance datasheets (§91).")

    # Monthly generation vs use (chart data)
    gen = [installed_w * p * derate * d / 1000 for p, d in zip(psh, DAYS)]
    use = [pa["daily_wh"] * d / 1000 for d in DAYS]
    tables["Monthly generation vs use"] = [
        {"Month": m, "Sun hours": round(p, 2), "Solar (kWh)": round(g, 1), "Use (kWh)": round(u, 1),
         "Surplus (kWh)": round(g - u, 1)} for m, p, g, u in zip(MONTHS, psh, gen, use)]
    outputs["annual_generation_kwh"] = Q(sum(gen), "kWh/yr", "Estimated solar generation per year")
    outputs["annual_use_kwh"] = Q(sum(use), "kWh/yr", "Appliance use per year")
    short = [MONTHS[m - 1] for m in req if gen[m - 1] < use[m - 1]]
    if short and x.mode == "off_grid":
        warnings.append(f"Solar is below use in {', '.join(short)}; rely on battery autonomy or a backup generator then.")

    assumptions = [
        f"Method and step order from {BOOK_REF}; sunshine is site data (PVGIS), not the book's UK/US tables.",
        f"Controller factor {eta_pp:g} ({x.controller}) as in the book (§58).",
        f"Temperature loss {temp * 100:.1f}% from the site's PVGIS model (replaces the book's ×1.4 roof rule).",
        f"Battery: {x.chemistry}, depth of discharge {dod * 100:.0f}%, efficiency {beff * 100:.0f}%.",
        "Book cable formula assumes copper and a 5 % voltage drop; final cables must also meet current-rating rules.",
    ]
    if x.mode == "hybrid_backup":
        assumptions.append("Grid is available most of the time; the battery only covers the chosen power-cut hours.")
    return CalcResult(name={"grid_tied": "Home solar - grid-tied", "hybrid_backup": "Home solar - hybrid with power-cut backup",
                            "off_grid": "Home solar - off-grid"}[x.mode],
                      inputs={"mode": Q(x.mode.replace("_", " "), "", "System type"),
                              "controller": Q(x.controller, "", "Charge controller / MPPT"),
                              "panel_wp": Q(wp, "W", "Panel rating"), "inverter_eff": Q(inv * 100, "%", "Inverter efficiency"),
                              "temp_loss": Q(temp * 100, "%", "Temperature loss"), "shade_loss": Q(shade * 100, "%", "Shading loss"),
                              "chemistry": Q(x.chemistry, "", "Battery type"), "dod": Q(dod * 100, "%", "Depth of discharge")},
                      outputs=outputs, equations=equations, assumptions=assumptions, warnings=warnings,
                      references=[BOOK_REF, "PVGIS v5.3 (EC JRC) monthly in-plane irradiation for the site"], tables=tables)


def plain_summary_home(r: CalcResult, saving_rs_year: float | None = None, payback_years: float | None = None,
                       capex_rs: float | None = None) -> list[str]:
    """The home design in plain words (all numbers from the calculation)."""
    o = r.outputs
    n = o["panel_count"].value
    lines = [f"You need {n} solar panel{'s' if n != 1 else ''} of {r.inputs['panel_wp'].value:g} W "
             f"({o['installed_w'].value / 1000:.2f} kW in total), needing about {o['array_area_m2'].value:.0f} m² of roof.",
             f"They should make about {o['annual_generation_kwh'].value:,.0f} units (kWh) a year - about "
             f"{o['annual_generation_kwh'].value / 12:,.0f} a month on average; you use about "
             f"{o['annual_use_kwh'].value / 12:,.0f} units a month.",
             f"Inverter (turns solar power into normal 230 V power): about {o['inverter_w'].value / 1000:.1f} kW."]
    if "battery_kwh_nominal" in o:
        lines.append(f"Battery: {o['battery_ah'].value:,.0f} Ah at {o['system_v'].value} V "
                     f"(about {o['battery_kwh_nominal'].value:.1f} kWh), lasting about {o['battery_life_years'].value:.0f} years.")
    if capex_rs:
        lines.append(f"Estimated cost: about Rs {capex_rs:,.0f} (indicative Nepal prices - get installer quotes).")
    if saving_rs_year:
        lines.append(f"Estimated saving on your NEA bill: about Rs {saving_rs_year:,.0f} per year.")
    if payback_years:
        lines.append(f"The system pays for itself in about {payback_years:.1f} years.")
    lines.append("This is a first estimate. A qualified electrical engineer must check it, the site and the equipment "
                 "before anything is bought or installed.")
    return lines
