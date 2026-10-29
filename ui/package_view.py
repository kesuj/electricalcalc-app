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


def render_card(c: dict) -> None:
    st.markdown(f"#### {c['name']}")
    if c.get("what_it_does"):
        st.markdown(c["what_it_does"])
    if c.get("best_for_you"):
        st.success(f"**Best for your system:** {c['best_for_you']}")
    cols = st.columns(2)
    with cols[0]:
        if c.get("how_to_select"):
            st.markdown("**How to select (your numbers)**")
            st.markdown("\n".join(f"- {x}" for x in c["how_to_select"]))
        if c.get("series_or_parallel"):
            st.markdown("**Series or parallel?**")
            st.info(c["series_or_parallel"])
    with cols[1]:
        if c.get("buying_checklist"):
            st.markdown("**When buying, check**")
            st.markdown("\n".join(f"- {x}" for x in c["buying_checklist"]))
        if c.get("mistakes"):
            st.markdown("**Common mistakes**")
            st.markdown("\n".join(f"- ⚠️ {x}" for x in c["mistakes"]))
    if c.get("types"):
        with st.popover("Compare the types"):
            st.dataframe(_display(c["types"]), hide_index=True, width="stretch")
    if c.get("how_to_connect"):
        st.markdown("**How to connect**")
        st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(c["how_to_connect"], 1)))
    if c.get("ref"):
        st.caption(f"Reference: {c['ref']}")
    st.divider()


def render_sections(sections: list[dict]) -> None:
    for i, sec in enumerate(sections):
        with st.expander(f"{chr(65 + i)}. {sec['title']}", expanded=i < 2):
            if sec.get("intro"):
                st.markdown(sec["intro"])
            if sec.get("diagram"):
                st.graphviz_chart(_dot(sec["diagram"]), width="stretch")
            for caption, svg in sec.get("svgs", []):
                if caption:
                    st.markdown(f"**{caption}**")
                st.html(f'<div style="max-width:100%;overflow-x:auto">{svg}</div>')
            for card in sec.get("cards", []):
                render_card(card)
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


def _row(rows: list[dict], prefix: str) -> dict:
    return next((r for r in rows if r.get("Circuit", "").startswith(prefix)), {})


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def home_sections(pkg, design=None, x=None, ii=None) -> list[dict]:
    """Complete self-install report: buy -> understand every part -> wiring drawings -> install -> test -> maintain."""
    from ecalc import drawings
    from ecalc.guide import component_guide, series_parallel_explainer, skills
    from ecalc.guide.research_2026 import apply_research, legal_points_2026

    st_ = pkg.strings or {}
    from ecalc.guide.requirement import requirement_table, with_requirement
    mode0 = getattr(x, "mode", "grid_tied") if x is not None else "grid_tied"
    secs: list[dict] = [
        {"title": "What to buy (shopping list)",
         "intro": "Buy equipment that meets NEPQA-2025 (AEPC) and ask the seller for each datasheet. Ratings are the "
                  "minimum - equal or higher is fine unless stated. The second column says whether the item is "
                  "compulsory in Nepal or optional; section B explains every item.",
         "table": with_requirement(pkg.bom, mode0), "bullets": pkg.warnings},
        {"title": "Compulsory or optional in Nepal (your system type)",
         "intro": "Compulsory (law / NEA) = NEPQA-2025 or NEA require it. Compulsory (safety) = IEC safety standards "
                  "and AEPC specifications require it. Strongly recommended = a real Nepal risk. Optional = convenience.",
         "table": requirement_table(mode0)},
    ]
    if design is not None and x is not None and ii is not None:
        secs.append({"title": "Every part explained - what it is, which type is best, how to choose and connect it",
                     "intro": "One card per part, written for your system. Read the card before you buy that part.",
                     "cards": apply_research(component_guide(pkg, design, x, ii), pkg, x, ii)})
    sp = series_parallel_explainer(pkg)
    svgs = []
    pv = _row(pkg.cable_schedule, "PV string")
    wp = design.inputs["panel_wp"].value if design is not None else 0
    if st_.get("modules_per_string"):
        svgs.append(("Your panels: how to connect them", drawings.panel_strings_svg(
            int(st_["modules_per_string"]), int(st_.get("strings", 1)), f"{wp:g} W panel",
            _num(st_.get("string_voc_cold_v"), 0), _num(st_.get("string_vmp_stc_v"), 0), ii.isc if ii else 0,
            _num(pv.get("Chosen (mm²)"), 4), _num(st_.get("string_fuses")))))
    if st_.get("battery_series"):
        bat = _row(pkg.cable_schedule, "Battery cable")
        bank_v = design.outputs["system_v"].value if design is not None and "system_v" in design.outputs else 48
        n_s, n_p = int(st_["battery_series"]), int(st_.get("battery_parallel", 1))
        chem = getattr(x, "chemistry", "LiFePO4") if x is not None else "LiFePO4"
        ah = (ii.battery_module_ah if ii and ii.battery_module_ah else (100 if chem.startswith("LiFePO4") else 150))
        svgs.append(("Your battery bank: how to connect it", drawings.battery_bank_svg(
            n_s, n_p, f"{bank_v / n_s:g} V {ah:g} Ah", bank_v, _num(st_.get("battery_kwh"), 0),
            _num(bat.get("Chosen (mm²)"), 25), _num(bat.get("Protective device (A)"), 63))))
    secs.append({"title": "Series and parallel - your panels and batteries",
                 "bullets": [v for k, v in sp.items() if isinstance(v, str)], "svgs": svgs})
    mode = getattr(x, "mode", "grid_tied") if x is not None else "grid_tied"
    secs.append({"title": "Your whole system, drawn",
                 "svgs": [("Complete system", drawings.system_overview_svg(mode, pkg)),
                          ("Earthing", drawings.earthing_svg(pkg)),
                          ("Inverter terminals - what goes where", drawings.inverter_terminals_svg(mode))],
                 "diagram": normalise_sld(pkg.sld),
                 "note": "Wire colours: AC live brown, neutral blue, earth green-yellow; DC + red, - black."})
    secs.append({"title": "Cables, fuses and breakers", "table": pkg.cable_schedule,
                 "note": "Chosen size = the larger of the current-rating size and the voltage-drop size."})
    stops = legal_points_2026(x) if x is not None else []
    secs.append({"title": "Safety first, and the legal stop-points", "bullets": pkg.safety + stops})
    if x is not None:
        secs.append({"title": "Skills you will need (learn these before starting)",
                     "groups": [(s_["title"], [f"Why: {s_['why']}"] + s_["steps"] +
                                 [f"Safety: {z}" for z in s_.get("safety", [])]) for s_ in skills(pkg, x)]})
    secs += [
        {"title": "Step-by-step installation", "groups": pkg.steps},
        {"title": "Testing before switching on (write the measured values)", "table": pkg.tests_table},
        {"title": "Looking after the system", "table": pkg.maintenance},
        {"title": "If something goes wrong", "table": pkg.troubleshooting,
         "note": ("References: " + "; ".join(pkg.references)) if pkg.references else None},
    ]
    return secs
