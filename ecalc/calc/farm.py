"""Utility-scale solar farm design following Neill, Stapleton & Martell, *Solar Farms* (Earthscan),
Ch.3-4: tilt -> row spacing -> 5-step array/inverter matching -> performance ratio -> yield ->
land -> transformer -> economics. Book errata are corrected (see ENGINEERING_METHODS.md); values
the book does not give (land per MW, transformer kVA, PR defaults) use modern sources, marked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .result import CalcResult, Quantity as Q, ValidationError, require_positive, require_range

BOOK = "Neill, Stapleton & Martell, Solar Farms (Earthscan)"
ROPANI_M2 = 508.72            # Nepal land units (hill system)
BIGHA_M2 = 6772.63            # Terai system
KATTHA_M2 = 338.63

# Modern default losses (%). Temperature and reflection normally come from PVGIS for the site.
DEFAULT_LOSSES = {
    "Temperature": 8.0, "Reflection (angle of incidence)": 3.0, "Soiling / dust": 3.0,
    "Mismatch and module tolerance": 1.5, "DC cable": 1.5, "Inverter": 2.0, "AC cable": 0.5,
    "Transformer": 1.0, "Availability / downtime": 1.0,
}


def optimal_tilt(latitude: float) -> float:
    """Box 4.1: annual optimum tilt = latitude (equinox), minimum 10° for self-cleaning (p.102)."""
    return max(abs(require_range("Latitude", latitude, -90, 90)), 10.0)


def winter_sun(latitude: float, hours_from_noon: float) -> tuple[float, float]:
    """Sun altitude and azimuth (from due south / the array normal) on the winter solstice at solar time
    noon ± hours: sin α = sin φ sin δ + cos φ cos δ cos ω,  cos γ = (sin α sin φ − sin δ) / (cos α cos φ)."""
    phi, dec = math.radians(abs(latitude)), math.radians(-23.45)
    w = math.radians(15 * hours_from_noon)
    sin_a = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(w)
    alt = math.asin(max(-1.0, min(1.0, sin_a)))
    if alt <= 0:
        raise ValidationError("The sun is below the horizon at that time on the shortest day - choose a shorter "
                              "shade-free window.")
    cos_g = (math.sin(alt) * math.sin(phi) - math.sin(dec)) / (math.cos(alt) * math.cos(phi))
    return math.degrees(alt), math.degrees(math.acos(max(-1.0, min(1.0, cos_g))))


def row_spacing(latitude: float, tilt_deg: float, slant_length_m: float, sun_altitude_deg: float | None = None,
                sun_azimuth_from_normal_deg: float = 0.0, shade_free_hours: float | None = None) -> dict:
    """p.102-103: d = l·cosβ + l·sinβ·cosλ / tanα.  Default (book minimum): shade-free at winter-solstice
    solar noon.  shade_free_hours=h: shade-free from noon−h to noon+h on the solstice (the book's <1 %/yr
    shading target in practice; 3 h = 9 am-3 pm is common)."""
    lat = abs(require_range("Latitude", latitude, -90, 90))
    b = math.radians(require_range("Tilt", tilt_deg, 0, 90))
    length = require_positive("Table slant length", slant_length_m)
    if shade_free_hours:
        alt, lam_deg = winter_sun(lat, require_range("Shade-free hours", shade_free_hours, 0, 5))
    else:
        alt = sun_altitude_deg if sun_altitude_deg is not None else 90 - lat - 23.45
        lam_deg = sun_azimuth_from_normal_deg
    if alt <= 0:
        raise ValidationError("The sun does not rise above the horizon at this latitude in winter.")
    a, lam = math.radians(alt), math.radians(lam_deg)
    footprint = length * math.cos(b)
    shadow = length * math.sin(b) * math.cos(lam) / math.tan(a)
    d = footprint + shadow
    return {"sun_altitude_deg": alt, "sun_azimuth_deg": lam_deg, "height_m": length * math.sin(b),
            "footprint_m": footprint, "shadow_m": shadow, "pitch_m": d, "gap_m": shadow, "gcr": length / d}


def performance_ratio(losses_pct: dict[str, float]) -> float:
    """p.148: PR = Π (1 − loss) (the book misprints Σ)."""
    pr = 1.0
    for name, v in losses_pct.items():
        pr *= 1 - require_range(f"{name} loss", v, 0, 50) / 100
    return pr


@dataclass
class Module:
    wp: float
    vmp: float
    imp: float
    voc: float
    isc: float
    beta_voc_pct: float          # %/°C (negative)
    gamma_pmax_pct: float        # %/°C (negative); book applies it to Vmp
    efficiency_pct: float = 21.0
    isc_coef_pct: float = 0.0    # %/°C (positive); 0 = use Isc at STC as the book's example does


@dataclass
class Inverter:
    ac_kva: float
    max_dc_kw: float
    v_dc_max: float
    v_mppt_min: float
    v_mppt_max: float
    i_dc_max: float
    dc_inputs: int = 1


def book_string_design(m: Module, inv: Inverter, t_cell_min: float, t_cell_max: float = 70.0,
                       dc_drop: float = 0.02, min_margin: float = 0.10, max_margin: float = 0.05) -> CalcResult:
    """The book's Steps 1-5 (pp.105-116), with the errata corrected:
    Step 1  N_min = ceil( V_MPPT,min / (Vmp(T_max) × (1 − DC drop) × (1 − margin)) )
    Step 2  N_max = floor( V_DC,max / (Voc(T_min) × (1 + margin)) )
    Step 3  strings = floor( I_DC,max / Isc(T_max) )
    Step 4  power check: N × strings × Wp ≤ inverter max DC power (oversizing allowed if V/I hold)
    """
    g_v = m.gamma_pmax_pct / 100 * m.vmp      # V/°C (book uses the Pmax coefficient on Vmp)
    g_oc = m.beta_voc_pct / 100 * m.voc
    vmp_hot = m.vmp + g_v * (t_cell_max - 25)
    vmp_cold = m.vmp + g_v * (t_cell_min - 25)
    voc_cold = m.voc + g_oc * (t_cell_min - 25)
    isc_hot = m.isc * (1 + m.isc_coef_pct / 100 * (t_cell_max - 25))
    vmin_mod = vmp_hot * (1 - dc_drop) * (1 - min_margin)
    vmax_mod = voc_cold * (1 + max_margin)
    n_min = math.ceil(inv.v_mppt_min / vmin_mod)
    n_max = math.floor(inv.v_dc_max / vmax_mod)
    n_min_raw = math.ceil(inv.v_mppt_min / (vmp_hot * (1 - dc_drop)))
    n_max_raw = math.floor(inv.v_dc_max / voc_cold)
    n_max_mppt = math.floor(inv.v_mppt_max / (vmp_cold * (1 + max_margin)))
    strings = math.floor(inv.i_dc_max / isc_hot)
    feasible = [n for n in range(n_min, n_max + 1)]
    feasible_raw = [n for n in range(n_min_raw, n_max_raw + 1)]
    warnings = []
    if not feasible:
        warnings.append(f"No string length meets both limits with safety margins (min {n_min} > max {n_max}).")
    if not feasible_raw:
        warnings.append(f"No string length works even without margins (min {n_min_raw} > max {n_max_raw}): "
                        "choose a module/inverter pair with a wider voltage window or a 1500 V inverter.")
    chosen = (feasible or feasible_raw or [None])[-1]
    out = {
        "vmp_hot_v": Q(vmp_hot, "V", f"Module Vmp at {t_cell_max:g} °C cell"),
        "voc_cold_v": Q(voc_cold, "V", f"Module Voc at {t_cell_min:g} °C cell"),
        "n_min": Q(n_min, "modules", "Minimum per string (with margins)"),
        "n_max": Q(n_max, "modules", "Maximum per string (with margins)"),
        "n_min_raw": Q(n_min_raw, "modules", "Minimum per string (no margin)"),
        "n_max_raw": Q(n_max_raw, "modules", "Maximum per string (no margin)"),
        "n_max_mppt": Q(n_max_mppt, "modules", "Maximum for the MPPT upper limit (secondary check)"),
        "strings_max": Q(strings, "strings", "Maximum parallel strings per inverter (current)"),
    }
    if chosen:
        dc_kw = chosen * strings * m.wp / 1000
        strings_p = strings
        if dc_kw > inv.max_dc_kw:          # Step 4: reduce strings to respect max DC power
            strings_p = math.floor(inv.max_dc_kw * 1000 / (chosen * m.wp))
            dc_kw = chosen * strings_p * m.wp / 1000
        per = divmod(strings_p, inv.dc_inputs)
        out.update({
            "modules_per_string": Q(chosen, "modules", "Chosen modules per string"),
            "strings_used": Q(strings_p, "strings", "Strings per inverter (after power check)"),
            "dc_kw_per_inverter": Q(dc_kw, "kWp", "DC power per inverter"),
            "dc_ac_ratio": Q(dc_kw / inv.ac_kva, "", "DC/AC ratio"),
            "string_voc_cold_v": Q(chosen * voc_cold, "V", "String Voc on the coldest morning"),
            "input_split": Q(f"{inv.dc_inputs - per[1]} × {per[0]} + {per[1]} × {per[0] + 1}" if per[1] else
                             f"{inv.dc_inputs} × {per[0]}", "strings", "Strings per DC input"),
        })
        if chosen * voc_cold > inv.v_dc_max:
            warnings.append(f"String Voc on a cold morning ({chosen * voc_cold:,.0f} V) exceeds the inverter's "
                            f"{inv.v_dc_max:g} V limit - this string length is NOT safe.")
    else:
        shortest = n_min_raw            # shortest string that still reaches the MPPT window when hot
        out["string_voc_cold_v"] = Q(shortest * voc_cold, "V", f"Voc on a cold morning of the shortest workable "
                                                               f"string ({shortest} modules)")
        warnings.append(f"A {shortest}-module string would reach {shortest * voc_cold:,.0f} V on a cold morning, above "
                        f"the {inv.v_dc_max:g} V limit - NOT safe.")
    return CalcResult(
        name="String and inverter matching (5-step method)",
        inputs={"module": Q(f"{m.wp:g} Wp, Voc {m.voc:g} V, Vmp {m.vmp:g} V, Isc {m.isc:g} A", "", "Module"),
                "inverter": Q(f"{inv.ac_kva:g} kVA, {inv.v_dc_max:g} V max, MPPT {inv.v_mppt_min:g}-{inv.v_mppt_max:g} V, "
                              f"{inv.i_dc_max:g} A", "", "Inverter"),
                "t_cell_min": Q(t_cell_min, "°C", "Coldest cell temperature (dawn)"),
                "t_cell_max": Q(t_cell_max, "°C", "Hottest cell temperature"),
                "margins": Q(f"DC drop {dc_drop:.0%}, min −{min_margin:.0%}, max +{max_margin:.0%}", "", "Book margins")},
        outputs=out,
        equations=["V(T) = V_STC + γ·(T − 25), γ in V/°C = %/100 × V_STC  (pp.106-107)",
                   "N_min = ceil(V_MPPT,min / (Vmp(70 °C) × (1 − DC drop) × 0.9))  (Step 1)",
                   "N_max = floor(V_DC,max / (Voc(T_min) × 1.05))  (Step 2; book prints the inequality reversed)",
                   "Strings = floor(I_DC,max / Isc)  (Step 3)", "N × strings × Wp ≤ inverter max DC power  (Step 4)"],
        assumptions=["Coldest cell temperature equals the record minimum ambient at dawn.",
                     "The book applies the Pmax temperature coefficient to Vmp; the same approximation is used here."],
        warnings=warnings, references=[BOOK + ", Ch.4 pp.105-116"],
    )


@dataclass
class FarmInputs:
    capacity_mwp: float
    latitude: float
    annual_psh: float                       # global tilted irradiation, kWh/m²/day (PVGIS H(i)_d average)
    monthly_psh: list[float] = field(default_factory=list)
    losses_pct: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_LOSSES))
    tilt_deg: float | None = None
    table_slant_m: float = 4.6              # e.g. 2 modules in portrait (~2.3 m each)
    module_efficiency_pct: float = 22.0
    land_extra_pct: float = 20.0            # roads, setbacks, substation (modern assumption)
    ac_mw: float | None = None
    degradation_pct: float = 0.5
    shade_free_hours: float = 3.0           # 9 am-3 pm on 21 Dec (0 = noon only, the book's minimum)


def farm_design(x: FarmInputs) -> CalcResult:
    p = require_positive("Plant capacity", x.capacity_mwp)
    tilt = optimal_tilt(x.latitude) if x.tilt_deg is None else require_range("Tilt", x.tilt_deg, 0, 60)
    rs = row_spacing(x.latitude, tilt, x.table_slant_m, shade_free_hours=x.shade_free_hours or None)
    pr = performance_ratio(x.losses_pct)
    psh = require_positive("Sun hours", x.annual_psh)
    e_mwh = p * psh * 365 * pr
    eff = require_range("Module efficiency", x.module_efficiency_pct, 5, 30) / 100
    module_area = p * 1e6 / (eff * 1000)                 # m² of modules
    land = module_area / rs["gcr"] * (1 + require_range("Extra land", x.land_extra_pct, 0, 200) / 100)
    ac = x.ac_mw or p / 1.25
    out = {
        "tilt_deg": Q(tilt, "°", "Panel tilt (facing south)"),
        "pitch_m": Q(rs["pitch_m"], "m", "Row pitch (front edge to front edge)"),
        "gap_m": Q(rs["gap_m"], "m", "Clear gap between rows"),
        "gcr": Q(rs["gcr"], "", "Ground coverage ratio"),
        "pr": Q(pr, "", "Performance ratio"),
        "annual_mwh": Q(e_mwh, "MWh/yr", "First-year energy (P50)"),
        "specific_yield": Q(e_mwh * 1000 / (p * 1000), "kWh/kWp/yr", "Specific yield"),
        "cf_dc_pct": Q(e_mwh / (p * 8760) * 100, "%", "Capacity factor (DC basis)"),
        "cf_ac_pct": Q(e_mwh / (ac * 8760) * 100, "%", "Capacity factor (AC basis)"),
        "ac_mw": Q(ac, "MW", "Inverter / export capacity (AC)"),
        "transformer_mva": Q(ac, "MVA", "Step-up transformer rating (≥ total inverter kVA)"),
        "land_ha": Q(land / 10000, "ha", "Land needed"),
        "land_bigha": Q(land / BIGHA_M2, "bigha", "Land needed (Terai units)"),
        "land_ropani": Q(land / ROPANI_M2, "ropani", "Land needed (hill units)"),
        "land_per_mwp_ha": Q(land / 10000 / p, "ha/MWp", "Land per MWp"),
    }
    tables = {"Losses": [{"Loss": k, "Loss (%)": v, "Factor": round(1 - v / 100, 4)} for k, v in x.losses_pct.items()]}
    if x.monthly_psh:
        days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        tables["Monthly energy"] = [{"Month": mn, "Sun hours": round(s, 2), "Energy (MWh)": round(p * s * d * pr, 0)}
                                    for mn, s, d in zip(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                                         "Oct", "Nov", "Dec"], x.monthly_psh, days)]
    return CalcResult(
        name="Solar farm - energy, layout and land",
        inputs={"capacity_mwp": Q(p, "MWp", "Plant DC capacity"), "latitude": Q(x.latitude, "°", "Latitude"),
                "annual_psh": Q(psh, "kWh/m²/day", "Sun on the tilted panels (PVGIS)"),
                "table_slant_m": Q(x.table_slant_m, "m", "Table slant length"),
                "module_eff": Q(eff * 100, "%", "Module efficiency")},
        outputs=out,
        equations=["Tilt = latitude, minimum 10°  (Box 4.1)",
                   "Row pitch d = l·cosβ + l·sinβ·cosλ / tan α  (p.102); α, λ = sun height and direction on 21 Dec at the "
                   "edge of the shade-free window: sin α = sin φ sin δ + cos φ cos δ cos ω, δ = −23.45°",
                   "GCR = l / d", "PR = Π (1 − loss_i)  (p.148)", "Energy = MWp × sun hours × 365 × PR  (p.81)",
                   "Capacity factor = Energy / (capacity × 8760 h)",
                   "Land = module area ÷ GCR × (1 + extra for roads/substation)  [modern assumption]"],
        assumptions=[(f"Rows are shade-free from {12 - x.shade_free_hours:g}:00 to {12 + x.shade_free_hours:g}:00 solar time "
                      "on 21 December (book target: < 1 % shading loss a year)." if x.shade_free_hours else
                      "Rows are shade-free only at noon on 21 December (book minimum); expect some morning/evening shading."),
                     f"Extra land {x.land_extra_pct:g}% for roads, setbacks and substation (assumption).",
                     "Transformer rated at least the total inverter AC kVA (book: match the inverter rating, pp.116-117).",
                     "Energy is the P50 (median) estimate; bankable studies also report P90."],
        warnings=["Preliminary feasibility only: a bankable design needs an hourly simulation (e.g. PVsyst), a "
                  "geotechnical survey, grid-impact study and NEA connection approval."],
        references=[BOOK, "PVGIS v5.3 (EC JRC)", "LBNL utility-scale land-use study (2022) for land-use cross-check"],
        tables=tables,
    )
