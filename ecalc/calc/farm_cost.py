"""Rough capital-cost estimate of a solar farm in Nepal from the construction package quantities.

Every rate has a low / central / high value and a basis tag:
  [S] secondary source (news, aggregator, practitioner, Indian price converted at NPR 1.6 per INR)
  [A] assumption (no Nepali price found) - replace with real quotes.
Exchange-rate assumption: NPR 140 per USD [A]. Land purchase/lease is NOT included (shown separately).
"""

from __future__ import annotations

from .result import CalcResult, Quantity as Q, ValidationError, require_positive

NPR_PER_USD = 140.0
INR_TO_NPR = 1.6
LAKH, CRORE = 1e5, 1e7

# key -> (label, unit, low, central, high, basis)
RATES: dict[str, tuple[str, str, float, float, float, str]] = {
    "modules": ("PV modules (550 W TOPCon, bulk import, landed incl. VAT)", "per Wp", 21, 25, 30,
                "[A] global price 11.4-16 US¢/W (Ekantipur, May 2026) × NPR 140/USD + ~15 % freight/clearing + 13 % VAT"),
    "inverters": ("String inverters (100 kVA class, NEPQA certified)", "per kVA", 5500, 7500, 10000,
                  "[A] international utility string-inverter prices ~US$40-70/kW + import"),
    "structure": ("Mounting structure, hot-dip galvanised, incl. foundations", "per kWp", 9600, 12800, 19200,
                  "[S] Indian benchmark ₹6,000-12,000/kW (Bridgeway Power) × 1.6"),
    "string_cable": ("PV string cable 4 mm² H1Z2Z2-K", "per m", 90, 120, 160, "[A] Indian ₹55-100/m × 1.6"),
    "mc4": ("MC4 connector pairs (genuine, module maker's type)", "per pair", 150, 300, 450, "[A]"),
    "fuses": ("String fuses gPV + holders", "per fuse", 400, 700, 1200, "[A]"),
    "spd": ("DC surge protectors Type 2", "per unit", 3000, 5000, 8000, "[A]"),
    "lv_cable": ("LV AC cable (single-core length)", "per m", 900, 1200, 1600, "[A] Indian 70 mm² Cu ₹600-800/m × 1.6"),
    "acdb": ("AC combiner board with breakers (per inverter)", "per inverter", 30000, 50000, 80000, "[A]"),
    "transformer": ("Step-up transformer 0.8/11 kV ONAN", "per kVA", 2500, 3500, 5000,
                    "[A] Indian distribution transformer ≈ ₹1,800/kVA × 1.6 + transport"),
    "switchgear": ("11 kV switchgear (RMU / VCB panels) + protection relays", "per panel", 800000, 1200000, 1600000,
                   "[A] Indian ₹5-10 lakh per panel × 1.6"),
    "mv_cable": ("11 kV XLPE cable (single-core length)", "per m", 1300, 1800, 2400, "[A] Indian ₹800-1,500/m × 1.6"),
    "line": ("11 kV overhead line to the NEA substation", "per km", 1800000, 2500000, 3500000,
             "[A] no NEA unit rate found - get the NEA connection estimate"),
    "metering": ("NEA revenue metering, SCADA, weather station, CCTV", "lot", 1500000, 2500000, 4000000, "[A]"),
    "fence": ("Perimeter fence 2.1 m with gates", "per m", 2500, 3500, 5000, "[A]"),
    "civil": ("Site levelling, drainage, internal roads, control room", "per kWp", 2000, 3000, 5000, "[A]"),
    "earthing": ("Earth mesh, electrodes, lightning protection", "per kWp", 800, 1200, 2000, "[A]"),
    "labour": ("Installation, testing and commissioning labour", "per kWp", 3000, 4000, 6000, "[A]"),
}
SOFT = {"low": 0.03, "central": 0.04, "high": 0.06}         # engineering, permits, IEE, PPA, insurance [A]
CONTINGENCY = {"low": 0.05, "central": 0.075, "high": 0.10}  # [A]
BENCHMARKS = [
    "Nepal utility-scale EPC ≈ NPR 60,000-70,000 per kW [S: sandippaudel.com, Aug 2026]",
    "Nepal commercial rooftop ≥ 500 kWp ≈ NPR 35,000-45,000 per kWp, no transformer/line/land [S: same]",
    f"IRENA 2024 global utility PV average US$691/kW ≈ NPR {691 * NPR_PER_USD:,.0f}/kW at NPR {NPR_PER_USD:g}/USD [V/A]",
]


