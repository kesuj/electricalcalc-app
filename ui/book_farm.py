"""'📘 Book method' tab for the Solar farm page.

Makes the method of Neill, Stapleton & Martell, *Solar Farms* (Earthscan) visible with the user's own
Nepal project: the design steps in the book's order with the user's numbers substituted, the book's
charts recreated interactively, and the book's protection/testing tables evaluated for this design.
Book text is paraphrased, not copied; page numbers refer to the printed book.
"""

from __future__ import annotations

import math

import altair as alt
import pandas as pd
import streamlit as st

from ecalc import nepal_data as nd
from ecalc.calc.iv import array_curve, iv_curve, module_at_temperature
from ui.charts import BAD, BATT, GRID, SUN, USE

SOURCE = ("Method: Neill, Stapleton & Martell, *Solar Farms* (Earthscan) - Box 4.1 p.101, pp.102-103, 105-117, "
          "Box 4.2 p.121, Tables 4.4/4.6 pp.118-123, pp.145-148, Table 5.1 p.176, pp.63-67. Data: PVGIS (EC JRC) "
          "for the site, NEA 2024 solar tender rates, NEPQA-2025. Book text paraphrased; numbers are this project's.")
SHADE_HOURS = {"9 am - 3 pm (recommended)": 3, "10 am - 2 pm": 2, "Noon only (book minimum)": 0}
FUSES_A = [10, 12, 15, 16, 20, 25, 30, 32, 35, 40, 50, 63]
DEFAULT_COST_SHARES = {  # indicative split of utility PV build cost - ASSUMPTION, edit to your EPC quote
    "PV modules": 40.0, "Inverters": 8.0, "Mounting structure, cables & protection (BOS)": 20.0,
    "Civil works & installation": 12.0, "Grid connection (substation, line)": 12.0,
    "Development, permits & fees": 8.0,
}
INSULATION_TABLE = [  # Solar Farms Table 5.1 (after IEC 62446): system voltage = Voc_STC × N × 1.25
    {"System voltage": "< 120 V", "Test voltage": "250 V", "Minimum insulation resistance": "0.5 MΩ", "lo": 0, "hi": 120},
    {"System voltage": "120 - 500 V", "Test voltage": "500 V", "Minimum insulation resistance": "1 MΩ", "lo": 120, "hi": 500},
    {"System voltage": "> 500 V", "Test voltage": "1,000 V", "Minimum insulation resistance": "1 MΩ", "lo": 500, "hi": 1e9},
]
DISCONNECTOR_TABLE = [  # Solar Farms Table 4.4 (after AS/NZS 5033)
    ("Equipotential bonding only", "Separated (with transformer)", "Overall: ≥ 0.5 × array maximum voltage"),
    ("Functional earth", "Separated (with transformer)", "Each pole: ≥ array maximum voltage"),
    ("Equipotential bonding only", "Transformerless", "Each pole: ≥ array maximum voltage"),
    ("Functional earth", "Transformerless", "Not permitted"),
]


# ---- pure helpers (tested) ----------------------------------------------------------------------
def voltage_ladder(mod, inv, t_min: float, t_max: float, dc_drop: float = 0.02, min_margin: float = 0.10,
                   max_margin: float = 0.05) -> dict:
    """Module-level voltages at each derating step (Figs 4.15/4.16) and the resulting string limits."""
    g_v = mod.gamma_pmax_pct / 100 * mod.vmp
    g_oc = mod.beta_voc_pct / 100 * mod.voc
    voc_cold = mod.voc + g_oc * (t_min - 25)
    vmp_hot = mod.vmp + g_v * (t_max - 25)
    return {"voc_stc": mod.voc, "voc_cold": voc_cold, "voc_cold_margin": voc_cold * (1 + max_margin),
            "vmp_stc": mod.vmp, "vmp_hot": vmp_hot, "vmp_hot_drop": vmp_hot * (1 - dc_drop),
            "vmp_hot_margin": vmp_hot * (1 - dc_drop) * (1 - min_margin),
            "n_max": math.floor(inv.v_dc_max / (voc_cold * (1 + max_margin))),
            "n_min": math.ceil(inv.v_mppt_min / (vmp_hot * (1 - dc_drop) * (1 - min_margin)))}


