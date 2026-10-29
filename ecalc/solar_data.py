"""PVGIS client (JRC, European Commission). Free, no API key. Responses are cached in
SQLite so repeated designs do not re-query the service. Network errors are surfaced to
the user rather than replaced with invented data."""

from __future__ import annotations

import json

import requests

from .calc.result import ValidationError, require_range
from .calc.solar import SolarResource

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"

# Coordinates of common cities, for convenience only (users may enter any lat/lon).
PRESET_LOCATIONS = {
    "Kathmandu, Nepal": (27.7172, 85.3240), "Pokhara, Nepal": (28.2096, 83.9856),
    "Biratnagar, Nepal": (26.4525, 87.2718), "Nepalgunj, Nepal": (28.0500, 81.6167),
    "Bharatpur, Nepal": (27.6833, 84.4333), "Delhi, India": (28.6139, 77.2090),
    "London, UK": (51.5074, -0.1278), "Sydney, Australia": (-33.8688, 151.2093),
    "Phoenix, USA": (33.4484, -112.0740),
}


class PVGISError(RuntimeError):
    pass


def default_aspect(lat: float) -> float:
    """PVGIS azimuth convention: 0 = facing south, 180 = facing north."""
    return 0.0 if lat >= 0 else 180.0


def parse_pvgis(data: dict, lat: float, lon: float) -> SolarResource:
    try:
        totals = data["outputs"]["totals"]["fixed"]
        monthly = [m["E_m"] for m in data["outputs"]["monthly"]["fixed"]]
        meteo = data["inputs"]["meteo_data"]
        mounting = data["inputs"]["mounting_system"]["fixed"]
    except (KeyError, TypeError) as e:
        raise PVGISError(f"Unexpected PVGIS response format ({e}).") from None
    loss = data["inputs"].get("pv_module", {}).get("system_loss")
    return SolarResource(
        annual_kwh_per_kwp=float(totals["E_y"]),
        monthly_kwh_per_kwp=[float(x) for x in monthly],
        source=(f"PVGIS v5.3 ({meteo.get('radiation_db')}, {meteo.get('year_min')}-{meteo.get('year_max')}) at "
                f"{lat:.4f}, {lon:.4f}; tilt {mounting['slope']['value']}°, azimuth {mounting['azimuth']['value']}° "
                f"(0 = south); {loss}% system loss"),
        details={"E_y": totals["E_y"], "H_i_y": totals.get("H(i)_y"), "l_total_pct": totals.get("l_total"),
                 "SD_y": totals.get("SD_y")},
    )


def fetch_pvgis(lat: float, lon: float, tilt_deg: float, aspect_deg: float | None = None,
                loss_pct: float = 14.0, optimal_angle: bool = False, timeout: float = 30.0,
                cache=None) -> SolarResource:
    lat = require_range("Latitude", lat + 90, 0, 180) - 90
    lon = require_range("Longitude", lon + 180, 0, 360) - 180
    loss_pct = require_range("System losses", loss_pct, 0, 50)
    aspect = default_aspect(lat) if aspect_deg is None else aspect_deg
    params = {"lat": round(lat, 4), "lon": round(lon, 4), "peakpower": 1, "loss": loss_pct,
              "outputformat": "json", "pvtechchoice": "crystSi", "mountingplace": "free"}
    if optimal_angle:
        params["optimalangles"] = 1
    else:
        params.update({"angle": require_range("Tilt", tilt_deg, 0, 90), "aspect": aspect})
    key = json.dumps(params, sort_keys=True)
    if cache is not None:
        hit = cache.get_pvgis(key)
        if hit:
            return parse_pvgis(hit, lat, lon)
    try:
        r = requests.get(PVGIS_URL, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise PVGISError(f"Could not reach PVGIS ({type(e).__name__}). Check your internet connection or "
                         "enter peak sun hours manually.") from None
    if r.status_code != 200:
        msg = r.text[:200]
        try:
            msg = r.json().get("message", msg)
        except ValueError:
            pass
        raise PVGISError(f"PVGIS returned HTTP {r.status_code}: {msg}")
    data = r.json()
    res = parse_pvgis(data, lat, lon)
    if cache is not None:
        cache.put_pvgis(key, data)
    return res


def validate_coords(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValidationError("Latitude must be -90..90 and longitude -180..180.")
