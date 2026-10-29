"""Current Nepal data (checked 2026-10-29). Every value has a source and a tag:
[V] official/primary document, [S] secondary (news, aggregator), [A] assumption/derived.
Prices are indicative and change - the app always lets the user override them.
"""

from __future__ import annotations

from .calc.result import ValidationError, require_positive

CHECKED = "2026-10-29"
ERC_ORDER = ("ERC, NEA Electricity Consumer Tariff Determination 2078 (decided 2078/07/08 BS), p.74 [V] - "
             "https://www.erc.gov.np/charge-order")

# ---- NEA domestic single-phase tariff (ERC order 2078, p.74) [V] ------------------------------
# energy blocks: (upper limit of block in units, Rs/kWh) - first block rate depends on meter size
DOMESTIC_FIRST_BLOCK = {5: 0.0, 15: 4.0, 30: 5.0, 60: 6.0}          # 0-20 units
DOMESTIC_FIRST_BLOCK_5A_ABOVE_20 = 3.0                              # 5 A meter, if > 20 units
DOMESTIC_BLOCKS = [(30, 6.5), (50, 8.0), (100, 9.5), (250, 9.5), (float("inf"), 11.0)]
# service ("minimum") charge by consumption band and meter size, Rs/month
DOMESTIC_SERVICE = {  # band upper limit -> {amp: Rs}
    20: {5: 30, 15: 50, 30: 75, 60: 125}, 30: {5: 50, 15: 75, 30: 100, 60: 125},
    50: {5: 50, 15: 75, 30: 100, 60: 125}, 100: {5: 75, 15: 100, 30: 125, 60: 150},
    250: {5: 100, 15: 125, 30: 150, 60: 200}, float("inf"): {5: 150, 15: 175, 30: 200, 60: 250},
}
VAT_PCT = 5.0   # on bills above 50 units/month from Shrawan 2083 [S] Ratopati 30 Jul 2026 (may be revised)

# ---- other tariffs ------------------------------------------------------------------------
NET_BILLING_EXPORT_RS = 5.94       # rooftop export credit (net billing since Jul 2022) [S]
UTILITY_PPA_RS = 5.30              # default within 2024 tender awards Rs 4.99-5.54/kWh, 25-yr PPA [S]
UTILITY_PPA_RANGE = (4.99, 5.54)
UTILITY_PPA_CEILING_RS = 5.94      # [S]
PPA_YEARS = 25                     # [S]
COMMERCIAL_LV_RS = 11.20           # Rs/kWh + Rs 325/kVA-month demand charge [V] ERC p.75
INDUSTRIAL_SMALL_LV_RS = 9.60      # + Rs 110/kVA-month [V] ERC p.75

# ---- indicative prices (NPR, incl. VAT) - pricenepal.com Jul 2026 [S]; sandippaudel.com [S] -------
PRICE_MODULE_RS_PER_WP = 80
PRICE_LIFEPO4_RS_PER_KWH = 35_000
PRICE_INVERTER_RS_PER_KW = 18_000
INSTALLED_ONGRID_RS_PER_KWP = 80_000     # residential / small commercial, installed
INSTALLED_UTILITY_RS_PER_KW = 65_000     # utility-scale EPC (range 60-70k)
UTILITY_OM_PCT_OF_CAPEX = 1.0            # [A] typical 1 %/yr of capex
DISCOUNT_RATE_PCT = 10.0                 # [S] emerging-market range 8-12 %

# ---- climate (record lows / highs, Wikipedia climate boxes citing DHM/WMO) [S] ------------------
SITE_TEMPS_C = {  # site -> (record low, record high)
    "Kathmandu": (-3.5, 36.6), "Pokhara": (0.5, 38.5), "Biratnagar": (-1.0, 43.0),
    "Nepalgunj": (-0.3, 45.0), "Jumla": (-15.0, 33.3),
}

# ---- NEPQA-2025 (AEPC) minimums [V] ----------------------------------------------------------
NEPQA = {"module_min_eff_pct": 21.0, "li_min_cycles_at_80dod": 3000, "li_min_rte_pct": 85.0,
         "mppt_min_eff_pct": 95.0, "grid_inv_min_eff_pct_over_5kva": 97.0, "grid_inv_min_eff_pct_upto_5kva": 95.0,
         "module_warranty_yr": 10, "inverter_warranty_yr": 5, "battery_warranty_yr": 5}

SOURCES = [
    ERC_ORDER,
    "NEPQA-2025 and Amendment-1 (AEPC, Aug 2025 / Apr 2026) [V]",
    "Net billing export Rs 5.94/kWh - Kathmandu Post 2022; Urja Khabar Jul 2026 [S]",
    "Utility solar PPA Rs 4.99-5.54/kWh (2024 NEA tender) - Urja Khabar 28 May 2025 [S]",
    "Equipment prices - pricenepal.com (Jul 2026), sandippaudel.com (Aug 2026) [S, indicative]",
    "Temperatures - DHM/WMO normals via Wikipedia climate tables [S]",
]


def domestic_bill(units: float, meter_amp: int = 15, include_vat: bool = False) -> float:
    """Monthly NEA domestic single-phase bill (Rs): service charge for the consumption band +
    progressive energy blocks (ERC order 2078 p.74)."""
    if meter_amp not in DOMESTIC_FIRST_BLOCK:
        raise ValidationError("Meter size must be 5, 15, 30 or 60 A.")
    u = require_positive("Units", units, allow_zero=True)
    service = next(v[meter_amp] for lim, v in DOMESTIC_SERVICE.items() if u <= lim)
    first_rate = DOMESTIC_FIRST_BLOCK[meter_amp]
    if meter_amp == 5 and u > 20:
        first_rate = DOMESTIC_FIRST_BLOCK_5A_ABOVE_20
    energy, lower = min(u, 20) * first_rate, 20.0
    for upper, rate in DOMESTIC_BLOCKS:
        if u <= lower:
            break
        energy += (min(u, upper) - lower) * rate
        lower = upper
    total = service + energy
    if include_vat and u > 50:
        total *= 1 + VAT_PCT / 100
    return total


def site_temperatures(site_name: str) -> tuple[float, float] | None:
    for key, temps in SITE_TEMPS_C.items():
        if site_name.startswith(key):
            return temps
    return None
