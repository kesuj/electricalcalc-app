"""Solar geometry helpers (standard formulas; solar time, degrees).

declination δ = 23.45° × sin(360/365 × (284 + n))            (Cooper)
sin α = sin φ sin δ + cos φ cos δ cos ω                       (altitude, ω = 15° × hours from noon)
cos γ = (sin α sin φ − sin δ) / (cos α cos φ)                 (azimuth from due south; − east / + west)
noon altitude = 90° − |φ − δ|
"""

from __future__ import annotations

import math

# Klein's representative day of the year for each month (used for monthly sun heights)
MONTH_DAYS = [17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344]
SOLSTICE_JUN, EQUINOX_MAR, SOLSTICE_DEC = 172, 80, 355


def declination(day_of_year: int) -> float:
    return 23.45 * math.sin(math.radians(360 / 365 * (284 + day_of_year)))


def noon_altitude(latitude: float, decl: float) -> float:
    return 90.0 - abs(latitude - decl)


def solar_position(latitude: float, decl: float, hours_from_noon: float) -> tuple[float, float]:
    """(altitude°, azimuth° from south: negative = east/morning, positive = west/afternoon)."""
    phi, d, w = math.radians(latitude), math.radians(decl), math.radians(15 * hours_from_noon)
    sin_a = math.sin(phi) * math.sin(d) + math.cos(phi) * math.cos(d) * math.cos(w)
    alt = math.asin(max(-1.0, min(1.0, sin_a)))
    if math.cos(alt) < 1e-9:
        return math.degrees(alt), 0.0
    cos_g = (math.sin(alt) * math.sin(phi) - math.sin(d)) / (math.cos(alt) * math.cos(phi))
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_g))))
    return math.degrees(alt), (az if hours_from_noon >= 0 else -az)


def sun_path(latitude: float, day_of_year: int, step_h: float = 0.25) -> list[dict]:
    """Points with the sun above the horizon on that day: solar clock time, altitude, azimuth."""
    d = declination(day_of_year)
    pts, h = [], -12.0
    while h <= 12.0:
        alt, az = solar_position(latitude, d, h)
        if alt > 0:
            pts.append({"Solar time": 12 + h, "Altitude": alt, "Azimuth": az})
        h += step_h
    return pts


def day_length_hours(latitude: float, decl: float) -> float:
    x = -math.tan(math.radians(latitude)) * math.tan(math.radians(decl))
    if x <= -1:
        return 24.0
    if x >= 1:
        return 0.0
    return 2 * math.degrees(math.acos(x)) / 15
