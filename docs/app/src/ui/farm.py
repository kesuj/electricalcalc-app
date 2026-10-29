"""'Solar farm' page: utility-scale PV for Nepal. Method from Neill, Stapleton & Martell, *Solar Farms*
(Earthscan) Ch.3-4 (errata corrected in ecalc.calc.farm); data is current and Nepal-specific
(PVGIS for the site, NEA 2024 tender PPA rates, NEPQA-2025, indicative NPR costs).
"""

from __future__ import annotations

import math

import altair as alt
import pandas as pd
import streamlit as st

from ecalc import nepal_data as nd
from ecalc import reports, solar_data
from ecalc.calc import ValidationError
from ecalc.calc.farm import (BIGHA_M2, DEFAULT_LOSSES, ROPANI_M2, FarmInputs, Inverter, Module, book_string_design,
                             farm_design, optimal_tilt, row_spacing)
from ecalc.calc.result import CalcResult, Quantity as Q
from ecalc.finance import cash_flow
from ecalc.nepal import site_choices, site_coords, site_name
from ecalc.solar_data import PVGISError
from ui.charts import BAD, SUN, USE, cumulative_cash, losses_waterfall
from ui.book_farm import book_farm_tab
from ecalc.calc.install_farm import PackageInputs, build_farm_package
from ecalc.calc.farm_cost import farm_cost
from ecalc.drawings import farm_sld_svg
from ui.package_view import farm_sections, render_sections
from ui.common import get_store, page_header, render_result
from ui.hints import missing, num

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
CRORE = 1e7


def _engineer_settings() -> dict:
    e: dict = {}
    with st.expander("🔧 Engineer settings (optional - typical current values are already filled in)"):
        st.caption("Standard values for today's equipment. Replace them with your chosen module and inverter "
                   "datasheets. Every value is printed in the report.")
        st.markdown("**Module** (TOPCon-class 550 Wp; NEPQA-2025 requires ≥ 21 % efficiency above 350 Wp)")
        a, b, c, d = st.columns(4)
        e["wp"] = a.number_input("Module Wp", 100.0, 900.0, 550.0, 5.0, key="f_wp")
        e["voc"] = b.number_input("Voc (V)", 10.0, 100.0, 49.5, 0.1, key="f_voc")
        e["vmp"] = c.number_input("Vmp (V)", 10.0, 100.0, 41.6, 0.1, key="f_vmp")
        e["isc"] = d.number_input("Isc (A)", 1.0, 30.0, 14.0, 0.1, key="f_isc")
        a, b, c, d = st.columns(4)
        e["imp"] = a.number_input("Imp (A)", 1.0, 30.0, 13.2, 0.1, key="f_imp")
        e["beta"] = b.number_input("β Voc (%/°C)", -1.0, 0.0, -0.25, 0.01, key="f_beta")
        e["gamma"] = c.number_input("γ Pmax (%/°C)", -1.0, 0.0, -0.29, 0.01, key="f_gamma")
        e["eff"] = d.number_input("Module efficiency (%)", 5.0, 30.0, 21.3, 0.1, key="f_eff")
        st.markdown("**Inverter** (utility string inverter, 1500 V class)")
        a, b, c, d = st.columns(4)
        e["kva"] = a.number_input("AC rating (kVA)", 1.0, 5000.0, 330.0, key="f_kva")
        e["dc_max_kw"] = b.number_input("Max DC power (kW)", 1.0, 7000.0, 450.0, key="f_dckw")
        e["vdc"] = c.number_input("Max DC voltage (V)", 100.0, 1500.0, 1500.0, key="f_vdc")
        e["idc"] = d.number_input("Max DC input current (A)", 1.0, 5000.0, 390.0, key="f_idc",
                                  help="Total for the inverter (e.g. 6 MPPT × 65 A = 390 A).")
        a, b, c, d = st.columns(4)
        e["mppt_min"] = a.number_input("MPPT min (V)", 50.0, 1500.0, 500.0, key="f_mmin")
        e["mppt_max"] = b.number_input("MPPT max (V)", 50.0, 1500.0, 1500.0, key="f_mmax")
        e["inputs"] = int(c.number_input("DC inputs / MPPTs", 1, 50, 6, key="f_inputs"))
        e["tmax"] = d.number_input("Hottest cell temperature (°C)", 40.0, 90.0, 70.0, key="f_tmax",
                                   help="The book recommends 70 °C for design (Solar Farms p.107).")
        a, b, c = st.columns(3)
        e["sigma"] = a.number_input("Year-to-year uncertainty σ (%)", 1.0, 20.0, 5.0, 0.5, key="f_sigma",
                                    help="Combined uncertainty of weather and model, used for P90 = P50 × (1 − 1.282σ).")
        e["extra_land"] = b.number_input("Extra land for roads/substation (%)", 0.0, 200.0, 20.0, key="f_extra")
        e["sys_loss"] = c.number_input("PVGIS system loss (%)", 0.0, 50.0, 14.0, key="f_sysloss",
                                       help="Only used for the PVGIS request; the farm's own loss table sets PR.")
    return e


