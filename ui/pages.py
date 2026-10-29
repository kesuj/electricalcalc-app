"""All Streamlit page functions (registered in app.py via st.navigation)."""

from __future__ import annotations

import os

import streamlit as st

from ecalc import ai, config, documents, reports
from ecalc.calc import ValidationError, cable as cab, fundamentals as fun
from ecalc.calc.solar import SolarInputs, SolarResource, size_pv_system
from ecalc.demo import load_demo_project
from ecalc.solar_data import PRESET_LOCATIONS, PVGISError, fetch_pvgis
from ui.common import get_store, page_header, render_result, save_and_export, show_error

CURRENCIES = ["NPR", "USD", "AUD", "GBP", "INR", "EUR"]


# ---- Home ---------------------------------------------------------------------------------
def home():
    store = get_store()
    page_header(f"⚡ {config.APP_NAME}", config.APP_TAGLINE)
    st.markdown("Preliminary **solar PV** and **electrical** calculations with transparent methods, "
                "draft engineering reports, and an optional AI assistant that explains results - "
                "it never invents the numbers.")
    projects = store.list_projects()
    calcs = store.list_calculations()
    c1, c2, c3 = st.columns(3)
    c1.metric("Projects", len(projects))
    c2.metric("Saved calculations", len(calcs))
    c3.metric("AI spend this month", f"${store.month_spend_usd():.4f}")

    st.subheader("Projects")
    with st.form("new_project", clear_on_submit=True):
        a, b, c = st.columns(3)
        name = a.text_input("Project name *")
        client = b.text_input("Client")
        loc = c.text_input("Location")
        notes = st.text_area("Scope / notes", height=70)
        if st.form_submit_button("Create project", type="primary"):
            try:
                store.create_project(name, client, loc, notes)
                st.success(f"Project '{name}' created.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    if st.button("Load demonstration project (clearly labelled sample data)"):
        pid = load_demo_project(store)
        st.success(f"Demo project #{pid} created. Open Reports & history to export its sample report.")
        st.rerun()
    if projects:
        st.dataframe([{"ID": p["id"], "Project": p["name"] + (" [DEMO]" if p["is_demo"] else ""),
                       "Client": p["client"], "Location": p["location"], "Calculations": p["n_calcs"],
                       "Updated (UTC)": p["updated"]} for p in projects], hide_index=True, use_container_width=True)
    else:
        st.info("No projects yet - create one above or load the demonstration project.")


# ---- Solar ----------------------------------------------------------------------------------
def solar():
    page_header("☀️ Solar PV preliminary sizing",
                "Grid-tied or hybrid (battery) systems. Solar data from PVGIS or your own peak-sun-hours value.")
    store = get_store()
    st.subheader("1. Location and solar resource")
    src = st.radio("Solar resource source", ["PVGIS (online, free)", "Enter peak sun hours manually"], horizontal=True)
    loss = st.number_input("System losses (%)", 0.0, 50.0, 14.0, 1.0,
                           help="Wiring, inverter, soiling, mismatch, etc. PVGIS's own default is 14%.")
    if src.startswith("PVGIS"):
        preset = st.selectbox("Location", ["Custom coordinates"] + list(PRESET_LOCATIONS), index=1)
        lat0, lon0 = PRESET_LOCATIONS.get(preset, (27.7172, 85.3240))
        a, b, c, d = st.columns(4)
        lat = a.number_input("Latitude", -90.0, 90.0, lat0, format="%.4f")
        lon = b.number_input("Longitude", -180.0, 180.0, lon0, format="%.4f")
        tilt = c.number_input("Tilt (°)", 0.0, 90.0, float(round(abs(lat0))), 1.0)
        aspect = d.number_input("Azimuth (° from south, PVGIS)", -180.0, 180.0, 0.0 if lat >= 0 else 180.0, 5.0,
                                help="PVGIS convention: 0 = south-facing, 90 = west, -90 = east, 180 = north.")
        location_label = preset if preset != "Custom coordinates" else f"{lat:.4f}, {lon:.4f}"
        if st.button("Get solar data from PVGIS"):
            try:
                with st.spinner("Querying PVGIS..."):
                    st.session_state["solar_res"] = fetch_pvgis(lat, lon, tilt, aspect, loss, cache=store)
                    st.session_state["solar_loc"] = location_label
            except (PVGISError, ValidationError) as e:
                st.error(str(e))
        res: SolarResource | None = st.session_state.get("solar_res")
        if res:
            st.success(f"Specific yield {res.annual_kwh_per_kwp:,.1f} kWh/kWp/yr - {res.source}")
    else:
        psh = st.number_input("Average peak sun hours on the array plane (kWh/m²/day)", 0.5, 9.0, 5.0, 0.1,
                              help="Use a value from a reliable dataset for your site; do not guess.")
        location_label = st.text_input("Location label", "")
        try:
            res = SolarResource.from_peak_sun_hours(psh, loss)
        except ValidationError as e:
            res = None; show_error(e)

    st.subheader("2. Consumption, equipment and economics")
    a, b, c = st.columns(3)
    basis = a.radio("Consumption basis", ["Daily (kWh/day)", "Monthly (kWh/month)"])
    cons = a.number_input("Consumption", 0.1, 1e6, 12.0 if basis.startswith("Daily") else 360.0)
    daily = cons if basis.startswith("Daily") else cons * 12 / 365
    system = b.radio("System type", ["Grid-tied", "Hybrid with battery"])
    offset = b.number_input("Target share of consumption (%)", 1.0, 200.0, 100.0, 5.0)
    area = b.number_input("Available module area (m², 0 = not limited)", 0.0, 1e5, 0.0)
    wp = c.number_input("Panel rating (Wp)", 50.0, 1000.0, 550.0, 5.0, help="From the chosen module datasheet.")
    parea = c.number_input("Panel area (m²)", 0.3, 4.0, 2.58, 0.01, help="Length × width from the datasheet.")
    ratio = c.number_input("DC/AC ratio", 0.8, 1.6, 1.2, 0.05)
    a, b, c, d = st.columns(4)
    cur = a.selectbox("Currency", CURRENCIES)
    tariff = b.number_input(f"Tariff ({cur}/kWh, 0 = skip)", 0.0, 1e4, 0.0)
    export = c.number_input(f"Export rate ({cur}/kWh)", 0.0, 1e4, 0.0)
    cost_kwp = d.number_input(f"Installed cost ({cur}/kWp, 0 = skip)", 0.0, 1e8, 0.0)
    bat = {}
    if system.startswith("Hybrid"):
        st.markdown("**Battery and backup**")
        a, b, c, d, e = st.columns(5)
        bat = dict(backup_kwh_per_day=a.number_input("Backup energy (kWh/day)", 0.1, 1e4, 5.0),
                   autonomy_days=b.number_input("Autonomy (days)", 0.1, 7.0, 1.0, 0.5),
                   battery_dod_pct=c.number_input("Depth of discharge (%)", 10.0, 100.0, 80.0),
                   battery_voltage_v=d.number_input("Bank voltage (V)", 12.0, 1000.0, 48.0),
                   peak_load_kw=e.number_input("Peak load (kW, 0 = unknown)", 0.0, 1e4, 0.0) or None)
        bcost = st.number_input(f"Battery cost ({cur}/kWh nominal, 0 = skip)", 0.0, 1e7, 0.0)
        bat["battery_cost_per_kwh"] = bcost or None

    if st.button("Calculate", type="primary", disabled=res is None):
        try:
            r = size_pv_system(SolarInputs(
                daily_consumption_kwh=daily, panel_wp=wp, panel_area_m2=parea, resource=res,
                system_type="grid_tied" if system == "Grid-tied" else "hybrid_battery", target_offset_pct=offset,
                available_area_m2=area or None, dc_ac_ratio=ratio, tariff_per_kwh=tariff or None,
                export_rate_per_kwh=export, currency=cur, cost_per_kwp=cost_kwp or None,
                location_label=st.session_state.get("solar_loc", location_label) if src.startswith("PVGIS") else location_label,
                **bat))
            st.session_state["solar_result"] = r
        except ValidationError as e:
            show_error(e)
    if res is None and src.startswith("PVGIS"):
        st.caption("Fetch PVGIS data first (or switch to manual peak sun hours).")
    r = st.session_state.get("solar_result")
    if r:
        st.subheader("3. Results")
        keys = ["pv_kwp", "panel_count", "annual_generation_kwh", "inverter_ac_kw"]
        render_result(r, keys)
        save_and_export(r, "solar", "solar")


# ---- Electrical tools --------------------------------------------------------------------
def electrical():
    page_header("🔌 Electrical calculation tools", "Fundamentals with stated equations, units and assumptions.")
    tabs = st.tabs(["AC power", "Load current", "PF correction", "Ohm's law", "Energy & cost", "Unit conversions"])
    with tabs[0]:
        a, b, c, d = st.columns(4)
        ph = a.selectbox("Phases", [3, 1], key="acp_ph")
        v = b.number_input("Voltage (V, line-line for 3-phase)", 1.0, 1e6, 400.0 if ph == 3 else 230.0, key="acp_v")
        i = c.number_input("Line current (A)", 0.001, 1e6, 10.0, key="acp_i")
        pf = d.number_input("Power factor", 0.01, 1.0, 0.85, 0.01, key="acp_pf")
        lag = st.radio("PF type", ["Lagging (inductive)", "Leading (capacitive)"], horizontal=True, key="acp_l")
        _run(lambda: fun.ac_power(v, i, pf, ph, lag.startswith("Lag")), "ac_power", "acp")
    with tabs[1]:
        a, b, c, d = st.columns(4)
        ph = a.selectbox("Phases", [3, 1], key="lc_ph")
        p = b.number_input("Real power (kW)", 0.001, 1e6, 15.0, key="lc_p")
        v = c.number_input("Voltage (V)", 1.0, 1e6, 400.0 if ph == 3 else 230.0, key="lc_v")
        pf = d.number_input("Power factor", 0.01, 1.0, 0.85, 0.01, key="lc_pf")
        _run(lambda: fun.current_from_power(p, v, pf, ph), "load_current", "lc")
    with tabs[2]:
        a, b, c = st.columns(3)
        p = a.number_input("Real power (kW)", 0.001, 1e6, 100.0, key="pf_p")
        pf1 = b.number_input("Existing PF", 0.01, 0.999, 0.70, 0.01, key="pf_1")
        pf2 = c.number_input("Target PF", 0.02, 1.0, 0.95, 0.01, key="pf_2")
        a, b, c = st.columns(3)
        v = a.number_input("Line voltage for capacitance (V, 0 = skip)", 0.0, 1e6, 400.0, key="pf_v")
        f = b.selectbox("Frequency (Hz)", [50.0, 60.0], key="pf_f")
        conn = c.selectbox("Capacitor connection", ["delta", "star"], key="pf_c")
        _run(lambda: fun.pf_correction(p, pf1, pf2, v or None, f, conn), "pf_correction", "pfc")
    with tabs[3]:
        st.caption("Enter exactly two values; leave the unknown at 0.")
        a, b, c = st.columns(3)
        v = a.number_input("Voltage (V)", 0.0, 1e7, 230.0, key="o_v")
        i = b.number_input("Current (A)", 0.0, 1e7, 0.0, key="o_i")
        rr = c.number_input("Resistance (Ω)", 0.0, 1e9, 46.0, key="o_r")
        _run(lambda: fun.ohms_law(v or None, i or None, rr or None), "ohms_law", "ohm")
    with tabs[4]:
        a, b, c, d = st.columns(4)
        p = a.number_input("Average power (kW)", 0.001, 1e6, 2.0, key="e_p")
        h = b.number_input("Hours per day", 0.0, 24.0, 8.0, key="e_h")
        days = c.number_input("Days", 1.0, 3660.0, 30.0, key="e_d")
        t = d.number_input("Tariff per kWh (0 = skip)", 0.0, 1e4, 0.0, key="e_t")
        cur = st.selectbox("Currency", CURRENCIES, key="e_c")
        _run(lambda: fun.energy_cost(p, h, days, t or None, cur), "energy", "en")
    with tabs[5]:
        a, b = st.columns(2)
        with a:
            hp = st.number_input("Horsepower (hp)", 0.0, 1e6, 10.0)
            st.write(f"= **{hp * fun.HP_TO_KW:,.3f} kW** (imperial hp)  ·  {hp * fun.METRIC_HP_TO_KW:,.3f} kW (metric hp)")
            kwh = st.number_input("Energy (kWh)", 0.0, 1e9, 1.0)
            st.write(f"= **{kwh * fun.KWH_TO_MJ:,.3f} MJ**")
        with b:
            awg = st.number_input("AWG (use -1 for 2/0, -2 for 3/0, -3 for 4/0)", -3, 40, 10)
            try:
                st.write(f"= **{fun.awg_to_mm2(int(awg)):.3f} mm²** (solid conductor, ASTM B258 diameter)")
            except ValidationError as e:
                show_error(e)
            kc = st.number_input("kcmil", 1.0, 5000.0, 250.0)
            st.write(f"= **{fun.kcmil_to_mm2(kc):.2f} mm²**")


def _run(fn, kind, key):
    try:
        r = fn()
    except ValidationError as e:
        show_error(e)
        return
    render_result(r)
    save_and_export(r, kind, key)


# ---- Cable --------------------------------------------------------------------------------
def cable():
    page_header("🧵 Cable voltage drop (preliminary)",
                "IEC 60228 conductor resistance, temperature corrected. Voltage-drop criterion only.")
    st.info("This tool does **not** select a final cable. Ampacity (installation method, ambient temperature, "
            "grouping, insulation), protection and short-circuit withstand must be checked separately "
            "against the applicable wiring rules.", icon="ℹ️")
    mode = st.radio("Mode", ["Check a chosen size", "Find minimum size for a drop limit"], horizontal=True)
    a, b, c, d = st.columns(4)
    system = a.selectbox("System", ["single_phase", "three_phase", "dc"],
                         format_func=lambda s: {"single_phase": "Single-phase AC", "three_phase": "Three-phase AC",
                                                "dc": "DC"}[s])
    v = b.number_input("Nominal voltage (V)", 1.0, 1e5, {"single_phase": 230.0, "three_phase": 400.0, "dc": 48.0}[system],
                       help="Phase-neutral for single-phase; line-line for three-phase.")
    i = c.number_input("Design current (A)", 0.01, 1e5, 20.0)
    length = d.number_input("One-way route length (m)", 0.1, 1e5, 30.0)
    a, b, c, d = st.columns(4)
    mat = a.selectbox("Conductor", ["copper", "aluminium"])
    temp = b.number_input("Conductor temperature (°C)", -20.0, 250.0, 70.0,
                          help="70 °C = PVC max operating; 90 °C = XLPE/EPR max. Use the actual insulation rating.")
    pf = c.number_input("Power factor", 0.01, 1.0, 1.0 if system == "dc" else 0.9, disabled=system == "dc")
    x = d.number_input("Reactance (mΩ/m, from datasheet; 0 = ignore)", 0.0, 2.0, 0.0, 0.01, disabled=system == "dc")
    limit = st.number_input("Voltage-drop limit (%)", 0.1, 20.0, 3.0, 0.5,
                            help="Choose the limit required by your applicable code or specification.")
    try:
        if mode.startswith("Check"):
            size = st.selectbox("Conductor size (mm²)", cab.STANDARD_SIZES[mat],
                                index=cab.STANDARD_SIZES[mat].index(4) if mat == "copper" else 0)
            r = cab.voltage_drop(system, v, i, length, size, mat, temp, pf, x, limit)
            keys = ["voltage_drop_v", "voltage_drop_pct", "receiving_voltage_v", "within_limit"]
        else:
            r = cab.minimum_size_for_drop(system, v, i, length, limit, mat, temp, pf, x)
            keys = ["min_size_mm2", "voltage_drop_pct", "voltage_drop_v", "power_loss_w"]
    except ValidationError as e:
        show_error(e)
        return
    render_result(r, keys)
    save_and_export(r, "cable", "cab")


# ---- Reports & history -------------------------------------------------------------------
def report_page():
    page_header("📄 Reports & project history", "Combine saved calculations into a draft report (PDF or editable Markdown).")
    store = get_store()
    projects = store.list_projects()
    if not projects:
        st.info("No projects yet. Create one on the Home page.")
        return
    labels = {p["id"]: p["name"] + (" [DEMO]" if p["is_demo"] else "") for p in projects}
    pid = st.selectbox("Project", list(labels), format_func=labels.get)
    proj = store.get_project(pid)
    calcs = store.list_calculations(pid)
    if not calcs:
        st.info("This project has no saved calculations yet.")
    else:
        st.dataframe([{"ID": c["id"], "Type": c["kind"], "Title": c["title"], "Saved (UTC)": c["created"]} for c in calcs],
                     hide_index=True, use_container_width=True)
        chosen = st.multiselect("Calculations to include", [c["id"] for c in calcs], default=[c["id"] for c in calcs],
                                format_func=lambda i: next(f"#{c['id']} {c['title']}" for c in calcs if c["id"] == i))
        st.subheader("Report details")
        a, b = st.columns(2)
        prepared = a.text_input("Prepared by")
        status = b.selectbox("Review status", reports.REVIEW_STATUSES)
        reviewer = a.text_input("Reviewer name (only if actually reviewed)",
                                disabled=status == reports.REVIEW_STATUSES[0])
        notes = st.text_area("Scope and notes", value=proj.get("notes") or "")
        if status != reports.REVIEW_STATUSES[0] and not reviewer:
            st.warning("Enter the reviewer's name, or keep the status as DRAFT.")
        commentary = st.session_state.get(f"ai_comment_{pid}")
        if commentary:
            st.markdown("**AI commentary to include (from the AI assistant page):**")
            commentary = st.text_area("Edit or clear", commentary, height=150)
        results = [store.get_calculation(i)["result"] for i in chosen]
        meta = reports.ReportMeta(project_name=proj["name"], client=proj["client"] or "", location=proj["location"] or "",
                                  prepared_by=prepared, review_status=status,
                                  reviewer=reviewer if status != reports.REVIEW_STATUSES[0] else "", notes=notes,
                                  is_demo=bool(proj["is_demo"]))
        if results:
            a, b = st.columns(2)
            safe = "".join(ch if ch.isalnum() else "_" for ch in proj["name"])[:40]
            a.download_button("Download PDF report", reports.build_pdf(meta, results, commentary or None),
                              f"{safe}_report.pdf", "application/pdf", type="primary")
            b.download_button("Download editable Markdown", reports.build_markdown(meta, results, commentary or None),
                              f"{safe}_report.md", "text/markdown")
        with st.expander("Delete data"):
            cid = st.selectbox("Calculation to delete", [c["id"] for c in calcs])
            if st.button("Delete calculation"):
                store.delete_calculation(cid); st.rerun()
    with st.expander("Delete this project and all its calculations"):
        if st.checkbox(f"I understand '{proj['name']}' will be permanently deleted") and st.button("Delete project"):
            store.delete_project(pid); st.rerun()


# ---- AI assistant -------------------------------------------------------------------------
def _provider_picker(key: str):
    names = list(ai.PROVIDERS)
    name = st.selectbox("AI provider", names, format_func=lambda n: ai.PROVIDERS[n].label, key=key)
    prov = ai.get_provider(name)
    ok, why = prov.status()
    (st.success if ok else st.warning)(f"{prov.label}: {why}" + (f" · model `{prov.model}`" if prov.model else ""))
    if prov.privacy_note:
        st.caption(prov.privacy_note)
    if prov.paid:
        st.caption(f"Paid provider. Monthly budget ${config.MONTHLY_AI_BUDGET_USD:.2f}, "
                   f"per-request cap ${config.MAX_COST_PER_REQUEST_USD:.2f} (set in .env).")
    return prov, ok


def assistant():
    page_header("🤖 AI engineering assistant",
                "Explains saved calculations. Numbers always come from the calculation engine, never from the AI.")
    store = get_store()
    prov, ok = _provider_picker("asst_prov")
    calcs = store.list_calculations()
    ctx = None
    if calcs:
        opts = [None] + [c["id"] for c in calcs]
        cid = st.selectbox("Calculation to discuss", opts,
                           format_func=lambda i: "None" if i is None else
                           next(f"#{c['id']} {c['title']} ({c['project']})" for c in calcs if c["id"] == i))
        if cid:
            rec = store.get_calculation(cid)
            ctx = rec["result"]
            if st.button("Explain this calculation (offline, free)"):
                st.markdown(ai.explain_offline(ctx))
    hist = st.session_state.setdefault("chat", [])
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    q = st.chat_input("Ask about the selected calculation or a general engineering principle")
    if q:
        hist.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        msgs = list(hist)
        if ctx:
            msgs[-1] = {"role": "user", "content": ai.calc_context(ctx) + "\n\nQUESTION: " + q}
        with st.chat_message("assistant"):
            try:
                with st.spinner("Thinking..."):
                    rep = ai.ask(prov, msgs[-8:], store=store, purpose="assistant")
                st.markdown(rep.text)
                st.caption(f"AI commentary · {rep.provider}/{rep.model} · {rep.input_tokens}+{rep.output_tokens} tokens · "
                           f"${rep.cost_usd:.5f}")
                hist.append({"role": "assistant", "content": rep.text})
                if ctx and rec:
                    st.session_state[f"ai_comment_{rec['project_id']}"] = rep.text
            except ai.AIError as e:
                hist.pop()
                st.error(f"{e} ({e.kind}). No other provider was tried automatically.")
                if ctx:
                    st.info("Offline explanation instead:")
                    st.markdown(ai.explain_offline(ctx))
    if hist and st.button("Clear conversation"):
        st.session_state["chat"] = []; st.rerun()


# ---- Documents ------------------------------------------------------------------------------
def docs():
    page_header("📚 Document assistant",
                "Upload datasheets, manuals and notes. Search runs locally; nothing is sent anywhere unless you ask the AI.")
    store = get_store()
    if config.PUBLIC_DEMO:
        st.info("Document upload is disabled in the public demo to protect visitors' files. "
                "Run the app locally to use the document assistant.")
        return
    up = st.file_uploader(f"Upload PDF, TXT or MD (max {config.MAX_UPLOAD_MB:g} MB). Only upload documents you are "
                          "authorised to use.", type=["pdf", "txt", "md"])
    if up and st.button("Index document"):
        data = up.getvalue()
        try:
            pages = documents.extract_pages(up.name, data)
            store.add_document(up.name, documents.sha256(data), documents.chunk_pages(pages))
            flags = ai.injection_flags(" ".join(t for _, t in pages))
            st.success(f"Indexed {up.name}: {len(pages)} pages with text.")
            if flags:
                st.warning("This document contains text that looks like instructions to an AI. It will be treated "
                           "strictly as data, but review it before relying on it.")
        except (documents.UploadError, ValueError) as e:
            st.error(str(e))
    docs_ = store.list_documents()
    if not docs_:
        st.info("No documents indexed yet.")
        return
    st.dataframe([{"ID": d["id"], "File": d["filename"], "Pages": d["pages"], "Characters": d["chars"],
                   "Added (UTC)": d["created"]} for d in docs_], hide_index=True, use_container_width=True)
    q = st.text_input("Question or keywords")
    if q:
        hits = documents.search(store.all_chunks(), q, k=5)
        if not hits:
            st.warning("No passage in your documents matches this question. The documents may not contain the answer.")
        for h in hits:
            with st.expander(f"{h['filename']} - page {h['page']} (score {h['score']})"):
                st.write(h["text"])
        if hits:
            st.divider()
            prov, ok = _provider_picker("doc_prov")
            consent = prov.name in ("offline", "ollama") or st.checkbox(
                f"I authorise sending these {len(hits)} excerpts to {prov.label}.")
            if st.button("Answer with AI using these passages", disabled=not (ok and consent)):
                prompt = (ai.wrap_passages(hits) + "\n\nAnswer the QUESTION using only the passages above. Cite as "
                          "[filename p.N]. If they do not contain the answer, say so.\n\nQUESTION: " + q)
                try:
                    rep = ai.ask(prov, [{"role": "user", "content": prompt}], store=store, purpose="documents")
                    st.markdown(rep.text)
                    st.caption("AI answer - verify against the cited pages.")
                except ai.AIError as e:
                    st.error(f"{e} ({e.kind})")
    with st.expander("Delete a document"):
        did = st.selectbox("Document", [d["id"] for d in docs_],
                           format_func=lambda i: next(d["filename"] for d in docs_ if d["id"] == i))
        if st.button("Delete document and its index"):
            store.delete_document(did); st.rerun()


# ---- Settings / usage / help ---------------------------------------------------------------
def settings():
    page_header("⚙️ Settings & AI providers")
    st.markdown(f"**App name:** {config.APP_NAME} (change `ECALC_APP_NAME` in `.env`)")
    st.markdown(f"**Data folder:** `{config.DATA_DIR.name}/` (local SQLite database; not in version control)")
    st.subheader("Provider status")
    rows = []
    for name, cls in ai.PROVIDERS.items():
        p = cls()
        ok, why = p.status()
        rows.append({"Provider": p.label, "Model": p.model or "-", "Status": "Ready" if ok else "Not ready",
                     "Detail": why, "Cost type": "Paid / credits" if p.paid else "Free"})
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.subheader("Cost controls")
    st.markdown(f"- Monthly paid-AI budget: **${config.MONTHLY_AI_BUDGET_USD:.2f}** "
                f"({'paid providers BLOCKED' if config.MONTHLY_AI_BUDGET_USD <= 0 else 'enforced'})\n"
                f"- Per-request cap: **${config.MAX_COST_PER_REQUEST_USD:.2f}**\n"
                f"- Request timeout: **{config.AI_TIMEOUT_SECONDS:g} s**")
    st.info("API keys are read only from the `.env` file (copy `.env.example`). They are never shown here, "
            "stored in the database or written to logs. Restart the app after editing `.env`.")
    keys = {k: bool(os.getenv(k)) for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY")}
    st.write({k: ("set" if v else "not set") for k, v in keys.items()})


def usage():
    page_header("💲 AI usage & costs")
    store = get_store()
    rows = store.usage_rows()
    spent = store.month_spend_usd()
    a, b, c = st.columns(3)
    a.metric("Spend this month (USD)", f"${spent:.4f}")
    a2 = config.MONTHLY_AI_BUDGET_USD
    b.metric("Monthly budget (USD)", f"${a2:.2f}")
    c.metric("Requests logged", len(rows))
    if rows:
        st.dataframe([{"Time (UTC)": r["ts"], "Provider": r["provider"], "Model": r["model"], "Purpose": r["purpose"],
                       "In tok": r["input_tokens"], "Out tok": r["output_tokens"], "Cost $": round(r["cost_usd"], 6),
                       "OK": "yes" if r["ok"] else "no", "Error": r["error"], "Seconds": round(r["duration_s"] or 0, 1)}
                      for r in rows], hide_index=True, use_container_width=True)
    else:
        st.info("No AI requests yet. Calculations, reports and document search never use AI and cost nothing.")
    st.subheader("Estimated cost per 1,000 requests (pricing table, verify on provider sites)")
    st.caption("Assumes 2,000 input + 500 output tokens per request. Actual usage is logged above.")
    st.table([{"Model": m, "USD per 1,000 requests": f"${ai.cost_usd(m, 2_000_000, 500_000):.2f}"} for m in ai.PRICES])


def help_page():
    page_header("❓ Help")
    st.markdown(f"""
**What {config.APP_NAME} does**
- Preliminary solar PV sizing (grid-tied / hybrid) with PVGIS data or your own peak sun hours.
- Electrical fundamentals: AC power, load current, power-factor correction, Ohm's law, energy cost, unit conversions.
- Cable voltage drop using IEC 60228 conductor resistances, and minimum size by voltage-drop criterion.
- Draft PDF / Markdown reports with inputs, equations, results, assumptions, warnings and a review record.
- An optional AI assistant that *explains* results, plus a local document search with page citations.

**What it does not do**
- It does not produce certified, stamped or construction-ready designs.
- It does not select final cables (ampacity, protection and short-circuit checks are not implemented).
- It does not perform load-flow, short-circuit or protection-coordination studies.
- The AI never computes engineering values; if it states a number not in the calculation, treat it as an error.

**Typical workflow:** Home → create project → run calculations → save → Reports → download draft → engineer review.

See `README.md` and `ENGINEERING_METHODS.md` in the project folder for full details.
""")
