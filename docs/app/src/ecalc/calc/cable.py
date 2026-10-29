"""Module C - cable voltage drop (preliminary).

Resistance basis: IEC 60228 maximum DC conductor resistance at 20 °C for class 1/2
conductors (plain copper / aluminium), corrected to operating temperature with
R_T = R_20 × (1 + α20 × (T − 20)). Values must be checked against the actual cable
manufacturer's datasheet. Ampacity, protection and short-circuit withstand are NOT
checked here - this module answers only the voltage-drop question.
"""

from __future__ import annotations

import math

from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range

# IEC 60228 Table 2 (class 2 stranded; class 1 values for 0.5-1.0 mm² are equal) - Ω/km at 20 °C.
R20_OHM_PER_KM = {
    "copper": {0.75: 24.5, 1.0: 18.1, 1.5: 12.1, 2.5: 7.41, 4: 4.61, 6: 3.08, 10: 1.83, 16: 1.15,
               25: 0.727, 35: 0.524, 50: 0.387, 70: 0.268, 95: 0.193, 120: 0.153, 150: 0.124,
               185: 0.0991, 240: 0.0754, 300: 0.0601},
    "aluminium": {16: 1.91, 25: 1.20, 35: 0.868, 50: 0.641, 70: 0.443, 95: 0.320, 120: 0.253,
                  150: 0.206, 185: 0.164, 240: 0.125, 300: 0.100},
}
# Temperature coefficient of resistance at 20 °C (IEC 60228 Annex B / IEC 60287).
ALPHA20 = {"copper": 0.00393, "aluminium": 0.00403}
STANDARD_SIZES = {m: sorted(t) for m, t in R20_OHM_PER_KM.items()}
SYSTEMS = ("dc", "single_phase", "three_phase")

IEC60228_REF = "IEC 60228:2004, Table 2 - maximum DC resistance of class 2 conductors at 20 °C"


def conductor_resistance_ohm_per_km(material: str, size_mm2: float, temp_c: float) -> float:
    material = material.lower()
    if material not in R20_OHM_PER_KM:
        raise ValidationError("Conductor material must be 'copper' or 'aluminium'.")
    table = R20_OHM_PER_KM[material]
    if size_mm2 not in table:
        raise ValidationError(f"{size_mm2} mm² is not a standard {material} size in the table: "
                              f"{', '.join(str(s) for s in table)}.")
    return table[size_mm2] * (1 + ALPHA20[material] * (temp_c - 20))


def _drop_volts(system: str, current_a: float, length_m: float, r_ohm_km: float,
                x_mohm_m: float, pf: float) -> float:
    l_km = length_m / 1000
    if system == "dc":
        return 2 * current_a * r_ohm_km * l_km
    sin_phi = math.sqrt(1 - pf * pf)
    z = r_ohm_km * pf + (x_mohm_m) * sin_phi  # x in mΩ/m == Ω/km
    if system == "single_phase":
        return 2 * current_a * z * l_km
    return math.sqrt(3) * current_a * z * l_km


