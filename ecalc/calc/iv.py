"""Simple explicit PV module I-V curve fitted to datasheet points (Isc, Voc, Imp, Vmp).

    I(V) = Isc × [1 − C1 × (exp(V / (C2 × Voc)) − 1)]
    C2 = (Vmp/Voc − 1) / ln(1 − Imp/Isc),   C1 = (1 − Imp/Isc) × exp(−Vmp / (C2 × Voc))

The curve passes exactly through (0, Isc) and (Vmp, Imp) and reaches ≈ 0 A at Voc (exactly C1·Isc,
a negligible value; clipped to 0). Temperature effects use the datasheet coefficients, applied the
same way as the Solar Farms book (pp.106-107): voltages with the Voc / Pmax coefficients, current
with the Isc coefficient. Irradiance is fixed at 1000 W/m² (the design case for inverter matching).
"""

from __future__ import annotations

import math

from .result import ValidationError, require_positive


def iv_curve(isc: float, voc: float, imp: float, vmp: float, points: int = 60) -> list[tuple[float, float]]:
    isc = require_positive("Isc", isc)
    voc = require_positive("Voc", voc)
    imp = require_positive("Imp", imp)
    vmp = require_positive("Vmp", vmp)
    if not (imp < isc and vmp < voc):
        raise ValidationError("Need Imp < Isc and Vmp < Voc for an I-V curve.")
    c2 = (vmp / voc - 1) / math.log(1 - imp / isc)
    c1 = (1 - imp / isc) * math.exp(-vmp / (c2 * voc))
    out = []
    for k in range(points + 1):
        v = voc * k / points
        i = isc * (1 - c1 * (math.exp(v / (c2 * voc)) - 1))
        out.append((v, max(i, 0.0) if k < points else 0.0))
    return out


def module_at_temperature(voc: float, vmp: float, isc: float, imp: float, beta_voc_pct: float,
                          gamma_pmax_pct: float, t_cell: float, isc_coef_pct: float = 0.0) -> dict:
    """Datasheet values corrected to cell temperature t_cell (book method, pp.106-107)."""
    dt = t_cell - 25
    k_i = 1 + isc_coef_pct / 100 * dt
    return {"voc": voc * (1 + beta_voc_pct / 100 * dt), "vmp": vmp * (1 + gamma_pmax_pct / 100 * dt),
            "isc": isc * k_i, "imp": imp * k_i}


def array_curve(module_points: list[tuple[float, float]], n_series: int, n_parallel: int) -> list[tuple[float, float]]:
    """Series modules add voltage; parallel strings add current."""
    if n_series < 1 or n_parallel < 1:
        raise ValidationError("Need at least one module per string and one string.")
    return [(v * n_series, i * n_parallel) for v, i in module_points]
