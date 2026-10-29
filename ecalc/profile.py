"""Hour-by-hour energy balance for an average day of a chosen month.

Solar shape comes from PVGIS DRcalc (average daily irradiance profile per month, UTC), shifted to
local time and scaled so the day's PV energy equals the PVGIS monthly yield for the system (so the
losses PVGIS applied are kept). Load shape is a user-chosen profile (an assumption, stated as such).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import requests

from .calc.result import ValidationError, require_positive, require_range
from .solar_data import PVGISError, default_aspect

DRCALC_URL = "https://re.jrc.ec.europa.eu/api/v5_3/DRcalc"
NEPAL_UTC_OFFSET_H = 5.75

# Share of daily energy used in each local hour (0-23). Typical shapes - assumptions, user-selectable.
LOAD_SHAPES: dict[str, list[float]] = {
    "Home - morning and evening peaks": [2, 1.5, 1.5, 1.5, 2, 4, 6, 6, 5, 4, 3.5, 3.5,
                                         3.5, 3.5, 3.5, 3.5, 4, 5, 7, 8, 7.5, 6, 4, 3],
    "Shop / office - daytime": [1, 1, 1, 1, 1, 1, 1.5, 3, 6, 8, 8.5, 8.5,
                                8, 8.5, 8.5, 8, 7, 5, 3.5, 2.5, 2, 1.5, 1, 1],
    "Flat - same all day (pumps, servers, cold rooms)": [1] * 24,
}


def shape_kw(daily_kwh: float, shape: str) -> list[float]:
    w = LOAD_SHAPES[shape]
    s = sum(w)
    return [daily_kwh * x / s for x in w]  # kWh in each 1-hour step == average kW


def parse_drcalc(data: dict, utc_offset_h: float = NEPAL_UTC_OFFSET_H) -> dict[int, list[float]]:
    """Return {month: [G W/m2 for local hours 0..23]} (linear interpolation onto whole local hours)."""
    try:
        rows = data["outputs"]["daily_profile"]
    except (KeyError, TypeError):
        raise PVGISError("Unexpected PVGIS daily-profile format.") from None
    by_month: dict[int, list[tuple[float, float]]] = {}
    for r in rows:
        hh, mm = (int(x) for x in r["time"].split(":"))
        t = (hh + mm / 60 + utc_offset_h) % 24
        by_month.setdefault(int(r["month"]), []).append((t, float(r["G(i)"])))
    out = {}
    for m, pts in by_month.items():
        pts.sort()
        pts = [(t - 24, g) for t, g in pts[-1:]] + pts + [(t + 24, g) for t, g in pts[:1]]
        hourly = []
        for h in range(24):
            x = h + 0.5
            for (t0, g0), (t1, g1) in zip(pts, pts[1:]):
                if t0 <= x <= t1:
                    hourly.append(g0 + (g1 - g0) * (x - t0) / (t1 - t0) if t1 > t0 else g0)
                    break
        out[m] = hourly
    return out


def fetch_daily_profiles(lat: float, lon: float, tilt: float, aspect: float | None = None,
                         timeout: float = 30.0, cache=None) -> dict[int, list[float]]:
    aspect = default_aspect(lat) if aspect is None else aspect
    params = {"lat": round(lat, 4), "lon": round(lon, 4), "month": 0, "global": 1, "angle": tilt,
              "aspect": aspect, "outputformat": "json"}
    key = "DR" + json.dumps(params, sort_keys=True)
    data = cache.get_pvgis(key) if cache is not None else None
    if not data:
        try:
            r = requests.get(DRCALC_URL, params=params, timeout=timeout)
        except requests.RequestException as e:
            raise PVGISError(f"Could not reach PVGIS ({type(e).__name__}).") from None
        if r.status_code != 200:
            raise PVGISError(f"PVGIS returned HTTP {r.status_code}.")
        data = r.json()
        if cache is not None:
            cache.put_pvgis(key, data)
    return parse_drcalc(data)


@dataclass
class DayResult:
    hours: list[int]
    pv_kw: list[float]
    load_kw: list[float]
    grid_import_kw: list[float]
    grid_export_kw: list[float]
    batt_kw: list[float]            # + charging, - discharging
    soc_kwh: list[float]
    unserved_kw: list[float]
    outage: list[bool]
    totals: dict = field(default_factory=dict)


def simulate_day(irradiance_wm2: list[float], pv_kwp: float, pv_kwh_per_kwp_day: float, load_kw: list[float],
                 outage_start: int | None = None, outage_hours: int = 0, battery_usable_kwh: float = 0.0,
                 inverter_kw: float | None = None, critical_kw: float | None = None,
                 export_allowed: bool = True, pv_in_outage: bool = True) -> DayResult:
    """One average day, hourly steps. During the outage only `critical_kw` (if given) is supplied,
    from PV then battery; anything else is unserved. Outside the outage the grid fills gaps and the
    battery is recharged from surplus PV only (it starts the day full - typical for grid-backup use)."""
    if len(irradiance_wm2) != 24 or len(load_kw) != 24:
        raise ValidationError("Profiles must have 24 hourly values.")
    require_positive("PV size", pv_kwp)
    require_positive("PV energy per kWp per day", pv_kwh_per_kwp_day, allow_zero=True)
    require_range("Power-cut length", outage_hours, 0, 24)
    sum_g = sum(irradiance_wm2)
    scale = pv_kwh_per_kwp_day / (sum_g / 1000) if sum_g > 0 else 0.0   # PVGIS losses kept
    pv = [pv_kwp * g / 1000 * scale for g in irradiance_wm2]
    if inverter_kw:
        pv = [min(p, inverter_kw) for p in pv]
    outage = [False] * 24
    if outage_start is not None and outage_hours:
        for k in range(int(outage_hours)):
            outage[(outage_start + k) % 24] = True
    if not pv_in_outage:   # grid-tied inverters shut down when the grid fails (anti-islanding)
        pv = [0.0 if outage[h] else pv[h] for h in range(24)]
    soc = battery_usable_kwh
    imp, exp, bat, socs, uns = [], [], [], [], []
    for h in range(24):
        demand = load_kw[h]
        if outage[h]:
            demand = min(demand, critical_kw) if critical_kw is not None else demand
        net = pv[h] - demand
        i = e = b = u = 0.0
        if net >= 0:
            b = min(net, battery_usable_kwh - soc)
            soc += b
            e = (net - b) if (export_allowed and not outage[h]) else 0.0
        else:
            need = -net
            if outage[h]:
                d = min(need, soc)
                soc -= d; b = -d
                u = need - d
            else:
                i = need
        imp.append(i); exp.append(e); bat.append(b); socs.append(soc); uns.append(u)
    load_served = [min(load_kw[h], critical_kw) if (outage[h] and critical_kw is not None) else load_kw[h]
                   for h in range(24)]
    totals = {"pv_kwh": sum(pv), "load_kwh": sum(load_kw), "import_kwh": sum(imp), "export_kwh": sum(exp),
              "unserved_kwh": sum(uns), "self_consumed_kwh": sum(pv) - sum(exp) - max(0.0, socs[-1] - battery_usable_kwh),
              "outage_supplied_kwh": sum(load_served[h] for h in range(24) if outage[h]) - sum(uns)}
    return DayResult(list(range(24)), pv, load_kw, imp, exp, bat, socs, uns, outage, totals)
