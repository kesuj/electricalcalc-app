"""'New project design' page: enter one project's data once, get every calculation and the full report."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ecalc import reports
from ecalc.calc import ValidationError
from ecalc.calc.solar import SolarResource
from ecalc.solar_data import PRESET_LOCATIONS, PVGISError, fetch_pvgis
from ecalc.workflow import ProjectDesign, run_full_design, summary
from ui.common import get_store, page_header, render_result

LOAD_COLS = {"name": "Load / appliance", "power_w": "Power (W)", "qty": "Qty", "hours_per_day": "Hours/day",
             "critical": "Critical (backup)", "motor": "Motor / compressor"}
EXAMPLE_LOADS = [  # illustrative values only - user must replace with real equipment ratings
    {"name": "LED lights (example)", "power_w": 12, "qty": 20, "hours_per_day": 6, "critical": True, "motor": False},
    {"name": "Ceiling fans (example)", "power_w": 75, "qty": 6, "hours_per_day": 8, "critical": False, "motor": True},
    {"name": "Refrigerator (example)", "power_w": 150, "qty": 1, "hours_per_day": 10, "critical": True, "motor": True},
    {"name": "Computers (example)", "power_w": 120, "qty": 4, "hours_per_day": 8, "critical": True, "motor": False},
    {"name": "Water pump (example)", "power_w": 750, "qty": 1, "hours_per_day": 1.5, "critical": False, "motor": True},
]


def _empty_loads(n=6):
    return pd.DataFrame([{"name": "", "power_w": None, "qty": 1, "hours_per_day": None, "critical": False,
                          "motor": False} for _ in range(n)])


def design():
    page_header("📐 New project design",
                "Enter your project once. The app runs every calculation and builds the full report.")
    store = get_store()

    # ---- 1. project --------------------------------------------------------------------
    st.subheader("1. Project details")
    a, b, c = st.columns(3)
    name = a.text_input("Project name *", placeholder="e.g. Sharma residence rooftop solar")
    client = b.text_input("Client")
    prepared = c.text_input("Prepared by")
    notes = st.text_area("Scope / notes (printed in the report)", height=68)

    # ---- 2. site and solar data ----------------------------------------------------------
    st.subheader("2. Site and solar data")
    src = st.radio("Solar data", ["PVGIS for my location (online, free)", "I know the peak sun hours"], horizontal=True)
    pvgis_mode = src.startswith("PVGIS")
    loss = st.number_input(
        "System losses (%)" if pvgis_mode else "Total losses (%) - includes temperature",
        0.0, 50.0, 14.0 if pvgis_mode else 23.0, 1.0,
        help=("Cables, inverter, dust, mismatch, ageing. PVGIS adds temperature and reflection losses itself, "
              "so 14% (PVGIS default) is typical." if pvgis_mode else
              "With peak sun hours nothing else is deducted, so include temperature (~8%) and reflection (~3%) "
              "on top of cables/inverter/dust (~14%): about 23% total, i.e. performance ratio ~0.77."))
    resource: SolarResource | None = None
    if src.startswith("PVGIS"):
        a, b, c, d, e = st.columns([2, 1, 1, 1, 1])
        preset = a.selectbox("Nearest city (or Custom)", ["Custom coordinates"] + list(PRESET_LOCATIONS), index=1)
        lat0, lon0 = PRESET_LOCATIONS.get(preset, (27.7172, 85.3240))
        lat = b.number_input("Latitude", -90.0, 90.0, lat0, format="%.4f",
                             help="Find it on Google Maps: right-click your site → the first number.")
        lon = c.number_input("Longitude", -180.0, 180.0, lon0, format="%.4f", help="The second number.")
        tilt = d.number_input("Panel tilt (°)", 0.0, 90.0, float(round(abs(lat0))), 1.0)
        aspect = e.number_input("Azimuth (0 = south)", -180.0, 180.0, 0.0 if lat >= 0 else 180.0, 5.0)
        location_label = preset if preset != "Custom coordinates" else f"{lat:.4f}, {lon:.4f}"
        key = (round(lat, 4), round(lon, 4), tilt, aspect, loss)
        if st.session_state.get("design_res_key") == key:
            resource = st.session_state["design_res"]
            st.success(f"Solar data loaded: {resource.annual_kwh_per_kwp:,.0f} kWh per kWp per year.")
        else:
            st.caption("Solar data is fetched from PVGIS when you press Calculate.")
    else:
        a, b = st.columns(2)
        psh = a.number_input("Peak sun hours (kWh/m²/day on the panels)", 0.5, 9.0, 5.0, 0.1)
        location_label = b.text_input("Location name", "")
        lat = lon = tilt = aspect = key = None

    # ---- 3. demand -----------------------------------------------------------------------
    st.subheader("3. Electricity demand")
    mode = st.radio("How do you know the demand?", ["List the loads (appliances)", "Monthly units from the electricity bill"],
                    horizontal=True)
    loads_df, monthly, peak = None, None, None
    if mode.startswith("List"):
        if "design_loads" not in st.session_state:
            st.session_state["design_loads"] = _empty_loads()
        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("Fill example loads"):
            st.session_state["design_loads"] = pd.DataFrame(EXAMPLE_LOADS)
            st.session_state.pop("design_editor", None)
        if b2.button("Clear table"):
            st.session_state["design_loads"] = _empty_loads()
            st.session_state.pop("design_editor", None)
        loads_df = st.data_editor(
            st.session_state["design_loads"], num_rows="dynamic", use_container_width=True, key="design_editor",
            column_config={k: (st.column_config.CheckboxColumn(v) if k in ("critical", "motor") else
                               st.column_config.TextColumn(v) if k == "name" else
                               st.column_config.NumberColumn(v, min_value=0)) for k, v in LOAD_COLS.items()})
        div = st.slider("Diversity factor (share of loads running at the same time)", 0.1, 1.0, 0.8, 0.05)
        st.caption("Tick **Critical** for loads that must run during power cuts (sizes the battery). "
                   "Tick **Motor** for fridges, pumps, fans, ACs (surge warning).")
    else:
        a, b = st.columns(2)
        monthly = a.number_input("Average monthly consumption (kWh = units)", 1.0, 1e7, 300.0)
        peak = b.number_input("Peak load (kW, 0 = unknown)", 0.0, 1e5, 0.0) or None
        div = 0.8

    # ---- 4. system -----------------------------------------------------------------------
    st.subheader("4. Solar system")
    a, b, c, d = st.columns(4)
    system = a.radio("System type", ["Grid-tied (no battery)", "Hybrid (with battery backup)"])
    hybrid = system.startswith("Hybrid")
    offset = a.number_input("Cover this % of consumption", 1.0, 200.0, 100.0, 5.0)
    wp = b.number_input("Panel rating (Wp)", 50.0, 1000.0, 550.0, 5.0)
    parea = b.number_input("Panel area (m²)", 0.3, 4.0, 2.58, 0.01)
    area = c.number_input("Roof area available (m², 0 = no limit)", 0.0, 1e6, 0.0)
    ratio = c.number_input("DC/AC ratio", 0.8, 1.6, 1.2, 0.05)
    vbat = d.number_input("Battery voltage (V)", 12.0, 1000.0, 48.0, disabled=not hybrid)
    dod = d.number_input("Battery depth of discharge (%)", 10.0, 100.0, 80.0, disabled=not hybrid)
    autonomy = d.number_input("Backup days", 0.1, 7.0, 1.0, 0.5, disabled=not hybrid)
    backup_manual = None
    if hybrid and not mode.startswith("List"):
        backup_manual = st.number_input("Backup energy needed (kWh/day)", 0.1, 1e5, 5.0)

    # ---- 5. money and cables ---------------------------------------------------------------
    with st.expander("5. Costs and tariff (optional - for savings and payback)", expanded=False):
        a, b, c, d, e = st.columns(5)
        cur = a.selectbox("Currency", ["NPR", "USD", "AUD", "GBP", "INR", "EUR"])
        tariff = b.number_input("Tariff per unit (0 = skip)", 0.0, 1e4, 0.0)
        export = c.number_input("Export rate per unit", 0.0, 1e4, 0.0)
        cost_kwp = d.number_input("Installed cost per kWp (0 = skip)", 0.0, 1e9, 0.0)
        bcost = e.number_input("Battery cost per kWh (0 = skip)", 0.0, 1e8, 0.0, disabled=not hybrid)
    with st.expander("6. Wiring (cable voltage-drop checks)", expanded=False):
        a, b, c, d = st.columns(4)
        supply = a.selectbox("Supply", ["Single-phase 230 V", "Three-phase 400 V", "Single-phase 120 V", "Three-phase 415 V"])
        ac_len = b.number_input("Inverter → main board length (m)", 0.5, 2000.0, 20.0)
        ac_lim = b.number_input("AC voltage-drop limit (%)", 0.1, 10.0, 3.0, 0.5)
        dc_len = c.number_input("Battery → inverter length (m)", 0.2, 100.0, 3.0, disabled=not hybrid)
        dc_lim = c.number_input("DC voltage-drop limit (%)", 0.1, 10.0, 1.0, 0.5, disabled=not hybrid)
        mat = d.selectbox("Conductor", ["copper", "aluminium"])
        temp = d.number_input("Conductor temperature (°C)", 20.0, 250.0, 70.0, help="70 °C PVC, 90 °C XLPE")
    phases = 3 if supply.startswith("Three") else 1
    volts = float(supply.split()[-2])

    # ---- calculate -------------------------------------------------------------------------
    if st.button("Calculate everything", type="primary", use_container_width=True):
        if not name.strip():
            st.error("Enter a project name first.")
            return
        try:
            if src.startswith("PVGIS"):
                if resource is None:
                    with st.spinner("Getting solar data from PVGIS..."):
                        resource = fetch_pvgis(lat, lon, tilt, aspect, loss, cache=store)
                    st.session_state["design_res"], st.session_state["design_res_key"] = resource, key
            else:
                resource = SolarResource.from_peak_sun_hours(psh, loss)
            loads = []
            if loads_df is not None:
                loads = [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in loads_df.to_dict("records")]
            d = ProjectDesign(
                resource=resource, location_label=location_label, loads=loads, diversity_factor=div,
                monthly_kwh=monthly, peak_load_kw=peak, backup_kwh_per_day=backup_manual,
                system_type="hybrid_battery" if hybrid else "grid_tied", panel_wp=wp, panel_area_m2=parea,
                available_area_m2=area or None, target_offset_pct=offset, dc_ac_ratio=ratio, battery_voltage_v=vbat,
                battery_dod_pct=dod, autonomy_days=autonomy, currency=cur, tariff_per_kwh=tariff or None,
                export_rate_per_kwh=export, cost_per_kwp=cost_kwp or None, battery_cost_per_kwh=bcost or None,
                supply_phases=phases, supply_voltage_v=volts, ac_cable_length_m=ac_len, ac_drop_limit_pct=ac_lim,
                dc_cable_length_m=dc_len, dc_drop_limit_pct=dc_lim, conductor=mat, conductor_temp_c=temp)
            results = run_full_design(d)
        except (ValidationError, PVGISError) as e:
            st.error(f"Please check your inputs: {e}")
            return
        pid = store.create_project(name, client, location_label, notes)
        for r in results:
            store.save_calculation(pid, "design", r.name, r.to_dict())
        st.session_state["design_out"] = {"pid": pid, "name": name, "client": client, "location": location_label,
                                          "prepared": prepared, "notes": notes, "results": results}

    out = st.session_state.get("design_out")
    if not out:
        return
    results = out["results"]
    st.divider()
    st.header(f"Results - {out['name']}")
    st.caption(f"Saved as project #{out['pid']} (see Reports & history). Preliminary - for review by a qualified engineer.")
    items = list(summary(results).items())
    for i in range(0, len(items), 4):
        cols = st.columns(4)
        for col, (k, v) in zip(cols, items[i:i + 4]):
            col.metric(k, v)

    meta = reports.ReportMeta(project_name=out["name"], client=out["client"], location=out["location"],
                              prepared_by=out["prepared"], notes=out["notes"])
    dicts = [r.to_dict() for r in results]
    safe = "".join(ch if ch.isalnum() else "_" for ch in out["name"])[:40] or "project"
    a, b = st.columns(2)
    a.download_button("⬇️ Download full PDF report", reports.build_pdf(meta, dicts), f"{safe}_report.pdf",
                      "application/pdf", type="primary", use_container_width=True)
    b.download_button("⬇️ Download editable report (Markdown)", reports.build_markdown(meta, dicts),
                      f"{safe}_report.md", "text/markdown", use_container_width=True)

    for r in results:
        with st.expander(r.name, expanded=r.name == "Load schedule" or r.name.startswith("Solar PV")):
            render_result(r)
