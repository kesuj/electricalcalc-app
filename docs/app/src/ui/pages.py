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
from ui.hints import missing, num

CURRENCIES = ["NPR", "USD", "AUD", "GBP", "INR", "EUR"]


# ---- Solar ----------------------------------------------------------------------------------
def solar():
    page_header("☀️ Solar PV sizing",
                "Quick solar sizing for engineers. Fill in the boxes - the grey text says where to find each value.")
    store = get_store()
    st.subheader("1. Location and sunshine data")
    src = st.radio("Sunshine data *", ["PVGIS (online, free)", "Enter peak sun hours"], horizontal=True)
    pvgis_mode = src.startswith("PVGIS")
    lat = lon = tilt = aspect = psh = None
    if pvgis_mode:
        a, b, c = st.columns([2, 1, 1])
        city = a.selectbox("Nearest city *", list(PRESET_LOCATIONS), index=None, placeholder="Choose, or type coordinates →")
        lat_in = num(b, "lat", "Latitude", -90.0, 90.0, wkey="s_lat")
        lon_in = num(c, "lon", "Longitude", -180.0, 180.0, wkey="s_lon")
        if lat_in is not None and lon_in is not None:
            lat, lon, location_label = lat_in, lon_in, f"{lat_in:.4f}, {lon_in:.4f}"
        elif city:
            (lat, lon), location_label = PRESET_LOCATIONS[city], city
        else:
            location_label = ""
        a, b, c = st.columns(3)
        tilt = num(a, "tilt", "Tilt (°) *", 0.0, 90.0, wkey="s_tilt")
        aspect = num(b, "azimuth", "Azimuth (°, 0 = south) *", -180.0, 180.0, wkey="s_az")
        loss = num(c, "loss_pvgis", "System losses (%) *", 0.0, 50.0, wkey="s_loss_p")
    else:
        a, b, c = st.columns(3)
        psh = num(a, "psh", "Peak sun hours (kWh/m²/day) *", 0.5, 9.0, wkey="s_psh")
        loss = num(b, "loss_psh", "Total losses (%) - includes temperature *", 0.0, 50.0, wkey="s_loss_t")
        location_label = c.text_input("Location name", placeholder="e.g. Pokhara-8, Kaski")

    st.subheader("2. Consumption and system")
    a, b = st.columns(2)
    basis = a.radio("Consumption entered as *", ["Per day (kWh/day)", "Per month (kWh = bill units)"], horizontal=True)
    cons = (num(b, "daily_kwh", "Consumption (kWh/day) *", 0.01, 1e6, wkey="s_cd") if basis.startswith("Per day")
            else num(b, "monthly_kwh", "Consumption (kWh/month) *", 0.1, 1e7, wkey="s_cm"))
    system = st.radio("System type *", ["Grid-tied", "Hybrid with battery"], index=None, horizontal=True)
    a, b, c, d = st.columns(4)
    offset = num(a, "offset", "Cover % of consumption *", 1.0, 200.0, wkey="s_off")
    wp = num(b, "panel_wp", "Panel rating (Wp) *", 50.0, 1000.0, wkey="s_wp")
    parea = num(c, "panel_area", "Panel area (m²) *", 0.3, 4.0, wkey="s_pa")
    ratio = num(d, "dc_ac", "DC/AC ratio *", 0.8, 1.6, wkey="s_ratio")
    area = num(st, "roof_area", "Available module area (m²) - optional", 0.0, 1e6, wkey="s_area")
    hybrid = system == "Hybrid with battery"
    bat: dict = {}
    if hybrid:
        st.markdown("**Battery and backup**")
        a, b, c, d, e = st.columns(5)
        bat = dict(backup_kwh_per_day=num(a, "backup_eng", "Backup energy (kWh/day) *", 0.01, 1e5, wkey="s_bk"),
                   autonomy_days=num(b, "autonomy", "Autonomy (days) *", 0.1, 7.0, wkey="s_aut"),
                   battery_dod_pct=num(c, "dod", "Depth of discharge (%) *", 10.0, 100.0, wkey="s_dod"),
                   battery_voltage_v=num(d, "vbat", "Bank voltage (V) *", 12.0, 1000.0, wkey="s_vb"),
                   peak_load_kw=num(e, "peak_kw", "Peak load (kW)", 0.0, 1e5, wkey="s_pk"))
    with st.expander("Costs and tariff (optional - for savings and payback)"):
        a, b, c, d, e = st.columns(5)
        cur = a.selectbox("Currency", CURRENCIES)
        tariff = num(b, "tariff", "Tariff per unit", 0.0, 1e4, wkey="s_tar")
        export = num(c, "export", "Export rate per unit", 0.0, 1e4, wkey="s_exp")
        cost_kwp = num(d, "cost_kwp", "Installed cost per kWp", 0.0, 1e9, wkey="s_ck")
        bcost = num(e, "bat_cost", "Battery cost per kWh", 0.0, 1e8, disabled=not hybrid, wkey="s_bc")

    if st.button("Calculate", type="primary"):
        required = {"Losses": loss, "Consumption": cons, "System type": system, "Cover %": offset,
                    "Panel rating": wp, "Panel area": parea, "DC/AC ratio": ratio}
        if pvgis_mode:
            required.update({"Nearest city or latitude/longitude": lat, "Tilt": tilt, "Azimuth": aspect})
        else:
            required["Peak sun hours"] = psh
        if hybrid:
            required.update({"Backup energy": bat["backup_kwh_per_day"], "Autonomy": bat["autonomy_days"],
                             "Depth of discharge": bat["battery_dod_pct"], "Bank voltage": bat["battery_voltage_v"]})
        gaps = missing(required)
        if gaps:
            st.error("Please fill in: " + ", ".join(gaps) + ".")
        else:
            try:
                res = (fetch_pvgis(lat, lon, tilt, aspect, loss, cache=store) if pvgis_mode
                       else SolarResource.from_peak_sun_hours(psh, loss))
                daily = cons if basis.startswith("Per day") else cons * 12 / 365
                if bat:
                    bat["peak_load_kw"] = bat["peak_load_kw"] or None
                    bat["battery_cost_per_kwh"] = bcost or None
                st.session_state["solar_result"] = size_pv_system(SolarInputs(
                    daily_consumption_kwh=daily, panel_wp=wp, panel_area_m2=parea, resource=res,
                    system_type="hybrid_battery" if hybrid else "grid_tied", target_offset_pct=offset,
                    available_area_m2=area or None, dc_ac_ratio=ratio, tariff_per_kwh=tariff,
                    export_rate_per_kwh=export or 0, currency=cur, cost_per_kwp=cost_kwp or None,
                    location_label=location_label, **bat))
            except (PVGISError, ValidationError) as e:
                show_error(e)
    r = st.session_state.get("solar_result")
    if r:
        st.subheader("3. Results")
        render_result(r, ["pv_kwp", "panel_count", "annual_generation_kwh", "inverter_ac_kw"])
        save_and_export(r, "solar", "solar")