def noon_capture(latitude: float, tilt: float) -> dict[str, float]:
    """Relative capture cos(incidence) at solar noon for a south-facing panel (Figs 4.8/4.9).
    Incidence = |sun zenith − tilt|; noon altitude = 90 − φ + δ."""
    out = {}
    for name, dec in (("Equinox (21 Mar / 23 Sep)", 0.0), ("Summer solstice (21 Jun)", 23.45),
                      ("Winter solstice (21 Dec)", -23.45)):
        zenith = abs(latitude) - dec
        out[name] = max(0.0, math.cos(math.radians(zenith - tilt)))
    return out


def insulation_row(system_v: float) -> int:
    return next(i for i, r in enumerate(INSULATION_TABLE) if r["lo"] <= system_v < r["hi"])


def string_voltage_drop(length_m: float, imp: float, n_series: int, vmp: float, area_mm2: float = 4.0,
                        rho: float = 0.0183) -> dict:
    """Box 4.2 p.121: Vdrop = 2·L·I·ρ / A; %drop = Vdrop / (N × Vmp); A_min for a 3 % limit."""
    v_string = n_series * vmp
    vd = 2 * length_m * imp * rho / area_mm2
    return {"v_string": v_string, "vdrop_v": vd, "vdrop_pct": vd / v_string * 100,
            "a_min_3pct": 2 * length_m * imp * rho / (0.03 * v_string)}


def string_fuse(isc: float, module_max_fuse: float | None = None) -> int | None:
    hi = 2.4 * isc if module_max_fuse is None else min(2.4 * isc, module_max_fuse)
    return next((f for f in FUSES_A if 1.5 * isc <= f <= hi), None)


def step_status(sr) -> list[tuple[str, str, bool]]:
    """(step title, result text, ok) for the 5-step flowchart (Fig 4.13)."""
    o = sr.outputs
    n_min, n_max = o["n_min"].value, o["n_max"].value
    feasible = n_min <= n_max
    chosen = o.get("modules_per_string")
    safe = not any("NOT safe" in w for w in sr.warnings)
    steps = [
        ("1 · Minimum modules per string (hot, MPPT min)", f"N_min = {n_min}", True),
        ("2 · Maximum modules per string (cold, max DC V)", f"N_max = {n_max}", feasible),
        ("3 · Strings in parallel (current limit)", f"{o['strings_max'].value} strings", True),
    ]
    if chosen is not None:
        steps.append(("4 · Power check (max DC power)",
                      f"{o['dc_kw_per_inverter'].value:,.0f} kWp, DC/AC {o['dc_ac_ratio'].value:.2f}", True))
        steps.append(("5 · Configure inputs", f"{chosen.value} × {o['strings_used'].value}; {o['input_split'].value}", safe))
    else:
        steps.append(("4 · Power check (max DC power)", "not reached - no safe string length", False))
        steps.append(("5 · Configure inputs", "change module or inverter", False))
    return steps


# ---- rendering ----------------------------------------------------------------------------------
def _fmt(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}"


def book_farm_tab(out: dict, fr, sr, mod, inv, losses: dict, cf, shade_free_hours: float | None = None,
                  capex_rs: float | None = None) -> None:
    """Render the Book-method tab. `out` = st.session_state['farm_out']; fr = farm_design result; sr =
    book_string_design result; mod/inv = Module/Inverter; losses = loss % dict; cf = CashFlowResult."""
    if shade_free_hours is None:
        shade_free_hours = SHADE_HOURS.get(st.session_state.get("f_shade", ""), 3)
    t_min, t_max = sr.inputs["t_cell_min"].value, sr.inputs["t_cell_max"].value
    lat = out["lat"]
    mwp = out["mwp"]
    if capex_rs is None:
        capex_rs = mwp * 1000 * st.session_state.get("f_capex", nd.INSTALLED_UTILITY_RS_PER_KW)
    st.info("This tab follows the book step by step with **your** project's numbers, and redraws the book's "
            "charts and tables for your site. Open any step to see the formula and the working.", icon="📘")

    st.subheader("A · The design, step by step (book order)")
    _steps(out, fr, sr, mod, inv, losses, cf, lat, t_min, t_max, shade_free_hours, capex_rs)
    _errata()

    st.subheader("B · The book's charts, redrawn for your site")
    _iv_window(sr, mod, inv, t_min, t_max)
    _ladder(mod, inv, t_min, t_max, sr)
    _flowchart(sr)
    _tilt_chart(lat, fr.out("tilt_deg"))
    _lifetime(cf, out)
    _cost_stack(capex_rs)

    st.subheader("C · The book's tables, checked for this design")
    _tables(sr, mod, inv)
    st.caption(SOURCE)


