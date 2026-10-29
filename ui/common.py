"""Shared Streamlit helpers: storage handle, result rendering, save-to-project widget."""

from __future__ import annotations

import streamlit as st

from ecalc import config, reports
from ecalc.calc.result import CalcResult
from ecalc.storage import Store

CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
div[data-testid="stMetricValue"] {font-size: 1.45rem;}
.ec-note {font-size: .85rem; color: #6b7280;}
.ec-badge {display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:600;
           background:#fde68a;color:#78350f;margin-left:6px;}
</style>
"""


@st.cache_resource
def get_store() -> Store:
    return Store()


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def fmt_q(q) -> str:
    v = q.value
    if isinstance(v, float):
        v = f"{v:,.2f}" if abs(v) >= 100 else f"{v:,.4g}"
    return f"{v} {q.unit}".strip()


def render_result(r: CalcResult, key_outputs: list[str] | None = None) -> None:
    keys = key_outputs or list(r.outputs)[:4]
    cols = st.columns(min(4, len(keys)) or 1)
    for col, k in zip(cols * 3, keys):
        q = r.outputs[k]
        col.metric(q.label, fmt_q(q))
    st.markdown("##### All results")
    st.table({"Result": [q.label or k for k, q in r.outputs.items()], "Value": [fmt_q(q) for q in r.outputs.values()]})
    for name, rows in r.tables.items():
        st.markdown(f"##### {name}")
        st.dataframe(rows, use_container_width=True, hide_index=True)
    if r.warnings:
        for w in r.warnings:
            st.warning(w, icon="⚠️")
    with st.expander("Method, equations, assumptions and inputs"):
        st.markdown("**Equations**")
        for e in r.equations:
            st.code(e, language=None)
        st.markdown("**Assumptions**")
        for a in r.assumptions:
            st.markdown(f"- {a}")
        if r.references:
            st.markdown("**References**")
            for ref in r.references:
                st.markdown(f"- {ref}")
        st.markdown("**Inputs used**")
        st.table({"Input": [q.label or k for k, q in r.inputs.items()], "Value": [fmt_q(q) for q in r.inputs.values()]})


def save_and_export(r: CalcResult, kind: str, key: str) -> None:
    """Save a result to a project and offer an immediate single-calculation PDF."""
    store = get_store()
    st.divider()
    c1, c2 = st.columns([3, 2])
    with c1:
        projects = store.list_projects()
        if not projects:
            st.info("Create a project on the Home page to save calculations.")
        else:
            labels = {p["id"]: f"{p['name']}" + (" (demo)" if p["is_demo"] else "") for p in projects}
            pid = st.selectbox("Save to project", list(labels), format_func=labels.get, key=f"{key}_proj")
            title = st.text_input("Calculation title", value=r.name, key=f"{key}_title")
            if st.button("Save calculation", key=f"{key}_save", type="primary"):
                store.save_calculation(pid, kind, title, r.to_dict())
                st.success("Saved. Build a full report on the Reports page.")
    with c2:
        meta = reports.ReportMeta(project_name=r.name)
        st.download_button("Download quick PDF (draft)", data=reports.build_pdf(meta, [r.to_dict()]),
                           file_name=f"{kind}_draft.pdf", mime="application/pdf", key=f"{key}_pdf")
        st.markdown(f'<span class="ec-note">Draft, unreviewed. {config.APP_NAME} never marks reports as certified.</span>',
                    unsafe_allow_html=True)


def show_error(e: Exception) -> None:
    st.error(f"Input problem: {e}")
