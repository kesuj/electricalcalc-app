"""Interactive Altair charts (hover tooltips, zoom/pan) shared by the Home and Farm pages."""

from __future__ import annotations

import altair as alt
import pandas as pd

from ecalc.profile import DayResult

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SUN, USE, GRID, BATT, BAD = "#f2a900", "#1f4e79", "#8a8f98", "#2e9e5b", "#d1495b"


def monthly_energy(gen_kwh: list[float], use_kwh: list[float] | None = None) -> alt.Chart:
    rows = [{"Month": m, "Series": "Solar generation", "kWh": g} for m, g in zip(MONTHS, gen_kwh)]
    if use_kwh:
        rows += [{"Month": m, "Series": "Your use", "kWh": u} for m, u in zip(MONTHS, use_kwh)]
    df = pd.DataFrame(rows)
    return alt.Chart(df).mark_bar().encode(
        x=alt.X("Month:N", sort=MONTHS, title=None),
        xOffset="Series:N",
        y=alt.Y("kWh:Q", title="Energy per month (kWh = units)"),
        color=alt.Color("Series:N", scale=alt.Scale(domain=["Solar generation", "Your use"], range=[SUN, USE]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Month", "Series", alt.Tooltip("kWh:Q", format=",.0f")],
    ).properties(height=320)


def day_profile(d: DayResult) -> alt.LayerChart:
    df = pd.DataFrame({"Hour": d.hours, "Solar (kW)": d.pv_kw, "Use (kW)": d.load_kw,
                       "From grid (kW)": d.grid_import_kw, "Battery charge (kWh)": d.soc_kwh,
                       "Not supplied (kW)": d.unserved_kw, "Power cut": ["Yes" if o else "" for o in d.outage]})
    base = alt.Chart(df).encode(x=alt.X("Hour:Q", scale=alt.Scale(domain=[0, 23]), title="Hour of the day (Nepal time)"))
    cut = alt.Chart(df[df["Power cut"] == "Yes"]).mark_rect(color=BAD, opacity=0.12).encode(
        x="Hour:Q", x2=alt.X2("end:Q")).transform_calculate(end="datum.Hour + 1")
    long = df.melt(id_vars=["Hour"], value_vars=["Solar (kW)", "Use (kW)", "From grid (kW)", "Not supplied (kW)"],
                   var_name="Series", value_name="kW")
    lines = alt.Chart(long).mark_line(point=True, interpolate="step-after").encode(
        x="Hour:Q", y=alt.Y("kW:Q", title="Power (kW)"),
        color=alt.Color("Series:N", scale=alt.Scale(domain=["Solar (kW)", "Use (kW)", "From grid (kW)", "Not supplied (kW)"],
                                                    range=[SUN, USE, GRID, BAD]), legend=alt.Legend(orient="top", title=None)),
        tooltip=["Hour", "Series", alt.Tooltip("kW:Q", format=".2f")])
    soc = base.mark_area(opacity=0.25, color=BATT, interpolate="step-after").encode(
        y=alt.Y("Battery charge (kWh):Q", title="Battery charge (kWh)", axis=alt.Axis(titleColor=BATT)),
        tooltip=["Hour", alt.Tooltip("Battery charge (kWh):Q", format=".2f")])
    return alt.layer(cut, lines, soc).resolve_scale(y="independent").properties(height=340).interactive(bind_y=False)


def cumulative_cash(rows: list[dict], currency: str) -> alt.LayerChart:
    df = pd.DataFrame(rows)
    line = alt.Chart(df).mark_line(point=True, color=USE).encode(
        x=alt.X("Year:Q", title="Year"), y=alt.Y("Cumulative:Q", title=f"Money back so far ({currency})"),
        tooltip=["Year", alt.Tooltip("Cumulative:Q", format=",.0f"), alt.Tooltip("Net cash flow:Q", format=",.0f")])
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=BAD, strokeDash=[4, 4]).encode(y="y:Q")
    return alt.layer(zero, line).properties(height=300).interactive()


def losses_waterfall(steps: list[tuple[str, float]], start_label: str = "Sunlight on panels") -> alt.Chart:
    """steps: (loss name, loss %) applied in order; shows what remains after each loss."""
    remaining, rows = 100.0, [{"Step": start_label, "start": 0.0, "end": 100.0, "Kind": "Start", "Value": 100.0}]
    for name, pct in steps:
        new = remaining * (1 - pct / 100)
        rows.append({"Step": name, "start": new, "end": remaining, "Kind": "Loss", "Value": -(remaining - new)})
        remaining = new
    rows.append({"Step": "Delivered to grid", "start": 0.0, "end": remaining, "Kind": "Result", "Value": remaining})
    df = pd.DataFrame(rows)
    order = list(df["Step"])
    return alt.Chart(df).mark_bar().encode(
        x=alt.X("Step:N", sort=order, title=None, axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("start:Q", title="% of energy remaining"), y2="end:Q",
        color=alt.Color("Kind:N", scale=alt.Scale(domain=["Start", "Loss", "Result"], range=[SUN, BAD, BATT]), legend=None),
        tooltip=["Step", alt.Tooltip("Value:Q", format=".1f", title="% points")],
    ).properties(height=320)