def _steps(out, fr, sr, mod, inv, losses, cf, lat, t_min, t_max, shade_h, capex_rs):
    o, so = fr.outputs, sr.outputs
    lad = voltage_ladder(mod, inv, t_min, t_max)
    with st.expander("1 · Site and tilt (Ch.3; Box 4.1 p.101)"):
        st.markdown(f"Site: **{out.get('location') or ''}**, latitude φ = **{lat:.2f}°**.  \n"
                    f"Sun height at noon on the equinox: 90° − φ = **{90 - abs(lat):.1f}°**.  \n"
                    f"Best yearly tilt = 180° − 90° − altitude = φ = **{abs(lat):.1f}°** (minimum 10° so rain cleans "
                    f"the panels). Tilt used in this design: **{o['tilt_deg'].value:.1f}°**, facing south.")
    with st.expander("2 · Row spacing (pp.102-103, Fig 4.10)"):
        l = fr.inputs["table_slant_m"].value
        b = math.radians(o["tilt_deg"].value)
        window = ("noon only" if not shade_h else f"{12 - shade_h:g}:00 to {12 + shade_h:g}:00 solar time")
        st.markdown(f"Shade-free window on 21 December: **{window}**.  \n"
                    f"Table length l = **{l:g} m**, tilt β = **{o['tilt_deg'].value:.1f}°**.  \n"
                    f"Height h = l·sin β = {l:g} × {math.sin(b):.3f} = **{l * math.sin(b):.2f} m**; "
                    f"footprint a = l·cos β = **{l * math.cos(b):.2f} m**.  \n"
                    f"Row pitch d = a + h·cos λ / tan α = **{o['pitch_m'].value:.2f} m** "
                    f"(gap between rows **{o['gap_m'].value:.2f} m**).  \n"
                    f"Ground coverage ratio = l / d = **{o['gcr'].value:.2f}** → land **{o['land_ha'].value:,.1f} ha** "
                    f"(**{o['land_bigha'].value:,.0f} bigha / {o['land_ropani'].value:,.0f} ropani**).")
    with st.expander("3 · Temperature-corrected module voltages (pp.106-107)"):
        st.markdown(
            f"V(T) = V_STC + γ·(T − 25), γ in V/°C = (%/°C ÷ 100) × V_STC.  \n"
            f"Voc at the record low {t_min:g} °C: {mod.voc:g} + ({mod.beta_voc_pct:g}% × {mod.voc:g}) × ({t_min:g} − 25) "
            f"= **{lad['voc_cold']:.2f} V**.  \n"
            f"Vmp at the hottest cell {t_max:g} °C: {mod.vmp:g} + ({mod.gamma_pmax_pct:g}% × {mod.vmp:g}) × ({t_max:g} − 25) "
            f"= **{lad['vmp_hot']:.2f} V** (the book applies the Pmax coefficient to Vmp).")
    with st.expander("4 · The 5-step array / inverter matching (pp.105-116)"):
        st.markdown(
            f"**Step 1 - minimum string length.** Vmp(hot) × (1 − 2 % DC drop) × (1 − 10 % margin) = "
            f"{lad['vmp_hot']:.2f} × 0.98 × 0.9 = **{lad['vmp_hot_margin']:.2f} V**; "
            f"N_min = ceil({inv.v_mppt_min:g} ÷ {lad['vmp_hot_margin']:.2f}) = **{so['n_min'].value}** "
            f"(no margin: {so['n_min_raw'].value}).  \n"
            f"**Step 2 - maximum string length.** Voc(cold) × 1.05 = {lad['voc_cold']:.2f} × 1.05 = "
            f"**{lad['voc_cold_margin']:.2f} V**; N_max = floor({inv.v_dc_max:g} ÷ {lad['voc_cold_margin']:.2f}) = "
            f"**{so['n_max'].value}** (no margin: {so['n_max_raw'].value}; MPPT-upper check: {so['n_max_mppt'].value}).  \n"
            f"**Step 3 - strings in parallel.** floor({inv.i_dc_max:g} A ÷ {mod.isc:g} A) = **{so['strings_max'].value}**.  \n")
        if "modules_per_string" in so:
            st.markdown(
                f"**Step 4 - power check.** {so['modules_per_string'].value} modules × {so['strings_used'].value} strings × "
                f"{mod.wp:g} W = **{so['dc_kw_per_inverter'].value:,.1f} kWp** ≤ {inv.max_dc_kw:g} kW max DC; "
                f"DC/AC = {so['dc_kw_per_inverter'].value:,.1f} ÷ {inv.ac_kva:g} = **{so['dc_ac_ratio'].value:.2f}**.  \n"
                f"**Step 5 - configuration.** Strings shared over {inv.dc_inputs} inputs: **{so['input_split'].value}**. "
                f"Cold-morning string Voc = {so['modules_per_string'].value} × {lad['voc_cold']:.2f} = "
                f"**{so['string_voc_cold_v'].value:,.0f} V** (limit {inv.v_dc_max:g} V).")
        else:
            st.error(f"Steps 4-5 cannot be completed: N_min {so['n_min'].value} > N_max {so['n_max'].value}. "
                     f"{' '.join(w for w in sr.warnings if 'NOT safe' in w)}")
    with st.expander("5 · Performance ratio (pp.145-148)"):
        terms = " × ".join(f"(1 − {v:g}%)" for v in losses.values())
        st.markdown(f"PR = Π (1 − loss) = {terms} = **{o['pr'].value:.3f}** (the book prints Σ; it means the product).  \n"
                    "A well-performing plant reaches about 0.8 (book p.81).")
    with st.expander("6 · Energy and capacity factor (p.81, p.148)"):
        psh = fr.inputs["annual_psh"].value
        st.markdown(f"E = MWp × sun hours × 365 × PR = {mwp_s(out)} × {psh:.2f} × 365 × {o['pr'].value:.3f} = "
                    f"**{o['annual_mwh'].value:,.0f} MWh/yr**.  \n"
                    f"Capacity factor (DC) = E ÷ (MWp × 8760) = **{o['cf_dc_pct'].value:.1f} %**; specific yield "
                    f"**{o['specific_yield'].value:,.0f} kWh/kWp**.")
    with st.expander("7 · Transformer (pp.116-117)"):
        st.markdown(f"Rate each step-up transformer at least at its inverters' AC output. Total AC = "
                    f"**{o['ac_mw'].value:,.2f} MW** → transformer(s) ≥ **{o['transformer_mva'].value:,.2f} MVA**. "
                    "Oversizing costs efficiency; undersizing caps output (book).")
    with st.expander("8 · Voltage drop on one string cable (Box 4.2 p.121)"):
        a, b = st.columns(2)
        length = a.number_input("String cable length, one way (m)", 1.0, 2000.0, 100.0, 10.0, key="bf_len")
        area = b.selectbox("Cable size (mm²)", [2.5, 4.0, 6.0, 10.0], index=1, key="bf_area")
        n = so["modules_per_string"].value if "modules_per_string" in so else so["n_min_raw"].value
        vd = string_voltage_drop(length, mod.imp, n, mod.vmp, area)
        ok = vd["vdrop_pct"] < 3
        st.markdown(f"Vdrop = 2·L·I·ρ / A = 2 × {length:g} × {mod.imp:g} × 0.0183 ÷ {area:g} = **{vd['vdrop_v']:.2f} V**; "
                    f"string voltage {n} × {mod.vmp:g} = {vd['v_string']:,.0f} V → **{vd['vdrop_pct']:.2f} %** "
                    f"({'within' if ok else 'above'} the book's 3 % DC limit). Smallest area for 3 %: "
                    f"**{vd['a_min_3pct']:.2f} mm²**.")
    with st.expander("9 · Levelised cost of electricity (pp.63-67)"):
        st.markdown(f"LCOE = Σ (investment + O&M)ₜ/(1+r)ᵗ ÷ Σ energyₜ/(1+r)ᵗ = **Rs {cf.lcoe:.2f}/kWh** for a build cost of "
                    f"Rs {capex_rs / 1e7:,.1f} crore. NEA's 2024 tender paid Rs {nd.UTILITY_PPA_RANGE[0]}-"
                    f"{nd.UTILITY_PPA_RANGE[1]}/kWh, so the plant is viable when LCOE is below the sale price. "
                    f"IRR **{cf.irr_pct:.1f} %**." if cf.irr_pct is not None else
                    f"LCOE = **Rs {cf.lcoe:.2f}/kWh**; the project does not pay back its cost at these inputs.")