def voltage_drop(system: str, voltage_v: float, current_a: float, length_m: float,
                 size_mm2: float, material: str = "copper", conductor_temp_c: float = 70.0,
                 power_factor: float = 1.0, reactance_mohm_per_m: float = 0.0,
                 limit_pct: float | None = None) -> CalcResult:
    """Voltage drop for a single circuit.

    system: 'dc', 'single_phase' (V = phase-neutral), 'three_phase' (V = line-line, balanced).
    length_m: one-way route length.
    """
    if system not in SYSTEMS:
        raise ValidationError(f"System must be one of {SYSTEMS}.")
    v = require_positive("Nominal voltage", voltage_v)
    i = require_positive("Design current", current_a)
    l = require_positive("Route length", length_m)
    t = require_range("Conductor temperature", conductor_temp_c, -20, 250)
    pf = 1.0 if system == "dc" else require_range("Power factor", power_factor, 0.01, 1.0)
    x = require_positive("Reactance", reactance_mohm_per_m, allow_zero=True)
    r = conductor_resistance_ohm_per_km(material, size_mm2, t)
    vd = _drop_volts(system, i, l, r, x, pf)
    pct = vd / v * 100
    eq = {"dc": "ΔV = 2 × I × R × L",
          "single_phase": "ΔV = 2 × I × L × (R cos φ + X sin φ)",
          "three_phase": "ΔV(line-line) = √3 × I × L × (R cos φ + X sin φ)"}[system]
    warnings: list[str] = []
    assumptions = [
        f"Conductor resistance from IEC 60228 maximum values at 20 °C, corrected to {t:g} °C "
        f"(α20 = {ALPHA20[material.lower()]}/K).",
        "Length is the one-way route length; the return conductor is included by the formula.",
    ]
    if system != "dc":
        if x == 0:
            assumptions.append("Conductor reactance taken as zero (not entered).")
            if size_mm2 >= 35 and pf < 1:
                warnings.append("Reactance is significant for conductors of 35 mm² and above; enter the "
                                "datasheet value (typically mΩ/m) for a better estimate.")
        assumptions.append("Sinusoidal current; skin and proximity effects neglected.")
    if system == "three_phase":
        assumptions.append("Balanced three-phase load; percentage relative to line-line voltage.")
    passes = None
    if limit_pct is not None:
        lim = require_positive("Voltage-drop limit", limit_pct)
        passes = pct <= lim
        if not passes:
            warnings.append(f"Voltage drop {pct:.2f}% exceeds the {lim:g}% design limit.")
    warnings.append("Voltage drop only: ampacity (installation method, ambient temperature, grouping, "
                    "insulation), protective-device coordination and short-circuit withstand are not "
                    "checked and must be verified against the applicable wiring rules.")
    outputs = {"resistance_ohm_per_km": Q(r, "Ω/km", f"Conductor resistance at {t:g} °C"),
               "voltage_drop_v": Q(vd, "V", "Voltage drop ΔV"),
               "voltage_drop_pct": Q(pct, "%", "Voltage drop"),
               "receiving_voltage_v": Q(v - vd, "V", "Voltage at load (approx.)"),
               "power_loss_w": Q(_loss_w(system, i, r, l), "W", "Conductor I²R loss")}
    if passes is not None:
        outputs["within_limit"] = Q("Yes" if passes else "No", "", f"Within {limit_pct:g}% limit")
    return CalcResult(
        name="Cable voltage drop (preliminary)",
        inputs={"system": Q(system.replace("_", " "), "", "System"),
                "voltage_v": Q(v, "V", "Nominal voltage" + (" (line-line)" if system == "three_phase" else "")),
                "current_a": Q(i, "A", "Design current"), "length_m": Q(l, "m", "One-way length"),
                "size_mm2": Q(size_mm2, "mm²", "Conductor size"), "material": Q(material, "", "Conductor"),
                "conductor_temp_c": Q(t, "°C", "Conductor operating temperature"),
                "power_factor": Q(pf, "", "Power factor"),
                "reactance_mohm_per_m": Q(x, "mΩ/m", "Reactance")},
        outputs=outputs, equations=[eq, "R_T = R_20 × (1 + α20 × (T − 20))", "ΔV% = ΔV / V × 100"],
        assumptions=assumptions, warnings=warnings, references=[IEC60228_REF],
    )


def _loss_w(system: str, i: float, r_ohm_km: float, l_m: float) -> float:
    conductors = 3 if system == "three_phase" else 2
    return conductors * i * i * r_ohm_km * l_m / 1000


def minimum_size_for_drop(system: str, voltage_v: float, current_a: float, length_m: float,
                          limit_pct: float, material: str = "copper", conductor_temp_c: float = 70.0,
                          power_factor: float = 1.0, reactance_mohm_per_m: float = 0.0) -> CalcResult:
    """Smallest standard size meeting the voltage-drop limit (voltage-drop criterion only)."""
    material = material.lower()
    if material not in STANDARD_SIZES:
        raise ValidationError("Conductor material must be 'copper' or 'aluminium'.")
    rows = []
    chosen = None
    for size in STANDARD_SIZES[material]:
        r = voltage_drop(system, voltage_v, current_a, length_m, size, material, conductor_temp_c,
                         power_factor, reactance_mohm_per_m, limit_pct)
        ok = r.out("voltage_drop_pct") <= limit_pct
        rows.append({"Size (mm²)": size, "ΔV (V)": round(r.out("voltage_drop_v"), 2),
                     "ΔV (%)": round(r.out("voltage_drop_pct"), 2), "Meets limit": "Yes" if ok else "No"})
        if ok and chosen is None:
            chosen = r
    if chosen is None:
        raise ValidationError(f"No standard {material} size up to {STANDARD_SIZES[material][-1]} mm² meets "
                              f"{limit_pct}% - consider parallel conductors, a higher voltage or a shorter route.")
    chosen.name = "Minimum conductor size by voltage drop (preliminary)"
    chosen.outputs = {"min_size_mm2": Q(chosen.inputs["size_mm2"].value, "mm²", "Smallest size meeting limit"),
                      **chosen.outputs}
    chosen.inputs.pop("size_mm2")
    chosen.inputs["limit_pct"] = Q(limit_pct, "%", "Voltage-drop limit")
    chosen.tables["Size comparison"] = rows
    chosen.warnings.insert(0, "This size satisfies the voltage-drop criterion ONLY. The final cable must "
                              "also be selected for current-carrying capacity and protection by a qualified person.")
    return chosen
