"""Turn installation / construction packages into report sections, and render the same sections on
screen - so the website and the PDF always show identical content."""

from __future__ import annotations

import streamlit as st


def _dot(diagram: dict) -> str:
    lines = ['digraph G {', 'rankdir=TB; node [shape=box, style="rounded,filled", fillcolor="#eaf2fb", '
             'color="#1f4e79", fontname="Helvetica", fontsize=11]; edge [fontname="Helvetica", fontsize=9];']
    for n in diagram.get("nodes", []):
        lines.append(f'"{n["id"]}" [label="{n["label"].replace(chr(34), chr(39))}"];')
    for e in diagram.get("edges", []):
        lines.append(f'"{e["from"]}" -> "{e["to"]}" [label="{e.get("label", "").replace(chr(34), chr(39))}"];')
    return "\n".join(lines + ["}"])


def normalise_sld(sld: dict) -> dict:
    """Accept nodes as (id, label) tuples or dicts, edges as (a, b, label) tuples or dicts."""
    nodes = [n if isinstance(n, dict) else {"id": n[0], "label": n[1]} for n in sld.get("nodes", [])]
    edges = [e if isinstance(e, dict) else {"from": e[0], "to": e[1], "label": e[2] if len(e) > 2 else ""}
             for e in sld.get("edges", [])]
    return {"nodes": nodes, "edges": edges}


def _display(rows: list[dict]) -> list[dict]:
    """Tables mix numbers and words in a column (e.g. '250' and 'RMU / VCB'): show everything as text."""
    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:,.2f}".rstrip("0").rstrip(".")
        return str(v)
    return [{k: fmt(v) for k, v in r.items()} for r in rows]


def render_sections(sections: list[dict]) -> None:
    for i, sec in enumerate(sections):
        with st.expander(f"{chr(65 + i)}. {sec['title']}", expanded=i < 2):
            if sec.get("intro"):
                st.markdown(sec["intro"])
            if sec.get("diagram"):
                st.graphviz_chart(_dot(sec["diagram"]), width="stretch")
            for b in sec.get("bullets", []):
                st.markdown(f"- {b}")
            if sec.get("numbered"):
                st.markdown("\n".join(f"{n}. {t}" for n, t in enumerate(sec["numbered"], 1)))
            for gtitle, steps in sec.get("groups", []):
                st.markdown(f"**{gtitle}**")
                st.markdown("\n".join(f"{n}. {t}" for n, t in enumerate(steps, 1)))
            if sec.get("table"):
                st.dataframe(_display(sec["table"]), hide_index=True, width="stretch")
            for tname, rows in (sec.get("tables") or {}).items():
                if rows:
                    st.markdown(f"**{tname}**")
                    st.dataframe(_display(rows), hide_index=True, width="stretch")
            if sec.get("note"):
                st.caption(sec["note"])


def farm_sections(pkg) -> list[dict]:
    counts = [{"Item": v.get("label", k), "Quantity": v.get("value"), "Unit": v.get("unit", "")}
              for k, v in pkg.counts.items()]
    return [
        {"title": "Plant at a glance", "intro": pkg.note,
         "bullets": [pkg.hierarchy.get("text", "")] + pkg.warnings, "table": counts},
        {"title": "Single-line diagram (one block)", "diagram": normalise_sld(pkg.sld),
         "tables": {"Blocks and transformers": pkg.blocks}},
        {"title": "Bill of quantities", "table": pkg.boq,
         "note": "Quantities of cable are estimates from route assumptions - confirm with the detailed layout."},
        {"title": "Cable schedule", "table": pkg.cable_schedule,
         "note": "Size = larger of current rating (Ib ≤ In ≤ Iz) and voltage drop (DC < 3 %, AC < 1 %)."},
        {"title": "Switchgear, protection, earthing and grid connection",
         "tables": {"Switchgear": pkg.switchgear, "Protection": pkg.protection, "Earthing and lightning": pkg.earthing,
                    "NEA interconnection": pkg.interconnection}},
        {"title": "Construction sequence", "groups": pkg.construction},
        {"title": "Testing and commissioning",
         "intro": (f"Insulation test: system voltage {pkg.insulation_test.get('system_voltage_v', 0):,.0f} V -> test at "
                   f"{pkg.insulation_test.get('test_v')} V, minimum {pkg.insulation_test.get('min_mohm')} MΩ "
                   "(Solar Farms Table 5.1, IEC 62446)."),
         "table": pkg.commissioning},
        {"title": "Operation and maintenance", "table": pkg.o_and_m},
        {"title": "Permits and approvals in Nepal (verify current procedure)", "table": pkg.permits},
    ]


def home_sections(pkg) -> list[dict]:
    st_ = pkg.strings or {}
    layout = [f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in st_.items()]
    return [
        {"title": "What to buy (shopping list)",
         "intro": "Buy equipment that meets NEPQA-2025 (AEPC) and ask the seller for the datasheets. Ratings below "
                  "are the minimum - equal or higher is fine unless stated.",
         "table": pkg.bom, "bullets": pkg.warnings},
        {"title": "How the panels and batteries are connected", "bullets": layout},
        {"title": "Wiring diagram", "diagram": normalise_sld(pkg.sld),
         "note": "Each arrow is a cable: the label gives its size and the fuse/breaker that protects it."},
        {"title": "Cables, fuses and breakers", "table": pkg.cable_schedule,
         "note": "Chosen size = the larger of the current-rating size and the voltage-drop size."},
        {"title": "Safety first", "bullets": pkg.safety},
        {"title": "Step-by-step installation", "groups": pkg.steps},
        {"title": "Testing before switching on (write the measured values)", "table": pkg.tests_table},
        {"title": "Looking after the system", "table": pkg.maintenance},
        {"title": "If something goes wrong", "table": pkg.troubleshooting,
         "note": "References: " + "; ".join(pkg.references) if pkg.references else None},
    ]