def mwp_s(out: dict) -> str:
    return f"{out['mwp']:g}"


def _errata():
    with st.expander("Book errata found and corrected in this app"):
        st.markdown(
            "- 100 MWp example (pp.113-116): Voc at 5 °C printed **40.69 V** - correct value **41.95 V**.\n"
            "- N_max printed **23.87** - recomputed 23.41, and **22.70** with the corrected Voc → 22 modules.\n"
            "- With the corrected voltage the book's chosen **24-module string reaches ≈ 1,007 V** on a 5 °C morning, "
            "above the 1,000 V inverter limit: no safe string length exists for that pair.\n"
            "- Minimum-voltage step: printed 26.07 V - correct 25.43 V (also labelled 75 °C instead of 70 °C).\n"
            "- PR formula printed as a sum (Σ) - it is a product (Π) of loss factors.\n"
            "- N_max inequality printed reversed; resistivity unit misprinted (Ω·mm²/m).")


def _iv_window(sr, mod, inv, t_min, t_max):
    so = sr.outputs
    n_s = so["modules_per_string"].value if "modules_per_string" in so else so["n_min_raw"].value
    n_p = so["strings_used"].value if "strings_used" in so else so["strings_max"].value
    rows = []
    for label, t in ((f"Array at {t_min:g} °C (cold)", t_min), (f"Array at {t_max:g} °C (hot)", t_max)):
        m = module_at_temperature(mod.voc, mod.vmp, mod.isc, mod.imp, mod.beta_voc_pct, mod.gamma_pmax_pct, t,
                                  getattr(mod, "isc_coef_pct", 0.0))
        for v, i in array_curve(iv_curve(m["isc"], m["voc"], m["imp"], m["vmp"]), n_s, n_p):
            rows.append({"V": v, "I": i, "Curve": label})
    df = pd.DataFrame(rows)
    v_hi = max(df["V"].max(), inv.v_dc_max) * 1.05
    i_hi = max(df["I"].max(), inv.i_dc_max) * 1.15
    hyper = pd.DataFrame([{"V": v, "I": inv.max_dc_kw * 1000 / v} for v in
                          [inv.v_mppt_min + k * (v_hi - inv.v_mppt_min) / 60 for k in range(61)]
                          if inv.max_dc_kw * 1000 / v <= i_hi])
    curves = alt.Chart(df).mark_line(strokeWidth=3).encode(
        x=alt.X("V:Q", title="Array voltage (V)", scale=alt.Scale(domain=[0, v_hi])),
        y=alt.Y("I:Q", title="Array current (A)", scale=alt.Scale(domain=[0, i_hi])),
        color=alt.Color("Curve:N", scale=alt.Scale(range=[USE, SUN]), legend=alt.Legend(orient="top", title=None)),
        tooltip=["Curve", alt.Tooltip("V:Q", format=",.0f"), alt.Tooltip("I:Q", format=",.1f")])
    power = alt.Chart(hyper).mark_line(color="#7b4fa0", strokeDash=[6, 3]).encode(
        x="V:Q", y="I:Q", tooltip=[alt.Tooltip("V:Q", format=",.0f"), alt.Tooltip("I:Q", format=",.1f")])
    lims = pd.DataFrame([{"v": inv.v_mppt_min, "what": "MPPT min"}, {"v": inv.v_mppt_max, "what": "MPPT max"}])
    mppt = alt.Chart(lims).mark_rule(color=GRID, strokeDash=[4, 4]).encode(x="v:Q", tooltip=["what", "v"])
    vmax = alt.Chart(pd.DataFrame([{"v": inv.v_dc_max, "what": "Max DC voltage"}])).mark_rule(
        color=BAD, strokeWidth=2).encode(x="v:Q", tooltip=["what", "v"])
    imax = alt.Chart(pd.DataFrame([{"i": inv.i_dc_max, "what": "Max DC current"}])).mark_rule(
        color=BAD, strokeWidth=2).encode(y="i:Q", tooltip=["what", "i"])
    st.markdown("**1 · Inverter operating window (Figs 4.14, 4.18, 4.19)** - your array's I-V curves on a cold "
                "morning and a hot afternoon must stay left of the red voltage line and below the red current line; "
                "the maximum-power point should fall between the grey MPPT lines; the purple curve is the inverter's "
                "power limit (above it the inverter clips).")
    st.altair_chart(alt.layer(mppt, vmax, imax, power, curves).properties(height=380).interactive(), width="stretch")
    voc_cold = df[df["Curve"].str.contains("cold")]["V"].max()
    if voc_cold > inv.v_dc_max:
        st.error(f"Unsafe: the cold-morning open-circuit voltage ({voc_cold:,.0f} V) crosses the inverter's "
                 f"{inv.v_dc_max:g} V limit.")
    else:
        st.caption(f"{n_s} modules × {n_p} strings. Cold open-circuit voltage {voc_cold:,.0f} V "
                   f"< {inv.v_dc_max:g} V limit ✓")