def _boq_qty(boq: list[dict], start: str) -> float:
    for r in boq:
        if str(r.get("Item", "")).startswith(start):
            try:
                return float(r.get("Qty") or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def farm_cost(pkg, module_wp: float, inverter_kva: float, line_km: float, land_ha: float | None = None) -> CalcResult:
    """Capital cost from a FarmPackage (ecalc.calc.install_farm) with low / central / high scenarios."""
    c = pkg.counts
    n_mod, n_inv = c["modules"]["value"], c["inverters"]["value"]
    kwp = n_mod * require_positive("Module Wp", module_wp) / 1000
    if kwp <= 0:
        raise ValidationError("No modules in the package.")
    qty = {
        "modules": n_mod * module_wp, "inverters": n_inv * require_positive("Inverter kVA", inverter_kva),
        "structure": kwp, "string_cable": _boq_qty(pkg.boq, "PV string cable") * 1000,
        "mc4": _boq_qty(pkg.boq, "MC4"), "fuses": _boq_qty(pkg.boq, "String fuses"),
        "spd": _boq_qty(pkg.boq, "DC SPD"), "lv_cable": _boq_qty(pkg.boq, "LV AC cable") * 1000,
        "acdb": n_inv, "transformer": c["transformer_kva_total"]["value"],
        "switchgear": _boq_qty(pkg.boq, "MV switchgear"), "mv_cable": _boq_qty(pkg.boq, "MV cable") * 1000,
        "line": require_positive("Line length", line_km, allow_zero=True), "metering": 1,
        "fence": _boq_qty(pkg.boq, "Perimeter fence"), "civil": kwp, "earthing": kwp, "labour": kwp,
    }
    rows, totals = [], {"low": 0.0, "central": 0.0, "high": 0.0}
    for key, (label, unit, lo, mid, hi, basis) in RATES.items():
        q = qty[key]
        if not q:
            continue
        amt = {"low": q * lo, "central": q * mid, "high": q * hi}
        for s in totals:
            totals[s] += amt[s]
        rows.append({"Item": label, "Quantity": f"{q:,.0f}" if q >= 10 else f"{q:g}", "Unit": unit.replace("per ", ""),
                     "Rate (central, NPR)": f"{mid:,.0f}", "Low (NPR lakh)": round(amt["low"] / LAKH, 1),
                     "Central (NPR lakh)": round(amt["central"] / LAKH, 1), "High (NPR lakh)": round(amt["high"] / LAKH, 1),
                     "Basis": basis})
    hard = dict(totals)
    for s in totals:
        soft = hard[s] * SOFT[s]
        cont = (hard[s] + soft) * CONTINGENCY[s]
        totals[s] = hard[s] + soft + cont
    rows.append({"Item": "Engineering, permits (DoED, IEE), PPA, insurance", "Quantity": "", "Unit": "% of hard cost",
                 "Rate (central, NPR)": f"{SOFT['central']:.0%}",
                 **{f"{k.capitalize()} (NPR lakh)": round(hard[k] * SOFT[k] / LAKH, 1) for k in ("low", "central", "high")},
                 "Basis": "[A] 3 / 4 / 6 %"})
    rows.append({"Item": "Contingency", "Quantity": "", "Unit": "%", "Rate (central, NPR)": f"{CONTINGENCY['central']:.1%}",
                 **{f"{k.capitalize()} (NPR lakh)": round((hard[k] * (1 + SOFT[k])) * CONTINGENCY[k] / LAKH, 1)
                    for k in ("low", "central", "high")}, "Basis": "[A] 5 / 7.5 / 10 %"})
    out = {
        "kwp": Q(kwp, "kWp", "Installed DC capacity"),
        "total_low_crore": Q(totals["low"] / CRORE, "NPR crore", "Total (low)"),
        "total_central_crore": Q(totals["central"] / CRORE, "NPR crore", "Total (central estimate)"),
        "total_high_crore": Q(totals["high"] / CRORE, "NPR crore", "Total (high)"),
        "per_kwp_central": Q(totals["central"] / kwp, "NPR/kWp", "Cost per kWp (central)"),
        "per_kwp_range": Q(f"{totals['low'] / kwp:,.0f} - {totals['high'] / kwp:,.0f}", "NPR/kWp", "Cost per kWp (range)"),
    }
    if land_ha:
        out["land_ha"] = Q(land_ha, "ha", "Land needed (not priced - buy or lease separately)")
    return CalcResult(
        name="Solar farm capital cost estimate (rough)",
        inputs={"kwp": Q(kwp, "kWp", "Plant size"), "line_km": Q(line_km, "km", "11 kV line to NEA substation"),
                "fx": Q(NPR_PER_USD, "NPR/USD", "Exchange-rate assumption")},
        outputs=out,
        equations=["Item cost = quantity (from the construction package) × unit rate",
                   "Total = hard costs × (1 + soft %) × (1 + contingency %)"],
        assumptions=["Rates tagged [A] are assumptions where no Nepali price was found - replace with supplier quotes.",
                     "Land purchase or lease, financing costs during construction and VAT recovery are not included.",
                     "Module prices were rising through 2026; re-check before budgeting."],
        warnings=["Rough feasibility estimate (±25-30 %), not a quotation."],
        references=BENCHMARKS, tables={"Cost breakdown": rows},
    )
