"""Load schedule: appliance list -> daily energy, connected load, maximum demand and
critical (backup) load. Motor loads are flagged; start-up surge is not estimated because
it depends on the motor/compressor datasheet."""

from __future__ import annotations

from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range


def load_schedule(rows: list[dict], coincidence_factor: float = 1.0) -> CalcResult:
    """rows: dicts with keys name, power_w, qty, hours_per_day, critical (bool), motor (bool).

    coincidence_factor (simultaneity factor, IEC "ks", <= 1) = share of connected load running at the same time.
    It is the inverse of the textbook diversity factor (sum of individual max demands / group max demand, >= 1).
    """
    cf = require_range("Coincidence factor", coincidence_factor, 0.1, 1.0)
    clean = []
    for i, r in enumerate(rows, 1):
        name = str(r.get("name") or "").strip()
        if not name and not r.get("power_w"):
            continue  # blank row in the editor
        label = name or f"Row {i}"
        p = require_positive(f"{label}: power", r.get("power_w"))
        n = require_positive(f"{label}: quantity", r.get("qty") or 0)
        h = require_range(f"{label}: hours per day", r.get("hours_per_day") if r.get("hours_per_day") is not None else -1, 0, 24)
        clean.append({"name": label, "p": p, "n": n, "h": h, "crit": bool(r.get("critical")), "motor": bool(r.get("motor"))})
    if not clean:
        raise ValidationError("Enter at least one load (name, power, quantity and hours per day).")

    table, connected, daily, crit_kw, crit_kwh, motors = [], 0.0, 0.0, 0.0, 0.0, []
    for c in clean:
        kw = c["p"] * c["n"] / 1000
        kwh = kw * c["h"]
        connected += kw
        daily += kwh
        if c["crit"]:
            crit_kw += kw
            crit_kwh += kwh
        if c["motor"]:
            motors.append(c["name"])
        table.append({"Load": c["name"], "Power (W)": c["p"], "Qty": c["n"], "Hours/day": c["h"],
                      "Connected (kW)": round(kw, 3), "Energy (kWh/day)": round(kwh, 3),
                      "Critical": "Yes" if c["crit"] else "", "Motor": "Yes" if c["motor"] else ""})
    table.append({"Load": "TOTAL", "Power (W)": "", "Qty": "", "Hours/day": "", "Connected (kW)": round(connected, 3),
                  "Energy (kWh/day)": round(daily, 3), "Critical": "", "Motor": ""})

    warnings = []
    if cf < 1 and len(clean) < 10:
        warnings.append(f"Coincidence factor {cf:g} assumed with only {len(clean)} load types. In small buildings "
                        "most loads can run together; a value below 1.0 may undersize the inverter.")
    if motors:
        warnings.append(f"Motor/compressor loads ({', '.join(motors)}) have start-up surge, typically several times running "
                        "power. Check the inverter surge rating against the equipment datasheets.")
    if daily == 0:
        warnings.append("Total daily energy is zero - check the hours per day.")
    return CalcResult(
        name="Load schedule",
        inputs={"n_loads": Q(len(clean), "", "Number of load types"),
                "coincidence_factor": Q(cf, "", "Coincidence (simultaneity) factor")},
        outputs={"daily_kwh": Q(daily, "kWh/day", "Daily energy consumption"),
                 "monthly_kwh": Q(daily * 30, "kWh/month", "Monthly energy (30 days)"),
                 "connected_kw": Q(connected, "kW", "Total connected load"),
                 "max_demand_kw": Q(connected * cf, "kW", "Estimated maximum demand"),
                 "critical_kwh": Q(crit_kwh, "kWh/day", "Critical (backup) energy"),
                 "critical_kw": Q(crit_kw, "kW", "Critical connected load")},
        equations=["Connected kW = Σ (W × qty) / 1000", "Daily kWh = Σ (W × qty × hours) / 1000",
                   "Maximum demand = connected kW × coincidence factor",
                   "Coincidence factor = 1 / diversity factor"],
        assumptions=["Power values are the user-entered running (rated) powers.",
                     f"Coincidence factor {cf:g} (equivalent diversity factor {1 / cf:.2f}) is a design assumption for how much "
                     "load runs simultaneously.",
                     "Hours per day are average equivalent full-power operating hours."],
        warnings=warnings, tables={"Load schedule": table},
    )