def _cross_section(rs: dict, tilt: float, slant: float) -> alt.LayerChart:
    """Two rows side view with the winter-solstice noon sun ray grazing the next row's bottom edge."""
    a, h, d = rs["footprint_m"], rs["height_m"], rs["pitch_m"]
    rows = pd.DataFrame([{"x": 0, "y": 0, "row": "Row 1"}, {"x": a, "y": h, "row": "Row 1"},
                         {"x": d, "y": 0, "row": "Row 2"}, {"x": d + a, "y": h, "row": "Row 2"}])
    ray = pd.DataFrame([{"x": a, "y": h}, {"x": d, "y": 0}])
    ground = pd.DataFrame([{"x": -0.5, "y": 0}, {"x": d + a + 0.5, "y": 0}])
    lines = alt.Chart(rows).mark_line(strokeWidth=6, color=USE).encode(
        x=alt.X("x:Q", title="Metres (south → north)"), y=alt.Y("y:Q", title="Height (m)"), detail="row:N")
    sun = alt.Chart(ray).mark_line(strokeDash=[6, 4], color=SUN, strokeWidth=2).encode(x="x:Q", y="y:Q")
    gnd = alt.Chart(ground).mark_line(color="#8a8f98").encode(x="x:Q", y="y:Q")
    return alt.layer(gnd, lines, sun).properties(height=220)


def _monthly_mwh(mwh: list[float], p90_factor: float) -> alt.LayerChart:
    df = pd.DataFrame({"Month": MONTHS, "P50 (MWh)": mwh, "P90 (MWh)": [m * p90_factor for m in mwh]})
    bars = alt.Chart(df).mark_bar(color=SUN).encode(
        x=alt.X("Month:N", sort=MONTHS, title=None), y=alt.Y("P50 (MWh):Q", title="Energy per month (MWh)"),
        tooltip=["Month", alt.Tooltip("P50 (MWh):Q", format=",.0f"), alt.Tooltip("P90 (MWh):Q", format=",.0f")])
    tick = alt.Chart(df).mark_tick(color=BAD, thickness=2, size=28).encode(x=alt.X("Month:N", sort=MONTHS),
                                                                         y="P90 (MWh):Q")
    return alt.layer(bars, tick).properties(height=320)


