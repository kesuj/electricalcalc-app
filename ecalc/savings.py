"""Month-by-month NEA bill with and without solar for a home (Nepal net billing).

For each month an average day is simulated hour by hour (ecalc.profile) to split solar into
self-used and exported energy. Grid imports are billed with the NEA domestic slab tariff; exports
are credited at the net-billing rate. Assumptions: grid available all day for billing purposes,
credit is not carried between months, battery starts each day full (backup reserve).
"""

from __future__ import annotations

from .calc.result import require_positive
from .nepal_data import domestic_bill
from .profile import shape_kw, simulate_day

DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def monthly_bills(day_profiles: dict[int, list[float]], kwp: float, kwh_per_kwp_day: list[float],
                  daily_use_kwh: float, load_shape: str, meter_amp: int | None = 15,
                  flat_rate_rs: float | None = None, export_rs: float = 5.94, inverter_kw: float | None = None,
                  include_vat: bool = False) -> list[dict]:
    """meter_amp: NEA single-phase meter size (slab tariff); or give flat_rate_rs (e.g. three-phase)."""
    require_positive("Daily use", daily_use_kwh)
    load = shape_kw(daily_use_kwh, load_shape)
    rows = []
    for m in range(1, 13):
        d = simulate_day(day_profiles[m], kwp, kwh_per_kwp_day[m - 1], load, inverter_kw=inverter_kw)
        n = DAYS[m - 1]
        use, imp, exp = daily_use_kwh * n, d.totals["import_kwh"] * n, d.totals["export_kwh"] * n

        def bill(units):
            return domestic_bill(units, meter_amp, include_vat) if flat_rate_rs is None else units * flat_rate_rs
        before = bill(use)
        after = max(bill(imp) - exp * export_rs, 0.0)
        rows.append({"Month": MONTHS[m - 1], "Use (kWh)": round(use), "Solar (kWh)": round(d.totals["pv_kwh"] * n),
                     "From grid (kWh)": round(imp), "To grid (kWh)": round(exp),
                     "Bill without solar (Rs)": round(before), "Bill with solar (Rs)": round(after),
                     "Saving (Rs)": round(before - after)})
    return rows