# ---- Power-factor correction -------------------------------------------------------------
def pf_page():
    page_header("⚡ Power-factor correction",
                "Capacitor bank size to raise power factor - e.g. to avoid utility low-PF penalties. "
                "The grey text in each box says where to find the value.")
    src = st.radio("Existing power factor *", ["From meter / bill readings (kWh and kVArh)", "I know the power factor"],
                   horizontal=True)
    meter = src.startswith("From")
    a, b, c = st.columns(3)
    p = num(a, "max_demand", "Maximum demand (kW) *", 0.001, 1e6, wkey="pf_p")
    kwh = kvarh = pf1 = None
    if meter:
        kwh = num(b, "kwh", "Active energy in the period (kWh) *", 0.001, 1e9, wkey="pf_kwh")
        kvarh = num(c, "kvarh", "Reactive energy in the period (kVArh) *", 0.0, 1e9, wkey="pf_kvarh")
        if kwh is not None and kvarh is not None:
            st.caption(f"Average power factor from these readings: **{fun.pf_from_energy(kwh, kvarh):.3f}**")
    else:
        pf1 = num(b, "pf_existing", "Existing PF *", 0.01, 0.999, 0.01, wkey="pf_1")
    pf2 = num(st, "pf_target", "Target PF *", 0.02, 1.0, 0.01, wkey="pf_2")
    with st.expander("Capacitance per phase (optional)"):
        a, b, c = st.columns(3)
        v = num(a, "pf_volts", "Line voltage (V)", 0.0, 1e6, wkey="pf_v")
        f = b.selectbox("Frequency (Hz)", [50.0, 60.0], help="Nepal, India, UK, Australia: 50 Hz. USA: 60 Hz.")
        conn = c.selectbox("Capacitor connection", ["delta", "star"],
                           help="From the capacitor bank datasheet; low-voltage banks are usually delta.")
    required = {"Maximum demand": p, "Target PF": pf2}
    required.update({"kWh": kwh, "kVArh": kvarh} if meter else {"Existing PF": pf1})
    if _need(required):
        return
    if meter:
        _run(lambda: fun.pf_correction_from_meter(p, kwh, kvarh, pf2, v or None, f, conn), "pf_correction", "pfc")
    else:
        _run(lambda: fun.pf_correction(p, pf1, pf2, v or None, f, conn), "pf_correction", "pfc")