def _ladder(mod, inv, t_min, t_max, sr):
    lad = voltage_ladder(mod, inv, t_min, t_max)
    rows = [
        {"Step": "Voc at 25 °C (datasheet)", "Volts per module": lad["voc_stc"], "Path": "Maximum voltage (Step 2)"},
        {"Step": f"Voc at {t_min:g} °C", "Volts per module": lad["voc_cold"], "Path": "Maximum voltage (Step 2)"},
        {"Step": "+5 % safety margin", "Volts per module": lad["voc_cold_margin"], "Path": "Maximum voltage (Step 2)"},
        {"Step": "Vmp at 25 °C (datasheet)", "Volts per module": lad["vmp_stc"], "Path": "Minimum voltage (Step 1)"},
        {"Step": f"Vmp at {t_max:g} °C", "Volts per module": lad["vmp_hot"], "Path": "Minimum voltage (Step 1)"},
        {"Step": "−2 % cable drop", "Volts per module": lad["vmp_hot_drop"], "Path": "Minimum voltage (Step 1)"},
        {"Step": "−10 % safety margin", "Volts per module": lad["vmp_hot_margin"], "Path": "Minimum voltage (Step 1)"},
    ]
    df = pd.DataFrame(rows)
    order = list(df["Step"])
    st.markdown("**2 · Module voltage ladder (Figs 4.15, 4.16)** - how temperature, cable drop and safety margins move "
                f"the module voltage. Result: between **{lad['n_min']}** and **{lad['n_max']}** modules per string.")
    st.altair_chart(alt.Chart(df).mark_bar().encode(
        x=alt.X("Volts per module:Q"), y=alt.Y("Step:N", sort=order, title=None),
        color=alt.Color("Path:N", scale=alt.Scale(range=[BAD, BATT]), legend=alt.Legend(orient="top", title=None)),
        tooltip=["Step", alt.Tooltip("Volts per module:Q", format=".2f")]).properties(height=260), width="stretch")


