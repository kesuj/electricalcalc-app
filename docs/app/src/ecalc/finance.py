"""Project money maths: yearly cash flow, simple and discounted payback, NPV, IRR and LCOE.

LCOE follows the standard discounted form (NREL/IRENA): sum of discounted costs / sum of discounted
energy. All inputs are user-entered; nothing here assumes a price.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calc.result import ValidationError, require_positive, require_range


@dataclass
class CashFlowResult:
    rows: list[dict]
    simple_payback_years: float | None
    discounted_payback_years: float | None
    npv: float
    irr_pct: float | None
    lcoe: float


def _irr(flows: list[float]) -> float | None:
    def npv(r):
        return sum(f / (1 + r) ** t for t, f in enumerate(flows))
    lo, hi = -0.99, 1.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def cash_flow(capex: float, year1_energy_kwh: float, value_per_kwh: float, years: int = 25,
              degradation_pct: float = 0.5, price_escalation_pct: float = 0.0, om_per_year: float = 0.0,
              om_escalation_pct: float = 0.0, discount_rate_pct: float = 10.0,
              replacements: dict[int, float] | None = None) -> CashFlowResult:
    """value_per_kwh: what one kWh is worth (bill saving tariff for homes, PPA/sale rate for farms)."""
    capex = require_positive("Capital cost", capex)
    e1 = require_positive("First-year energy", year1_energy_kwh)
    v = require_positive("Value per kWh", value_per_kwh, allow_zero=True)
    years = int(require_range("Project life", years, 1, 50))
    deg = require_range("Degradation", degradation_pct, 0, 5) / 100
    esc = require_range("Price escalation", price_escalation_pct, -10, 20) / 100
    om_esc = require_range("O&M escalation", om_escalation_pct, -10, 20) / 100
    r = require_range("Discount rate", discount_rate_pct, 0, 50) / 100
    replacements = replacements or {}
    rows, flows = [], [-capex]
    cum, cum_disc = -capex, -capex
    disc_cost, disc_energy = capex, 0.0
    simple_pb = disc_pb = None
    for t in range(1, years + 1):
        energy = e1 * (1 - deg) ** (t - 1)
        income = energy * v * (1 + esc) ** (t - 1)
        om = om_per_year * (1 + om_esc) ** (t - 1) + replacements.get(t, 0.0)
        net = income - om
        df = (1 + r) ** t
        prev, prev_d = cum, cum_disc
        cum += net
        cum_disc += net / df
        disc_cost += om / df
        disc_energy += energy / df
        if simple_pb is None and cum >= 0 and net > 0:
            simple_pb = t - 1 + (-prev / net)
        if disc_pb is None and cum_disc >= 0 and net > 0:
            disc_pb = t - 1 + (-prev_d / (net / df))
        flows.append(net)
        rows.append({"Year": t, "Energy (kWh)": round(energy), "Income": round(income), "O&M + replacements": round(om),
                     "Net cash flow": round(net), "Cumulative": round(cum), "Cumulative (discounted)": round(cum_disc)})
    if disc_energy <= 0:
        raise ValidationError("Energy must be positive to compute LCOE.")
    irr = _irr(flows)
    return CashFlowResult(rows, simple_pb, disc_pb, cum_disc, None if irr is None else irr * 100,
                          disc_cost / disc_energy)