def _need(fields: dict) -> bool:
    """Show which boxes are still empty; True means results cannot be calculated yet."""
    gaps = missing(fields)
    if gaps:
        st.info("Fill in the boxes marked * to see the result. Still empty: " + ", ".join(gaps) + ".")
    return bool(gaps)


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
    page_header("🧵 Cable voltage drop",
                "Checks voltage drop only (IEC 60228 conductor resistance). The grey text in each box says where to "
                "find the value.")
    st.info("This tool does **not** select a final cable. Ampacity (installation method, ambient temperature, "
            "grouping, insulation), protection and short-circuit withstand must be checked separately "
            "against the applicable wiring rules.", icon="ℹ️")
    mode = st.radio("What do you want? *", ["Check a chosen size", "Find the smallest size that meets a drop limit"],
                    horizontal=True)
    check = mode.startswith("Check")
    a, b, c, d = st.columns(4)
    system = a.selectbox("System *", ["single_phase", "three_phase", "dc"], index=None, placeholder="1-phase, 3-phase or DC",
                         format_func=lambda s: {"single_phase": "Single-phase AC", "three_phase": "Three-phase AC",
                                                "dc": "DC (battery / solar)"}[s],
                         help="Single-phase: 2 wires (L+N). Three-phase: 3 or 4 wires. DC: battery or solar circuits.")
    v = num(b, "nom_v", "Nominal voltage (V) *", 1.0, 1e5, wkey="c_v")
    i = num(c, "design_i", "Design current (A) *", 0.01, 1e5, wkey="c_i")
    length = num(d, "cable_len", "One-way route length (m) *", 0.1, 1e5, wkey="c_len")
    a, b, c, d = st.columns(4)
    mat = a.selectbox("Conductor *", ["copper", "aluminium"], index=None, placeholder="Printed on the cable sheath",
                      help="Copper or aluminium - printed on the cable sheath or datasheet.")
    temp = num(b, "temp", "Conductor temperature (°C) *", -20.0, 250.0, wkey="c_t")
    pf = num(c, "pf", "Power factor *", 0.01, 1.0, 0.01, disabled=system == "dc", wkey="c_pf")
    x = num(d, "reactance", "Reactance (mΩ/m)", 0.0, 2.0, 0.01, disabled=system == "dc", wkey="c_x")
    a, b = st.columns(2)
    limit = num(a, "vd_limit", "Voltage-drop limit (%)" + (" - optional" if check else " *"), 0.1, 20.0, 0.5, wkey="c_lim")
    size = None
    if check:
        size = b.selectbox("Conductor size (mm²) *", cab.STANDARD_SIZES[mat] if mat else [], index=None,
                           placeholder="Printed on the cable, e.g. 4" if mat else "Choose the conductor first",
                           help="Cross-section printed on the cable sheath, e.g. '3C x 4 mm²'.")
    required = {"System": system, "Nominal voltage": v, "Design current": i, "Route length": length,
                "Conductor": mat, "Conductor temperature": temp}
    if system != "dc":
        required["Power factor"] = pf
    required.update({"Conductor size": size} if check else {"Voltage-drop limit": limit})
    if _need(required):
        return
    pf = 1.0 if system == "dc" else pf
    try:
        if check:
            r = cab.voltage_drop(system, v, i, length, size, mat, temp, pf, x or 0.0, limit)
            keys = ["voltage_drop_v", "voltage_drop_pct", "receiving_voltage_v"] + (["within_limit"] if limit else ["power_loss_w"])
        else:
            r = cab.minimum_size_for_drop(system, v, i, length, limit, mat, temp, pf, x or 0.0)
            keys = ["min_size_mm2", "voltage_drop_pct", "voltage_drop_v", "power_loss_w"]
    except ValidationError as e:
        show_error(e)
        return
    render_result(r, keys)
    save_and_export(r, "cable", "cab")