def _flowchart(sr):
    steps = step_status(sr)
    nodes = []
    for k, (title, result, ok) in enumerate(steps):
        colour = "#d9f2e3" if ok else "#f8d7da"
        mark = "✓" if ok else "✗"
        nodes.append(f'  s{k} [label="{mark} {title}\\n{result}", style=filled, fillcolor="{colour}", shape=box];')
    edges = "\n".join(f"  s{k} -> s{k + 1};" for k in range(len(steps) - 1))
    dot = "digraph G {\n  rankdir=TB; node [fontname=Helvetica, fontsize=11];\n" + "\n".join(nodes) + "\n" + edges + "\n}"
    st.markdown("**3 · The 5-step method (Fig 4.13)** - green = satisfied for this design, red = needs a change.")
    st.graphviz_chart(dot)


def _tilt_chart(lat, tilt_used):
    st.markdown("**4 · Tilt and sun angle (Figs 4.8, 4.9, Box 4.1)** - share of noon sunlight a panel catches "
                "(cos of the angle between the sun and the panel) for each tilt; best yearly tilt ≈ latitude.")
    tilt = st.slider("Try a tilt (°)", 0, 60, int(round(tilt_used)), 1, key="bf_tilt")
    rows = []
    for b in range(0, 61):
        for name, val in noon_capture(lat, b).items():
            rows.append({"Tilt (°)": b, "Day": name, "Captured at noon": val})
    df = pd.DataFrame(rows)
    lines = alt.Chart(df).mark_line().encode(
        x="Tilt (°):Q", y=alt.Y("Captured at noon:Q", scale=alt.Scale(domain=[0.4, 1.0]), axis=alt.Axis(format="%")),
        color=alt.Color("Day:N", scale=alt.Scale(range=[USE, SUN, GRID]), legend=alt.Legend(orient="top", title=None)),
        tooltip=["Day", "Tilt (°)", alt.Tooltip("Captured at noon:Q", format=".1%")])
    marks = pd.DataFrame([{"x": abs(lat), "what": f"Latitude {abs(lat):.1f}° (book: best yearly)"},
                          {"x": tilt, "what": f"Your choice {tilt}°"}])
    rules = alt.Chart(marks).mark_rule(strokeDash=[5, 3]).encode(x="x:Q", color=alt.Color("what:N", legend=None),
                                                                  tooltip=["what"])
    st.altair_chart(alt.layer(lines, rules).properties(height=300), width="stretch")
    cap = noon_capture(lat, tilt)
    st.caption(" · ".join(f"{k}: {v:.0%}" for k, v in cap.items()))