def farm():
    page_header("🏭 Solar farm (utility-scale)",
                "Plan a grid-connected solar power plant in Nepal - energy, layout, land, strings, losses and "
                "money. Grey text in each box tells you what to enter.")
    store = get_store()

    st.subheader("Step 1 · Project and site")
    a, b = st.columns(2)
    name = a.text_input("Project name *", placeholder="e.g. Nawalparasi 10 MW solar", key="f_name")
    developer = b.text_input("Developer / client", placeholder="Optional", key="f_dev")
    a, b = st.columns(2)
    site = a.selectbox("Nearest place *", site_choices(), index=None, placeholder="Choose the nearest town",
                       key="f_site")
    with b.popover("📍 Use exact site location (optional)"):
        st.markdown("In **Google Maps**, right-click the land and click the numbers to copy them: first latitude, "
                    "then longitude.")
        lat_in = num(st, "lat", "Latitude", -90.0, 90.0, wkey="f_lat")
        lon_in = num(st, "lon", "Longitude", -180.0, 180.0, wkey="f_lon")
    exact = lat_in is not None and lon_in is not None
    lat, lon = (lat_in, lon_in) if exact else (site_coords(site) if site else (None, None))
    place = site_name(site) if site else ""
    location_label = (f"{lat:.4f}, {lon:.4f}" + (f" (near {place})" if place else "")) if exact else place

    st.subheader("Step 2 · Plant size")
    a, b, c = st.columns(3)
    mwp = num(a, "farm_mwp", "Plant size (MWp of panels) *", 0.1, 500.0, wkey="f_mwp")
    ac_limit = num(b, "farm_ac_mw", "Export limit (MW AC) - optional", 0.1, 500.0, wkey="f_acmw")
    temps = nd.site_temperatures(place) if place and not exact else None
    tmin = c.number_input("Record low temperature (°C)" + ("" if temps else " *"), -40.0, 30.0,
                          value=temps[0] if temps else None, placeholder="Record low at site (°C)",
                          help="Coldest temperature ever recorded near the site (DHM). Sets the maximum string "
                               "length. Pre-filled for Kathmandu, Pokhara, Biratnagar, Nepalgunj and Jumla.",
                          key=f"f_tmin_{place}")
    eng = _engineer_settings()

    if st.button("Calculate the solar farm", type="primary", width="stretch", key="f_go"):
        gaps = missing({"Project name": name, "Nearest place (or exact location)": lat,
                        "Plant size": mwp, "Record low temperature": tmin})
        if gaps:
            st.error("Please answer: " + ", ".join(gaps) + ".")
            return
        tilt0 = optimal_tilt(lat)
        try:
            with st.spinner("Getting sunshine data for the site from PVGIS..."):
                res = solar_data.fetch_pvgis(lat, lon, tilt0, None, eng["sys_loss"], cache=store)
        except (PVGISError, ValidationError) as e:
            st.error(f"Could not get sunshine data: {e}")
            return
        st.session_state["farm_out"] = {"name": name, "developer": developer, "location": location_label,
                                        "lat": lat, "mwp": mwp, "ac_limit": ac_limit, "tmin": tmin, "res": res,
                                        "tilt0": tilt0, "pid": None}
    out = st.session_state.get("farm_out")
    if out:
        _results(store, out, eng)


