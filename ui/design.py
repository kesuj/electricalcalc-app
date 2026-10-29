"""🏠 Home solar - plain-language questions for anyone in Nepal, interactive results.

Method: Boxwell, Solar Electricity Handbook (step order and formulas, ecalc.calc.home).
Data: PVGIS for the exact Nepal site, NEA slab tariff (ERC 2078), net-billing export rate,
NEPQA-2025 equipment floors and indicative 2026 Nepal prices (ecalc.nepal_data).
Every user box starts empty with grey hint text; technical values sit in Engineer settings.
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from ecalc import nepal_data as nd
from ecalc import reports
from ecalc.calc import CalcResult, Quantity as Q, ValidationError
from ecalc.calc.home import CHEMISTRY, HomeInputs, home_design, plain_summary_home
from ecalc.calc.install_home import InstallInputs, build_home_install
from ecalc.finance import cash_flow
from ecalc.nepal import site_choices, site_coords, site_name
from ecalc.profile import LOAD_SHAPES, fetch_daily_profiles, shape_kw, simulate_day
from ecalc.savings import MONTHS, monthly_bills
from ecalc.solar_data import PVGISError, fetch_pvgis
from ui import charts
from ui.book_home import book_home_tab
from ui.package_view import home_sections, render_sections
from ui.common import get_store, page_header, render_result
from ui.hints import H, missing, num

# Typical electrical input power (W) - a starting point only; the user should check the label.
APPLIANCES = {
    "LED bulb": (10, False), "LED tube light": (20, False), "Ceiling fan": (75, True), "Table / stand fan": (50, True),
    "LED TV (32-43 inch)": (60, False), "Refrigerator": (150, True), "Deep freezer": (200, True),
    "Laptop": (60, False), "Desktop computer": (150, False), "Wi-Fi router": (10, False),
    "Mobile phone charger": (10, False), "CCTV system": (40, False), "Water pump 0.5 HP": (450, True),
    "Water pump 1 HP": (900, True), "Washing machine": (500, True), "Rice cooker": (700, False),
    "Electric kettle": (1500, False), "Clothes iron": (1000, False), "Microwave oven": (1200, False),
    "Induction cooker": (1800, False), "Air conditioner 1 ton": (1000, True),
    "Air conditioner 1.5 ton": (1500, True), "Water heater (geyser)": (2000, False),
}
METERS = {"Single-phase 5 A": 5, "Single-phase 15 A (most homes)": 15, "Single-phase 30 A": 30,
          "Single-phase 60 A": 60, "Three-phase": None}
MODES = {"Grid-tied - lower my NEA bill (no battery)": "grid_tied",
         "Hybrid - lower my bill AND keep power during load-shedding": "hybrid_backup",
         "Off-grid - no NEA connection at the site": "off_grid"}
ROOF_DIRECTIONS = {"South": 0, "South-east": -45, "South-west": 45, "East": -90, "West": 90, "North": 180}
SLOPES = {"Gentle (about 15°)": 15, "Medium (about 25°)": 25, "Steep (about 35°)": 35}
COLS = ["name", "power_w", "qty", "hours_per_day", "critical", "motor"]


def _table(key: str) -> pd.DataFrame:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame(columns=COLS).astype(
            {"name": str, "power_w": float, "qty": float, "hours_per_day": float, "critical": bool, "motor": bool})
    return st.session_state[key]


def _appliance_picker(key: str, backup_list: bool) -> pd.DataFrame:
    with st.form(f"add_{key}", clear_on_submit=True, enter_to_submit=False):
        a, b, c, d = st.columns([3, 1, 1, 2] if not backup_list else [3, 1, 2, 2])
        item = a.selectbox("Appliance", list(APPLIANCES), index=None, placeholder="Pick an appliance",
                           help="Typical power is filled in - correct it in the table if the label differs.")
        qty = b.number_input("How many?", 1, 10000, value=None, placeholder="e.g. 4")
        hours = None
        if not backup_list:
            hours = c.number_input("Hours ON per day", 0.0, 24.0, value=None, step=0.5, placeholder="e.g. 6")
            crit = d.checkbox("Needed during power cuts")
        else:
            crit = True
        if st.form_submit_button("➕ Add to list"):
            if item is None or qty is None or (not backup_list and hours is None):
                st.warning("Pick an appliance and fill in the boxes before adding.")
            else:
                w, motor = APPLIANCES[item]
                row = {"name": f"{item} (typical - check label)", "power_w": float(w), "qty": float(qty),
                       "hours_per_day": hours if not backup_list else 0.0, "critical": crit, "motor": motor}
                st.session_state[key] = pd.concat([_table(key), pd.DataFrame([row])], ignore_index=True)
                st.session_state.pop(f"{key}_editor", None)
    cfg = {"name": st.column_config.TextColumn("Appliance"),
           "power_w": st.column_config.NumberColumn("Power (W)", min_value=0, help="Watts on the label. Amps only? W = 230 × A."),
           "qty": st.column_config.NumberColumn("How many", min_value=0),
           "hours_per_day": st.column_config.NumberColumn("Hours/day", min_value=0, max_value=24),
           "critical": st.column_config.CheckboxColumn("Needed in power cut"),
           "motor": st.column_config.CheckboxColumn("Has a motor", help="Fridges, pumps, fans, ACs need extra power to start.")}
    hidden = ["hours_per_day", "critical"] if backup_list else []
    return st.data_editor(_table(key), num_rows="dynamic", width="stretch", key=f"{key}_editor",
                          column_config={k: (None if k in hidden else v) for k, v in cfg.items()}, hide_index=True)


def _rows(df: pd.DataFrame | None) -> list[dict]:
    if df is None:
        return []
    return [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict("records")]


def design():
    page_header("🏠 Home solar",
                "For houses, shops and small offices in Nepal. Answer the questions - the grey text in each box tells "
                "you how to find the answer.")
    store = get_store()

    st.subheader("Step 1 · Your project")
    a, b, c = st.columns(3)
    name = a.text_input("Project name *", placeholder="e.g. My house, Baneshwor")
    client = b.text_input("Owner / client", placeholder="Optional")
    prepared = c.text_input("Prepared by", placeholder="Optional - your name")

    st.subheader("Step 2 · Where are the panels going?")
    a, b = st.columns(2)
    site = a.selectbox("Nearest place in Nepal *", site_choices(), index=None, placeholder="Choose the nearest city / district HQ")
    with b.popover("📍 Use exact location instead (optional)"):
        st.markdown("Open **Google Maps**, right-click your roof and click the numbers to copy them. "
                    "First number = latitude, second = longitude.")
        lat_in = num(st, "lat", "Latitude", 26.0, 31.0)
        lon_in = num(st, "lon", "Longitude", 79.0, 89.0)
    exact = lat_in is not None and lon_in is not None
    lat, lon = (lat_in, lon_in) if exact else (site_coords(site) if site else (None, None))
    place = site_name(site) if site else ""
    location_label = (f"{lat:.4f}, {lon:.4f}" + (f" (near {place})" if place else "")) if exact else place
    roof = st.radio("What kind of roof? *", ["Flat roof - panels go on a metal frame", "Sloping roof - panels lie on the roof"],
                    index=None, horizontal=True)
    roof_dir = slope = None
    if roof and roof.startswith("Sloping"):
        a, b = st.columns(2)
        roof_dir = a.selectbox("Which way does that side of the roof face? *", list(ROOF_DIRECTIONS), index=None,
                               placeholder="Use your phone's compass app")
        slope = b.selectbox("How steep is the roof? *", list(SLOPES), index=None, placeholder="Choose the closest")
    area = num(st, "roof_area", "Free roof space (m²) - optional", 0.0, 1e6, wkey="h_area")

    st.subheader("Step 3 · What kind of system?")
    mode_label = st.radio("Choose one *", list(MODES), index=None)
    mode = MODES.get(mode_label)

    st.subheader("Step 4 · How much electricity do you use?")
    if mode == "off_grid":
        st.caption("Off-grid sites have no bill, so list the appliances you will run.")
        how = "I'll list my appliances"
    else:
        how = st.radio("Choose one *", ["I have my NEA bill", "I'll list my appliances"], index=None, horizontal=True,
                       key="h_how")
    monthly, loads_df, backup_df = None, None, None
    if how == "I have my NEA bill":
        monthly = num(st, "monthly_kwh", "Units used per month (kWh) *", 1.0, 1e7, wkey="h_units")
    elif how == "I'll list my appliances":
        st.caption("Add each type of appliance. Tick **Needed during power cuts** for things that must keep working.")
        loads_df = _appliance_picker("h_loads", backup_list=False)

    outage = autonomy = None
    if mode == "hybrid_backup":
        st.subheader("Step 5 · Load-shedding / power cuts")
        outage = st.number_input("Longest power cut on a normal day (hours) *", 0.5, 24.0, value=None, step=0.5,
                                 placeholder="e.g. 4", help="The battery runs your chosen appliances for this many hours.")
        if how == "I have my NEA bill":
            st.caption("Which appliances must work during a power cut?")
            backup_df = _appliance_picker("h_backup", backup_list=True)
        else:
            st.caption("The battery will run the appliances you ticked as **Needed in power cut** above.")
    elif mode == "off_grid":
        st.subheader("Step 5 · Cloudy days")
        autonomy = st.number_input("Days the battery must last without sun *", 0.5, 7.0, value=None, step=0.5,
                                   placeholder="Usually 2-3 days", help="Book method: 3-5 days; Nepal monsoon sites "
                                   "often need more, or a backup generator.")

    st.subheader("Step 6 · Your NEA connection and money")
    a, b, c = st.columns(3)
    meter = a.selectbox("Your NEA meter *" if mode != "off_grid" else "NEA meter (not needed off-grid)", list(METERS),
                        index=None, placeholder="Printed on your NEA bill", disabled=mode == "off_grid",
                        help="The bill shows the meter capacity (5/15/30/60 A single-phase, or three-phase).")
    quote = num(b, "cost_kwp", "Installer's price per kW (Rs) - optional", 0.0, 1e7, wkey="h_quote")
    flat_rate = None
    if meter == "Three-phase":
        flat_rate = c.number_input("Your energy rate (Rs/unit) *", 0.0, 100.0, value=None, placeholder="From bill, e.g. 11",
                                   help="Domestic three-phase: Rs 10.50 (wet season) / 11.50 (dry) per unit (ERC 2078).")

    st.subheader("Step 7 · Installation details")
    st.caption("Measure by walking the route the cable will take: one normal step is about 0.75 m.")
    a, b, c, d = st.columns(4)
    len_pv = a.number_input("Panels → inverter cable route (m) *", 1.0, 300.0, value=None, step=1.0,
                            placeholder="Steps × 0.75", help="From the roof where the panels are, down to where "
                            "the inverter will hang on the wall. Add a little for bends.")
    len_db = b.number_input("Inverter → main switchboard (m) *", 0.5, 300.0, value=None, step=0.5,
                            placeholder="Steps × 0.75", help="From the inverter to your main distribution board "
                            "(the box with the MCBs).")
    len_bat = c.number_input("Battery → inverter (m)" + (" *" if mode in ("hybrid_backup", "off_grid") else ""),
                             0.3, 20.0, value=None, step=0.5, placeholder="Usually 1-2 (keep it short)",
                             disabled=mode == "grid_tied", help="Put the battery right next to the inverter - short "
                             "battery cables are safer and cheaper.")
    len_earth = d.number_input("Inverter → earth pit (m)", 1.0, 200.0, value=None, step=1.0,
                               placeholder="Optional - default 10", help="Where the earth electrode (earthing rod) "
                               "will be driven into the ground, ideally in moist soil near the building.")
    inv_loc = st.radio("Where will the inverter be mounted? *", ["Indoors (dry, ventilated wall)", "Outdoors (shaded wall)"],
                       index=None, horizontal=True, help="Indoors is better: cooler and protected from rain.")

    eng = _engineer_settings(mode)

    if not st.button("Calculate my solar system", type="primary", width="stretch"):
        _show_results(store)
        return
    loads, backup_loads = _rows(loads_df), _rows(backup_df)
    required = {"Project name": name, "Nearest place (or exact location)": lat, "Kind of roof": roof,
                "System type": mode, "Electricity use": how}
    if roof and roof.startswith("Sloping"):
        required.update({"Roof direction": roof_dir, "Roof steepness": slope})
    if how == "I have my NEA bill":
        required["Units used per month"] = monthly
    if how == "I'll list my appliances" and not any(r.get("power_w") for r in loads):
        required["At least one appliance"] = None
    if mode == "hybrid_backup":
        required["Longest power cut"] = outage
        if how == "I have my NEA bill" and not backup_loads:
            required["Appliances needed during power cuts"] = None
    if mode == "off_grid":
        required["Days without sun"] = autonomy
    required.update({"Panels → inverter distance": len_pv, "Inverter → switchboard distance": len_db,
                     "Inverter location": inv_loc})
    if mode in ("hybrid_backup", "off_grid"):
        required["Battery → inverter distance"] = len_bat
    if mode in ("grid_tied", "hybrid_backup"):
        required["NEA meter"] = meter
        if meter == "Three-phase":
            required["Energy rate"] = flat_rate
    gaps = missing(required)
    if gaps:
        st.error("Please answer: " + ", ".join(gaps) + ".")
        _show_results(store)
        return

    if roof.startswith("Flat"):
        tilt, aspect = float(round(lat)), 0.0
    else:
        tilt, aspect = float(SLOPES[slope]), float(ROOF_DIRECTIONS[roof_dir])
    try:
        with st.spinner("Getting sunshine data for your exact location (PVGIS)..."):
            res = fetch_pvgis(lat, lon, tilt, aspect, 14.0, cache=store)
            try:
                profiles = fetch_daily_profiles(lat, lon, tilt, aspect, cache=store)
            except PVGISError:
                profiles = None
        if how == "I have my NEA bill":
            daily_wh = monthly * 12 / 365 * 1000
            loads = [{"name": "Household use (from NEA bill)", "power_w": daily_wh / 24, "qty": 1, "hours_per_day": 24}]
            loads += [dict(r, hours_per_day=0.0, critical=True) for r in backup_loads if r.get("power_w")]
        x = HomeInputs(loads=loads, monthly_psh=res.monthly_irr_kwh_m2_day, mode=mode,
                       months_required=eng["months"], phantom_w=eng["phantom"], controller=eng["controller"],
                       temp_loss_pct=abs(res.details.get("l_tg_pct") or 0.0), shade_loss_pct=eng["shade"],
                       panel_wp=eng["wp"], panel_area_m2=eng["parea"], inverter_eff_pct=eng["inv_eff"],
                       chemistry=eng["chem"], dod_pct=eng["dod"], holdover_days=autonomy or 3.0,
                       outage_hours=outage or 4.0, system_voltage=eng["vsys"], dc_cable_length_m=eng["dc_len"],
                       available_area_m2=area or None)
        result = home_design(x)
        ii = InstallInputs(voc=eng["voc"], vmp=eng["vmp"], isc=eng["isc"], imp=eng["imp"], beta_voc_pct=eng["beta"],
                           module_max_fuse_a=eng["max_fuse"], battery_module_ah=eng["bat_ah"] or None,
                           len_array_to_inverter_m=len_pv, len_battery_to_inverter_m=len_bat or 2.0,
                           len_inverter_to_db_m=len_db, len_earth_pit_m=len_earth or 10.0, site_name=place,
                           roof="RCC flat roof" if roof.startswith("Flat") else "Tin / sloping roof",
                           inverter_location="indoor" if inv_loc.startswith("Indoor") else "outdoor",
                           ac_phases=3 if meter == "Three-phase" else 1)
        pkg = build_home_install(result, x, ii)
    except PVGISError as e:
        st.error(f"Could not get sunshine data: {e}")
        return
    except ValidationError as e:
        st.error(f"Please check your answers: {e}")
        return

    o = result.outputs
    kwp = o["installed_w"].value / 1000
    derate = (0.9 if eng["controller"] == "MPPT" else 0.75) * (1 - x.temp_loss_pct / 100) * (1 - eng["shade"] / 100)
    bat_kwh = o["battery_kwh_nominal"].value if "battery_kwh_nominal" in o else 0.0
    per_kwp = quote or eng["rs_per_kwp"]
    capex = kwp * per_kwp + bat_kwh * (eng["rs_per_kwh_batt"] or 0)
    notes = (f"Roof: {roof}" + (f", facing {roof_dir}, {slope}" if roof_dir else "") +
             f". Panels modelled at {tilt:g}° tilt, azimuth {aspect:g}° (0 = south). {res.source}.")
    prev = st.session_state.get("home_out")
    if prev and prev["name"] == name and store.get_project(prev["pid"]):
        pid = prev["pid"]
        for c in store.list_calculations(pid):
            store.delete_calculation(c["id"])
        store.update_project(pid, client, location_label, notes)
    else:
        pid = store.create_project(name, client, location_label, notes)
    store.save_calculation(pid, "home", result.name, result.to_dict())
    st.session_state["home_out"] = {
        "pid": pid, "name": name, "client": client, "location": location_label, "prepared": prepared, "notes": notes,
        "result": result, "mode": mode, "profiles": profiles, "kwp": kwp, "bat_kwh": bat_kwh, "capex": capex,
        "psh_derated": [p * derate for p in res.monthly_irr_kwh_m2_day],   # kWh per kWp per day, as in home_design
        "daily_kwh": o["daily_wh"].value / 1000, "meter": METERS.get(meter) if meter else None, "flat_rate": flat_rate,
        "outage": outage or 4.0, "battery_usable_kwh": (o["battery_usable_wh"].value / 1000) if "battery_usable_wh" in o else 0.0,
        "critical_kw": sum((r.get("power_w") or 0) * (r.get("qty") or 0) for r in x.loads if r.get("critical")) / 1000,
        "inverter_kw": o["inverter_w"].value / 1000, "chem": eng["chem"], "rs_per_kwh_batt": eng["rs_per_kwh_batt"],
        "battery_life": o["battery_life_years"].value if "battery_life_years" in o else None,
        "export_rs": eng["export_rs"], "vat": eng["vat"],
        # for the 📘 Book method tab
        "lat": lat, "lon": lon, "tilt": tilt, "aspect": aspect, "place": place, "inputs": x,
        "monthly_psh": res.monthly_irr_kwh_m2_day, "temp_loss_pct": x.temp_loss_pct, "res_details": res.details,
        "pkg": pkg, "ii": ii,
    }
    _show_results(store)


def _engineer_settings(mode: str | None) -> dict:
    e: dict = {}
    battery = mode in ("hybrid_backup", "off_grid")
    with st.expander("🔧 Engineer settings (optional - standard values are already filled in)"):
        st.caption("Standard modern values (2026) are filled in and printed in the report. Change them if you have the "
                   "actual datasheets. Method: Boxwell, Solar Electricity Handbook; data: PVGIS, NEPQA-2025, ERC 2078.")
        a, b, c, d = st.columns(4)
        e["wp"] = a.number_input("Panel rating (Wp)", 50.0, 1000.0, 550.0, 5.0, help=H["panel_wp"][1])
        e["parea"] = b.number_input("Panel area (m²)", 0.3, 4.0, 2.58, 0.01, help=H["panel_area"][1])
        e["controller"] = c.selectbox("Charge controller", ["MPPT", "PWM"],
                                      help="MPPT harvests ~20 % more (book §90); NEPQA requires ≥95 % MPPT efficiency.")
        e["inv_eff"] = d.number_input("Inverter efficiency (%)", 80.0, 99.0, 94.0, 0.5,
                                      help="NEPQA-2025 floor: ≥95 % peak / 94 % Euro for ≤5 kVA; ≥97/96 % above 5 kVA.")
        st.markdown("**Panel datasheet** (printed on the back label of the panel)")
        a, b, c, d, f, g = st.columns(6)
        e["voc"] = a.number_input("Voc (V)", 5.0, 100.0, 49.5, 0.1, help="Open-circuit voltage at STC.")
        e["vmp"] = b.number_input("Vmp (V)", 5.0, 100.0, 41.6, 0.1, help="Voltage at maximum power.")
        e["isc"] = c.number_input("Isc (A)", 0.5, 30.0, 14.0, 0.1, help="Short-circuit current.")
        e["imp"] = d.number_input("Imp (A)", 0.5, 30.0, 13.2, 0.1, help="Current at maximum power.")
        e["beta"] = f.number_input("Voc temp. coeff. (%/°C)", -1.0, 0.0, -0.25, 0.01,
                                   help="Temperature coefficient of Voc (negative).")
        e["max_fuse"] = g.number_input("Max series fuse (A)", 5.0, 60.0, 25.0, 1.0,
                                       help="'Maximum series fuse rating' on the datasheet.")
        a, b, c, d = st.columns(4)
        e["chem"] = a.selectbox("Battery type", list(CHEMISTRY), disabled=not battery)
        e["dod"] = b.number_input("Depth of discharge (%)", 10.0, 100.0, CHEMISTRY[e["chem"]]["dod"], 5.0,
                                  help=H["dod"][1], disabled=not battery)
        e["vsys"] = c.selectbox("Battery voltage", ["Auto (book cable rule)", 12, 24, 48], disabled=not battery)
        e["vsys"] = None if isinstance(e["vsys"], str) else e["vsys"]
        e["bat_ah"] = st.number_input("Battery module size (Ah) - one battery unit", 0.0, 1000.0,
                                      100.0 if e["chem"].startswith("LiFePO4") else 150.0, 10.0, disabled=not battery,
                                      help="e.g. a 48 V 100 Ah LiFePO4 module, or a 12 V 150 Ah tubular battery.")
        e["dc_len"] = d.number_input("Battery/array cable length (m)", 0.5, 50.0, 3.0, 0.5, disabled=not battery,
                                     help="Longest low-voltage cable run, one way (book §87).")
        a, b, c, d = st.columns(4)
        e["shade"] = a.number_input("Shading loss (%)", 0.0, 80.0, 0.0, 1.0,
                                    help="Book §145: shade 9-10 am costs ~3 % (winter); 11 am-1 pm ~27 %.")
        e["phantom"] = b.number_input("Standby loads (W)", 0.0, 500.0, 0.0, 1.0, help="Things left on standby (book §48).")
        e["rs_per_kwp"] = c.number_input("Installed price (Rs per kW of panels)", 10_000.0, 500_000.0,
                                         float(nd.INSTALLED_ONGRID_RS_PER_KWP), 1000.0,
                                         help="Indicative Nepal 2026: Rs 75-90k/kWp installed on-grid [secondary source].")
        e["rs_per_kwh_batt"] = d.number_input("Battery price (Rs per kWh)", 0.0, 200_000.0,
                                              float(nd.PRICE_LIFEPO4_RS_PER_KWH) if e["chem"].startswith("LiFePO4") else 0.0,
                                              1000.0, disabled=not battery,
                                              help="Indicative LiFePO4 Rs 29-40k/kWh (2026). Enter a lead-acid quote if used.")
        a, b, c = st.columns(3)
        e["export_rs"] = a.number_input("Export credit (Rs/unit)", 0.0, 20.0, nd.NET_BILLING_EXPORT_RS, 0.01,
                                        help="NEA net billing since Jul 2022 [secondary source]; confirm with NEA.")
        e["vat"] = b.checkbox("Add 5 % VAT to bills above 50 units", value=False,
                              help="VAT on electricity from Shrawan 2083 [secondary source; may be revised].")
        e["months"] = c.multiselect("Months the system must fully cover (off-grid)", MONTHS, default=MONTHS,
                                    disabled=mode != "off_grid")
        e["months"] = [MONTHS.index(m) + 1 for m in e["months"]] or list(range(1, 13))
    return e


def _show_results(store):
    out = st.session_state.get("home_out")
    if not out:
        return
    r: CalcResult = out["result"]
    st.divider()
    st.header(f"Your solar system - {out['name']}")

    bills, cf = None, None
    if out["mode"] != "off_grid" and out["profiles"]:
        bills = monthly_bills(out["profiles"], out["kwp"], out["psh_derated"], out["daily_kwh"],
                              st.session_state.get("h_shape", list(LOAD_SHAPES)[0]), out["meter"],
                              flat_rate_rs=out["flat_rate"], export_rs=out["export_rs"],
                              inverter_kw=out["inverter_kw"], include_vat=out["vat"])
    saving = sum(b["Saving (Rs)"] for b in bills) if bills else None
    gen_year = r.out("annual_generation_kwh")
    repl = {}
    if out["bat_kwh"] and out["battery_life"]:
        life = max(1, math.ceil(out["battery_life"]))
        repl = {y: out["bat_kwh"] * (out["rs_per_kwh_batt"] or 0) for y in range(life, 26, life) if y < 25}
    if saving:
        cf = cash_flow(out["capex"], gen_year, saving / gen_year, years=25, degradation_pct=0.5, discount_rate_pct=10,
                       replacements=repl)
    plain = plain_summary_home(r, saving, cf.simple_payback_years if cf else None, out["capex"])
    st.success("\n".join(f"- {line}" for line in plain))

    sections = home_sections(out["pkg"], r, out.get("inputs"), out.get("ii")) if out.get("pkg") else []
    tabs = st.tabs(["🛠 Installation guide", "📅 Month by month", "🕐 A day with a power cut", "💰 Money",
                    "🔧 Engineering details", "📄 Report", "📘 Book method"])
    with tabs[0]:
        st.markdown("Everything you need, in the order you need it: **what to buy → how it connects → how to install "
                    "→ how to test → how to look after it.** The same content is in the PDF report.")
        render_sections(sections)
    with tabs[6]:
        book_home_tab(out)
    tabs = tabs[1:]
    with tabs[0]:
        rows = r.tables["Monthly generation vs use"]
        st.altair_chart(charts.monthly_energy([x["Solar (kWh)"] for x in rows], [x["Use (kWh)"] for x in rows]),
                        width="stretch")
        st.caption("Nepal's weakest solar months are usually the monsoon (Jun-Sep) and mid-winter fog in the Terai.")
        if bills:
            st.markdown("**Your NEA bill each month (NEA domestic slab tariff, ERC 2078)**")
            st.dataframe(bills, hide_index=True, width="stretch")
    with tabs[1]:
        _day_tab(out)
    with tabs[2]:
        _money_tab(out, saving, gen_year, repl)
    with tabs[3]:
        render_result(r)
        with st.expander("Data sources and dates"):
            for s in nd.SOURCES:
                st.markdown(f"- {s}")
            st.caption(f"Checked {nd.CHECKED}. Prices are indicative; tariffs may be revised by ERC/NEA.")
    with tabs[4]:
        results = [r.to_dict()]
        if bills:
            results.append(CalcResult(
                name="NEA bill and savings (month by month)",
                inputs={"meter": Q(str(out["meter"] or "three-phase"), "A", "NEA meter"),
                        "export": Q(out["export_rs"], "Rs/kWh", "Export credit (net billing)")},
                outputs={"saving": Q(saving, "Rs/yr", "Estimated yearly saving"),
                         "capex": Q(out["capex"], "Rs", "Estimated installed cost (indicative)")},
                equations=["Bill = NEA service charge + progressive slab energy charge (ERC 2078 p.74)",
                           "Bill with solar = bill(grid units) − exported units × export credit"],
                assumptions=["Hourly split of solar into self-use and export from an average day per month (PVGIS profile).",
                             "Household load shape: " + st.session_state.get("h_shape", list(LOAD_SHAPES)[0]) + "."],
                references=nd.SOURCES[:3], tables={"Monthly bills": bills}).to_dict())
        meta = reports.ReportMeta(project_name=out["name"], client=out["client"], location=out["location"],
                                  prepared_by=out["prepared"], notes=out["notes"])
        safe = "".join(ch if ch.isalnum() else "_" for ch in out["name"])[:40] or "project"
        a, b = st.columns(2)
        a.download_button("⬇️ Download the full report (PDF)",
                          reports.build_pdf(meta, results, summary=plain, sections=sections,
                                            title="Solar Installation Report"),
                          f"{safe}_report.pdf", "application/pdf", type="primary", width="stretch")
        b.download_button("⬇️ Download an editable copy",
                          reports.build_markdown(meta, results, summary=plain, sections=sections,
                                                 title="Solar Installation Report"),
                          f"{safe}_report.md", "text/markdown", width="stretch")
        st.caption(f"Saved on this computer as project #{out['pid']}.")


def _day_tab(out: dict):
    if not out["profiles"]:
        st.info("Hourly sunshine data could not be loaded, so the day simulation is unavailable.")
        return
    a, b, c, d = st.columns(4)
    month = a.select_slider("Month", MONTHS, value="Jan")
    shape = b.selectbox("How you use power", list(LOAD_SHAPES), key="h_shape")
    off_grid = out["mode"] == "off_grid"
    start = c.slider("Power cut starts (hour)", 0, 23, 18, disabled=off_grid)
    hours = d.slider("Power cut length (hours)", 0, 24, 24 if off_grid else int(round(out["outage"])), disabled=off_grid)
    m = MONTHS.index(month) + 1
    day = simulate_day(out["profiles"][m], out["kwp"], out["psh_derated"][m - 1], shape_kw(out["daily_kwh"], shape),
                       outage_start=0 if off_grid else start, outage_hours=hours,
                       battery_usable_kwh=out["battery_usable_kwh"],
                       inverter_kw=out["inverter_kw"],
                       critical_kw=out["critical_kw"] if out["mode"] == "hybrid_backup" else None,
                       export_allowed=not off_grid, pv_in_outage=out["mode"] != "grid_tied")
    st.altair_chart(charts.day_profile(day), width="stretch")
    if out["mode"] == "grid_tied":
        st.warning("A grid-tied system has no battery and must switch off during an NEA power cut (anti-islanding "
                   "safety), so solar does not help during load-shedding. Choose Hybrid if you need backup.")
    t = day.totals
    a, b, c, d = st.columns(4)
    a.metric("Solar today", f"{t['pv_kwh']:.1f} kWh")
    b.metric("Bought from NEA", f"{t['import_kwh']:.1f} kWh")
    c.metric("Sold to NEA", f"{t['export_kwh']:.1f} kWh")
    d.metric("Not supplied in the cut", f"{t['unserved_kwh']:.2f} kWh", delta=None if t["unserved_kwh"] < 0.01 else
             "battery too small", delta_color="inverse")
    st.caption("Red band = power cut. Green area = battery charge. Average day for the month (PVGIS); real days vary "
               "with weather. The battery starts the day full (backup reserve).")


def _money_tab(out: dict, saving: float | None, gen_year: float, repl: dict):
    if out["mode"] == "off_grid":
        cf = cash_flow(out["capex"], gen_year, 0.0, years=25, degradation_pct=0.5, discount_rate_pct=10, replacements=repl)
        st.metric("Estimated cost (indicative)", f"Rs {out['capex']:,.0f}")
        st.metric("Cost per unit over 25 years (LCOE)", f"Rs {cf.lcoe:,.1f} per kWh")
        st.caption("Off-grid: compare this cost per unit with a diesel generator or the cost of extending the NEA line.")
        return
    if not saving:
        st.info("Bill savings need the hourly sunshine data, which could not be loaded.")
        return
    a, b, c, d = st.columns(4)
    esc = a.slider("NEA price rise per year (%)", 0.0, 10.0, 0.0, 0.5)
    deg = b.slider("Panel ageing per year (%)", 0.0, 1.5, 0.5, 0.1, help="NEPQA warranty floor: ≤0.8 %/yr.")
    rate = c.slider("Discount rate (%)", 0.0, 20.0, 10.0, 0.5, help="Value of money elsewhere, e.g. bank FD rate.")
    capex = d.number_input("System cost (Rs)", 0.0, 1e9, float(round(out["capex"], -3)), 5000.0)
    cf = cash_flow(capex, gen_year, saving / gen_year, years=25, degradation_pct=deg, price_escalation_pct=esc,
                   discount_rate_pct=rate, replacements=repl)
    a, b, c, d = st.columns(4)
    a.metric("Saving in year 1", f"Rs {saving:,.0f}")
    b.metric("Pays back in", f"{cf.simple_payback_years:.1f} years" if cf.simple_payback_years else "> 25 years")
    c.metric("Money gained over 25 years", f"Rs {cf.rows[-1]['Cumulative']:,.0f}")
    d.metric("Return (IRR)", f"{cf.irr_pct:.1f} %" if cf.irr_pct is not None else "n/a")
    st.altair_chart(charts.cumulative_cash(cf.rows, "Rs"), width="stretch")
    if repl:
        st.caption(f"Includes battery replacement in year(s) {', '.join(str(y) for y in repl)}.")
    st.caption("Below the red line you have not yet earned back the cost; above it the system is making you money.")