def _lifetime(cf, out):
    rows = [{"Year": r["Year"], "Energy (MWh)": r["Energy (kWh)"] / 1000} for r in cf.rows]
    if not rows:
        return
    e1 = rows[0]["Energy (MWh)"]
    warranty = pd.DataFrame([{"Year": 1, "Warranty floor (MWh)": e1}, {"Year": 10, "Warranty floor (MWh)": e1 * 0.90},
                             {"Year": 25, "Warranty floor (MWh)": e1 * 0.80}])
    df = pd.DataFrame(rows)
    st.markdown("**5 · Energy over the plant's life (p.148)** - panels slowly age; the book's typical power warranty is "
                "90 % after 10 years and 80 % after 25 years (red line).")
    line = alt.Chart(df).mark_line(point=True, color=SUN).encode(
        x="Year:Q", y=alt.Y("Energy (MWh):Q", title="Energy per year (MWh)"),
        tooltip=["Year", alt.Tooltip("Energy (MWh):Q", format=",.0f")])
    warr = alt.Chart(warranty).mark_line(color=BAD, strokeDash=[5, 3]).encode(
        x="Year:Q", y="Warranty floor (MWh):Q", tooltip=["Year", alt.Tooltip("Warranty floor (MWh):Q", format=",.0f")])
    st.altair_chart(alt.layer(line, warr).properties(height=280).interactive(), width="stretch")
    st.caption(f"Total over {len(rows)} years: {sum(r['Energy (MWh)'] for r in rows):,.0f} MWh.")