def _results(store, out: dict, eng: dict):
    res = out["res"]
    psh_m = res.monthly_irr_kwh_m2_day
    if len(psh_m) != 12:
        st.error("The sunshine data has no monthly in-plane values; try again.")
        return
    psh = sum(p * d for p, d in zip(psh_m, DAYS)) / 365
    st.divider()
    st.header(f"Your solar farm - {out['name']}")
    t_pkg, t_energy, t_layout, t_strings, t_losses, t_money, t_book, t_report = st.tabs(
        ["🛠 Construction package", "📊 Energy", "📐 Layout & land", "⚡ Strings & inverters", "🔻 Losses", "💰 Money",
         "📘 Book method", "📄 Report"])

    # ---- interactive inputs first (tabs can be filled in any order) ---------------------------
    with t_losses:
        st.caption("Edit any loss. Temperature and reflection come from PVGIS for this site; the rest are typical "
                   "modern values (the book's 13 % transformer loss is replaced by ~1 % for a modern unit).")
        losses = dict(DEFAULT_LOSSES)
        if res.details.get("l_tg_pct") is not None:
            losses["Temperature"] = round(abs(float(res.details["l_tg_pct"])), 2)
        if res.details.get("l_aoi_pct") is not None:
            losses["Reflection (angle of incidence)"] = round(abs(float(res.details["l_aoi_pct"])), 2)
        df = st.data_editor(pd.DataFrame({"Loss": list(losses), "Loss (%)": list(losses.values())}),
                            hide_index=True, width="stretch", key="f_losses", disabled=["Loss"],
                            column_config={"Loss (%)": st.column_config.NumberColumn(min_value=0.0, max_value=50.0,
                                                                                     step=0.1)})
        losses = {r["Loss"]: float(r["Loss (%)"] or 0) for r in df.to_dict("records")}
    with t_layout:
        st.selectbox("Keep rows free of shade on the shortest day (21 Dec)", ["9 am - 3 pm (recommended)", "10 am - 2 pm",
                     "Noon only (book minimum)"], key="f_shade",
                     help="The book's minimum is no shade at winter noon, but it targets < 1 % shading loss a year; "
                          "keeping 9 am-3 pm shade-free is common practice and needs wider rows (more land).")
        st.caption("Move the sliders: rows are spaced so they don't shade each other at noon on the shortest day "
                   "(21 December), as the book recommends.")
        a, b = st.columns(2)
        tilt = a.slider("Panel tilt (°)", 0.0, 45.0, float(round(out["tilt0"], 1)), 0.5, key="f_tilt",
                        help="Best yearly tilt ≈ latitude (Solar Farms Box 4.1); at least 10° so rain cleans the panels.")
        slant = b.slider("Table length up the slope (m)", 1.0, 9.0, 4.6, 0.1, key="f_slant",
                         help="e.g. two 2.3 m modules in portrait = 4.6 m; one module ≈ 2.3 m.")
    with t_money:
        st.caption(f"Indicative Nepal values (checked {nd.CHECKED}) - replace with your EPC quote and PPA.")
        a, b, c = st.columns(3)
        lo, hi = nd.UTILITY_PPA_RANGE
        ppa = a.slider("Sale price to NEA (Rs/kWh)", 4.0, 7.5, nd.UTILITY_PPA_RS, 0.01, key="f_ppa",
                       help=f"2024 NEA tender awards: Rs {lo}-{hi}/kWh; ceiling Rs {nd.UTILITY_PPA_CEILING_RS}.")
        capex_kw = b.slider("Build cost (Rs per kW)", 40_000, 100_000, nd.INSTALLED_UTILITY_RS_PER_KW, 1_000,
                            key="f_capex", help="Utility-scale EPC is roughly Rs 60,000-70,000 per kW (indicative).")
        years = int(c.slider("Contract length (years)", 10, 30, nd.PPA_YEARS, 1, key="f_years"))
        a, b, c = st.columns(3)
        om_pct = a.slider("Operation & maintenance (% of build cost per year)", 0.0, 4.0,
                          nd.UTILITY_OM_PCT_OF_CAPEX, 0.1, key="f_om")
        disc = b.slider("Discount rate (%)", 0.0, 20.0, nd.DISCOUNT_RATE_PCT, 0.5, key="f_disc",
                        help="Cost of money; 8-12 % is typical for emerging markets.")
        deg = c.slider("Panel ageing (% per year)", 0.0, 1.5, 0.5, 0.05, key="f_deg",
                       help="NEPQA-2025 warranty floor allows up to 0.8 %/yr after year 1.")

    # ---- calculations -------------------------------------------------------------------------
    try:
        mod = Module(wp=eng["wp"], vmp=eng["vmp"], imp=eng["imp"], voc=eng["voc"], isc=eng["isc"],
                     beta_voc_pct=eng["beta"], gamma_pmax_pct=eng["gamma"], efficiency_pct=eng["eff"])
        inv = Inverter(ac_kva=eng["kva"], max_dc_kw=eng["dc_max_kw"], v_dc_max=eng["vdc"], v_mppt_min=eng["mppt_min"],
                       v_mppt_max=eng["mppt_max"], i_dc_max=eng["idc"], dc_inputs=eng["inputs"])
        sr = book_string_design(mod, inv, t_cell_min=out["tmin"], t_cell_max=eng["tmax"])
        n_inv = None
        if "dc_kw_per_inverter" in sr.outputs:
            n_inv = math.ceil(out["mwp"] * 1000 / sr.out("dc_kw_per_inverter"))
            sr.outputs["n_inverters"] = Q(n_inv, "inverters", "Number of inverters")
            sr.outputs["total_ac_mw"] = Q(n_inv * eng["kva"] / 1000, "MW", "Total inverter AC rating")
        ac_mw = out["ac_limit"] or (n_inv * eng["kva"] / 1000 if n_inv else None)
        shade_h = {"Noon only (book minimum)": 0, "10 am - 2 pm": 2, "9 am - 3 pm (recommended)": 3}[
            st.session_state.get("f_shade", "9 am - 3 pm (recommended)")]
        fi = FarmInputs(capacity_mwp=out["mwp"], latitude=out["lat"], annual_psh=psh, monthly_psh=psh_m,
                        losses_pct=losses, tilt_deg=tilt, table_slant_m=slant,
                        module_efficiency_pct=eng["eff"], land_extra_pct=eng["extra_land"], ac_mw=ac_mw,
                        degradation_pct=deg, shade_free_hours=shade_h)
        fr = farm_design(fi)
    except ValidationError as e:
        st.error(f"Please check the settings: {e}")
        return
    pr, mwh = fr.out("pr"), fr.out("annual_mwh")
    p90_factor = 1 - 1.282 * eng["sigma"] / 100
    monthly = [out["mwp"] * p * d * pr for p, d in zip(psh_m, DAYS)]
    capex = out["mwp"] * 1000 * capex_kw
    cf = cash_flow(capex, mwh * 1000, ppa, years=years, degradation_pct=deg, om_per_year=capex * om_pct / 100,
                   discount_rate_pct=disc)

    # ---- construction package (needs a safe string design) ----------------------------------------
    ss = st.session_state
    pi = PackageInputs(inverter_type=ss.get("f_pk_type", "string"), string_run_m=ss.get("f_pk_str", 60.0),
                       lv_run_m=ss.get("f_pk_lv", 150.0), mv_run_m=ss.get("f_pk_mv", 500.0),
                       line_to_nea_km=ss.get("f_pk_line", 2.0), ambient_max_c=ss.get("f_pk_amb", 40.0),
                       module_max_fuse_a=eng.get("max_fuse", 30.0) if isinstance(eng, dict) else 30.0)
    try:
        pkg = build_farm_package(fr, sr, mod, inv, fi, pi)
        pkg_error = None
    except ValidationError as e:
        pkg, pkg_error = None, str(e)
    cost = sld = None
    if pkg:
        cost = farm_cost(pkg, eng["wp"], eng["kva"], ss.get("f_pk_line", 2.0), fr.out("land_ha"))
        sld = farm_sld_svg(pkg, int(sr.out("modules_per_string")), sr.out("string_voc_cold_v"),
                           sr.out("modules_per_string") * eng["vmp"], eng["wp"], eng["kva"])
    sections = farm_sections(pkg, cost, sld) if pkg else []

    # ---- outputs ------------------------------------------------------------------------------
    with t_pkg:
        st.markdown("The design and construction package for the contractor (EPC): **what to build, how it connects, "
                    "what to order, how to build it, how to test it, how to run it.** The same content is in the PDF.")
        with st.expander("Site distances and inverter type (change to match your land)"):
            a, b, c = st.columns(3)
            a.selectbox("Inverter type", ["string", "central"], key="f_pk_type",
                        help="String inverters (e.g. 330 kVA, 1500 V) spread across the field; central inverters "
                             "(MW size) need DC combiner boxes.")
            b.number_input("Average string cable run (m)", 5.0, 500.0, 60.0, 5.0, key="f_pk_str")
            c.number_input("Inverter → transformer cable (m)", 5.0, 2000.0, 150.0, 10.0, key="f_pk_lv")
            a.number_input("Transformer → switchyard cable (m)", 10.0, 5000.0, 500.0, 50.0, key="f_pk_mv")
            b.number_input("Line to the NEA substation (km)", 0.1, 100.0, 2.0, 0.1, key="f_pk_line",
                           help="Distance along the planned 11/33 kV line to the NEA substation.")
            c.number_input("Hottest air temperature at site (°C)", 20.0, 50.0, 40.0, 1.0, key="f_pk_amb",
                           help="Used to derate cable current ratings.")
        if pkg_error:
            st.error(f"Construction package not possible yet: {pkg_error}")
        else:
            render_sections(sections)
    with t_energy:
        a, b, c, d = st.columns(4)
        a.metric("Energy per year (P50)", f"{mwh:,.0f} MWh")
        b.metric("Energy per year (P90)", f"{mwh * p90_factor:,.0f} MWh",
                 help="Exceeded in 9 years out of 10: P90 = P50 × (1 − 1.282σ).")
        c.metric("Specific yield", f"{fr.out('specific_yield'):,.0f} kWh/kWp")
        d.metric("Performance ratio", f"{pr:.3f}")
        a, b, c, d = st.columns(4)
        a.metric("Capacity factor (DC)", f"{fr.out('cf_dc_pct'):.1f} %")
        b.metric("Capacity factor (AC)", f"{fr.out('cf_ac_pct'):.1f} %")
        c.metric("Sun on the panels", f"{psh:.2f} kWh/m²/day")
        d.metric("Homes supplied (approx.)", f"{mwh * 1000 / (150 * 12):,.0f}",
                 help="Assuming a Nepali household uses about 150 units per month (illustrative).")
        st.altair_chart(_monthly_mwh(monthly, p90_factor), width="stretch")
        st.caption(f"Energy = MWp × sun hours × days × PR (Solar Farms p.81). Sunshine: {res.source}. "
                   "Red ticks show P90. The monsoon (Jun-Sep) is lower because of cloud.")
        if fr.out("specific_yield") > 1400:
            st.warning("Satellite data (PVGIS) can be optimistic in Nepal, especially the Terai in winter fog and haze: "
                       "Nepali plants report about 1,100-1,400 kWh/kWp a year (secondary source). Use the P90 figure "
                       "for planning and measured site data for a bankable study.")
    with t_layout:
        rs = row_spacing(out["lat"], tilt, slant, shade_free_hours=shade_h or None)
        a, b, c, d = st.columns(4)
        a.metric("Row pitch", f"{rs['pitch_m']:.2f} m")
        b.metric("Gap between rows", f"{rs['gap_m']:.2f} m")
        c.metric("Ground coverage", f"{rs['gcr']:.2f}")
        d.metric("Lowest design sun height (21 Dec)", f"{rs['sun_altitude_deg']:.1f}°")
        st.altair_chart(_cross_section(rs, tilt, slant), width="stretch")
        land_m2 = fr.out("land_ha") * 10000
        a, b, c, d = st.columns(4)
        a.metric("Land needed", f"{fr.out('land_ha'):,.1f} ha")
        b.metric("In bigha (Terai)", f"{land_m2 / BIGHA_M2:,.0f} bigha")
        c.metric("In ropani (hills)", f"{land_m2 / ROPANI_M2:,.0f} ropani")
        d.metric("Land per MWp", f"{fr.out('land_per_mwp_ha'):.2f} ha")
        st.caption("Check: NEA's 2024 tender projects need roughly 2.1 ha per MW (secondary source); US fixed-tilt "
                   "plants average ~1.2 ha/MWdc (LBNL 2022). Steeper tilt or longer tables → wider spacing → more land.")
    with t_strings:
        if sr.warnings and any("NOT safe" in w or "No string" in w for w in sr.warnings):
            st.error("This module and inverter combination does not give a safe string length at this site's record "
                     "low temperature. Change the inverter or module in Engineer settings.")
        render_result(sr, [k for k in ("modules_per_string", "strings_used", "n_inverters", "dc_ac_ratio")
                           if k in sr.outputs] or ["n_min", "n_max"])
        st.metric("Step-up transformer (total)", f"{fr.out('transformer_mva'):.2f} MVA",
                  help="At least the total inverter AC rating (Solar Farms pp.116-117). Typical NEA connection: "
                       "11 or 33 kV for plants of this size; 132 kV for large plants.")
    with t_losses:
        st.altair_chart(losses_waterfall(list(losses.items())), width="stretch")
        st.metric("Performance ratio (PR = Π (1 − loss))", f"{pr:.3f}")
    with t_money:
        a, b, c, d = st.columns(4)
        a.metric("Build cost", f"Rs {capex / CRORE:,.1f} crore")
        b.metric("Cost per unit (LCOE)", f"Rs {cf.lcoe:.2f}/kWh", delta=f"{ppa - cf.lcoe:+.2f} vs sale price",
                 help="Levelised cost: discounted lifetime costs ÷ discounted lifetime energy (NREL/IRENA form).")
        c.metric("Return (IRR)", f"{cf.irr_pct:.1f} %" if cf.irr_pct is not None else "below 0 %")
        d.metric("Payback", f"{cf.simple_payback_years:.1f} years" if cf.simple_payback_years else f"> {years} years")
        st.metric("Net present value", f"Rs {cf.npv / CRORE:,.1f} crore",
                  help="Positive = earns more than the discount rate.")
        rows = [dict(r, Cumulative=r["Cumulative"] / CRORE, **{"Net cash flow": r["Net cash flow"] / CRORE})
                for r in cf.rows]
        st.altair_chart(cumulative_cash(rows, "Rs crore"), width="stretch")
        with st.expander("Year-by-year cash flow"):
            st.dataframe(cf.rows, hide_index=True, width="stretch")
        with st.expander("Data sources and dates"):
            for s in nd.SOURCES:
                st.markdown(f"- {s}")
    fin = CalcResult(
        name="Solar farm - money (indicative)",
        inputs={"ppa": Q(ppa, "Rs/kWh", "Sale price to NEA"), "capex_kw": Q(capex_kw, "Rs/kW", "Build cost"),
                "om": Q(om_pct, "%/yr", "O&M (% of build cost)"), "disc": Q(disc, "%", "Discount rate"),
                "deg": Q(deg, "%/yr", "Panel ageing"), "years": Q(years, "years", "Contract length")},
        outputs={"capex": Q(capex, "Rs", "Build cost"), "lcoe": Q(cf.lcoe, "Rs/kWh", "Cost per unit (LCOE)"),
                 "irr": Q(cf.irr_pct if cf.irr_pct is not None else "n/a", "%", "IRR"),
                 "npv": Q(cf.npv, "Rs", "Net present value"),
                 "payback": Q(cf.simple_payback_years or "beyond contract", "years", "Simple payback")},
        equations=["LCOE = (capex + Σ O&M_t/(1+r)^t) / Σ E_t/(1+r)^t", "E_t = E_1 × (1 − ageing)^(t−1)"],
        assumptions=["Prices are indicative Nepal values (see sources); no tax, loan, VAT or land cost included."],
        references=nd.SOURCES)
    with t_book:
        book_farm_tab(out, fr, sr, mod, inv, losses, cf, shade_free_hours=shade_h, capex_rs=capex)
    with t_report:
        plain = [
            f"A {out['mwp']:g} MWp solar farm at {out['location']} should produce about {mwh:,.0f} MWh a year "
            f"(about {mwh * p90_factor:,.0f} MWh in a poor year, P90).",
            f"Panels tilted {tilt:g}° facing south, rows {rs['pitch_m']:.1f} m apart; land about "
            f"{fr.out('land_ha'):,.1f} ha ({land_m2 / BIGHA_M2:,.0f} bigha).",
            (f"{sr.out('modules_per_string'):g} panels per string, {n_inv} inverters of {eng['kva']:g} kVA, "
             f"transformer about {fr.out('transformer_mva'):.1f} MVA." if n_inv else
             "No safe string length with the chosen module and inverter - change the equipment."),
            f"Build cost about Rs {capex / CRORE:,.1f} crore; cost per unit Rs {cf.lcoe:.2f}/kWh against a sale "
            f"price of Rs {ppa:.2f}/kWh" + (f"; return {cf.irr_pct:.1f}% per year." if cf.irr_pct is not None else "."),
            "Preliminary feasibility only - a bankable design needs a detailed simulation, site survey, grid study "
            "and NEA approval.",
        ]
        st.success("\n".join(f"- {x}" for x in plain))
        results = [fr, sr, fin]
        meta = reports.ReportMeta(project_name=out["name"], client=out["developer"], location=out["location"],
                                  notes="Utility-scale solar farm - method: Neill, Stapleton & Martell, Solar Farms "
                                        "(Earthscan); data: PVGIS, NEA/ERC, NEPQA-2025, indicative Nepal prices.")
        dicts = [r.to_dict() for r in results]
        safe = "".join(ch if ch.isalnum() else "_" for ch in out["name"])[:40] or "solar_farm"
        a, b = st.columns(2)
        a.download_button("⬇️ Download the full report (PDF)",
                          reports.build_pdf(meta, dicts, summary=plain, sections=sections,
                                            title="Solar Farm Design & Construction Package"),
                          f"{safe}_report.pdf", "application/pdf", type="primary", width="stretch",
                          key="f_pdf")
        b.download_button("⬇️ Download an editable copy",
                          reports.build_markdown(meta, dicts, summary=plain, sections=sections,
                                                 title="Solar Farm Design & Construction Package"),
                          f"{safe}_report.md", "text/markdown", width="stretch", key="f_md")
        if st.button("💾 Save on this computer", key="f_save"):
            pid = out.get("pid")
            if pid and store.get_project(pid):
                for c in store.list_calculations(pid):
                    store.delete_calculation(c["id"])
                store.update_project(pid, out["developer"], out["location"], meta.notes)
            else:
                pid = store.create_project(out["name"], out["developer"], out["location"], meta.notes)
                out["pid"] = pid
            for r in results:
                store.save_calculation(pid, "farm", r.name, r.to_dict())
            st.success(f"Saved on this computer as project #{pid}.")
