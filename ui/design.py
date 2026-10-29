"""'Plan a solar system' page, written for non-engineers.

Questions a layman can answer start EMPTY, with grey hint text saying how to find or measure the
value. Technical values a layman cannot know sit in 'Engineer settings' with standard values that
are printed in the report for an engineer to check.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ecalc import reports
from ecalc.calc import ValidationError
from ecalc.calc.solar import SolarResource
from ecalc.solar_data import PRESET_LOCATIONS, PVGISError, fetch_pvgis
from ecalc.workflow import ProjectDesign, plain_summary, run_full_design, summary
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
SUPPLIES = {"Single-phase 230 V (most homes and shops)": (1, 230.0),
            "Three-phase 400 V (big buildings, factories)": (3, 400.0)}
ROOF_DIRECTIONS = {"South": 0, "South-east": -45, "South-west": 45, "East": -90, "West": 90, "North": 180}
SLOPES = {"Gentle (about 15°)": 15, "Medium (about 25°)": 25, "Steep (about 35°)": 35}
COLS = ["name", "power_w", "qty", "hours_per_day", "critical", "motor"]


def _table(state_key: str) -> pd.DataFrame:
    if state_key not in st.session_state:
        st.session_state[state_key] = pd.DataFrame(columns=COLS).astype(
            {"name": str, "power_w": float, "qty": float, "hours_per_day": float, "critical": bool, "motor": bool})
    return st.session_state[state_key]


def _appliance_picker(state_key: str, backup_list: bool) -> pd.DataFrame:
    """Add appliances from a list (typical watts) and edit them in a table."""
    with st.form(f"add_{state_key}", clear_on_submit=True, border=True):
        a, b, c, d = st.columns([3, 1, 1, 2] if not backup_list else [3, 1, 2, 2])
        item = a.selectbox("Appliance", list(APPLIANCES), index=None, placeholder="Pick an appliance",
                           help="Typical power is filled in automatically - correct it in the table if the label differs.")
        qty = b.number_input("How many?", 1, 10000, value=None, placeholder="e.g. 4")
        hours = None
        if not backup_list:
            hours = c.number_input("Hours ON per day", 0.0, 24.0, value=None, step=0.5,
                                   placeholder="e.g. 6", help="Average hours it is switched on each day.")
            crit = d.checkbox("Needed during power cuts", help="Tick if this must keep working when the grid is off.")
        else:
            crit = True
        if st.form_submit_button("➕ Add to list"):
            if item is None or qty is None or (not backup_list and hours is None):
                st.warning("Pick an appliance and fill in the boxes before adding.")
            else:
                w, motor = APPLIANCES[item]
                row = {"name": f"{item} (typical - check label)", "power_w": float(w), "qty": float(qty),
                       "hours_per_day": hours, "critical": crit, "motor": motor}
                st.session_state[state_key] = pd.concat([_table(state_key), pd.DataFrame([row])], ignore_index=True)
                st.session_state.pop(f"{state_key}_editor", None)
    cfg = {"name": st.column_config.TextColumn("Appliance"),
           "power_w": st.column_config.NumberColumn("Power (W)", min_value=0,
                                                    help="Watts on the label. If it shows amps: W = 230 × A."),
           "qty": st.column_config.NumberColumn("How many", min_value=0),
           "hours_per_day": st.column_config.NumberColumn("Hours/day", min_value=0, max_value=24),
           "critical": st.column_config.CheckboxColumn("Needed in power cut"),
           "motor": st.column_config.CheckboxColumn("Has a motor", help="Fridges, pumps, fans, ACs need extra power to start.")}
    hidden = ["hours_per_day", "critical"] if backup_list else []
    df = st.data_editor(_table(state_key), num_rows="dynamic", use_container_width=True, key=f"{state_key}_editor",
                        column_config={k: (None if k in hidden else v) for k, v in cfg.items()}, hide_index=True)
    st.caption("You can also type directly in the table, change any number, or delete a row (select it, then the bin icon).")
    return df


def _rows(df: pd.DataFrame) -> list[dict]:
    return [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict("records")]


def design():
    page_header("☀️ Plan a solar system",
                "Answer the questions below. The grey text inside each box tells you how to find the answer.")
    store = get_store()

    # ---- Step 1 -------------------------------------------------------------------------
    st.subheader("Step 1 · Your project")
    a, b, c = st.columns(3)
    name = a.text_input("Project name *", placeholder="e.g. My house, Baneshwor")
    client = b.text_input("Owner / client", placeholder="Optional")
    prepared = c.text_input("Prepared by", placeholder="Optional - your name")

    # ---- Step 2 -------------------------------------------------------------------------
    st.subheader("Step 2 · Where are the panels going?")
    a, b = st.columns(2)
    city = a.selectbox("Nearest city *", list(PRESET_LOCATIONS), index=None, placeholder="Choose the nearest city")
    with b.popover("📍 Use exact location instead (optional)"):
        st.markdown("Open **Google Maps**, right-click your roof and click the numbers that appear to copy them. "
                    "The first number is latitude, the second is longitude.")
        lat_in = num(st, "lat", "Latitude", -90.0, 90.0)
        lon_in = num(st, "lon", "Longitude", -180.0, 180.0)
    exact = lat_in is not None and lon_in is not None
    lat, lon = (lat_in, lon_in) if exact else (PRESET_LOCATIONS[city] if city else (None, None))
    location_label = f"{lat:.4f}, {lon:.4f}" + (f" (near {city})" if city else "") if exact else (city or "")

    roof = st.radio("What kind of roof? *", ["Flat roof - panels go on a metal frame", "Sloping roof - panels lie on the roof"],
                    index=None, horizontal=True)
    roof_dir = slope = None
    if roof and roof.startswith("Sloping"):
        a, b = st.columns(2)
        roof_dir = a.selectbox("Which way does that side of the roof face? *", list(ROOF_DIRECTIONS), index=None,
                               placeholder="Use your phone's compass app",
                               help="Stand looking at the roof surface, open the phone compass, and read the direction you face away from the roof.")
        slope = b.selectbox("How steep is the roof? *", list(SLOPES), index=None, placeholder="Choose the closest",
                            help="Gentle: you could walk on it. Medium: typical tin/tile roof. Steep: hard to stand on.")
    area = num(st, "roof_area", "Free roof space (m²) - optional", 0.0, 1e6)

    # ---- Step 3 -------------------------------------------------------------------------
    st.subheader("Step 3 · How much electricity do you use?")
    mode = st.radio("Choose one *", ["I have my electricity bill", "I'll list my appliances"], index=None, horizontal=True)
    monthly, loads_df = None, None
    if mode == "I have my electricity bill":
        monthly = num(st, "monthly_kwh", "Units used per month (kWh) *", 1.0, 1e7)
    elif mode == "I'll list my appliances":
        st.caption("Add each type of appliance you use. Tick **Needed during power cuts** for things that must "
                   "keep working when the electricity goes off.")
        loads_df = _appliance_picker("loads", backup_list=False)

    # ---- Step 4 -------------------------------------------------------------------------
    st.subheader("Step 4 · Power cuts")
    backup = st.radio("Do you want electricity during power cuts? *",
                      ["No - I only want to reduce my bill (no battery)",
                       "Yes - keep some things running during power cuts (with battery)"], index=None)
    hybrid = bool(backup and backup.startswith("Yes"))
    outage, backup_df = None, None
    if hybrid:
        outage = st.number_input("Longest power cut on a normal day (hours) *", 0.5, 24.0, value=None, step=0.5,
                                 placeholder="e.g. 4 - think of a typical bad day",
                                 help="The battery is sized to run your chosen appliances for this many hours.")
        if mode == "I'll list my appliances":
            st.caption("The battery will run the appliances you ticked as **Needed in power cut** in Step 3.")
        else:
            st.caption("Which appliances must work during a power cut?")
            backup_df = _appliance_picker("backup", backup_list=True)

    # ---- Step 5 -------------------------------------------------------------------------
    st.subheader("Step 5 · Your connection and money")
    a, b = st.columns(2)
    supply = a.selectbox("Type of electricity supply *", list(SUPPLIES), index=None, placeholder="Look at your meter",
                         help="Single-phase meters have 2 wires in (phase + neutral). Three-phase meters have 4 wires "
                              "(3 phases + neutral) and are used in bigger buildings. It is also printed on the bill.")
    cur = b.selectbox("Currency", ["NPR", "USD", "AUD", "GBP", "INR", "EUR"])
    a, b, c = st.columns(3)
    tariff = num(a, "tariff", "Price you pay per unit - optional", 0.0, 1e4)
    cost_kwp = num(b, "cost_kwp", "Installer's price per kW of solar - optional", 0.0, 1e9)
    ac_len = c.number_input("Distance from inverter to main switchboard (m) - optional", 0.5, 2000.0, value=None,
                            placeholder="Count your steps × 0.75 m",
                            help="Walk the route the cable will take and count steps; one step ≈ 0.75 m. Used to "
                                 "check the cable size. Leave empty to skip.")

    eng = _engineer_settings(hybrid)

    # ---- calculate ----------------------------------------------------------------------
    if not st.button("Calculate my solar system", type="primary", use_container_width=True):
        _show_results(store)
        return
    loads = _rows(loads_df) if loads_df is not None else []
    backup_loads = _rows(backup_df) if backup_df is not None else []
    required = {"Project name": name, "Nearest city (or exact location)": lat, "Kind of roof": roof,
                "Electricity use (Step 3)": mode, "Power cuts (Step 4)": backup, "Type of electricity supply": supply}
    if roof and roof.startswith("Sloping"):
        required.update({"Roof direction": roof_dir, "Roof steepness": slope})
    if mode == "I have my electricity bill":
        required["Units used per month"] = monthly
    if mode == "I'll list my appliances" and not loads:
        required["At least one appliance in the list"] = None
    if hybrid:
        required["Longest power cut (hours)"] = outage
        if mode == "I have my electricity bill" and not backup_loads:
            required["Appliances needed during power cuts"] = None
    if not eng["pvgis"]:
        required["Peak sun hours (Engineer settings)"] = eng["psh"]
    gaps = missing(required)
    if gaps:
        st.error("Please answer: " + ", ".join(gaps) + ".")
        _show_results(store)
        return

    if roof.startswith("Flat"):
        tilt, aspect = float(round(abs(lat))), (0.0 if lat >= 0 else 180.0)
    else:
        tilt, aspect = float(SLOPES[slope]), float(ROOF_DIRECTIONS[roof_dir])
    tilt = eng["tilt"] if eng["tilt"] is not None else tilt
    aspect = eng["aspect"] if eng["aspect"] is not None else aspect
    try:
        if eng["pvgis"]:
            key = (round(lat, 4), round(lon, 4), tilt, aspect, eng["loss"])
            if st.session_state.get("design_res_key") != key:
                with st.spinner("Getting sunshine data for your location from PVGIS..."):
                    st.session_state["design_res"] = fetch_pvgis(lat, lon, tilt, aspect, eng["loss"], cache=store)
                st.session_state["design_res_key"] = key
            resource = st.session_state["design_res"]
        else:
            resource = SolarResource.from_peak_sun_hours(eng["psh"], eng["loss"])
        phases, volts = SUPPLIES[supply]
        d = ProjectDesign(
            resource=resource, location_label=location_label, loads=loads, coincidence_factor=eng["coinc"],
            monthly_kwh=monthly, outage_hours=outage, backup_loads=backup_loads,
            system_type="hybrid_battery" if hybrid else "grid_tied", panel_wp=eng["wp"], panel_area_m2=eng["parea"],
            available_area_m2=area or None, target_offset_pct=eng["offset"], dc_ac_ratio=eng["ratio"],
            battery_voltage_v=eng["vbat"], battery_dod_pct=eng["dod"], autonomy_days=1, currency=cur,
            tariff_per_kwh=tariff or None, export_rate_per_kwh=eng["export"] or 0, cost_per_kwp=cost_kwp or None,
            battery_cost_per_kwh=eng["bcost"] or None, supply_phases=phases, supply_voltage_v=volts,
            ac_cable_length_m=ac_len, ac_drop_limit_pct=eng["ac_lim"],
            dc_cable_length_m=eng["dc_len"] if hybrid else None, dc_drop_limit_pct=eng["dc_lim"],
            conductor=eng["mat"], conductor_temp_c=eng["temp"])
        results = run_full_design(d)
    except PVGISError as e:
        st.error(f"Could not get sunshine data: {e} You can enter peak sun hours under Engineer settings instead.")
        return
    except ValidationError as e:
        st.error(f"Please check your answers: {e}")
        return
    notes = (f"Roof: {roof}" + (f", facing {roof_dir}, {slope}" if roof_dir else "") +
             f". Panels modelled at {tilt:g}° tilt, azimuth {aspect:g}° (0 = south).")
    prev = st.session_state.get("design_out")
    if prev and prev["name"] == name and store.get_project(prev["pid"]):
        pid = prev["pid"]  # recalculating the same project: replace its results instead of duplicating it
        for c in store.list_calculations(pid):
            store.delete_calculation(c["id"])
        store.update_project(pid, client, location_label, notes)
    else:
        pid = store.create_project(name, client, location_label, notes)
    for r in results:
        store.save_calculation(pid, "design", r.name, r.to_dict())
    st.session_state["design_out"] = {"pid": pid, "name": name, "client": client, "location": location_label,
                                      "prepared": prepared, "notes": notes, "results": results}
    _show_results(store)


def _engineer_settings(hybrid: bool) -> dict:
    """Technical values with standard defaults; all are printed in the report."""
    e: dict = {}
    with st.expander("🔧 Engineer settings (optional - standard values are already filled in)"):
        st.caption("You can leave these as they are. They are standard design values and are printed in the report "
                   "so an engineer can check them. Change them if you have the actual equipment datasheets.")
        src = st.radio("Sunshine data", ["PVGIS (online, recommended)", "Enter peak sun hours"], horizontal=True)
        e["pvgis"] = src.startswith("PVGIS")
        a, b, c, d = st.columns(4)
        e["psh"] = None if e["pvgis"] else num(a, "psh", "Peak sun hours *", 0.5, 9.0)
        e["loss"] = (b if not e["pvgis"] else a).number_input(
            "System losses (%)" if e["pvgis"] else "Total losses (%)", 0.0, 50.0, 14.0 if e["pvgis"] else 23.0, 1.0,
            help=H["loss_pvgis" if e["pvgis"] else "loss_psh"][1])
        e["tilt"] = c.number_input("Tilt override (°)", 0.0, 90.0, value=None, placeholder="From roof answer",
                                   help=H["tilt"][1])
        e["aspect"] = d.number_input("Azimuth override (°)", -180.0, 180.0, value=None, placeholder="From roof answer",
                                     help=H["azimuth"][1])
        a, b, c, d = st.columns(4)
        e["wp"] = a.number_input("Panel rating (Wp)", 50.0, 1000.0, 550.0, 5.0, help=H["panel_wp"][1])
        e["parea"] = b.number_input("Panel area (m²)", 0.3, 4.0, 2.58, 0.01, help=H["panel_area"][1])
        e["ratio"] = c.number_input("DC/AC ratio", 0.8, 1.6, 1.2, 0.05, help=H["dc_ac"][1])
        e["offset"] = d.number_input("Cover % of consumption", 1.0, 200.0, 100.0, 5.0, help=H["offset"][1])
        a, b, c, d = st.columns(4)
        e["coinc"] = a.number_input("Coincidence factor", 0.1, 1.0, 1.0, 0.05, help=H["coincidence"][1])
        e["vbat"] = b.number_input("Battery voltage (V)", 12.0, 1000.0, 48.0, help=H["vbat"][1], disabled=not hybrid)
        e["dod"] = c.number_input("Depth of discharge (%)", 10.0, 100.0, 80.0, help=H["dod"][1], disabled=not hybrid)
        e["bcost"] = d.number_input("Battery cost per kWh", 0.0, 1e8, value=None, placeholder="Optional",
                                    help=H["bat_cost"][1], disabled=not hybrid)
        a, b, c, d = st.columns(4)
        e["mat"] = a.selectbox("Cable conductor", ["copper", "aluminium"])
        e["temp"] = b.number_input("Conductor temperature (°C)", 20.0, 250.0, 70.0, help=H["temp"][1])
        e["ac_lim"] = c.number_input("AC voltage-drop limit (%)", 0.1, 10.0, 1.5, 0.5, help=H["ac_limit"][1])
        e["export"] = d.number_input("Export rate per unit", 0.0, 1e4, value=None, placeholder="Optional",
                                     help=H["export"][1])
        a, b, _, _ = st.columns(4)
        e["dc_len"] = a.number_input("Battery → inverter cable (m)", 0.2, 100.0, 2.0, help=H["dc_len"][1],
                                     disabled=not hybrid)
        e["dc_lim"] = b.number_input("DC voltage-drop limit (%)", 0.1, 10.0, 1.0, 0.5, help=H["dc_limit"][1],
                                     disabled=not hybrid)
    return e


def _show_results(store):
    out = st.session_state.get("design_out")
    if not out:
        return
    results = out["results"]
    st.divider()
    st.header(f"Your solar system - {out['name']}")
    plain = plain_summary(results)
    st.success("\n".join(f"- {line}" for line in plain))

    meta = reports.ReportMeta(project_name=out["name"], client=out["client"], location=out["location"],
                              prepared_by=out["prepared"], notes=out["notes"])
    dicts = [r.to_dict() for r in results]
    safe = "".join(ch if ch.isalnum() else "_" for ch in out["name"])[:40] or "project"
    a, b = st.columns(2)
    a.download_button("⬇️ Download the full report (PDF)", reports.build_pdf(meta, dicts, summary=plain),
                      f"{safe}_report.pdf", "application/pdf", type="primary", use_container_width=True)
    b.download_button("⬇️ Download an editable copy", reports.build_markdown(meta, dicts, summary=plain),
                      f"{safe}_report.md", "text/markdown", use_container_width=True)
    st.caption(f"Saved as project #{out['pid']} under My projects & reports.")

    st.subheader("Details for engineers")
    items = list(summary(results).items())
    for i in range(0, len(items), 4):
        cols = st.columns(4)
        for col, (k, v) in zip(cols, items[i:i + 4]):
            col.metric(k, v)
    for r in results:
        with st.expander(r.name):
            render_result(r)
