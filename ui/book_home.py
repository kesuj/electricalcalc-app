"""📘 Book method tab for Home solar: the step order, calculations, tables and charts of Boxwell,
*Solar Electricity Handbook* (2012), shown with the user's own Nepal project numbers.

Book content is paraphrased (no text copied); § numbers refer to the book's sections.
Modern data replaces the book's 2012 / UK-US data and is labelled as such.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from ecalc.calc.home import CHEMISTRY, DAYS, LEAD_ACID_CYCLES, MONTHS, book_cable_mm2, power_analysis
from ecalc.calc.sun import (EQUINOX_MAR, MONTH_DAYS, SOLSTICE_DEC, SOLSTICE_JUN, declination, noon_altitude,
                            sun_path)
from ecalc.nepal_data import site_temperatures
from ecalc.solar_data import PVGISError, fetch_pvgis
from ui.common import get_store

SUN, USE, BAD, GOOD, GREY = "#f2a900", "#1f4e79", "#d1495b", "#2e9e5b", "#8a8f98"
IEC_SIZES = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95]
# §145: % of a day's generation lost if that hour is shaded (core window 9 am - 3 pm)
SHADE_TABLE = {"9-10 am": (3, 6), "10-11 am": (15, 10), "11 am-12": (27, 14), "12-1 pm": (27, 14),
               "1-2 pm": (15, 10), "2-3 pm": (3, 6)}
# §69/§145: shade outside the core window (each side): summer ~20 % before 9 or after 3; winter 5-10 %
OUTSIDE = {"Before 9 am": (5, 20), "After 3 pm": (5, 20)}
SOURCE = ("Method: Boxwell, *Solar Electricity Handbook* (2012), section numbers shown as §. "
          "Data: PVGIS v5.3 for your site, NEPQA-2025 (AEPC), ERC tariff order 2078, 2026 Nepal prices.")


def _f(v, d=0):
    return f"{v:,.{d}f}"


def book_home_tab(out: dict) -> None:
    r = out["result"]
    x = out["inputs"]
    o = r.outputs
    st.markdown("This tab shows **how the book designs your system, step by step, with your numbers**, and "
                "recreates the book's charts for your site in Nepal. The design itself is the same as in the other tabs.")
    st.caption(SOURCE)
    _steps(out, r, x, o)
    st.divider()
    st.subheader("Charts from the book, redrawn for your site")
    _mounting_angles(out, x, o)
    _roof_direction(out)
    _sun_height(out)
    _temperature(out)
    _shading()
    _battery_life(out, x)
    _cable_table(out, x, o)
    st.divider()
    _what_changed()


# ---- A. step by step ---------------------------------------------------------------------------
def _steps(out, r, x, o):
    st.subheader("The book's 7 design steps with your numbers (§41)")
    pa = power_analysis(x.loads, x.phantom_w)
    inv = x.inverter_eff_pct / 100
    mode = out["mode"]
    chem = CHEMISTRY[x.chemistry]
    beff = chem["eff"] / 100
    eta = 0.90 if x.controller == "MPPT" else 0.75
    temp = x.temp_loss_pct / 100
    shade = x.shade_loss_pct / 100

    with st.expander("Step 1 - Scope the project: what must the system do? (§45-§54)", expanded=True):
        st.markdown(f"- System type: **{r.inputs['mode'].value}**  \n"
                    f"- Site: **{out.get('place') or 'your location'}** ({out['lat']:.3f}° N, {out['lon']:.3f}° E)  \n"
                    f"- Months that must be fully covered: **{', '.join(MONTHS[m - 1] for m in sorted(x.months_required))}**")
        st.caption("The book starts by deciding what the system must power and when. Off-grid systems are sized for the "
                   "worst month; grid systems for the yearly average (§46).")

    with st.expander("Step 2 - Calculate the energy you need (§47-§53)", expanded=True):
        st.markdown("**Power analysis (§48):** energy = power × hours for every appliance, then add them up.")
        st.dataframe(pd.DataFrame(pa["rows"]), hide_index=True, width="stretch")
        st.code(f"Daily energy  = Σ (W × qty × hours) = {_f(pa['daily_wh'])} Wh/day\n"
                f"Peak load     = Σ W (everything on at once) = {_f(pa['peak_w'])} W", language=None)
        lines = [f"Design energy = DC {_f(pa['dc_wh'])} Wh + AC {_f(pa['ac_wh'])} Wh ÷ {inv:.2f} (inverter)"]
        if mode == "off_grid":
            lines.append(f"              ÷ {beff:.2f} (battery charge/discharge efficiency)")
        lines.append(f"              = {_f(o['design_wh'].value)} Wh/day")
        st.markdown("**Inefficiencies (§50):** the book adds the inverter loss to mains (AC) appliances and the "
                    "battery loss for battery systems. The app divides by the efficiency (the exact form).")
        st.code("\n".join(lines), language=None)

    with st.expander("Step 3 - Calculate the solar energy available (§55-§62)", expanded=True):
        psh = out["monthly_psh"]
        if mode == "off_grid":
            req = sorted(x.months_required)
            worst = min(req, key=lambda m: psh[m - 1])
            basis = (f"Worst required month = {MONTHS[worst - 1]}: {psh[worst - 1]:.2f} kWh/m²/day "
                     "(off-grid must survive the darkest month, §56)")
        else:
            basis = (f"Yearly average = Σ(sun × days) ÷ 365 = {o['design_psh'].value:.2f} kWh/m²/day "
                     "(grid systems are sized on the year, §46)")
        st.markdown(f"Sun on your panels by month (PVGIS, tilt {out['tilt']:g}°): " +
                    ", ".join(f"{m} {p:.2f}" for m, p in zip(MONTHS, psh)))
        st.code(basis, language=None)
        raw = o["design_wh"].value / o["design_psh"].value
        st.markdown(f"**Array size (§56, §58):** controller factor **{eta:g}** ({x.controller}: the book uses 0.90 with "
                    "MPPT, 0.75 without).")
        st.code(f"Raw array      = {_f(o['design_wh'].value)} Wh ÷ {o['design_psh'].value:.2f} h = {_f(raw)} W\n"
                f"With controller = {_f(raw)} ÷ {eta:g} = {_f(raw / eta)} W\n"
                f"With temperature ({temp * 100:.1f} %) and shading ({shade * 100:.0f} %) losses\n"
                f"               = {_f(raw / eta)} ÷ (1 − {temp:.3f}) ÷ (1 − {shade:.2f}) = {_f(o['array_w'].value)} W\n"
                f"Panels         = ceil({_f(o['array_w'].value)} ÷ {x.panel_wp:g} W) = {o['panel_count'].value} panels "
                f"= {_f(o['installed_w'].value)} W installed", language=None)
        temps = site_temperatures(out.get("place") or "")
        st.markdown("**Temperature (§59):** the book estimates panel temperature as air °C × 1.4 (roof) or × 1.2 (pole) "
                    "and applies 0.5 % loss per °C above 25 °C, only when the air averages ≥ 25 °C. The app uses the "
                    "site-specific temperature loss from PVGIS instead.")
        if temps:
            roof_t, pole_t = temps[1] * 1.4, temps[1] * 1.2
            st.code(f"Book rule at {out.get('place')}'s record high {temps[1]:g} °C (worst case):\n"
                    f"  roof panel ≈ {temps[1]:g} × 1.4 = {roof_t:.0f} °C -> loss {(roof_t - 25) * 0.5:.0f} %\n"
                    f"  pole panel ≈ {temps[1]:g} × 1.2 = {pole_t:.0f} °C -> loss {(pole_t - 25) * 0.5:.0f} %\n"
                    f"PVGIS yearly temperature loss used for your site: {temp * 100:.1f} %", language=None)
        else:
            st.code(f"PVGIS yearly temperature loss used for your site: {temp * 100:.1f} %", language=None)
        st.markdown("**Area (§61):** the book used 60 W/m² (amorphous) or 160 W/m² (crystalline, 2012). Today's panels "
                    f"give about {x.panel_wp / x.panel_area_m2:.0f} W/m².")
        st.code(f"Roof area = {o['panel_count'].value} × {x.panel_area_m2:g} m² = {o['array_area_m2'].value:.1f} m²  "
                f"(book 2012 crystalline: {o['installed_w'].value / 160:.1f} m²)", language=None)

    with st.expander("Step 4 - Survey the site (§63-§73)"):
        st.markdown("- Check shade from trees, water tanks and buildings between **9 am and 3 pm** - see the shading "
                    "chart below (§69, §145).\n- Measure cable runs: panels → controller → battery → inverter (§72).\n"
                    "- Battery place: dry, ventilated, not in sun, close to the inverter (§70).\n"
                    f"- Your panels face azimuth {out['aspect']:g}° (0 = due south) at {out['tilt']:g}° tilt.")

    with st.expander("Step 5 - Size the system: voltage, battery, controller, inverter (§85-§91)", expanded=True):
        if "system_v" in o:
            v = o["system_v"].value
            load_w = pa["critical_w"] if mode == "hybrid_backup" else pa["peak_w"]
            i_load, i_arr = load_w / v, o["installed_w"].value / v
            st.markdown("**System voltage (§85-§87):** choose the lowest of 12/24/48 V where the book's cable formula "
                        "stays at or under 6 mm².")
            st.code(f"Current = W ÷ V:  load {_f(load_w)} W ÷ {v} V = {i_load:.1f} A,  array {_f(o['installed_w'].value)} W ÷ "
                    f"{v} V = {i_arr:.1f} A\n"
                    f"Cable  = L × I × 0.04 ÷ (V ÷ 20) = {x.dc_cable_length_m:g} × {max(i_load, i_arr):.1f} × 0.04 ÷ "
                    f"({v} ÷ 20) = {o['dc_cable_mm2'].value:.2f} mm²  (≈ 5 % voltage drop)\n"
                    f"Chosen system voltage = {v} V", language=None)
            if mode == "off_grid":
                store = f"{_f(o['design_wh'].value)} Wh × {x.holdover_days:g} days of autonomy"
            else:
                store = (f"backup appliances {_f(pa['critical_w'])} W ÷ {inv:.2f} (inverter) × {x.outage_hours:g} h power cut "
                         f"÷ {beff:.2f} (battery)")
            st.markdown(f"**Battery (§89)** - {x.chemistry}, depth of discharge {r.inputs['dod'].value:.0f} %:")
            st.code(f"Energy from battery = {store} = {_f(o['battery_usable_wh'].value)} Wh\n"
                    f"Capacity = {_f(o['battery_usable_wh'].value)} Wh ÷ {v} V ÷ {r.inputs['dod'].value / 100:.2f} = "
                    f"{_f(o['battery_ah'].value)} Ah at {v} V ({o['battery_kwh_nominal'].value:.1f} kWh)\n"
                    f"Estimated life ≈ {o['battery_life_years'].value:.1f} years", language=None)
            if x.chemistry.startswith("Lead"):
                st.caption("Book life method: cycles at this depth of discharge (table below) × days per cycle, capped "
                           "at the battery's float life. The book also says second-hand batteries hold about 50 %.")
            st.markdown("**Charge controller (§90):** must carry the array current; the book only says 'buy bigger'. "
                        "The app adds 25 %.")
            st.code(f"Controller ≥ {_f(o['installed_w'].value)} W ÷ {v} V × 1.25 = {o['controller_a'].value:.1f} A", language=None)
        else:
            st.markdown("Grid-tied: no battery or charge controller. The inverter's input window must contain the string "
                        "voltage (§83).")
        rule = ("≥ 4/3 × appliances on at once (§91)" if mode == "off_grid" else
                "≥ max(4/3 × backup appliances (§91), array ÷ 1.2)" if mode == "hybrid_backup" else
                "≈ array ÷ 1.2 (DC/AC ratio, modern practice)")
        st.markdown(f"**Inverter:** {rule}. Pure sine wave; check surge for motors (§91).")
        st.code(f"Inverter ≈ {_f(o['inverter_w'].value)} W", language=None)

    with st.expander("Step 6 - Choose components and costs (§74-§103)"):
        st.markdown("- **Panels:** NEPQA-2025 requires ≥ 21 % efficiency above 350 Wp and 0/+3 % power tolerance "
                    "(the book: mono 15-24 %, 2012).\n"
                    "- **Controller:** MPPT ≥ 95 % efficient (NEPQA); the book notes MPPT gains ~20 % over PWM (§90).\n"
                    "- **Battery:** LiFePO4 ≥ 3,000 cycles at 80 % DoD (NEPQA) - the 2012 book covers lead-acid only.\n"
                    "- **Inverter:** pure sine wave (§91); NEPQA ≥ 95 % peak efficiency up to 5 kVA.\n"
                    "- **Costs:** the book's £/W figures are replaced by 2026 Nepal prices (Money tab).")

    with st.expander("Step 7 - Detailed design and protection checklist (§104-§112)", expanded=True):
        items = ["Fuse or DC breaker on the battery + terminal, so all current passes through it (§109)" if mode != "grid_tied" else None,
                 "DC isolator between panels and controller/inverter (arrays > 100 W, all grid systems) (§109)",
                 "DC isolator between battery and controller/inverter (§109)" if mode != "grid_tied" else None,
                 "RCD / earth-fault protection between inverter and the house wiring (§109)",
                 "AC isolator between inverter and distribution board; and between grid and board (§109)",
                 "Earth the panel frames (arrays > 200 W) and the battery negative; separate AC and DC earths (§109)",
                 "Use solar (PV) cable for panel runs; size the battery cable for the charge current too (§110)",
                 "Automatic transfer / changeover between grid and backup circuits (§160)" if mode == "hybrid_backup" else None,
                 "Do not use ordinary household plugs/sockets on 12/24 V DC circuits (§93)" if mode == "off_grid" else None]
        for n, it in enumerate(filter(None, items)):
            st.checkbox(it, key=f"bk_chk_{n}")
        st.caption("Tick items as your installer confirms them. Protection must also follow Nepal's electrical rules "
                   "and the equipment manuals.")


# ---- B. charts ---------------------------------------------------------------------------------
def _mounting_angles(out, x, o):
    st.markdown("#### 1. Sun on the panels at different angles (§56, like the book's Appendix B tables)")
    st.caption("What this shows: how much sun the panels catch each month if they lie flat, stand upright, or are "
               "tilted for the whole year, for winter, or for summer. Steeper tilt helps winter, flatter helps summer.")
    lat = abs(out["lat"])
    angles = {"Flat (0°)": 0.0, "Upright (90°)": 90.0, f"Year-round ({lat:.0f}°)": round(lat),
              f"Winter ({lat + 15.6:.0f}°)": round(lat + 15.6), f"Summer ({max(lat - 15.6, 0):.0f}°)": round(max(lat - 15.6, 0))}
    key = f"bk_angles_{out['lat']:.3f}_{out['lon']:.3f}"
    if key not in st.session_state:
        if not st.button("📡 Compare the 5 mounting angles (gets PVGIS data for your site)", key="bk_angles_btn"):
            return
        data = {}
        try:
            with st.spinner("Getting sunshine for 5 angles..."):
                for name, t in angles.items():
                    data[name] = fetch_pvgis(out["lat"], out["lon"], t, 0.0, 14.0, cache=get_store()).monthly_irr_kwh_m2_day
        except PVGISError as e:
            st.info(f"Could not load PVGIS data for the angle comparison: {e}")
            return
        st.session_state[key] = data
    data = st.session_state[key]
    rows = [{"Month": m, "Angle": name, "kWh/m²/day": v} for name, vals in data.items() for m, v in zip(MONTHS, vals)]
    chart = alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
        x=alt.X("Month:N", sort=MONTHS, title=None), y=alt.Y("kWh/m²/day:Q", title="Sun on panels (kWh/m²/day)"),
        color=alt.Color("Angle:N", legend=alt.Legend(orient="top", title=None)),
        tooltip=["Month", "Angle", alt.Tooltip("kWh/m²/day:Q", format=".2f")]).properties(height=320).interactive()
    st.altair_chart(chart, width="stretch")
    eta = 0.90 if x.controller == "MPPT" else 0.75
    sizes = []
    for name, vals in data.items():
        if out["mode"] == "off_grid":
            req = sorted(x.months_required)
            sun = min(vals[m - 1] for m in req)
            basis = "worst required month"
        else:
            sun = sum(v * d for v, d in zip(vals, DAYS)) / 365
            basis = "yearly average"
        sizes.append({"Angle": name, "Array needed (W)": o["design_wh"].value / sun / eta, "Sun used": sun})
    bars = alt.Chart(pd.DataFrame(sizes)).mark_bar(color=SUN).encode(
        x=alt.X("Angle:N", title=None, sort=list(data)), y=alt.Y("Array needed (W):Q"),
        tooltip=["Angle", alt.Tooltip("Array needed (W):Q", format=",.0f"), alt.Tooltip("Sun used:Q", format=".2f")]
    ).properties(height=260)
    st.markdown(f"**Array size needed at each angle** = design energy ÷ sun ({basis}) ÷ {eta:g} (§56). Smaller is better.")
    st.altair_chart(bars, width="stretch")


def _roof_direction(out):
    st.markdown("#### 2. Which way the roof faces (§56)")
    st.caption("What this shows: the book's rule of about 1.1 % loss for every 5° the panels turn away from due south "
               "(≈ 20 % facing east or west, ≈ 40 % facing north). Your panels are marked.")
    rows = []
    for bearing in range(0, 361, 5):
        dev = abs(((bearing - 180) + 180) % 360 - 180)
        rows.append({"Compass bearing (°)": bearing, "Output (%)": 100 - 1.1 * dev / 5})
    user_bearing = (180 + out["aspect"]) % 360
    dev = abs(((user_bearing - 180) + 180) % 360 - 180)
    line = alt.Chart(pd.DataFrame(rows)).mark_line(color=USE).encode(
        x=alt.X("Compass bearing (°):Q", scale=alt.Scale(domain=[0, 360]),
                axis=alt.Axis(values=[0, 90, 180, 270, 360], labelExpr="datum.value == 90 ? 'E' : datum.value == 180 ? 'S' : datum.value == 270 ? 'W' : 'N'")),
        y=alt.Y("Output (%):Q", scale=alt.Scale(domain=[50, 100])), tooltip=["Compass bearing (°)", "Output (%)"])
    you = alt.Chart(pd.DataFrame([{"Compass bearing (°)": user_bearing, "Output (%)": 100 - 1.1 * dev / 5,
                                   "label": "Your panels"}])).mark_point(color=BAD, size=150, filled=True).encode(
        x="Compass bearing (°):Q", y="Output (%):Q", tooltip=["label", "Output (%)"])
    st.altair_chart(alt.layer(line, you).properties(height=260), width="stretch")
    st.caption(f"Your panels: bearing {user_bearing:g}° → about {1.1 * dev / 5:.0f} % below a due-south roof "
               "(PVGIS already includes your real direction in the sunshine numbers).")


def _sun_height(out):
    st.markdown("#### 3. How high the sun gets over your site (§67)")
    st.caption("What this shows: the sun's height at noon each month and its path across the sky on the longest day, "
               "the equinox and the shortest day. Low winter sun makes long shadows - check trees and buildings to the south.")
    lat = out["lat"]
    noon = [{"Month": m, "Noon height (°)": noon_altitude(lat, declination(d))} for m, d in zip(MONTHS, MONTH_DAYS)]
    c1 = alt.Chart(pd.DataFrame(noon)).mark_bar(color=SUN).encode(
        x=alt.X("Month:N", sort=MONTHS, title=None), y=alt.Y("Noon height (°):Q", scale=alt.Scale(domain=[0, 90])),
        tooltip=["Month", alt.Tooltip("Noon height (°):Q", format=".1f")]).properties(height=240)
    paths = []
    for label, day in (("21 June (longest day)", SOLSTICE_JUN), ("21 March (equinox)", EQUINOX_MAR),
                       ("21 December (shortest day)", SOLSTICE_DEC)):
        paths += [dict(p, Day=label) for p in sun_path(lat, day)]
    c2 = alt.Chart(pd.DataFrame(paths)).mark_line().encode(
        x=alt.X("Azimuth:Q", title="Direction (° from south: − east, + west)", scale=alt.Scale(domain=[-130, 130])),
        y=alt.Y("Altitude:Q", title="Sun height (°)"), color=alt.Color("Day:N", legend=alt.Legend(orient="top", title=None)),
        tooltip=["Day", alt.Tooltip("Solar time:Q", format=".2f"), alt.Tooltip("Altitude:Q", format=".1f"),
                 alt.Tooltip("Azimuth:Q", format=".0f")]).properties(height=280).interactive()
    a, b = st.columns(2)
    a.altair_chart(c1, width="stretch")
    b.altair_chart(c2, width="stretch")
    st.caption(f"At {abs(lat):.1f}° N: noon sun {noon_altitude(lat, 23.45):.1f}° in June, {noon_altitude(lat, 0):.1f}° at "
               f"the equinox, {noon_altitude(lat, -23.45):.1f}° in December (= 90 − latitude ± 23.45°).")


def _temperature(out):
    st.markdown("#### 4. Heat reduces panel output (§59)")
    st.caption("What this shows: panel output against panel temperature. The 2012 book used 0.5 % per °C; today's "
               "panels lose about 0.29 % per °C. Move the slider to try the book's rule for a hot month.")
    rows = []
    for t in range(5, 86, 5):
        rows.append({"Panel temperature (°C)": t, "Panels": "2012 book (−0.5 %/°C)", "Output (%)": 100 * (1 - 0.005 * (t - 25))})
        rows.append({"Panel temperature (°C)": t, "Panels": "Modern TOPCon (−0.29 %/°C)", "Output (%)": 100 * (1 - 0.0029 * (t - 25))})
    ch = alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
        x="Panel temperature (°C):Q", y=alt.Y("Output (%):Q", scale=alt.Scale(domain=[60, 115])),
        color=alt.Color("Panels:N", scale=alt.Scale(range=[GREY, GOOD]), legend=alt.Legend(orient="top", title=None)),
        tooltip=["Panels", "Panel temperature (°C)", alt.Tooltip("Output (%):Q", format=".1f")]).properties(height=260)
    st.altair_chart(ch, width="stretch")
    temps = site_temperatures(out.get("place") or "")
    air = st.slider("Average air temperature in your hottest month (°C)", 10, 45, 30, key="bk_air",
                    help="Book §59: roof panel ≈ air × 1.4, pole panel ≈ air × 1.2; the loss applies only if the air "
                         "averages 25 °C or more." + (f" Record high near {out.get('place')}: {temps[1]:g} °C." if temps else ""))
    roof, pole = air * 1.4, air * 1.2
    a, b = st.columns(2)
    a.metric("Roof-mounted panel (book rule)", f"{roof:.0f} °C",
             f"{-(roof - 25) * 0.5:.1f} % output" if air >= 25 else "no loss (air below 25 °C)", delta_color="off")
    b.metric("Pole / frame-mounted panel (book rule)", f"{pole:.0f} °C",
             f"{-(pole - 25) * 0.5:.1f} % output" if air >= 25 else "no loss (air below 25 °C)", delta_color="off")
    st.caption(f"Used in your design instead: PVGIS site-specific temperature loss {out['temp_loss_pct']:.1f} % a year. "
               "Leave a 7-10 cm air gap under roof panels to keep them cooler (§59).")


def _shading():
    st.markdown("#### 5. What shade costs (§69, §145)")
    st.caption("What this shows: the share of a day's solar energy lost when the panels are shaded for one hour. Midday "
               "shade is worst. Tick the hours when a tree, tank or building shades your panels.")
    rows = [{"Hour": h, "Season": s, "Loss (%)": v} for h, (w, su) in SHADE_TABLE.items()
            for s, v in (("Winter", w), ("Summer", su))]
    heat = alt.Chart(pd.DataFrame(rows)).mark_rect().encode(
        x=alt.X("Hour:N", sort=list(SHADE_TABLE), title=None), y=alt.Y("Season:N", title=None),
        color=alt.Color("Loss (%):Q", scale=alt.Scale(scheme="orangered"), legend=alt.Legend(title="% lost")),
        tooltip=["Hour", "Season", "Loss (%)"]).properties(height=120)
    text = alt.Chart(pd.DataFrame(rows)).mark_text(fontSize=13).encode(
        x=alt.X("Hour:N", sort=list(SHADE_TABLE)), y="Season:N", text=alt.Text("Loss (%):Q", format=".0f"))
    st.altair_chart(heat + text, width="stretch")
    choices = list(OUTSIDE) + list(SHADE_TABLE)
    shaded = st.multiselect("Hours when your panels are shaded", choices, key="bk_shade")
    w = sum((SHADE_TABLE.get(h) or OUTSIDE[h])[0] for h in shaded)
    s = sum((SHADE_TABLE.get(h) or OUTSIDE[h])[1] for h in shaded)
    a, b = st.columns(2)
    a.metric("Energy lost in winter", f"{min(w, 100)} %")
    b.metric("Energy lost in summer", f"{min(s, 100)} %")
    st.caption("Enter the result as 'Shading loss' in Engineer settings to size the system for it. A small shadow on "
               "one crystalline panel can cut a whole string's output by 50-80 % (§57).")


def _battery_life(out, x):
    st.markdown("#### 6. Battery life vs how deeply it is emptied (§89)")
    st.caption("What this shows: the deeper a battery is emptied each day, the fewer cycles it lasts. The 2012 book's "
               "lead-acid table is compared with today's lithium (LiFePO4) batteries.")
    rows = [{"Depth of discharge (%)": d, "Cycles": c, "Battery": "Lead-acid (book §89)"} for d, c in sorted(LEAD_ACID_CYCLES.items())]
    rows += [{"Depth of discharge (%)": 80, "Cycles": 3000, "Battery": "LiFePO4 - NEPQA-2025 minimum"},
             {"Depth of discharge (%)": 95, "Cycles": 6000, "Battery": "LiFePO4 - typical 2026 datasheet"}]
    df = pd.DataFrame(rows)
    pts = alt.Chart(df).mark_line(point=alt.OverlayMarkDef(size=80)).encode(
        x=alt.X("Depth of discharge (%):Q", scale=alt.Scale(domain=[0, 100])), y="Cycles:Q",
        color=alt.Color("Battery:N", scale=alt.Scale(range=[GREY, BAD, GOOD]), legend=alt.Legend(orient="top", title=None)),
        tooltip=["Battery", "Depth of discharge (%)", "Cycles"])
    dod = x.dod_pct if x.dod_pct is not None else CHEMISTRY[x.chemistry]["dod"]
    rule = alt.Chart(pd.DataFrame([{"d": dod}])).mark_rule(color=USE, strokeDash=[4, 4]).encode(x="d:Q")
    st.altair_chart(alt.layer(pts, rule).properties(height=260), width="stretch")
    st.caption(f"Dashed line: your design depth of discharge ({dod:.0f} %, {x.chemistry}). Lead-acid lasts longest "
               "above 50 % charge; lithium handles deep daily cycling.")


def _cable_table(out, x, o):
    st.markdown("#### 7. Battery / panel cable size (§87)")
    st.caption("What this shows: the book's cable formula (≈ 5 % voltage drop, copper) for your currents at 12, 24 and "
               "48 V. Higher voltage means less current and thinner, cheaper cable - the book suggests going up a "
               "voltage when the cable would be thicker than 6 mm².")
    pa = power_analysis(x.loads, x.phantom_w)
    load_w = pa["critical_w"] if out["mode"] == "hybrid_backup" and pa["critical_w"] else pa["peak_w"]
    length = x.dc_cable_length_m
    rows = []
    for v in (12, 24, 48):
        i = max(load_w, o["installed_w"].value) / v
        mm2 = book_cable_mm2(length, i, v)
        std = next((s for s in IEC_SIZES if s >= mm2), None)
        rows.append({"System voltage": f"{v} V", "Current (A)": round(i, 1),
                     "Book formula (mm²)": round(mm2, 2), "Next standard size (mm²)": std or "> 95 - too high",
                     "Book verdict": "OK (≤ 6 mm²)" if mm2 <= 6 else "Go up a voltage"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(f"Cable length used: {length:g} m one way (change in Engineer settings). Formula: mm² = L × I × 0.04 ÷ "
               "(V ÷ 20). Final cables must also meet current-rating and protection rules.")


def _what_changed():
    st.info("**What changed since the book (2012), and what this app uses instead**\n\n"
            "- Panels: ~250 W, 15-18 % → **550-620 W TOPCon/HJT, ≥ 21 %** (NEPQA-2025).\n"
            "- Batteries: lead-acid only, 50 % depth of discharge → **LiFePO4, 80-95 %, 3,000-6,000+ cycles**.\n"
            "- Controllers: PWM common → **MPPT standard** (≥ 95 % efficient).\n"
            "- Sun data: UK/US NASA tables → **PVGIS for your exact site in Nepal**.\n"
            "- Temperature: air × 1.4 rule → **PVGIS site temperature model**.\n"
            "- Backup: days of autonomy → **Nepal load-shedding hours × backup appliances**.\n"
            "- Money: £/W and 'payback in a few years' → **NEA slab tariff, net billing (Rs 5.94/unit), 2026 Nepal prices**.")
