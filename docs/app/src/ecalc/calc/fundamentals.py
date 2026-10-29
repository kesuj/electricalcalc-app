"""Module A - electrical fundamentals: Ohm's law, AC power (1-phase and 3-phase),
power-factor correction and energy cost. All quantities in SI base units unless noted."""

from __future__ import annotations

import math

from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range

SQRT3 = math.sqrt(3)


def ohms_law(voltage_v: float | None = None, current_a: float | None = None,
             resistance_ohm: float | None = None) -> CalcResult:
    """Solve V = I*R for whichever one of the three is missing (exactly two must be given)."""
    given = {k: v for k, v in (("V", voltage_v), ("I", current_a), ("R", resistance_ohm)) if v is not None}
    if len(given) != 2:
        raise ValidationError("Enter exactly two of voltage, current and resistance.")
    if voltage_v is None:
        i = require_positive("Current", current_a); r = require_positive("Resistance", resistance_ohm)
        v = i * r
    elif current_a is None:
        v = require_positive("Voltage", voltage_v); r = require_positive("Resistance", resistance_ohm)
        i = v / r
    else:
        v = require_positive("Voltage", voltage_v); i = require_positive("Current", current_a)
        r = v / i
    return CalcResult(
        name="Ohm's law (DC / resistive)",
        inputs={k: Q(val, {"V": "V", "I": "A", "R": "Ω"}[k], k) for k, val in given.items()},
        outputs={"voltage_v": Q(v, "V", "Voltage"), "current_a": Q(i, "A", "Current"),
                 "resistance_ohm": Q(r, "Ω", "Resistance"), "power_w": Q(v * i, "W", "Power P = V·I")},
        equations=["V = I × R", "P = V × I = I² × R = V² / R"],
        assumptions=["Purely resistive DC circuit (or AC with unity power factor)."],
    )


def _pf_parts(pf: float) -> tuple[float, float]:
    pf = require_range("Power factor", pf, 0.01, 1.0)
    return pf, math.sqrt(1 - pf * pf)


def ac_power(voltage_v: float, current_a: float, power_factor: float, phases: int = 1,
             lagging: bool = True) -> CalcResult:
    """Real/reactive/apparent power from voltage, current and PF.

    phases=1: voltage is the line-to-neutral (or line) voltage of the single-phase supply.
    phases=3: voltage is the line-to-line voltage of a balanced three-phase supply.
    """
    if phases not in (1, 3):
        raise ValidationError("Phases must be 1 or 3.")
    v = require_positive("Voltage", voltage_v)
    i = require_positive("Current", current_a)
    pf, sin_phi = _pf_parts(power_factor)
    k = SQRT3 if phases == 3 else 1.0
    s = k * v * i
    p = s * pf
    q = s * sin_phi * (1 if lagging else -1)
    eq_s = "S = √3 × V_LL × I" if phases == 3 else "S = V × I"
    return CalcResult(
        name=f"{'Three' if phases == 3 else 'Single'}-phase AC power",
        inputs={"voltage_v": Q(v, "V", "Line-to-line voltage" if phases == 3 else "Voltage"),
                "current_a": Q(i, "A", "Line current"),
                "power_factor": Q(pf, "", f"Power factor ({'lagging' if lagging else 'leading'})")},
        outputs={"apparent_power_kva": Q(s / 1e3, "kVA", "Apparent power S"),
                 "real_power_kw": Q(p / 1e3, "kW", "Real power P"),
                 "reactive_power_kvar": Q(q / 1e3, "kvar", "Reactive power Q"),
                 "phase_angle_deg": Q(math.degrees(math.acos(pf)), "°", "Phase angle φ")},
        equations=[eq_s, "P = S × cos φ", "Q = S × sin φ", "S² = P² + Q²"],
        assumptions=["Sinusoidal steady state, no harmonics."] +
                    (["Balanced three-phase load."] if phases == 3 else []),
    )


def current_from_power(real_power_kw: float, voltage_v: float, power_factor: float,
                       phases: int = 1) -> CalcResult:
    """Line current drawn by a load of known real power."""
    if phases not in (1, 3):
        raise ValidationError("Phases must be 1 or 3.")
    p = require_positive("Real power", real_power_kw) * 1e3
    v = require_positive("Voltage", voltage_v)
    pf, _ = _pf_parts(power_factor)
    k = SQRT3 if phases == 3 else 1.0
    i = p / (k * v * pf)
    return CalcResult(
        name=f"Load current ({phases}-phase)",
        inputs={"real_power_kw": Q(p / 1e3, "kW", "Real power"), "voltage_v": Q(v, "V", "Voltage"),
                "power_factor": Q(pf, "", "Power factor")},
        outputs={"current_a": Q(i, "A", "Line current"), "apparent_power_kva": Q(p / pf / 1e3, "kVA", "Apparent power")},
        equations=["I = P / (√3 × V_LL × cos φ)" if phases == 3 else "I = P / (V × cos φ)"],
        assumptions=["Balanced, sinusoidal load."],
    )