# ---- My projects & reports ---------------------------------------------------------------
def report_page():
    page_header("📁 My projects & reports",
                "Every saved project. Pick one to download its report, add calculations or delete it.")
    store = get_store()
    projects = store.list_projects()
    if projects:
        st.dataframe([{"ID": p["id"], "Project": p["name"] + (" [DEMO]" if p["is_demo"] else ""),
                       "Client": p["client"], "Location": p["location"], "Calculations": p["n_calcs"],
                       "Updated (UTC)": p["updated"]} for p in projects], hide_index=True, width="stretch")
    with st.expander("Create an empty project (to save results from the individual calculator pages)"):
        with st.form("new_project", clear_on_submit=True):
            a, b, c = st.columns(3)
            name = a.text_input("Project name *")
            client = b.text_input("Client")
            loc = c.text_input("Location")
            notes = st.text_area("Scope / notes", height=70)
            if st.form_submit_button("Create project", type="primary"):
                try:
                    store.create_project(name, client, loc, notes)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    if st.button("Load demonstration project (clearly labelled sample data)"):
        load_demo_project(store)
        st.rerun()
    if not projects:
        st.info("No projects yet. Use **New project design** to enter your first project.")
        return
    st.subheader("Project report")
    labels = {p["id"]: p["name"] + (" [DEMO]" if p["is_demo"] else "") for p in projects}
    pid = st.selectbox("Project", list(labels), format_func=labels.get)
    proj = store.get_project(pid)
    calcs = store.list_calculations(pid)
    if not calcs:
        st.info("This project has no saved calculations yet.")
    else:
        st.dataframe([{"ID": c["id"], "Type": c["kind"], "Title": c["title"], "Saved (UTC)": c["created"]} for c in calcs],
                     hide_index=True, width="stretch")
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
                   "Added (UTC)": d["created"]} for d in docs_], hide_index=True, width="stretch")
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
    st.dataframe(rows, hide_index=True, width="stretch")
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
                      for r in rows], hide_index=True, width="stretch")
    else:
        st.info("No AI requests yet. Calculations, reports and document search never use AI and cost nothing.")
    st.subheader("Estimated cost per 1,000 requests (pricing table, verify on provider sites)")
    st.caption("Assumes 2,000 input + 500 output tokens per request. Actual usage is logged above.")
    st.table([{"Model": m, "USD per 1,000 requests": f"${ai.cost_usd(m, 2_000_000, 500_000):.2f}"} for m in ai.PRICES])


def help_page():
    page_header("❓ Help")
    st.markdown("""
**Two designers, both for Nepal**

| | 🏠 Home solar | 🏭 Solar farm |
|---|---|---|
| Who | Houses, shops, offices, health posts, schools | Grid-connected plants selling to NEA (MW scale) |
| Method from | Boxwell, *Solar Electricity Handbook* | Neill, Stapleton & Martell, *Solar Farms* |
| Data | PVGIS for your exact site, NEA slab tariff (ERC 2078), net-billing export rate, NEPQA-2025, 2026 Nepal prices | PVGIS, NEA solar PPA rates (2024 tender), NEPQA-2025, utility costs |
| You get | Panels, inverter, battery, cables, month-by-month NEA bill, a day with load-shedding, payback | Energy (P50/P90), layout & land (ha / bigha / ropani), strings & inverters, losses, LCOE, IRR |

**How to use:** answer the questions (the grey text in each box tells you how), press Calculate, then explore the
tabs and move the sliders - the charts update instantly. Download the PDF report at the end.

**Quick calculators** answer single questions (solar size, one cable's voltage drop, a capacitor bank).

**Honest limits**
- Preliminary designs only - a licensed engineer must check site, equipment and protection before purchase.
- The books are from 2012-2016: their *methods* are used, but all *data* is current (sources listed in each page).
  Errors found in the books' printed examples are corrected (see ENGINEERING_METHODS.md).
- Tariffs, net-billing rules and prices change; the date each was checked is shown with the source.
- Cable sizes are by voltage drop only; current rating, protection and earthing must be designed separately.
""")
