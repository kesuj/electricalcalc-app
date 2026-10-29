"""Browser (GitHub Pages) build only: answer PVGIS requests from pvgis_nepal.json.

Web browsers cannot call PVGIS directly (no CORS), so scripts/bake_pvgis.py pre-fetched real PVGIS
results for every Nepal site. A request is answered with the nearest site and the nearest baked
tilt/direction; the source text says so. System loss is applied exactly (PVGIS output scales with
(1 - loss)). Nothing is invented: every number is a PVGIS v5.3 result.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

_DATA = None
BAKED_LOSS = 14.0


def _data() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = json.loads((Path(__file__).parent / "pvgis_nepal.json").read_text(encoding="utf-8"))
    return _DATA


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def _nearest(lat: float, lon: float, tilt: float, aspect: float) -> tuple[str, float, str]:
    d = _data()
    site = min(d, key=lambda s: _km(lat, lon, d[s]["lat"], d[s]["lon"]))
    dist = _km(lat, lon, d[site]["lat"], d[site]["lon"])

    def cost(key: str) -> float:
        t, a = (float(v) for v in key.split("|"))
        da = abs((a - aspect + 180) % 360 - 180)
        return abs(t - tilt) + (da / 4 if t > 0 else 0)

    return site, dist, min(d[site]["pv"], key=cost)


class _Resp:
    status_code = 200

    def __init__(self, data: dict):
        self._data = data
        self.text = json.dumps(data)

    def json(self) -> dict:
        return self._data


def _label(site: str, dist: float, key: str) -> str:
    t, a = key.split("|")
    far = f", {dist:.0f} km from your point" if dist >= 1 else ""
    return f"pre-calculated for {site}{far}, tilt {t}°, azimuth {a}°"


def get(url: str, params: dict | None = None, timeout: float | None = None) -> _Resp:
    p = params or {}
    lat, lon = float(p.get("lat", 27.7)), float(p.get("lon", 85.3))
    tilt = float(p.get("angle", round(lat)))
    aspect = float(p.get("aspect", 0))
    site, dist, key = _nearest(lat, lon, tilt, aspect)
    rec = _data()[site]
    if "DRcalc" in url:
        dr = rec["dr"][key]
        rows = [{"month": m + 1, "time": t, "G(i)": g} for m, gs in enumerate(dr["g"]) for t, g in zip(dr["times"], gs)]
        return _Resp({"outputs": {"daily_profile": rows}})
    pv = json.loads(json.dumps(rec["pv"][key]))
    loss = float(p.get("loss", BAKED_LOSS))
    f = (1 - loss / 100) / (1 - BAKED_LOSS / 100)
    for m in pv["outputs"]["monthly"]["fixed"]:
        for k in ("E_d", "E_m"):
            if k in m:
                m[k] = m[k] * f
    tot = pv["outputs"]["totals"]["fixed"]
    for k in ("E_d", "E_m", "E_y", "SD_y"):
        if k in tot:
            tot[k] = tot[k] * f
    pv["inputs"]["pv_module"]["system_loss"] = loss
    meteo = pv["inputs"]["meteo_data"]
    meteo["radiation_db"] = f"{meteo.get('radiation_db')}, {_label(site, dist, key)}"
    return _Resp(pv)


class RequestException(Exception):
    pass


def install() -> None:
    """Point ecalc's PVGIS clients at the baked data (idempotent)."""
    import types

    from ecalc import profile, solar_data
    fake = types.SimpleNamespace(get=get, RequestException=RequestException)
    solar_data.requests = fake
    profile.requests = fake
