"""Cable current-carrying capacity (conservative) and protective-device selection.

Basis: copper conductors, PVC insulation, enclosed in conduit on a wall (IEC 60364-5-52 reference
method B1, two loaded conductors, 30 °C ambient). These are the commonly published reference values;
PV (XLPE, 90 °C) cable in free air carries more, so using them is on the safe side. Ambient
correction factors for PVC per IEC 60364-5-52. Grouping of many circuits needs further derating.
Coordination rule (IEC 60364-4-43): design current Ib ≤ device rating In ≤ cable capacity Iz.
"""

from __future__ import annotations

from .result import ValidationError, require_positive, require_range

IZ_B1_CU_PVC_A = {1.5: 17.5, 2.5: 24, 4: 32, 6: 41, 10: 57, 16: 76, 25: 101, 35: 125, 50: 151, 70: 192,
                  95: 232, 120: 269, 150: 309, 185: 353, 240: 415}
AMBIENT_FACTOR_PVC = {25: 1.03, 30: 1.00, 35: 0.94, 40: 0.87, 45: 0.79, 50: 0.71, 55: 0.61}
DEVICE_RATINGS_A = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400]
BASIS = "Copper/PVC in conduit, IEC 60364-5-52 method B1, 2 loaded conductors (conservative)"


def ambient_factor(ambient_c: float) -> float:
    t = require_range("Ambient temperature", ambient_c, -10, 55)
    for limit in sorted(AMBIENT_FACTOR_PVC):
        if t <= limit:
            return AMBIENT_FACTOR_PVC[limit]
    return AMBIENT_FACTOR_PVC[55]


def cable_capacity(size_mm2: float, ambient_c: float = 30.0) -> float:
    if size_mm2 not in IZ_B1_CU_PVC_A:
        raise ValidationError(f"{size_mm2} mm² is not in the current-rating table.")
    return IZ_B1_CU_PVC_A[size_mm2] * ambient_factor(ambient_c)


def device_rating(design_current_a: float, factor: float = 1.25) -> int:
    """Smallest standard fuse/breaker rating ≥ factor × design current."""
    need = require_positive("Design current", design_current_a) * factor
    for r in DEVICE_RATINGS_A:
        if r >= need:
            return r
    raise ValidationError(f"{need:.0f} A exceeds the largest standard device in the table - split the circuit.")


def size_for_current(device_a: float, ambient_c: float = 30.0, min_size: float = 1.5) -> float:
    """Smallest cable whose derated capacity Iz ≥ the protective device rating In."""
    require_positive("Device rating", device_a)
    for s in sorted(IZ_B1_CU_PVC_A):
        if s >= min_size and cable_capacity(s, ambient_c) >= device_a:
            return s
    raise ValidationError(f"No cable up to 240 mm² carries {device_a:.0f} A - use parallel cables or busbar.")
