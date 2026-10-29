"""Worked examples for the public website, computed with the same code and defaults as the app pages.

  - Off-grid small home in Jumla (lights, TV, phones, laptop, router; 2 days without sun)
  - 500 kW and 1 MW solar farms near Nepalgunj with 100 kVA string inverters and a 2 km 11 kV line
Sunshine data: the baked PVGIS file (web/pvgis_nepal.json), the same data the browser app uses.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "web")]

import offline_pvgis  # noqa: E402

offline_pvgis.install()

from ecalc import drawings, solar_data  # noqa: E402
from ecalc import nepal_data as nd  # noqa: E402
from ecalc.calc.farm import FarmInputs, Inverter, Module, book_string_design, farm_design, optimal_tilt  # noqa: E402
from ecalc.calc.farm_cost import farm_cost  # noqa: E402
from ecalc.calc.home import CHEMISTRY, HomeInputs, home_design  # noqa: E402
from ecalc.calc.install_farm import PackageInputs, build_farm_package  # noqa: E402
from ecalc.calc.install_home import InstallInputs, build_home_install  # noqa: E402
from ecalc.nepal import NEPAL_SITES  # noqa: E402
from ui.design import APPLIANCES  # noqa: E402
from ui.package_view import home_sections  # noqa: E402

OFFGRID_LOADS = [("LED bulb", 6, 5), ("LED TV (32-43 inch)", 1, 4), ("Mobile phone charger", 2, 3),
                 ("Laptop", 1, 3), ("Wi-Fi router", 1, 8)]


def offgrid_jumla() -> dict:
    lat, lon, _ = NEPAL_SITES["Jumla"]
    tilt = float(round(lat))
    res = solar_data.fetch_pvgis(lat, lon, tilt, 0.0, 14.0)
    loads = [{"name": n, "power_w": APPLIANCES[n][0], "qty": q, "hours_per_day": h, "critical": False,
              "motor": APPLIANCES[n][1]} for n, q, h in OFFGRID_LOADS]
    chem = list(CHEMISTRY)[0]
    x = HomeInputs(loads=loads, monthly_psh=res.monthly_irr_kwh_m2_day, mode="off_grid",
                   temp_loss_pct=abs(res.details.get("l_tg_pct") or 0.0), inverter_eff_pct=94.0, chemistry=chem,
                   dod_pct=CHEMISTRY[chem]["dod"], holdover_days=2.0)
    r = home_design(x)
    ii = InstallInputs(battery_module_ah=100.0, len_array_to_inverter_m=10.0, len_battery_to_inverter_m=1.5,
                       len_inverter_to_db_m=5.0, len_earth_pit_m=10.0, site_name="Jumla", roof="RCC flat roof",
                       inverter_location="indoor", ac_phases=1)
    pkg = build_home_install(r, x, ii)
    o = r.outputs
    kwp = o["installed_w"].value / 1000
    bat_kwh = o["battery_kwh_nominal"].value if "battery_kwh_nominal" in o else 0.0
    capex = kwp * nd.INSTALLED_ONGRID_RS_PER_KWP + bat_kwh * nd.PRICE_LIFEPO4_RS_PER_KWH
    secs = home_sections(pkg, r, x, ii)
    svgs = [s for sec in secs for s in sec.get("svgs", [])]
    return {"design": r, "pkg": pkg, "loads": loads, "capex": capex, "svgs": svgs, "sections": secs, "res": res}


MOD = Module(wp=550, vmp=41.6, imp=13.2, voc=49.5, isc=14.0, beta_voc_pct=-0.25, gamma_pmax_pct=-0.29, efficiency_pct=21.3)
INV = Inverter(ac_kva=100, max_dc_kw=150, v_dc_max=1100, v_mppt_min=200, v_mppt_max=1000, i_dc_max=260, dc_inputs=10)


def farm_example(mwp: float, line_km: float = 2.0) -> dict:
    lat, lon, _ = NEPAL_SITES["Nepalgunj"]
    tilt = optimal_tilt(lat)
    res = solar_data.fetch_pvgis(lat, lon, tilt, None, 14.0)
    psh_m = res.monthly_irr_kwh_m2_day
    tmin = nd.site_temperatures("Nepalgunj")[0]
    sr = book_string_design(MOD, INV, t_cell_min=tmin, t_cell_max=70.0)
    n_inv = math.ceil(mwp * 1000 / sr.out("dc_kw_per_inverter"))
    fi = FarmInputs(capacity_mwp=mwp, latitude=lat, annual_psh=sum(psh_m) / 12, monthly_psh=psh_m,
                    tilt_deg=round(tilt, 1), table_slant_m=4.6, module_efficiency_pct=21.3, ac_mw=n_inv * 100 / 1000)
    fr = farm_design(fi)
    pkg = build_farm_package(fr, sr, MOD, INV, fi, PackageInputs(line_to_nea_km=line_km))
    cost = farm_cost(pkg, 550, 100, line_km, fr.out("land_ha"))
    n_s = int(sr.out("modules_per_string"))
    sld = drawings.farm_sld_svg(pkg, n_s, sr.out("string_voc_cold_v"), n_s * MOD.vmp, 550, 100)
    return {"mwp": mwp, "fr": fr, "sr": sr, "pkg": pkg, "cost": cost, "sld": sld, "n_inv": n_inv, "res": res}


if __name__ == "__main__":
    h = offgrid_jumla()
    o = h["design"].outputs
    print({k: (round(v.value, 2) if isinstance(v.value, float) else v.value) for k, v in o.items()
           if k in ("installed_w", "n_panels", "battery_ah", "system_v", "battery_kwh_nominal", "inverter_w", "daily_wh")})
    print("capex", round(h["capex"]), "svgs", [t for t, _ in h["svgs"]])
    for m in (0.5, 1.0):
        f = farm_example(m)
        c = f["cost"]
        print(m, round(c.out("total_central_crore"), 2), round(c.out("total_low_crore"), 2),
              round(c.out("total_high_crore"), 2), round(c.out("per_kwp_central")), f["n_inv"],
              round(f["fr"].out("annual_mwh")), round(f["fr"].out("land_ha"), 2))