def _cost_stack(capex_rs):
    st.markdown("**6 · Where the build money goes (Fig 3.18 style)** - shares are **indicative assumptions**; "
                "replace them with your EPC contractor's breakdown.")
    df = st.data_editor(pd.DataFrame({"Item": list(DEFAULT_COST_SHARES), "Share (%)": list(DEFAULT_COST_SHARES.values())}),
                        hide_index=True, width="stretch", key="bf_costs", disabled=["Item"],
                        column_config={"Share (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0)})
    total = float(df["Share (%)"].fillna(0).sum()) or 1.0
    df["Rs crore"] = df["Share (%)"].fillna(0) / total * capex_rs / 1e7
    if abs(total - 100) > 0.5:
        st.caption(f"Shares add up to {total:.0f} %; amounts are scaled to 100 %.")
    st.altair_chart(alt.Chart(df).mark_bar().encode(
        x=alt.X("Rs crore:Q", stack="zero", title="Build cost (Rs crore)"),
        color=alt.Color("Item:N", legend=alt.Legend(orient="bottom", title=None, columns=2)),
        tooltip=["Item", alt.Tooltip("Rs crore:Q", format=",.2f"), alt.Tooltip("Share (%):Q", format=".0f")],
    ).properties(height=90), width="stretch")


def _tables(sr, mod, inv):
    so = sr.outputs
    n_s = so["modules_per_string"].value if "modules_per_string" in so else so["n_min_raw"].value
    n_p = so["strings_used"].value if "strings_used" in so else so["strings_max"].value
    # Table 5.1 - insulation test
    sys_v = mod.voc * n_s * 1.25
    row = insulation_row(sys_v)
    ins = pd.DataFrame([{k: v for k, v in r.items() if k not in ("lo", "hi")} for r in INSULATION_TABLE])
    ins["This plant"] = ["◀ applies" if i == row else "" for i in range(len(ins))]
    st.markdown(f"**Insulation resistance test at commissioning (Table 5.1, after IEC 62446)** - system voltage = "
                f"Voc × N × 1.25 = {mod.voc:g} × {n_s} × 1.25 = **{sys_v:,.0f} V**.")
    st.dataframe(ins, hide_index=True, width="stretch")
    # Table 4.4 - DC switch-disconnector
    a, b = st.columns(2)
    earthing = a.selectbox("Array earthing", ["Equipotential bonding only", "Functional earth"], key="bf_earth")
    inv_type = b.selectbox("Inverter type", ["Transformerless", "Separated (with transformer)"], key="bf_invtype")
    v_array = so["string_voc_cold_v"].value
    dis = pd.DataFrame(DISCONNECTOR_TABLE, columns=["Earthing", "Inverter", "Disconnector voltage rating"])
    dis["This plant"] = ["◀ applies" if (e == earthing and i == inv_type) else "" for e, i, _ in DISCONNECTOR_TABLE]
    rule = next(r for e, i, r in DISCONNECTOR_TABLE if e == earthing and i == inv_type)
    st.markdown(f"**DC switch-disconnector rating (Table 4.4, after AS/NZS 5033)** - array maximum (cold) voltage "
                f"**{v_array:,.0f} V** → {rule.replace('array maximum voltage', f'{v_array:,.0f} V')}.")
    st.dataframe(dis, hide_index=True, width="stretch")
    # Table 4.6 - cable current-carrying capacity
    fuse = string_fuse(mod.isc)
    per_input = math.ceil(n_p / max(inv.dc_inputs, 1))
    ccc = pd.DataFrame([
        {"Cable": "String cable (with string fuse)", "Rule": "CCC ≥ fuse trip rating",
         "Required CCC (A)": fuse if fuse else "check datasheet"},
        {"Cable": "String cable (no fuse)", "Rule": "CCC ≥ I_n + 1.25 × Isc × (strings − 1)",
         "Required CCC (A)": round((fuse or 0) + 1.25 * mod.isc * (per_input - 1), 1)},
        {"Cable": f"Input / sub-array cable ({per_input} strings)", "Rule": "CCC ≥ 1.25 × Isc of the strings",
         "Required CCC (A)": round(1.25 * mod.isc * per_input, 1)},
        {"Cable": f"Array cable ({n_p} strings)", "Rule": "CCC ≥ 1.25 × Isc of the array",
         "Required CCC (A)": round(1.25 * mod.isc * n_p, 1)},
    ])
    st.markdown(f"**Cable current-carrying capacity (Table 4.6)** - Isc = {mod.isc:g} A; string fuse by the IEC 62548 "
                f"window 1.5-2.4 × Isc → **{fuse} A** (not from the book). Derate CCC for installation method, grouping "
                "and temperature.")
    st.dataframe(ccc, hide_index=True, width="stretch")
