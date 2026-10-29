"""Home solar INSTALLATION PACKAGE: everything to buy, how to wire it, how to install, test and maintain.

Builds on the sizing from ecalc.calc.home (Boxwell, Solar Electricity Handbook). Installation order,
wiring practice, commissioning, maintenance and troubleshooting follow the book's chapters (§104-§112,
§117-§139), paraphrased and updated for modern equipment (LiFePO4, MPPT hybrid inverters) and Nepal
(NEPQA-2025 equipment floors, NEA connection rules). Cable sizes satisfy BOTH the current-carrying rule
(ecalc.calc.ampacity) and a voltage-drop limit (ecalc.calc.cable).

Defaults marked [typical] are common market values that the user should replace with the datasheet
of the equipment actually bought.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import ampacity
from .cable import minimum_size_for_drop, voltage_drop
from .home import HomeInputs
from .result import CalcResult, ValidationError, require_positive, require_range
from .strings import string_sizing
from ..nepal_data import NEPQA, site_temperatures

INVERTER_SIZES_KW = [0.5, 1, 1.5, 2, 3, 3.6, 4, 5, 6, 8, 10, 12, 15, 20]
CONTROLLER_SIZES_A = [10, 20, 30, 40, 50, 60, 80, 100]
SPD_CLASSES_V = [150, 600, 1000, 1200, 1500]
ISOLATOR_CLASSES_V = [150, 600, 1000, 1200, 1500]
ISOLATOR_CURRENTS_A = [16, 25, 32, 40, 63, 80, 100, 125, 160, 200, 250]
REF = "Boxwell, Solar Electricity Handbook"


@dataclass
class InstallInputs:
    """Extra installation answers. Datasheet defaults are [typical] - replace with the real equipment."""
    # PV module datasheet [typical 550 W TOPCon-class]
    voc: float = 49.5
    vmp: float = 41.6
    isc: float = 14.0
    imp: float = 13.2
    beta_voc_pct: float = -0.25
    module_max_fuse_a: float = 25.0
    panel_width_m: float = 1.134
    # grid-tied string inverter [typical 3-6 kW single-phase]
    grid_inv_vdc_max: float = 600.0
    grid_inv_mppt_min: float = 90.0
    grid_inv_mppt_max: float = 550.0
    grid_inv_mppt_current_a: float = 15.0
    grid_inv_mppts: int = 2
    # hybrid inverter with low-voltage (48 V) battery [typical]
    hybrid_vdc_max: float = 500.0
    hybrid_mppt_min: float = 125.0
    hybrid_mppt_max: float = 425.0
    hybrid_mppt_current_a: float = 18.0
    hybrid_mppts: int = 2
    # off-grid MPPT charge controller [typical "150 V" class]
    controller_voc_max: float = 150.0
    # battery module (None = one module per series string at the system voltage)
    battery_module_v: float | None = None
    battery_module_ah: float | None = None     # None = 100 Ah LiFePO4 / 150 Ah lead-acid
    # cable routes, one way (m)
    len_array_to_inverter_m: float = 15.0
    len_battery_to_inverter_m: float = 2.0
    len_inverter_to_db_m: float = 10.0
    len_earth_pit_m: float = 10.0
    # site
    site_name: str = ""
    t_min_c: float | None = None              # record low; None = from site table or -5 °C
    t_max_c: float | None = None              # record high; None = from site table or 40 °C
    roof: str = "RCC flat roof"               # "RCC flat roof" | "Tin / sloping roof"
    inverter_location: str = "indoor"         # "indoor" | "outdoor"
    panels_per_row: int | None = None
    ac_phases: int = 1
    pv_vd_limit_pct: float = 2.0
    battery_vd_limit_pct: float = 1.0
    ac_vd_limit_pct: float = 1.5


@dataclass
class InstallPackage:
    bom: list[dict]
    strings: dict
    cable_schedule: list[dict]
    sld: dict
    steps: list[tuple[str, list[str]]]
    tests_table: list[dict]
    maintenance: list[dict]
    troubleshooting: list[dict]
    safety: list[str]
    warnings: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


def _next(options, need):
    for o in options:
        if o >= need:
            return o
    return None


def _vd_size(system, v, i, length, limit):
    try:
        return minimum_size_for_drop(system, v, i, length, limit, "copper", 70.0, 1.0).out("min_size_mm2")
    except ValidationError:
        return None


def _vd_pct(system, v, i, length, size):
    return voltage_drop(system, v, i, length, size, "copper", 70.0, 1.0).out("voltage_drop_pct")


def _cable_row(circuit, route, length, system, voltage, ib, device, ambient, limit, min_size, warnings):
    """Chosen size = max(current rule, voltage-drop rule, minimum)."""
    s_cur = ampacity.size_for_current(device or ib, ambient, min_size=1.5)
    s_vd = _vd_size(system, voltage, ib, length, limit)
    if s_vd is None:
        warnings.append(f"{circuit}: no standard cable meets {limit:g}% voltage drop over {length:g} m - shorten the run.")
        s_vd = 240
    chosen = max(s_cur, s_vd, min_size)
    return {"Circuit": circuit, "From → To": route, "Length (m)": length, "Design current (A)": round(ib, 1),
            "Protective device (A)": device if device else "-", "Size for current (mm²)": s_cur,
            "Size for voltage drop (mm²)": s_vd, "Chosen (mm²)": chosen,
            "Voltage drop (%)": round(_vd_pct(system, voltage, ib, length, chosen), 2)}, chosen


def _arrange_strings(n_panels: int, n_min: int, n_max: int, max_strings: int) -> tuple[int, int, list[str]]:
    """Pick modules per string (as long as possible) and strings in parallel; may round panels up."""
    notes = []
    if n_min > n_max:
        raise ValidationError("No safe string length exists for this panel and inverter at the site temperatures "
                              f"(minimum {n_min} > maximum {n_max}). Choose a different inverter or panel.")
    if n_panels < n_min:
        notes.append(f"{n_panels} panel(s) cannot reach the inverter's minimum voltage; at least {n_min} in series are "
                     f"needed. The design is raised to {n_min} panels.")
        return n_min, 1, notes
    for s in range(min(n_max, n_panels), n_min - 1, -1):     # prefer an exact split
        if n_panels % s == 0 and n_panels // s <= max_strings:
            return s, n_panels // s, notes
    s = min(n_max, n_panels)
    p = math.ceil(n_panels / s)
    notes.append(f"Panels rounded up from {n_panels} to {s * p} to make {p} equal string(s) of {s}.")
    return s, p, notes


def build_home_install(design: CalcResult, x: HomeInputs, ii: InstallInputs) -> InstallPackage:
    require_inputs(ii)
    o = design.outputs
    mode = x.mode
    warnings: list[str] = []
    temps = site_temperatures(ii.site_name) if ii.site_name else None
    t_min = ii.t_min_c if ii.t_min_c is not None else (temps[0] if temps else -5.0)
    t_max = ii.t_max_c if ii.t_max_c is not None else (temps[1] if temps else 40.0)
    ambient = min(require_range("Maximum temperature", t_max, -10, 55), 55)
    n_design = int(o["panel_count"].value)
    wp = x.panel_wp
    eta = x.inverter_eff_pct / 100
    v_sys = o["system_v"].value if "system_v" in o else None

    # ---- 1. string design against the PV input (inverter or charge controller) -------------------
    if mode == "grid_tied":
        vdc, lo, hi, i_mppt, n_mppt = (ii.grid_inv_vdc_max, ii.grid_inv_mppt_min, ii.grid_inv_mppt_max,
                                       ii.grid_inv_mppt_current_a, ii.grid_inv_mppts)
        pv_input = "grid-tied inverter"
    elif mode == "hybrid_backup":
        vdc, lo, hi, i_mppt, n_mppt = (ii.hybrid_vdc_max, ii.hybrid_mppt_min, ii.hybrid_mppt_max,
                                       ii.hybrid_mppt_current_a, ii.hybrid_mppts)
        pv_input = "hybrid inverter"
    else:
        vdc = ii.controller_voc_max
        lo, hi = v_sys * 1.2 + 5, vdc * 0.97      # Vmp must stay above battery charging voltage [typical rule]
        i_mppt, n_mppt = None, 1
        pv_input = "MPPT charge controller"
    sz = string_sizing(ii.voc, ii.vmp, ii.isc, ii.beta_voc_pct, t_min, t_max, vdc, lo, hi, imp=ii.imp,
                       mppt_max_current_a=i_mppt, module_max_fuse_a=ii.module_max_fuse_a)
    n_min, n_max = int(sz.out("n_min")), int(sz.out("n_max"))
    per_mppt = int(sz.out("strings_per_mppt")) if i_mppt else 999
    if i_mppt and per_mppt < 1:
        warnings.append(f"Panel Imp {ii.imp:g} A is above the {i_mppt:g} A MPPT input limit - the inverter will clip; "
                        "check its maximum short-circuit current rating.")
        per_mppt = 1
    s, p, notes = _arrange_strings(n_design, n_min, n_max, per_mppt * n_mppt)
    warnings += notes
    if p > per_mppt * n_mppt:
        warnings.append(f"{p} strings exceed the {pv_input}'s {n_mppt} MPPT input(s) × {per_mppt} string(s) - "
                        "choose a larger model or a second unit.")
    n_panels = s * p
    kwp = n_panels * wp / 1000
    voc_cold = sz.out("voc_max_v") * s
    vmp_stc = ii.vmp * s
    sf = string_sizing(ii.voc, ii.vmp, ii.isc, ii.beta_voc_pct, t_min, t_max, vdc, lo, hi,
                       module_max_fuse_a=ii.module_max_fuse_a, strings_in_parallel=max(p, 1))
    fuses_needed = p >= 2 and sf.outputs["fuse_needed"].value == "Yes"
    fuse_a = sf.out("fuse_rating_a") if fuses_needed else None
    strings = {"modules_per_string": s, "strings": p, "panels": n_panels, "kwp": kwp,
               "string_voc_stc_v": ii.voc * s, "string_voc_cold_v": voc_cold, "string_vmp_stc_v": vmp_stc,
               "string_vmp_hot_v": sz.out("vmp_hot_v") * s, "n_min": n_min, "n_max": n_max,
               "pv_input": pv_input, "pv_input_limits": f"max {vdc:g} V, MPPT {lo:.0f}-{hi:.0f} V",
               "t_min_c": t_min, "t_max_c": t_max, "string_fuses": fuse_a}

    # ---- 2. inverter / controller ratings -------------------------------------------------------
    loads = [r for r in x.loads if r.get("power_w")]
    backup_loads = [r for r in loads if r.get("critical")] if mode == "hybrid_backup" else loads
    motors = [r["power_w"] for r in backup_loads if r.get("motor")]
    run_w = sum(r["power_w"] * (r.get("qty") or 1) for r in backup_loads)
    surge_w = run_w + 2 * max(motors, default=0)        # largest motor starts at ~3× running [typical]
    inv_kw = _next(INVERTER_SIZES_KW, o["inverter_w"].value / 1000) or math.ceil(o["inverter_w"].value / 1000)

    # ---- 3. cables, protection ------------------------------------------------------------------
    sched: list[dict] = []
    i_string = 1.25 * ii.isc                                  # IEC 62548 design current for string cable
    row, pv_mm2 = _cable_row("PV string cable (each string, + and −)", f"Array → {pv_input}",
                             ii.len_array_to_inverter_m, "dc", vmp_stc, ii.imp, fuse_a or i_string, ambient,
                             ii.pv_vd_limit_pct, 4.0, warnings)
    row["Design current (A)"] = round(i_string, 1)
    sched.append(row)
    bat_rows = {}
    if mode in ("hybrid_backup", "off_grid"):
        i_dis = inv_kw * 1000 / (v_sys * eta)
        i_chg = kwp * 1000 / v_sys
        ib = max(i_dis, i_chg)
        bat_fuse = ampacity.device_rating(ib)
        row, bat_mm2 = _cable_row("Battery cable (+ and −)", "Battery bank → fuse/isolator → inverter",
                                  ii.len_battery_to_inverter_m, "dc", v_sys, ib, bat_fuse, ambient,
                                  ii.battery_vd_limit_pct, 6.0, warnings)
        sched.append(row)
        bat_rows = {"i_discharge": i_dis, "i_charge": i_chg, "ib": ib, "fuse": bat_fuse, "mm2": bat_mm2}
        if mode == "off_grid":
            ctrl_a = _next(CONTROLLER_SIZES_A, o["controller_a"].value)
            n_ctrl = 1 if ctrl_a else math.ceil(o["controller_a"].value / 100)
            ctrl_a = ctrl_a or 100
            row, _ = _cable_row("Controller → battery", "Charge controller → battery busbar", 1.5, "dc", v_sys,
                                ctrl_a / 1.25, ctrl_a, ambient, ii.battery_vd_limit_pct, 6.0, warnings)
            sched.append(row)
    ac_v = 230.0 if ii.ac_phases == 1 else 400.0
    i_ac = inv_kw * 1000 / (ac_v if ii.ac_phases == 1 else math.sqrt(3) * ac_v)
    ac_mcb = ampacity.device_rating(i_ac)
    row, ac_mm2 = _cable_row("Inverter AC output", "Inverter → distribution board", ii.len_inverter_to_db_m,
                             "single_phase" if ii.ac_phases == 1 else "three_phase", ac_v, i_ac, ac_mcb, ambient,
                             ii.ac_vd_limit_pct, 2.5, warnings)
    sched.append(row)
    pe_mm2 = ac_mm2 if ac_mm2 <= 16 else max(16, ac_mm2 / 2)
    sched += [{"Circuit": "PV frame bonding (earth)", "From → To": "Each panel frame / rail → earth bar", "Length (m)": "-",
               "Design current (A)": "-", "Protective device (A)": "-", "Size for current (mm²)": "-",
               "Size for voltage drop (mm²)": "-", "Chosen (mm²)": 6, "Voltage drop (%)": "-"},
              {"Circuit": "Main earthing conductor", "From → To": "Main earth bar → earth electrode",
               "Length (m)": ii.len_earth_pit_m, "Design current (A)": "-", "Protective device (A)": "-",
               "Size for current (mm²)": "-", "Size for voltage drop (mm²)": "-", "Chosen (mm²)": 16, "Voltage drop (%)": "-"},
              {"Circuit": "Inverter / DB protective earth (PE)", "From → To": "Inverter → DB earth bar", "Length (m)": ii.len_inverter_to_db_m,
               "Design current (A)": "-", "Protective device (A)": "-", "Size for current (mm²)": "-",
               "Size for voltage drop (mm²)": "-", "Chosen (mm²)": pe_mm2, "Voltage drop (%)": "-"}]

    iso_v = _next(ISOLATOR_CLASSES_V, voc_cold) or 1500
    iso_a = _next(ISOLATOR_CURRENTS_A, 1.25 * ii.isc * max(1, min(p, per_mppt)))
    spd_v = _next(SPD_CLASSES_V, voc_cold) or 1500

    # ---- 4. bill of materials ---------------------------------------------------------------------
    rows_n = ii.panels_per_row or min(n_panels, 8)
    n_rows = math.ceil(n_panels / rows_n)
    rail_m = 2 * n_panels * (ii.panel_width_m + 0.02)
    flat = ii.roof.startswith("RCC")
    bom: list[dict] = []

    def add(item, spec, qty, why):
        bom.append({"Item": item, "Specification": spec, "Qty": qty, "Why / rule": why})

    eff_floor = NEPQA["module_min_eff_pct"]
    add("Solar PV module", f"{wp:g} Wp mono/TOPCon, Voc {ii.voc:g} V, Vmp {ii.vmp:g} V, Isc {ii.isc:g} A, efficiency ≥ "
        f"{eff_floor:g} %, power warranty ≥ 80 % at 25 yr, IEC 61215/61730", n_panels,
        f"Array {s} in series × {p} string(s) = {kwp:.2f} kWp; NEPQA-2025 module floors")
    add("Mounting structure", ("Hot-dip galvanised / aluminium tilt frame with anchor bolts, tilt as designed"
                               if flat else "Aluminium rails with L-feet / roof hooks fixed into purlins (not just sheet)"),
        f"{n_rows} row(s) of up to {rows_n}", f"{REF} §123; roof must carry the weight - check structure")
    add("Mounting rails", "Aluminium PV rail (2 per row of panels)", f"{math.ceil(rail_m)} m", "2 rails under each panel")
    add("End clamps / mid clamps", "Matching panel frame thickness", f"{4 * n_rows} end / {2 * (n_panels - n_rows)} mid",
        "4 end clamps per row, 2 mid clamps between neighbouring panels")
    add("Roof feet / anchors", "Stainless fixings, sealed against leaks", math.ceil(rail_m / 1.2) + 2 * n_rows,
        "One fixing about every 1.2 m of rail")
    add("PV cable (red and black)", f"{pv_mm2:g} mm² solar cable EN 50618 (H1Z2Z2-K), UV resistant, 1500 V DC",
        f"{math.ceil(p * (ii.len_array_to_inverter_m + 3))} m red + same black", "Cable schedule; book §87, §110")
    add("MC4 connector pairs", "Same brand as panel connectors (never mix brands)", 2 * p + 2, "Field-made string ends + spares")
    if fuses_needed:
        add("PV string fuse + holder (in combiner box)", f"{fuse_a} A gPV fuse, {iso_v:g} V DC", 2 * p,
            "IEC 62548: 1.5×Isc ≤ In ≤ module max series fuse; both + and −")
        add("PV combiner box", f"IP65, {p} string inputs with fuses, {iso_v:g} V DC", 1, "Joins parallel strings safely")
    add("DC isolator (PV)", f"{iso_v:g} V DC, ≥ {iso_a} A, 2-pole, lockable", n_mppt if mode != "off_grid" else 1,
        f"Rated above cold string Voc {voc_cold:.0f} V and 1.25 × Isc; book §79, §80, §109")
    add("DC surge protection device (Type 2, PV)", f"Ucpv ≥ {spd_v:g} V DC, In ≥ 20 kA", 1,
        "Lightning-induced surges are common in Nepal; above cold string Voc")
    if mode == "grid_tied":
        add("Grid-tied (on-grid) inverter", f"{inv_kw:g} kW, PV input max {vdc:g} V, MPPT {lo:g}-{hi:g} V, ≥ {n_mppt} MPPT; "
            f"efficiency ≥ {NEPQA['grid_inv_min_eff_pct_upto_5kva' if inv_kw <= 5 else 'grid_inv_min_eff_pct_over_5kva']:g} % "
            "peak, anti-islanding, IP65 if outdoor", 1, "NEPQA-2025 inverter floors; book §83")
    elif mode == "hybrid_backup":
        add("Hybrid inverter (low-voltage battery)", f"{inv_kw:g} kW continuous, surge ≥ {surge_w / 1000:.1f} kW, battery "
            f"{v_sys:g} V, PV max {vdc:g} V, MPPT {lo:g}-{hi:g} V, pure sine 230 V 50 Hz, grid + backup outputs",
            1, "Carries backup loads (×4/3, book §91) and the whole array")
    else:
        add("MPPT charge controller", f"{ctrl_a} A, {v_sys:g} V battery, PV max {vdc:g} V, efficiency ≥ "
            f"{NEPQA['mppt_min_eff_pct']:g} %, battery-type setting for {x.chemistry}", n_ctrl,
            "Array current × 1.25; NEPQA MPPT floor; book §90")
        add("Off-grid inverter", f"{inv_kw:g} kW continuous, surge ≥ {surge_w / 1000:.1f} kW, {v_sys:g} V DC input, pure sine "
            "230 V 50 Hz", 1, "≥ 4/3 × loads running together (book §91); motors need surge")
    if mode in ("hybrid_backup", "off_grid"):
        lfp = x.chemistry.startswith("LiFePO4")
        mod_v = ii.battery_module_v or v_sys
        mod_ah = ii.battery_module_ah or (100.0 if lfp else 150.0)
        if mod_v > v_sys or v_sys % mod_v:
            raise ValidationError(f"Battery module voltage {mod_v:g} V does not divide the {v_sys:g} V system voltage.")
        n_ser = int(v_sys // mod_v)
        n_par = math.ceil(o["battery_ah"].value / mod_ah)
        strings["battery_series"], strings["battery_parallel"] = n_ser, n_par
        strings["battery_kwh"] = n_ser * n_par * mod_v * mod_ah / 1000
        spec = (f"LiFePO4 {mod_v:g} V {mod_ah:g} Ah with BMS, ≥ {NEPQA['li_min_cycles_at_80dod']} cycles @ 80 % DoD, "
                f"round-trip ≥ {NEPQA['li_min_rte_pct']:g} %, warranty ≥ {NEPQA['battery_warranty_yr']} yr, communication "
                "with inverter (CAN/RS485)" if lfp else
                f"Deep-cycle lead-acid {mod_v:g} V {mod_ah:g} Ah (tubular/traction), same make and age")
        add("Battery", spec, n_ser * n_par, f"{n_ser} in series × {n_par} in parallel = {strings['battery_kwh']:.1f} kWh; "
            f"needs {o['battery_ah'].value:.0f} Ah at {v_sys:g} V (book §89)")
        add("Battery cable (red and black)", f"{bat_rows['mm2']:g} mm² flexible copper, crimped lugs",
            f"{math.ceil(2 * ii.len_battery_to_inverter_m + 1)} m each colour", "Cable schedule; keep as short as possible (§125)")
        add("Battery fuse (DC, high breaking capacity)", f"{bat_rows['fuse']} A NH/ANL/class-T DC fuse", 1,
            f"≥ 1.25 × max battery current {bat_rows['ib']:.0f} A; on the + terminal so all current passes (§109)")
        add("Battery isolator / DC breaker", f"{_next(ISOLATOR_CURRENTS_A, bat_rows['fuse']) or bat_rows['fuse']} A, "
            f"{v_sys:g} V DC rated", 1, "Lets you disconnect the battery safely (book §79)")
        if n_par > 1:
            add("Battery busbars (+ and −)", f"Copper, ≥ {bat_rows['fuse']} A", 2,
                "Equal cable lengths to each parallel string; take + from first, − from last (§107)")
        if not lfp:
            add("Battery spill kit and eye wash", "Acid neutraliser, gloves, goggles", 1, "Lead-acid safety (§119)")
    add("AC MCB (inverter output)", f"{ac_mcb} A, C-curve, {ii.ac_phases}-pole + N", 1,
        f"≥ 1.25 × inverter AC current {i_ac:.1f} A; cable sized to carry it")
    add("RCD / RCBO", "30 mA, Type A (Type B if the inverter manual requires)", 1, "Shock protection on AC circuits (§109)")
    add("AC surge protection device (Type 2)", "275 V AC, In ≥ 20 kA", 1, "Protects inverter and loads")
    add("AC cable", f"{ac_mm2:g} mm² copper (phase + neutral) + {pe_mm2:g} mm² earth", f"{math.ceil(ii.len_inverter_to_db_m + 2)} m",
        "Cable schedule")
    if mode == "hybrid_backup":
        add("Backup distribution board", "Separate small DB for the appliances needed in power cuts", 1,
            "Hybrid inverter backup output feeds only these circuits (book §29-§30, §160)")
        add("Manual bypass / changeover switch", f"{ac_mcb} A, 2-pole, 3-position (inverter / off / grid)", 1,
            "Keeps the backup circuits powered from NEA if the inverter is serviced")
    add("Earth electrode", "Copper-bonded rod ≥ 1.5 m (or copper plate earth pit per local practice), inspection pit",
        1, "Earth the array frame, inverter and battery negative (§109, §121, §124)")
    add("Earth cable (green/yellow)", f"6 mm² frame bonding, 16 mm² to electrode, {pe_mm2:g} mm² PE",
        f"{math.ceil(rail_m / 2 + ii.len_earth_pit_m + ii.len_inverter_to_db_m)} m total", "Cable schedule")
    add("Conduit / cable tray, glands, ties", "UV-resistant conduit outdoors; glands sized to cables", "as required",
        "Protect cable runs (§110)")
    add("Warning labels", "'Solar DC - live in daylight', isolator labels, dual-supply label at DB and meter", 1,
        "IEC 60364-7-712 practice")
    if mode in ("grid_tied", "hybrid_backup"):
        add("NEA bidirectional (import/export) meter", "Supplied/approved by NEA after net-billing application", 1,
            "Needed to be credited for exported units; apply at your NEA distribution centre")

    # ---- 5. single-line diagram -----------------------------------------------------------------
    nodes, edges = [], []

    def node(i, label):
        nodes.append({"id": i, "label": label})

    def edge(a, b, label):
        edges.append({"from": a, "to": b, "label": label})

    node("pv", f"PV array\n{n_panels} × {wp:g} W = {kwp:.2f} kWp\n{s} in series × {p} string(s)\nVoc cold {voc_cold:.0f} V")
    nxt = "pv"
    if fuses_needed:
        node("comb", f"Combiner box\n{fuse_a} A gPV fuses")
        edge("pv", "comb", f"{pv_mm2:g} mm² PV cable")
        nxt = "comb"
    node("dciso", f"DC isolator {iso_v:g} V / {iso_a} A\n+ DC SPD {spd_v:g} V")
    edge(nxt, "dciso", f"{pv_mm2:g} mm² PV cable, {ii.len_array_to_inverter_m:g} m")
    node("earth", "Earth electrode\n(16 mm² Cu)")
    edge("pv", "earth", "6 mm² frame bonding")
    if mode == "grid_tied":
        node("inv", f"Grid-tied inverter\n{inv_kw:g} kW")
        edge("dciso", "inv", "DC")
        node("acp", f"AC MCB {ac_mcb} A + RCD 30 mA\n+ AC SPD")
        edge("inv", "acp", f"{ac_mm2:g} mm², {ii.len_inverter_to_db_m:g} m")
        node("db", "Main distribution board\n(house loads)")
        edge("acp", "db", "")
        node("meter", "NEA bidirectional meter")
        edge("db", "meter", "import / export")
        node("grid", "NEA grid 230 V 50 Hz")
        edge("meter", "grid", "")
    else:
        node("bat", f"Battery {v_sys:g} V\n{strings['battery_series']} S × {strings['battery_parallel']} P = "
                    f"{strings['battery_kwh']:.1f} kWh")
        node("batp", f"Battery fuse {bat_rows['fuse']} A\n+ DC isolator")
        edge("bat", "batp", f"{bat_rows['mm2']:g} mm², {ii.len_battery_to_inverter_m:g} m")
        edge("bat", "earth", "battery − earthed (§109)")
        if mode == "hybrid_backup":
            node("inv", f"Hybrid inverter\n{inv_kw:g} kW, {v_sys:g} V battery")
            edge("dciso", "inv", "PV input")
            edge("batp", "inv", "battery")
            node("acp", f"AC MCB {ac_mcb} A + RCD 30 mA\n+ AC SPD")
            edge("inv", "acp", f"backup output, {ac_mm2:g} mm²")
            node("bdb", "Backup DB\n(power-cut appliances)\nvia changeover switch")
            edge("acp", "bdb", "")
            node("db", "Main distribution board")
            node("meter", "NEA bidirectional meter")
            node("grid", "NEA grid 230 V 50 Hz")
            edge("grid", "meter", "")
            edge("meter", "db", "")
            edge("db", "inv", f"grid input, {ac_mcb} A MCB")
        else:
            node("ctrl", f"MPPT charge controller\n{ctrl_a} A")
            edge("dciso", "ctrl", "PV input")
            edge("ctrl", "batp", "charge")
            node("inv", f"Off-grid inverter\n{inv_kw:g} kW")
            edge("batp", "inv", f"{bat_rows['mm2']:g} mm²")
            node("acp", f"AC MCB {ac_mcb} A + RCD 30 mA")
            edge("inv", "acp", f"{ac_mm2:g} mm²")
            node("db", "Loads distribution board")
            edge("acp", "db", "")
    edge("inv", "earth", f"{pe_mm2:g} mm² PE")
    sld = {"nodes": nodes, "edges": edges}

    # ---- 6. installation steps (paraphrased from the book, updated) -----------------------------
    hv = voc_cold > 120
    steps = [
        ("1. Before you start - safety and tools (§118-§120)", [
            "Read every manual (inverter/controller, battery) first - the settings matter as much as the wiring.",
            "Tools: digital multimeter (DC up to 1000 V), DC clamp meter, insulated screwdrivers, crimping tool for "
            "MC4 and battery lugs, torque wrench, drill, spirit level, compass (phone app), ladder or scaffold.",
            "Protection: insulated gloves (Class 0 for arrays above 500 V, Class 00 below), safety glasses, safety "
            "shoes, harness for roof work. Keep a first-aid kit; for lead-acid add eye wash and acid spill kit.",
            "Never work alone on a roof. Keep children and animals away and tell people nearby you are working with "
            "high voltage.",
            "Remove rings, watches and bracelets before touching batteries - a short circuit can weld metal."]),
        ("2. Site check (§63-§73, §121)", [
            "Confirm the roof spot is free of shade from about 9 am to 3 pm all year (trees, water tanks, neighbouring "
            "floors - Nepali rooftops grow!).",
            "Check the roof can carry the panels and frame; on tin roofs fix into the purlins, never only the sheet.",
            "Choose the inverter/battery place: dry, shaded, ventilated, close to the battery (within ~1-2 m, §125) and "
            "near the distribution board. Batteries off a cold concrete floor on a shelf (§124).",
            "Mark the cable route and the earth-pit location."]),
        ("3. Mount the structure and panels (§123)", [
            f"Fix the {'tilt frame' if flat else 'rails'} facing due south at the designed tilt; tighten all bolts.",
            "Unpack each panel and look for cracked glass; measure each panel's open-circuit voltage in sun - expect "
            f"about {ii.voc:g} V (cooler days higher).",
            "Clamp the panels to the rails (end clamps at row ends, mid clamps between panels).",
            "Keep panels covered with an opaque sheet, or leave the strings unconnected, while you wire - panels make "
            "electricity whenever light falls on them."]),
        ("4. Wire the PV strings and check polarity (§106, §123)", [
            f"Connect {s} panels in series per string (+ of one to − of the next) using the panel leads.",
            f"Make {p} string(s). Use only matching MC4 connectors, crimped with the proper tool.",
            f"Measure each string's open-circuit voltage before going further: expect about {ii.voc * s:.0f} V at 25 °C "
            f"(up to {voc_cold:.0f} V on a cold morning). All strings should read within ~2 % of each other.",
            "Check polarity with the meter (red + / black −). A reversed string can destroy the inverter.",
            f"Run the PV cables ({pv_mm2:g} mm² red and black) in UV-resistant conduit to the DC isolator; keep + and − "
            "close together to limit loops (lightning).",
            ("If several strings are paralleled, connect them through the combiner box with fuses on each string. "
             if fuses_needed else "") + "Leave the DC isolator OFF."]),
        ("5. Earthing (§109, §121, §124)", [
            "Make the earth pit/rod and connect a 16 mm² green/yellow cable to the main earth bar.",
            "Bond every panel frame and rail with 6 mm² green/yellow cable (or approved bonding clips).",
            "Connect the inverter and distribution-board earth terminals to the earth bar.",
            "For battery systems, earth the battery negative as the inverter manual allows (many LiFePO4 hybrid "
            "inverters require it to stay floating - follow the manual).",
            "Measure and record the earth resistance; improve the pit (deeper rod, second rod) if it is high."]),
        *([("6. Install the battery (§124)", [
            "Place the battery upright on a sturdy shelf, ventilated, away from sparks, sun and children; label it "
            "with the installation date.",
            f"Connect {strings.get('battery_series')} module(s) in series and {strings.get('battery_parallel')} string(s) "
            "in parallel with the maker's interconnect cables; use equal cable lengths for parallel strings.",
            "Tighten every terminal to the torque on the datasheet; protect terminals from short circuits.",
            f"Fit the {bat_rows['fuse']} A battery fuse on the + cable close to the battery, then the battery isolator - "
            "leave it OFF.",
            f"Measure the bank voltage: LiFePO4 {v_sys:g} V-class banks rest at about {v_sys * 1.07:.0f}-{v_sys * 1.11:.0f} V; "
            f"lead-acid about {v_sys * 1.06:.0f}-{v_sys * 1.1:.0f} V when charged."])] if mode != "grid_tied" else []),
        ("7. Mount the inverter / controller (§125)", [
            "Mount vertically on a non-flammable wall with the clearances in its manual (it gets hot).",
            f"Connect the battery cables ({bat_rows.get('mm2', '-')} mm²) to the inverter{' and controller' if mode == 'off_grid' else ''}: "
            "negative first, check polarity twice, then positive." if mode != "grid_tied" else
            "Connect the DC isolator output to the inverter PV input (check polarity twice).",
            "Connect the PV DC isolator output to the PV input terminals - still with the isolator OFF.",
            "Set the battery type and voltages in the inverter/controller menu before switching on (§127)."]),
        ("8. AC connection - STOP: licensed electrician (§119, §126)", [
            f"The inverter AC output goes through a {ac_mcb} A MCB, a 30 mA RCD and an AC surge protector to the "
            f"{'backup distribution board via the changeover switch' if mode == 'hybrid_backup' else 'distribution board'}.",
            "Connecting to the house wiring must be done or checked by a licensed electrician.",
            *(["For net billing: apply at your NEA distribution centre BEFORE connecting to the grid; NEA approves the "
               "inverter (anti-islanding) and fits a bidirectional meter. Exports are not credited before approval."]
              if mode != "off_grid" else [])]),
        ("9. Switch on (§125, §127-§128)", [
            *(["Turn ON the battery isolator - the inverter/controller should wake up and show battery voltage."]
              if mode != "grid_tied" else []),
            "Turn ON the PV DC isolator in daylight - check the PV voltage and charging/feeding power on the display.",
            "Turn ON the AC MCB and test with a small load such as a lamp.",
            "Shutdown order is the reverse: AC MCB off → PV isolator off → battery isolator off. Never open DC "
            "connectors under load."]),
        ("10. Commissioning tests and first week (§127-§128, IEC 62446)", [
            "Fill in the commissioning record table in this report (expected values are given).",
            f"Insulation test of each string to earth at {'1000' if voc_cold * 1.25 > 500 else '500' if voc_cold * 1.25 >= 120 else '250'} V: "
            f"minimum {'0.5' if voc_cold * 1.25 < 120 else '1'} MΩ.",
            "Simulate a power cut (switch off the NEA main) and check the backup circuits keep running."
            if mode == "hybrid_backup" else "Check the inverter reconnects after a grid interruption (anti-islanding test).",
            "For battery systems, let the battery charge fully for a day before heavy use (§128).",
            "Watch the daily kWh for a week; compare with the monthly estimate in this report."]),
    ]
    if hv:
        steps[0][1].append(f"This array reaches about {voc_cold:.0f} V DC - lethal. Wear insulated gloves when "
                           "handling PV connectors (§126).")

    # ---- 7. commissioning record, maintenance, troubleshooting, safety ---------------------------
    tests = [{"Test": f"String {k + 1} open-circuit voltage (Voc)", "Expected": f"≈ {ii.voc * s:.0f} V at 25 °C "
              f"(max {voc_cold:.0f} V cold)", "Measured": "", "OK?": ""} for k in range(p)]
    tests += [{"Test": f"String {k + 1} short-circuit current (clamp meter, sunny)", "Expected": f"≤ {ii.isc:g} A "
               "(≈ Isc × sunlight/1000 W/m²)", "Measured": "", "OK?": ""} for k in range(p)]
    tests += [{"Test": "Polarity of every string and the battery", "Expected": "Correct (+ to +)", "Measured": "", "OK?": ""},
              {"Test": "Insulation resistance, string + and − to earth", "Expected": "≥ 1 MΩ" if voc_cold * 1.25 >= 120 else "≥ 0.5 MΩ",
               "Measured": "", "OK?": ""},
              {"Test": "Earth electrode resistance", "Expected": "As low as practical - record value", "Measured": "", "OK?": ""}]
    if mode != "grid_tied":
        tests.append({"Test": "Battery bank voltage at rest", "Expected": f"{v_sys * 1.0:.0f}-{v_sys * 1.15:.0f} V",
                      "Measured": "", "OK?": ""})
    tests += [{"Test": "Inverter AC output voltage / frequency", "Expected": "230 V ±10 %, 50 Hz (NEPQA)", "Measured": "", "OK?": ""},
              {"Test": "RCD trip test button", "Expected": "Trips", "Measured": "", "OK?": ""}]
    maintenance = [
        {"When": "Weekly", "Task": "Glance at the inverter/controller display: daily kWh, battery state, any fault codes; "
                                   "keep a simple logbook (§139)."},
        {"When": "Monthly (dry season: Oct-May)", "Task": "Clean panels early morning with soft brush and plain water - "
                                                          "Nepal dust and brick-kiln soot cut output; no detergent abrasives."},
        {"When": "Monthly", "Task": "Check battery area: ventilation, no leaks, dust off battery tops; LiFePO4: check BMS "
                                    "alarms. Lead-acid: water level (§139)."},
        {"When": "Before monsoon", "Task": "Check roof fixings, conduit seals and junction boxes for water ingress; clear "
                                           "drains around the earth pit."},
        {"When": "Every 6 months", "Task": "Re-torque battery and DC terminals (power off); look for hot or discoloured "
                                           "connectors; test the RCD button."},
        {"When": "Yearly", "Task": "Measure string voltages and compare with the commissioning record; test earth "
                                   "resistance; check SPD status windows; balance lead-acid batteries (§139)."},
        {"When": "After lightning / storm", "Task": "Check SPD indicators and replace tripped cartridges; inspect panels for damage."},
    ]
    troubleshooting = [
        {"Symptom": "Battery runs flat / power cuts off early", "Likely cause": "Using more energy than designed (§134)",
         "What to check": "Logbook or inverter daily use vs the design figure; reduce load or add panels/battery."},
        {"Symptom": "Lower solar output than expected", "Likely cause": "Dirt, new shade, wrong angle (§135)",
         "What to check": "Clean panels; look for new shade (tree, tank, new floor next door); compare string voltages."},
        {"Symptom": "Strange or intermittent faults, worse in heat/cold", "Likely cause": "Loose or damaged connection (§136)",
         "What to check": "With power off: tighten terminals, inspect MC4s for burn marks, measure voltage drop along cables."},
        {"Symptom": "Power fails when a big appliance starts", "Likely cause": "Inverter surge too small or weak battery (§137-§138)",
         "What to check": "Compare motor starting current with inverter surge rating; check battery voltage under load."},
        {"Symptom": "One battery hotter or lower voltage than others", "Likely cause": "Failing cell (§137)",
         "What to check": "Voltage difference > 0.7 V needs balancing; ≥ 2 V means a failed battery - replace it."},
        {"Symptom": "Inverter trips on hot afternoons", "Likely cause": "Overheating / poor ventilation (§138)",
         "What to check": "Clear space around the inverter, keep it out of direct sun, check its fan."},
        {"Symptom": "Inverter trips in rain", "Likely cause": "Earth leakage / insulation fault (§138)",
         "What to check": "Insulation-test strings; look for water in junction boxes and damaged cable."},
        {"Symptom": "Grid-tied inverter shows 'grid over-voltage' at midday", "Likely cause": "High NEA voltage plus cable rise",
         "What to check": "Measure grid voltage; a larger AC cable reduces voltage rise; ask NEA about transformer tap."},
    ]
    safety = [
        "Panels produce dangerous DC voltage whenever there is daylight - there is no off switch on a panel (§119, §132).",
        "Never unplug MC4 connectors or open a DC fuse holder while current flows - switch off the isolator first.",
        "A battery short circuit releases huge current: fire, burns, explosion. Fuse it, insulate tools, remove jewellery.",
        "Work at height only with a ladder footed by a helper, a harness on steep roofs, and never in rain or wind.",
        "Lead-acid batteries contain acid and release hydrogen - ventilate, no flames, wear goggles and gloves.",
        "Connection to the building wiring and the NEA grid must be done/checked by a licensed electrician and "
        "approved by NEA; never back-feed the grid without approval (danger to line workers).",
        "Use NEPQA-2025 compliant equipment (AEPC) so warranties and any subsidy remain valid.",
    ]
    refs = [f"{REF} §104-§112 (design, protection), §117-§130 (installation), §131-§139 (troubleshooting, maintenance)",
            "IEC 62548-1 (PV array design), IEC 62446-1 (testing), IEC 60364-5-52 (cable current ratings), "
            "IEC 60364-7-712 (PV installations)", "NEPQA-2025 and Amendment-1 (AEPC)", ampacity.BASIS]
    return InstallPackage(bom=bom, strings=strings, cable_schedule=sched, sld=sld, steps=steps, tests_table=tests,
                          maintenance=maintenance, troubleshooting=troubleshooting, safety=safety,
                          warnings=warnings, references=refs)


def require_inputs(ii: InstallInputs) -> None:
    """Basic sanity checks on the editable datasheet values."""
    require_positive("Module Voc", ii.voc)
    if not 0 < ii.imp < ii.isc or not 0 < ii.vmp < ii.voc:
        raise ValidationError("Check the panel datasheet values: Vmp < Voc and Imp < Isc.")
