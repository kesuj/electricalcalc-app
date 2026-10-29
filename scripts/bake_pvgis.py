"""Pre-fetch PVGIS data for every Nepal site so the browser version (GitHub Pages) can work offline.

PVGIS does not allow calls from web browsers (no CORS header), so the in-browser app reads this
file instead. Stored per site: PVcalc (monthly E_m, H(i)_d, totals, loss 14 %) and DRcalc
(G(i) by month and UTC time) for every tilt/direction the Home and Farm pages can ask for.
Run:  python scripts/bake_pvgis.py   (about 1,000 free PVGIS calls, a few minutes)
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ecalc.nepal import NEPAL_SITES  # noqa: E402

OUT = ROOT / "web" / "pvgis_nepal.json"
PV = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
DR = "https://re.jrc.ec.europa.eu/api/v5_3/DRcalc"
SLOPED = [15, 25, 35]
ASPECTS = [0, -45, 45, -90, 90, 180]


def combos(lat: float) -> list[tuple[int, int]]:
    return [(t, a) for t in SLOPED for a in ASPECTS] + [(round(lat), 0)]


def get(url: str, params: dict) -> dict:
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"PVGIS failed: {url} {params}")


def one(site: str, lat: float, lon: float, tilt: int, aspect: int) -> tuple[str, str, dict, dict]:
    pv = get(PV, {"lat": lat, "lon": lon, "peakpower": 1, "loss": 14, "outputformat": "json",
                  "pvtechchoice": "crystSi", "mountingplace": "free", "angle": tilt, "aspect": aspect})
    dr = get(DR, {"lat": lat, "lon": lon, "month": 0, "global": 1, "angle": tilt, "aspect": aspect,
                  "outputformat": "json"})
    pv_small = {"inputs": {"meteo_data": {k: pv["inputs"]["meteo_data"].get(k) for k in ("radiation_db", "year_min", "year_max")},
                           "mounting_system": {"fixed": {"slope": {"value": tilt}, "azimuth": {"value": aspect}}},
                           "pv_module": {"system_loss": 14}},
                "outputs": {"totals": {"fixed": pv["outputs"]["totals"]["fixed"]},
                            "monthly": {"fixed": [{k: m[k] for k in ("month", "E_d", "E_m", "H(i)_d", "H(i)_m", "SD_m") if k in m}
                                                  for m in pv["outputs"]["monthly"]["fixed"]]}}}
    rows = dr["outputs"]["daily_profile"]
    times = sorted({r["time"] for r in rows})
    g = {m: [0.0] * len(times) for m in range(1, 13)}
    for r in rows:
        g[int(r["month"])][times.index(r["time"])] = round(float(r["G(i)"]), 1)
    return site, f"{tilt}|{aspect}", pv_small, {"times": times, "g": [g[m] for m in range(1, 13)]}


def main() -> None:
    jobs = [(s, lat, lon, t, a) for s, (lat, lon, _) in NEPAL_SITES.items() for t, a in combos(lat)]
    out = {s: {"lat": lat, "lon": lon, "pv": {}, "dr": {}} for s, (lat, lon, _) in NEPAL_SITES.items()}
    with ThreadPoolExecutor(6) as ex:
        for i, (site, key, pv, dr) in enumerate(ex.map(lambda j: one(*j), jobs), 1):
            out[site]["pv"][key], out[site]["dr"][key] = pv, dr
            if i % 25 == 0:
                print(f"{i}/{len(jobs)}", flush=True)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB, {len(jobs)} combinations)")


if __name__ == "__main__":
    main()