def pf_correction(real_power_kw: float, pf_existing: float, pf_target: float,
                  voltage_ll_v: float | None = None, frequency_hz: float = 50.0,
                  connection: str = "delta") -> CalcResult:
    """Capacitor kvar to raise PF:  Qc = P (tan φ1 − tan φ2)."""
    p = require_positive("Real power", real_power_kw)
    pf1, _ = _pf_parts(pf_existing)
    pf2, _ = _pf_parts(pf_target)
    if pf2 <= pf1:
        raise ValidationError("Target power factor must be higher than the existing power factor.")
    t1, t2 = math.tan(math.acos(pf1)), math.tan(math.acos(pf2))
    qc = p * (t1 - t2)
    outputs = {"capacitor_kvar": Q(qc, "kvar", "Required capacitor bank Qc"),
               "kva_before": Q(p / pf1, "kVA", "Apparent power before"),
               "kva_after": Q(p / pf2, "kVA", "Apparent power after"),
               "kva_reduction_pct": Q((1 - pf1 / pf2) * 100, "%", "Apparent power (and current) reduction")}
    equations = ["Qc = P × (tan φ1 − tan φ2)", "φ = arccos(PF)"]
    if voltage_ll_v:
        v = require_positive("Line voltage", voltage_ll_v)
        f = require_positive("Frequency", frequency_hz)
        w = 2 * math.pi * f
        if connection == "delta":
            c = qc * 1e3 / (3 * w * v ** 2)
            equations.append("C per phase (delta) = Qc / (3 × 2πf × V_LL²)")
        elif connection == "star":
            c = qc * 1e3 / (w * v ** 2)
            equations.append("C per phase (star) = Qc / (2πf × V_LL²)")
        else:
            raise ValidationError("Connection must be 'delta' or 'star'.")
        outputs["capacitance_per_phase_uf"] = Q(c * 1e6, "µF", f"Capacitance per phase ({connection})")
    return CalcResult(
        name="Power-factor correction estimate",
        inputs={"real_power_kw": Q(p, "kW", "Real power"), "pf_existing": Q(pf1, "", "Existing PF"),
                "pf_target": Q(pf2, "", "Target PF")},
        outputs=outputs, equations=equations,
        assumptions=["Real power stays constant after correction.",
                     "Fixed capacitor bank at nominal voltage; harmonics not considered."],
        warnings=["Check for harmonic resonance and utility PF penalty rules before selecting a bank; "
                  "detuned reactors may be required where harmonic loads (VFDs, rectifiers) exist."],
    )


def pf_from_energy(kwh: float, kvarh: float) -> float:
    """Average power factor over a billing period from active and reactive energy meter readings."""
    p = require_positive("Active energy (kWh)", kwh)
    q = require_positive("Reactive energy (kVArh)", kvarh, allow_zero=True)
    return p / math.hypot(p, q)


def pf_correction_from_meter(max_demand_kw: float, kwh: float, kvarh: float, pf_target: float,
                             voltage_ll_v: float | None = None, frequency_hz: float = 50.0,
                             connection: str = "delta") -> CalcResult:
    """PF correction where the existing PF is derived from kWh and kVArh readings (e.g. an industrial bill)."""
    pf1 = pf_from_energy(kwh, kvarh)
    r = pf_correction(max_demand_kw, pf1, pf_target, voltage_ll_v, frequency_hz, connection)
    r.name = "Power-factor correction estimate (from meter readings)"
    r.inputs = {"kwh": Q(kwh, "kWh", "Active energy in period"), "kvarh": Q(kvarh, "kVArh", "Reactive energy in period"),
                "max_demand_kw": Q(max_demand_kw, "kW", "Maximum demand (sizing basis)"), **r.inputs}
    r.inputs["pf_existing"].label = "Existing PF (average, from meter readings)"
    r.equations.insert(0, "PF_avg = kWh / √(kWh² + kVArh²)")
    r.assumptions.append("Existing PF is the billing-period average; PF at maximum demand may differ. Logged "
                         "measurements give a more reliable basis for automatic (stepped) banks.")
    return r


def energy_cost(power_kw: float, hours_per_day: float, days: float = 30,
                tariff_per_kwh: float | None = None, currency: str = "NPR") -> CalcResult:
    p = require_positive("Power", power_kw)
    h = require_range("Hours per day", hours_per_day, 0, 24)
    d = require_positive("Days", days)
    e = p * h * d
    outputs = {"energy_kwh": Q(e, "kWh", "Energy consumed")}
    if tariff_per_kwh is not None:
        t = require_positive("Tariff", tariff_per_kwh, allow_zero=True)
        outputs["cost"] = Q(e * t, currency, "Energy cost (flat tariff)")
    return CalcResult(
        name="Energy consumption",
        inputs={"power_kw": Q(p, "kW", "Average power"), "hours_per_day": Q(h, "h/day", "Operating hours"),
                "days": Q(d, "days", "Period")},
        outputs=outputs, equations=["E = P × h × days", "Cost = E × tariff"],
        assumptions=["Constant average power while operating.",
                     "Flat energy tariff; demand charges, slabs, taxes and fixed charges are not included."],
    )


# ---- unit conversions --------------------------------------------------------------
HP_TO_KW = 0.745699872  # mechanical (imperial) horsepower
METRIC_HP_TO_KW = 0.73549875
KWH_TO_MJ = 3.6


def awg_to_mm2(awg: int) -> float:
    """Cross-section of a solid AWG conductor (ASTM B258 diameter formula)."""
    if not -3 <= awg <= 40:  # 0000 = -3
        raise ValidationError("AWG must be between 0000 (-3) and 40.")
    d_mm = 0.127 * 92 ** ((36 - awg) / 39)
    return math.pi / 4 * d_mm ** 2


def kcmil_to_mm2(kcmil: float) -> float:
    return require_positive("kcmil", kcmil) * 0.506707479
