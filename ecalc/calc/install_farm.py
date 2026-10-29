"""Solar farm design & construction package (utility scale, Nepal).

Builds on the 5-step design (ecalc.calc.farm) to produce what an EPC contractor needs to price and
build the plant: plant hierarchy and counts, block/transformer design, cable schedule (current
rating + voltage drop), protection and earthing, insulation-test row, BOQ, block-level single-line
diagram, construction sequence, commissioning tests with expected values, O&M schedule and a Nepal
permits checklist.

Method: Neill, Stapleton & Martell, *Solar Farms* (Earthscan) - Ch.4 pp.116-124 (transformers, fault
prevention, cables), Ch.5 p.153 (installation sequence, Fig 5.1), pp.175-176 (tests, Table 5.1),
Ch.6 p.182 (preventative maintenance, Table 6.1). Book text is paraphrased, not copied.
A MW-scale plant must be built by a licensed EPC contractor under an engineer of record; this
package is a preliminary design basis for that contractor, not a construction-issue design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import cable
from .ampacity import BASIS, IZ_B1_CU_PVC_A, cable_capacity, device_rating, size_for_current
from .farm import FarmInputs, Inverter, Module
from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range
from .strings import FUSE_SIZES_A

BOOK = "Neill, Stapleton & Martell, Solar Farms (Earthscan)"
TRANSFORMER_KVA = [500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000]
MAX_BLOCK_KVA = 3150
EPC_NOTE = ("Utility-scale plants must be designed for construction, built and energised by a licensed EPC "
            "contractor under a registered engineer, with NEA approval of the grid connection. This package is a "
            "preliminary design basis and bill of quantities for that contractor - not construction drawings.")
VERIFY = "verify current procedure"


@dataclass
class PackageInputs:
    table_rows_portrait: int = 2               # modules stacked up the slope (2P)
    table_modules_wide: int | None = None      # None = one string length per row of the table
    module_width_m: float = 1.134
    tables_per_row: int = 10
    inverters_per_block: int | None = None     # None = as many as fit a 3150 kVA transformer
    mv_kv: float | None = None                 # None = 33 kV above 3 MWp, else 11 kV
    inverter_type: str = "string"              # string | central
    inverter_ac_v: float | None = None         # None = 800 V (string) / 400 V (central)
    strings_per_combiner: int = 16             # central inverters only
    string_run_m: float = 60.0                 # average one-way string cable length [assumption]
    lv_run_m: float = 150.0                    # inverter->transformer (string) or combiner->inverter (central)
    mv_run_m: float = 500.0                    # block transformer -> switchyard, average [assumption]
    line_to_nea_km: float = 2.0                # overhead line to the NEA substation [assumption]
    ambient_max_c: float = 40.0                # Terai summer; cable current derating
    dc_vd_limit_pct: float = 3.0               # book p.120: DC < 3 %, furthest module to inverter
    ac_vd_limit_pct: float = 1.0               # book Table 4.12: AC < 1 %
    module_max_fuse_a: float = 30.0            # module datasheet "max series fuse" [typical 25-35 A]
    transformerless_inverter: bool = True
    test_cell_temp_c: float = 25.0             # for expected commissioning values
    test_irradiance_wm2: float = 1000.0


@dataclass
class FarmPackage:
    hierarchy: dict
    counts: dict
    layout: dict
    blocks: list[dict]
    cable_schedule: list[dict]
    switchgear: list[dict]
    interconnection: list[dict]
    protection: list[dict]
    earthing: list[dict]
    insulation_test: dict
    boq: list[dict]
    sld: dict
    construction: list[tuple[str, list[str]]]
    commissioning: list[dict]
    o_and_m: list[dict]
    permits: list[dict]
    warnings: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    note: str = EPC_NOTE

    def calc_results(self) -> list[CalcResult]:
        """Report-ready sections (tables) for ecalc.reports.build_pdf."""
        c = self.counts
        return [
            CalcResult(name="Plant structure and quantities",
                       inputs={"structure": Q(self.hierarchy["text"], "", "Hierarchy")},
                       outputs={k: Q(v["value"], v["unit"], v["label"]) for k, v in c.items()},
                       equations=["Inverters = ceil(plant MWp / DC kWp per inverter)",
                                  "Transformer ≥ Σ inverter kVA in the block (book pp.116-117), next standard size"],
                       assumptions=[self.note], warnings=self.warnings,
                       references=[BOOK + " Ch.4"], tables={"Blocks and transformers": self.blocks,
                                                           "Layout": [self.layout]}),
            CalcResult(name="Cable schedule", inputs={"basis": Q(BASIS, "", "Current rating basis")},
                       outputs={}, equations=["Size = larger of (current rating ≥ protective device) and (voltage drop ≤ limit)",
                                              "DC: ΔV = 2·L·I·R (I = Imp); AC 3-phase: ΔV = √3·L·I·R  (book Box 4.2)"],
                       assumptions=["Copper conductors; route lengths are planning assumptions - confirm on the layout.",
                                    "MV cables: current given; size and screen to be selected by the supplier for the fault level."],
                       references=[BOOK + " pp.120-124 (Box 4.2, Table 4.6)", "IEC 60364-5-52"],
                       tables={"Cable schedule": self.cable_schedule}),
            CalcResult(name="Protection, switchgear, earthing and grid connection", inputs={}, outputs={},
                       equations=["String fuses: 1.5·Isc ≤ In ≤ min(2.4·Isc, module max fuse) (IEC 62548 approach)",
                                  "DC switch-disconnector rated for array max voltage per pole (book Table 4.4)"],
                       tables={"Protection": self.protection, "Switchgear": self.switchgear,
                               "Grid connection (NEA)": self.interconnection, "Earthing and lightning": self.earthing},
                       references=[BOOK + " pp.117-120, 138-143"]),
            CalcResult(name="Bill of quantities", inputs={}, outputs={}, tables={"BOQ": self.boq},
                       assumptions=["Quantities are preliminary (± 10-15 %); cable lengths are estimates."]),
            CalcResult(name="Construction, commissioning and O&M", inputs={},
                       outputs={"insulation_test_v": Q(self.insulation_test["test_v"], "V", "Insulation test voltage"),
                                "insulation_min_mohm": Q(self.insulation_test["min_mohm"], "MΩ", "Minimum insulation resistance")},
                       tables={"Construction sequence": [{"Phase": p, "Steps": "; ".join(s)} for p, s in self.construction],
                               "Commissioning tests": self.commissioning, "Preventative maintenance": self.o_and_m,
                               "Permits and approvals (Nepal)": self.permits},
                       references=[BOOK + " p.153 (Fig 5.1), pp.175-176 (Table 5.1), p.182 (Table 6.1)",
                                   "IEC 62446-1 (check current edition)"]),
        ]


def _std_transformer(kva: float) -> int:
    for s in TRANSFORMER_KVA:
        if s >= kva:
            return s
    raise ValidationError(f"Block of {kva:,.0f} kVA exceeds 5000 kVA - use fewer inverters per block.")


ACB_RATINGS_A = [630, 800, 1000, 1250, 1600, 2000, 2500, 3200, 4000]


def _device(design_current_a: float) -> int:
    """Standard breaker ≥ 1.25 × Ib: MCB/MCCB table, then air-circuit-breaker frame sizes for large feeders."""
    try:
        return device_rating(design_current_a)
    except ValidationError:
        need = 1.25 * design_current_a
        for r in ACB_RATINGS_A:
            if r >= need:
                return r
        raise ValidationError(f"{need:,.0f} A is beyond a single LV breaker - split the feeder.") from None


def insulation_test_row(system_voltage_v: float) -> dict:
    """Book Table 5.1 (p.176, IEC 62446): system voltage = Voc_STC × N × 1.25."""
    v = require_positive("System voltage", system_voltage_v)
    if v < 120:
        row = (250, 0.5)
    elif v <= 500:
        row = (500, 1.0)
    else:
        row = (1000, 1.0)
    return {"system_voltage_v": v, "test_v": row[0], "min_mohm": row[1]}


def _parallel_size(device_a: float, ambient: float, min_size: float = 1.5) -> tuple[int, float]:
    """Smallest number of parallel copper cables (each ≤ 240 mm²) carrying the device rating."""
    largest = cable_capacity(max(IZ_B1_CU_PVC_A), ambient)
    n = max(1, math.ceil(device_a / largest))
    return n, size_for_current(device_a / n, ambient, min_size)


def _vd_size(system: str, v: float, i: float, length: float, limit: float, n_par: int) -> float | None:
    try:
        r = cable.minimum_size_for_drop(system, v, i / n_par, length, limit, "copper", 70.0)
        return r.out("min_size_mm2")
    except ValidationError:
        return None


def _cable_row(level: str, system: str, v: float, i_design: float, device_a: float, length_m: float,
               limit: float, count: int, ambient: float, min_size: float, note: str) -> dict:
    n_par, size_i = _parallel_size(device_a, ambient, min_size)
    size_v = _vd_size(system, v, i_design, length_m, limit, n_par)
    if size_v is None:
        n_par += 1
        size_i = size_for_current(device_a / n_par, ambient, min_size)
        size_v = _vd_size(system, v, i_design, length_m, limit, n_par) or max(IZ_B1_CU_PVC_A)
    size = max(size_i, size_v, min_size)
    vd = cable.voltage_drop(system, v, i_design / n_par, length_m, size, "copper", 70.0).out("voltage_drop_pct")
    cores = 2 if system == "dc" else 4
    km = count * length_m * n_par * cores / 1000
    return {"Level": level, "Circuits": count, "Voltage (V)": round(v), "Design current (A)": round(i_design, 1),
            "Protective device (A)": device_a, "Size by current (mm²)": size_i, "Size by voltage drop (mm²)": size_v,
            "Selected": f"{n_par} × {size:g} mm² Cu" if n_par > 1 else f"{size:g} mm² Cu",
            "Voltage drop (%)": round(vd, 2), "Limit (%)": limit, "Conductor length (km, est.)": round(km, 1),
            "Note": note}


def build_farm_package(fr: CalcResult, sr: CalcResult, mod: Module, inv: Inverter, fi: FarmInputs,
                       pi: PackageInputs | None = None) -> FarmPackage:
    pi = pi or PackageInputs()
    if "modules_per_string" not in sr.outputs:
        raise ValidationError("No safe string length for this module/inverter at the site temperature - "
                              "fix the string design before preparing the construction package.")
    if pi.inverter_type not in ("string", "central"):
        raise ValidationError("Inverter type must be 'string' or 'central'.")
    amb = require_range("Maximum ambient temperature", pi.ambient_max_c, 10, 55)
    warnings: list[str] = []

    # ---- hierarchy and counts -------------------------------------------------------------
    n_series = int(sr.out("modules_per_string"))
    strings_inv = int(sr.out("strings_used"))
    dc_kw_inv = sr.out("dc_kw_per_inverter")
    n_inv = math.ceil(fi.capacity_mwp * 1000 / dc_kw_inv)
    n_strings = n_inv * strings_inv
    n_modules = n_strings * n_series
    mwp_actual = n_modules * mod.wp / 1e6
    wide = pi.table_modules_wide or n_series
    per_table = pi.table_rows_portrait * wide
    n_tables = math.ceil(n_modules / per_table)
    per_block = pi.inverters_per_block or max(1, math.floor(MAX_BLOCK_KVA / inv.ac_kva))
    n_blocks = math.ceil(n_inv / per_block)
    mv_kv = pi.mv_kv or (33.0 if fi.capacity_mwp > 3 else 11.0)
    ac_v = pi.inverter_ac_v or (800.0 if pi.inverter_type == "string" else 400.0)

    blocks = []
    for b in range(n_blocks):
        k = min(per_block, n_inv - b * per_block)
        kva = k * inv.ac_kva
        tx = _std_transformer(kva)
        blocks.append({"Block": b + 1, "Inverters": k, "Inverter kVA (sum)": round(kva), "Transformer (kVA)": tx,
                       "Ratio": f"{ac_v / 1000:g}/{mv_kv:g} kV", "DC kWp": round(k * dc_kw_inv, 1),
                       "MV current (A)": round(tx * 1000 / (math.sqrt(3) * mv_kv * 1000), 1)})
    total_tx = sum(b["Transformer (kVA)"] for b in blocks)
    export_mw = n_inv * inv.ac_kva / 1000
    if export_mw > 30 and mv_kv <= 33:
        warnings.append(f"About {export_mw:.0f} MW AC: NEA connection may need 132 kV and a plant substation - "
                        "confirm in the NEA connection study.")
    n_combiners = math.ceil(n_strings / pi.strings_per_combiner) if pi.inverter_type == "central" else 0

    counts = {
        "modules": {"value": n_modules, "unit": "modules", "label": f"PV modules ({mod.wp:g} Wp)"},
        "mwp_actual": {"value": round(mwp_actual, 3), "unit": "MWp", "label": "Installed DC capacity"},
        "strings": {"value": n_strings, "unit": "strings", "label": f"Strings of {n_series} modules"},
        "tables": {"value": n_tables, "unit": "tables", "label": f"Mounting tables ({pi.table_rows_portrait}P × {wide})"},
        "inverters": {"value": n_inv, "unit": "inverters", "label": f"Inverters ({inv.ac_kva:g} kVA)"},
        "blocks": {"value": n_blocks, "unit": "blocks", "label": "Power blocks (one transformer each)"},
        "transformer_kva_total": {"value": total_tx, "unit": "kVA", "label": "Total transformer capacity"},
        "ac_mw": {"value": round(export_mw, 3), "unit": "MW", "label": "Total inverter AC capacity"},
        "mv_kv": {"value": mv_kv, "unit": "kV", "label": "Collection / connection voltage"},
    }
    if n_combiners:
        counts["combiners"] = {"value": n_combiners, "unit": "boxes", "label": "DC combiner boxes (IP55 min.)"}
    hierarchy = {"text": (f"{n_series} modules → 1 string; {strings_inv} strings → 1 inverter ({dc_kw_inv:g} kWp DC / "
                          f"{inv.ac_kva:g} kVA); up to {per_block} inverters → 1 block transformer; "
                          f"{n_blocks} blocks → {mv_kv:g} kV collector → NEA connection"),
                 "modules_per_string": n_series, "strings_per_inverter": strings_inv, "inverters_per_block": per_block}

    # ---- layout ----------------------------------------------------------------------------
    pitch = fr.out("pitch_m")
    table_len = wide * (pi.module_width_m + 0.02)
    rows = math.ceil(n_tables / pi.tables_per_row)
    field_w = pi.tables_per_row * (table_len + 0.5)
    field_d = rows * pitch
    fenced_m2 = fr.out("land_ha") * 10000
    side = math.sqrt(fenced_m2)
    layout = {"Tables per row": pi.tables_per_row, "Rows": rows, "Table length (m)": round(table_len, 1),
              "Row pitch (m)": round(pitch, 2), "Array field (m × m)": f"{field_w:,.0f} × {field_d:,.0f}",
              "Fenced area (ha)": round(fr.out("land_ha"), 2), "Fence length (m, if square)": round(4 * side),
              "Roads": f"Perimeter and block access roads within the {fi.land_extra_pct:g}% extra land"}

    # ---- protection: string fuses ----------------------------------------------------------
    strings_per_input = math.ceil(strings_inv / max(1, inv.dc_inputs)) if pi.inverter_type == "string" \
        else pi.strings_per_combiner
    reverse = (strings_per_input - 1) * 1.25 * mod.isc
    fuses_needed = strings_per_input >= 3 and reverse > pi.module_max_fuse_a
    fuse_a = None
    if fuses_needed:
        hi = min(2.4 * mod.isc, pi.module_max_fuse_a)
        fuse_a = next((f for f in FUSE_SIZES_A if 1.5 * mod.isc <= f <= hi), None)
        if fuse_a is None:
            warnings.append("No standard gPV fuse fits 1.5-2.4 × Isc within the module's fuse rating - reduce strings "
                            "per input or choose another module.")
    voc_cold = sr.out("voc_cold_v")
    string_voc_cold = n_series * voc_cold
    v_class = next((c for c in (600, 1000, 1100, 1500) if c >= string_voc_cold), None)
    if v_class is None:
        warnings.append(f"String Voc on a cold morning ({string_voc_cold:,.0f} V) exceeds 1500 V equipment.")
        v_class = 1500

    # ---- cable schedule --------------------------------------------------------------------
    sched = []
    string_ccc = fuse_a if fuse_a else 1.25 * mod.isc * max(1, strings_per_input - 1)
    v_string = n_series * mod.vmp
    dc_limit_string = pi.dc_vd_limit_pct if pi.inverter_type == "string" else pi.dc_vd_limit_pct / 2
    sched.append(_cable_row("PV string (DC)", "dc", v_string, mod.imp, round(string_ccc, 1), pi.string_run_m,
                            dc_limit_string, n_strings, amb, 4.0,
                            "Solar cable (EN 50618 H1Z2Z2-K); CCC ≥ " + (f"string fuse {fuse_a} A" if fuse_a else
                                                                         "1.25·Isc·(Np−1), no fuse (book Table 4.6)")))
    if pi.inverter_type == "central":
        i_main = pi.strings_per_combiner * mod.imp
        dev = _device(pi.strings_per_combiner * mod.isc)
        sched.append(_cable_row("DC main (combiner → inverter)", "dc", v_string, i_main, dev, pi.lv_run_m,
                                pi.dc_vd_limit_pct / 2, n_combiners, amb, 16.0,
                                "Device ≥ 1.25 × Σ Isc of the combiner; DC-rated switch-disconnector at each end"))
    i_ac = inv.ac_kva * 1000 / (math.sqrt(3) * ac_v)
    dev_ac = _device(i_ac)
    lv_len = pi.lv_run_m if pi.inverter_type == "string" else 30.0
    sched.append(_cable_row("Inverter AC (LV) → transformer", "three_phase", ac_v, i_ac, dev_ac, lv_len,
                            pi.ac_vd_limit_pct, n_inv, amb, 16.0, f"Breaker {dev_ac} A per inverter; 3-phase + PE"))
    sched.append({"Level": f"MV {mv_kv:g} kV (block → switchyard)", "Circuits": n_blocks, "Voltage (V)": round(mv_kv * 1000),
                  "Design current (A)": blocks[0]["MV current (A)"], "Protective device (A)": "RMU / VCB",
                  "Size by current (mm²)": "by supplier", "Size by voltage drop (mm²)": "by supplier",
                  "Selected": "XLPE MV cable - size & screen by supplier for current and fault level",
                  "Voltage drop (%)": "-", "Limit (%)": pi.ac_vd_limit_pct,
                  "Conductor length (km, est.)": round(n_blocks * pi.mv_run_m / 1000, 1),
                  "Note": "Radial from each block; consider a ring with RMUs for availability"})
    i_export = n_inv * inv.ac_kva * 1000 / (math.sqrt(3) * mv_kv * 1000)
    sched.append({"Level": f"Line to NEA substation ({mv_kv:g} kV)", "Circuits": 1, "Voltage (V)": round(mv_kv * 1000),
                  "Design current (A)": round(i_export, 1), "Protective device (A)": "Feeder VCB + relays",
                  "Size by current (mm²)": "by NEA/designer", "Size by voltage drop (mm²)": "by NEA/designer",
                  "Selected": "Overhead line or cable per NEA connection agreement", "Voltage drop (%)": "-",
                  "Limit (%)": "-", "Conductor length (km, est.)": pi.line_to_nea_km, "Note": VERIFY})

    # ---- protection, switchgear, interconnection, earthing ----------------------------------
    protection = [
        {"Item": "String fuses (gPV)", "Requirement": f"{fuse_a} A, {v_class} V DC, both poles" if fuses_needed
            else "Not required", "Basis": f"{strings_per_input} strings per input: reverse current (Np−1)·1.25·Isc = "
            f"{reverse:.0f} A vs module max fuse {pi.module_max_fuse_a:g} A"},
        {"Item": "DC switch-disconnector", "Requirement": f"≥ {string_voc_cold:,.0f} V per pole ({v_class} V class), "
            f"≥ {1.25 * mod.isc * strings_per_input:.0f} A, DC-rated, lockable",
         "Basis": "Book Table 4.4: " + ("transformerless inverter with equipotential bonding only - rating per pole = array "
                                        "max voltage; functional earthing NOT permitted" if pi.transformerless_inverter
                                        else "separated inverter - see Table 4.4 for earthing case")},
        {"Item": "DC surge protection", "Requirement": f"Type 2 PV SPD, Ucpv ≥ {v_class} V at each inverter input",
         "Basis": "IEC 61643-31; string Voc on the coldest morning"},
        {"Item": "AC protection per inverter", "Requirement": f"{dev_ac} A breaker, AC SPD Type 2",
         "Basis": "Ib ≤ In ≤ Iz (IEC 60364-4-43)"},
        {"Item": "MV surge arresters", "Requirement": f"3 per transformer, {mv_kv:g} kV class", "Basis": "Lightning on MV lines"},
    ]
    switchgear = [
        {"Item": f"Block RMU / VCB ({mv_kv:g} kV)", "Qty": n_blocks, "Function": "Transformer protection and isolation"},
        {"Item": f"Main incomer / outgoing feeder VCB ({mv_kv:g} kV)", "Qty": 2, "Function": "Plant isolation and NEA feeder"},
        {"Item": "LV distribution panel per block", "Qty": n_blocks, "Function": f"Collects {per_block} inverter feeders"},
        {"Item": "Auxiliary transformer and UPS", "Qty": 1, "Function": "SCADA, security, lighting"},
    ]
    interconnection = [
        {"Item": "Revenue metering (main + check meter, CTs/PTs)", "Spec": "Class 0.2S per NEA connection agreement", "Note": VERIFY},
        {"Item": "Protection relays (ANSI/IEEE C37.2)", "Spec": "50/51, 50N/51N overcurrent/earth fault; 27/59 under/over "
            "voltage; 81U/81O frequency; anti-islanding (ROCOF / vector shift); 87T on large transformers",
         "Note": "Settings by NEA - " + VERIFY},
        {"Item": "Power factor / reactive control", "Spec": "Plant controller able to hold PF 0.95 lag-lead (book p.143)",
         "Note": "NEA grid code requirement - " + VERIFY},
        {"Item": "SCADA and communications", "Spec": "Inverter/string monitoring, weather station (POA pyranometer, "
            "module & ambient temperature), link to NEA Load Dispatch Centre", "Note": VERIFY},
    ]
    earthing = [
        {"Item": "Module frames and structures", "Spec": "Bonded to the earth grid, min 6 mm² Cu (10 mm² where lightning "
            "protection is installed) or equivalent", "Basis": "IEC 60364-7-712 equipotential bonding"},
        {"Item": "Earth grid / mesh", "Spec": "Buried mesh (e.g. 50-70 mm² Cu or galvanised steel strip) linking all blocks, "
            "rods at inverters and transformers", "Basis": "Designer to verify step/touch voltages from soil resistivity tests"},
        {"Item": "Transformer neutral and MV earthing", "Spec": "Per transformer vector group (e.g. Dyn11) and NEA rules",
         "Basis": VERIFY},
        {"Item": "Lightning protection", "Spec": "Risk assessment (IEC 62305); air terminals for control room/substation",
         "Basis": BOOK + " pp.117-120"},
    ]
    ins = insulation_test_row(mod.voc * n_series * 1.25)

    # ---- BOQ --------------------------------------------------------------------------------
    string_row = sched[0]
    lv_row = [r for r in sched if r["Level"].startswith("Inverter AC")][0]
    boq = [
        {"Item": "PV module", "Specification": f"{mod.wp:g} Wp, ≥ 21 % efficiency (NEPQA-2025), {v_class} V rated",
         "Qty": n_modules, "Unit": "nos", "Basis": "strings × modules per string"},
        {"Item": "Mounting table (fixed tilt)", "Specification": f"{pi.table_rows_portrait}P × {wide}, tilt "
            f"{fr.out('tilt_deg'):.0f}°, galvanised steel", "Qty": n_tables, "Unit": "nos", "Basis": "modules ÷ per table"},
        {"Item": "Inverter", "Specification": f"{inv.ac_kva:g} kVA, {inv.v_dc_max:g} V DC, MPPT {inv.v_mppt_min:g}-"
            f"{inv.v_mppt_max:g} V, ≥ 97 % efficiency (NEPQA)", "Qty": n_inv, "Unit": "nos", "Basis": "MWp ÷ kWp per inverter"},
        {"Item": "Step-up transformer", "Specification": "; ".join(sorted({f"{b['Transformer (kVA)']} kVA {b['Ratio']}"
                                                                            for b in blocks})) + ", ONAN, Dyn11",
         "Qty": n_blocks, "Unit": "nos", "Basis": "one per block"},
        {"Item": "MV switchgear (RMU/VCB)", "Specification": f"{mv_kv:g} kV", "Qty": n_blocks + 2, "Unit": "panels",
         "Basis": "per block + incomer + feeder"},
        {"Item": "PV string cable", "Specification": string_row["Selected"] + ", H1Z2Z2-K", "Qty": string_row[
            "Conductor length (km, est.)"], "Unit": "km", "Basis": "2 conductors × strings × average run"},
        {"Item": "MC4-type connector pairs", "Specification": f"{v_class} V, same make as module connectors",
         "Qty": n_strings * 2, "Unit": "pairs", "Basis": "2 field connections per string"},
        {"Item": "LV AC cable", "Specification": lv_row["Selected"] + ", 0.6/1 kV", "Qty": lv_row["Conductor length (km, est.)"],
         "Unit": "km", "Basis": "4 conductors × inverters × run"},
        {"Item": "MV cable", "Specification": f"{mv_kv:g} kV XLPE (size by supplier)", "Qty": round(
            n_blocks * pi.mv_run_m * 3 / 1000, 1), "Unit": "km (single-core)", "Basis": "3 cores × blocks × run"},
        {"Item": "DC SPD Type 2", "Specification": f"Ucpv ≥ {v_class} V", "Qty": n_inv * max(1, inv.dc_inputs) if
            pi.inverter_type == "string" else n_combiners, "Unit": "nos", "Basis": "per DC input / combiner"},
        {"Item": "Weather station", "Specification": "POA + GHI pyranometers, temperature sensors",
         "Qty": max(1, math.ceil(fi.capacity_mwp / 20)), "Unit": "nos", "Basis": "1 per ~20 MWp [assumption]"},
        {"Item": "Perimeter fence and gates", "Specification": "Chain-link, 2.1 m, with access gates",
         "Qty": round(4 * side), "Unit": "m", "Basis": "square site of the fenced area [estimate]"},
        {"Item": "Earthing and lightning", "Specification": "Earth mesh, rods, bonding conductors", "Qty": 1, "Unit": "lot",
         "Basis": "designer per soil test"},
        {"Item": "SCADA, communications, revenue metering", "Specification": "Per NEA connection agreement", "Qty": 1,
         "Unit": "lot", "Basis": VERIFY},
    ]
    if fuses_needed:
        boq.insert(7, {"Item": "String fuses gPV", "Specification": f"{fuse_a} A, {v_class} V", "Qty": n_strings * 2,
                       "Unit": "nos", "Basis": "both poles of each string"})
    if n_combiners:
        boq.insert(7, {"Item": "DC combiner box", "Specification": f"{pi.strings_per_combiner} inputs, IP55 min., "
                       "fuses, switch-disconnector, SPD", "Qty": n_combiners, "Unit": "nos", "Basis": "book p.124"})

    # ---- single-line diagram (block level) -------------------------------------------------
    nodes = [("pv", f"PV strings\n{strings_inv} × {n_series} modules"),
             ("inv", f"Inverter {inv.ac_kva:g} kVA\n× {per_block} per block"),
             ("lv", f"LV panel {ac_v:g} V\n{dev_ac} A breakers"),
             ("tx", f"Transformer\n{blocks[0]['Transformer (kVA)']} kVA {blocks[0]['Ratio']}"),
             ("rmu", f"RMU / VCB {mv_kv:g} kV"), ("bus", f"{mv_kv:g} kV collector bus\n{n_blocks} blocks"),
             ("meter", "Revenue metering\n+ protection relays"), ("nea", "NEA substation")]
    edges = [("pv", "inv", f"{string_row['Selected']} DC" + (f", {fuse_a} A fuses" if fuses_needed else "")),
             ("inv", "lv", lv_row["Selected"]), ("lv", "tx", "LV busbar"), ("tx", "rmu", "MV cable"),
             ("rmu", "bus", "MV cable"), ("bus", "meter", ""), ("meter", "nea", f"{pi.line_to_nea_km:g} km line")]
    sld = {"nodes": nodes, "edges": edges}

    # ---- construction, commissioning, O&M, permits ------------------------------------------
    construction = [
        ("1. Site access, clearance and security", ["Survey and set out the boundary and blocks",
                                                    "Build access road and laydown area", "Clear vegetation; manage drainage",
                                                    "Install fence, gates and site security"]),
        ("2. Foundations and trenches", ["Geotechnical pull-out tests on trial piles", "Drive/screw piles or cast "
                                         "footings per the soil report", "Excavate cable trenches; lay ducts with "
                                         "warning tape"]),
        ("3. Substation and MV works", ["Build transformer/RMU plinths and control room",
                                        "Install transformers, RMUs and MV cables; terminate and test"]),
        ("4. Mounting structures", [f"Erect {n_tables} tables; check tilt {fr.out('tilt_deg'):.0f}° and row pitch "
                                    f"{pitch:.2f} m", "Torque fasteners to the manufacturer's values"]),
        ("5. Electrical site works", ["Mount modules (handle by frame; keep connectors dry)",
                                      f"Wire strings of {n_series} modules; label every string",
                                      "Install inverters, SPDs, fuses and disconnectors", "Pull and terminate LV cables",
                                      "Bond all frames to the earth mesh"]),
        ("6. Communications", ["Install weather station, SCADA and network; configure monitoring"]),
        ("7. On-site grid works", ["Build the line to the NEA substation; install metering and relays per NEA"]),
        ("8. Testing and commissioning", ["Pre-connection tests (below)", "NEA witness test and approval",
                                          "Energise block by block", "Post-connection, PR and availability tests"]),
    ]
    g, t = pi.test_irradiance_wm2, pi.test_cell_temp_c
    voc_test = n_series * mod.voc * (1 + mod.beta_voc_pct / 100 * (t - 25))
    isc_test = mod.isc * g / 1000
    commissioning = [
        {"Test": "Polarity and string open-circuit voltage", "Expected": f"{voc_test:,.0f} V per string at {t:g} °C cell",
         "Accept": "Within ±5 % of expected and equal between strings", "Basis": "book p.175 / IEC 62446-1"},
        {"Test": "String short-circuit current", "Expected": f"{isc_test:.1f} A at {g:g} W/m² (scale with measured irradiance)",
         "Accept": "Within ±5-10 % of expected", "Basis": "book p.175"},
        {"Test": "Insulation resistance (DC)", "Expected": f"Test at {ins['test_v']} V", "Accept":
            f"≥ {ins['min_mohm']:g} MΩ", "Basis": f"book Table 5.1 p.176 (system voltage {ins['system_voltage_v']:,.0f} V)"},
        {"Test": "Earth continuity and earth resistance", "Expected": "Continuous bonding; resistance per design",
         "Accept": "Designer's limit", "Basis": "IEC 62446-1"},
        {"Test": "Substation tests", "Expected": "Cable voltage test, power-frequency test of switchgear, protection functions",
         "Accept": "Per IEC/TS 61936 and NEA", "Basis": "book p.175"},
        {"Test": "Functional and loss-of-mains test", "Expected": "Inverters stop when the AC isolator opens; restart on "
            "reclosure", "Accept": "Immediate stop", "Basis": "book p.176"},
        {"Test": "Performance ratio test", "Expected": f"PR ≈ {fr.out('pr'):.2f} (design)", "Accept": "≥ contract value",
         "Basis": "book p.176"},
        {"Test": "Availability test", "Expected": "Plant generating whenever irradiance allows", "Accept":
            "Typically ≥ 99 % over ~5 days", "Basis": "book pp.176, 182"},
    ]
    o_and_m = [
        {"Activity": "Visual and mechanical inspection", "Frequency": "Quarterly", "By": "O&M technician"},
        {"Activity": "Module cleaning (dust; more in the dry season)", "Frequency": "Monthly in Nov-May [assumption for Nepal]",
         "By": "Cleaning crew"},
        {"Activity": "Vegetation and grounds", "Frequency": "As needed (monsoon growth)", "By": "Grounds staff"},
        {"Activity": "String I-V curve tests", "Frequency": "Annually", "By": "Certified electrician"},
        {"Activity": "Cables, protection and isolation inspection", "Frequency": "Annually", "By": "Certified electrician"},
        {"Activity": "Thermal (IR) scan of modules, combiners, switchgear", "Frequency": "Annually", "By": "O&M technician"},
        {"Activity": "Transformer maintenance, relay calibration", "Frequency": "Annually", "By": "HV-authorised electrician"},
        {"Activity": "Weather station cleaning / calibration", "Frequency": "Fortnightly / annually", "By": "Technician"},
        {"Activity": "Inverter maintenance", "Frequency": "Per manufacturer", "By": "Certified electrician"},
        {"Activity": "Revenue meter verification", "Frequency": "Per PPA / NEA", "By": "Certified electrician"},
    ]
    permits = [
        {"Item": "DoED survey licence, then generation licence", "Authority": "Department of Electricity Development",
         "Status": VERIFY},
        {"Item": "Power purchase agreement (competitive tender)", "Authority": "NEA", "Status": VERIFY},
        {"Item": "Grid connection study and agreement", "Authority": "NEA (Grid Development / System Planning)", "Status": VERIFY},
        {"Item": "IEE / EIA environmental approval", "Authority": "Ministry of Forests and Environment / local government",
         "Status": VERIFY},
        {"Item": "Land purchase or lease; agricultural-land and ceiling rules", "Authority": "Land Revenue Office / local "
            "government", "Status": VERIFY},
        {"Item": "Forest land clearance (if any)", "Authority": "Department of Forests", "Status": VERIFY},
        {"Item": "Construction permits and local recommendation", "Authority": "Municipality / rural municipality",
         "Status": VERIFY},
    ]
    return FarmPackage(hierarchy=hierarchy, counts=counts, layout=layout, blocks=blocks, cable_schedule=sched,
                       switchgear=switchgear, interconnection=interconnection, protection=protection, earthing=earthing,
                       insulation_test=ins, boq=boq, sld=sld, construction=construction, commissioning=commissioning,
                       o_and_m=o_and_m, permits=permits, warnings=warnings,
                       references=[BOOK, "IEC 60364-5-52 / 4-43 / 7-712", "IEC 62548", "IEC 62446-1", "NEPQA-2025"])
