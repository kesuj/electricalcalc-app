"""PV string sizing against an inverter (temperature-corrected voltages) and string fuse check.

Method (IEC 62548-1 approach):
  Voc_max  = Voc_stc × (1 + β_Voc × (T_cell,min − 25))          coldest morning, cell ≈ ambient
  T_cell,max = T_amb,max + (NOCT − 20) / 800 × 1000             hot sunny afternoon
  Vmp_min  = Vmp_stc × (1 + β_Vmp × (T_cell,max − 25))           β_Vmp ≈ β_Voc if not given
  N_max = floor(min(V_dc,max / Voc_max, V_mppt,max / Vmp(T_min))),  N_min = ceil(V_mppt,min / Vmp_min)
  String fuses needed when (N_parallel − 1) × 1.25 × Isc > module max series fuse rating;
  rating 1.5 × Isc ≤ I_n ≤ 2.4 × Isc and ≤ module max series fuse rating.
"""

from __future__ import annotations

import math

from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range

FUSE_SIZES_A = [10, 12, 15, 16, 20, 25, 30, 32, 35, 40, 50, 63]


def string_sizing(voc: float, vmp: float, isc: float, beta_voc_pct: float, t_amb_min: float, t_amb_max: float,
                  v_dc_max: float, mppt_min: float, mppt_max: float, noct: float = 45.0,
                  beta_vmp_pct: float | None = None, imp: float | None = None,
                  mppt_max_current_a: float | None = None, module_max_fuse_a: float | None = None,
                  strings_in_parallel: int | None = None) -> CalcResult:
    voc = require_positive("Module Voc", voc)
    vmp = require_positive("Module Vmp", vmp)
    isc = require_positive("Module Isc", isc)
    if vmp >= voc:
        raise ValidationError("Vmp must be lower than Voc (check the datasheet).")
    b_voc = require_range("Voc temperature coefficient (%/°C)", beta_voc_pct, -1.0, 0.0) / 100
    b_vmp = b_voc if beta_vmp_pct is None else require_range("Vmp temperature coefficient (%/°C)", beta_vmp_pct, -1.0, 0.0) / 100
    tmin = require_range("Minimum ambient temperature (°C)", t_amb_min, -50, 40)
    tmax = require_range("Maximum ambient temperature (°C)", t_amb_max, -10, 60)
    if tmax <= tmin:
        raise ValidationError("Maximum temperature must be higher than the minimum.")
    noct = require_range("NOCT (°C)", noct, 30, 60)
    vdc = require_positive("Inverter maximum DC voltage", v_dc_max)
    lo = require_positive("MPPT minimum voltage", mppt_min)
    hi = require_positive("MPPT maximum voltage", mppt_max)
    if not lo < hi <= vdc:
        raise ValidationError("Need MPPT min < MPPT max ≤ inverter max DC voltage.")

    voc_max = voc * (1 + b_voc * (tmin - 25))
    vmp_cold = vmp * (1 + b_vmp * (tmin - 25))
    tcell_max = tmax + (noct - 20) / 800 * 1000
    vmp_hot = vmp * (1 + b_vmp * (tcell_max - 25))
    n_max = math.floor(min(vdc / voc_max, hi / vmp_cold))
    n_min = math.ceil(lo / vmp_hot)
    warnings = []
    if n_min > n_max:
        warnings.append("No string length satisfies both limits - choose a different inverter or module.")
    outputs = {
        "voc_max_v": Q(voc_max, "V", f"Module Voc at {tmin:g} °C"),
        "tcell_max_c": Q(tcell_max, "°C", "Hottest cell temperature"),
        "vmp_hot_v": Q(vmp_hot, "V", f"Module Vmp at {tcell_max:.0f} °C cell"),
        "n_min": Q(n_min, "modules", "Minimum modules per string"),
        "n_max": Q(n_max, "modules", "Maximum modules per string"),
        "string_voc_max_v": Q(n_max * voc_max, "V", "String Voc (cold) at maximum length"),
    }
    equations = ["Voc,max = Voc × (1 + β_Voc × (T_min − 25))", "T_cell,max = T_amb,max + (NOCT − 20)/800 × 1000",
                 "Vmp,hot = Vmp × (1 + β_Vmp × (T_cell,max − 25))",
                 "N_max = floor(min(V_dc,max / Voc,max ; V_MPPT,max / Vmp,cold))", "N_min = ceil(V_MPPT,min / Vmp,hot)"]
    if mppt_max_current_a:
        i_req = (imp or isc)
        outputs["strings_per_mppt"] = Q(math.floor(require_positive("MPPT max current", mppt_max_current_a) / i_req),
                                        "strings", "Max parallel strings per MPPT (current limit)")
        equations.append("Strings per MPPT = floor(I_MPPT,max / I_mp)")
    if strings_in_parallel:
        np_ = int(require_positive("Strings in parallel", strings_in_parallel))
        limit = require_positive("Module max series fuse rating", module_max_fuse_a) if module_max_fuse_a else None
        reverse = (np_ - 1) * 1.25 * isc
        outputs["reverse_current_a"] = Q(reverse, "A", "Worst-case reverse current into one string")
        needed = limit is not None and reverse > limit
        outputs["fuse_needed"] = Q("Yes" if needed else ("No" if limit is not None else "Check"), "", "String fuses required")
        lo_f, hi_f = 1.5 * isc, min(2.4 * isc, limit) if limit else 2.4 * isc
        fuse = next((f for f in FUSE_SIZES_A if lo_f <= f <= hi_f), None)
        outputs["fuse_rating_a"] = Q(fuse if fuse else "none fits", "A", "String fuse rating (gPV)")
        equations += ["I_reverse = (N_parallel − 1) × 1.25 × Isc", "1.5 × Isc ≤ I_fuse ≤ min(2.4 × Isc, module max fuse)"]
        if fuse is None:
            warnings.append("No standard fuse size fits the 1.5-2.4 × Isc window; check the module datasheet.")
        if limit is None:
            warnings.append("Module maximum series fuse rating not entered - fuse requirement not checked.")
    return CalcResult(
        name="PV string sizing",
        inputs={"voc": Q(voc, "V", "Module Voc (STC)"), "vmp": Q(vmp, "V", "Module Vmp (STC)"),
                "isc": Q(isc, "A", "Module Isc (STC)"), "beta_voc": Q(b_voc * 100, "%/°C", "Voc temperature coefficient"),
                "t_min": Q(tmin, "°C", "Record minimum ambient"), "t_max": Q(tmax, "°C", "Maximum ambient (daytime)"),
                "noct": Q(noct, "°C", "NOCT"), "v_dc_max": Q(vdc, "V", "Inverter max DC voltage"),
                "mppt": Q(f"{lo:g}-{hi:g}", "V", "MPPT voltage window")},
        outputs=outputs, equations=equations,
        assumptions=["Cell temperature at the coldest time equals ambient (no sun at dawn).",
                     "Hot cell temperature from the NOCT model at 1000 W/m²; mounting with poor ventilation runs hotter.",
                     "β_Vmp taken equal to β_Voc when not given (slightly conservative for most crystalline modules)."],
        warnings=warnings + ["Confirm against the inverter manufacturer's string-design tool and IEC 62548-1."],
        references=["IEC 62548-1 (PV array design requirements) - method summarised, check the current edition"],
    )
