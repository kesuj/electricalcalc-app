"""Wiring drawings of the user's exact home system, as plain SVG strings.

The same SVG is shown on the website and embedded in the PDF (fpdf2 renders SVG), so it uses only
basic elements (rect, line, polyline, circle, text, path), no CSS or markers, and Latin-1 text
(the PDF's core font cannot draw characters such as − or →).
Colours: + red, − black, earth green dashed; AC: L brown, N blue, PE green/yellow (IEC, used in Nepal).
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

RED, BLACK, EARTH, BLUE_N, BROWN_L = "#d1495b", "#222222", "#2e9e5b", "#1f5fbf", "#8b4513"
INK, FILL, PANEL, BATT, NOTE = "#1f4e79", "#eaf2fb", "#dbe9f7", "#e3f4e8", "#555555"
WIDTH = 680          # px; drawn at ~180 mm on A4
FONT = "Helvetica"


def _latin1(text: str) -> str:
    text = (str(text).replace("−", "-").replace("→", "->").replace("←", "<-").replace("≥", ">=").replace("≤", "<=")
            .replace("–", "-").replace("—", "-").replace("Σ", "sum ").replace("≈", "~"))
    return text.encode("latin-1", "replace").decode("latin-1")


class _Svg:
    def __init__(self, height: int, width: int = WIDTH):
        self.w, self.h, self.parts = width, height, []

    def rect(self, x, y, w, h, fill=FILL, stroke=INK, sw=1.2, ident=None, rx=4):
        idattr = f' id="{ident}"' if ident else ""
        self.parts.append(f'<rect{idattr} x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
                          f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1, y1, x2, y2, color=INK, sw=1.6, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
                          f'stroke-width="{sw}"{d}/>')

    def poly(self, pts, color=INK, sw=1.6, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.parts.append(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{sw}"{d}/>')

    def dot(self, x, y, r=3.5, color=INK):
        self.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" stroke="{color}" stroke-width="1"/>')

    def text(self, x, y, s, size=10, color=BLACK, anchor="start", bold=False):
        w = ' font-weight="bold"' if bold else ""
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" fill="{color}" '
                          f'text-anchor="{anchor}"{w}>{escape(_latin1(s))}</text>')

    def lines(self, x, y, rows, size=10, color=BLACK, anchor="start", bold=False, step=None):
        for i, r in enumerate(rows):
            self.text(x, y + i * (step or size * 1.3), r, size, color, anchor, bold)

    def arrow(self, x1, y1, x2, y2, color=INK, sw=1.6):
        """Straight arrow with a hand-drawn head (no SVG markers)."""
        self.line(x1, y1, x2, y2, color, sw)
        a = math.atan2(y2 - y1, x2 - x1)
        p1 = (x2 - 8 * math.cos(a - 0.4), y2 - 8 * math.sin(a - 0.4))
        p2 = (x2 - 8 * math.cos(a + 0.4), y2 - 8 * math.sin(a + 0.4))
        self.parts.append(f'<path d="M {x2:.1f} {y2:.1f} L {p1[0]:.1f} {p1[1]:.1f} L {p2[0]:.1f} {p2[1]:.1f} Z" '
                          f'fill="{color}" stroke="{color}" stroke-width="1"/>')

    def box(self, x, y, w, h, title, rows=(), fill=FILL, ident=None, size=10):
        self.rect(x, y, w, h, fill=fill, ident=ident)
        self.text(x + w / 2, y + 15, title, size + 1, INK, "middle", True)
        self.lines(x + w / 2, y + 29, list(rows), size - 1, BLACK, "middle")

    def svg(self) -> str:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}">'
                f'<rect x="0" y="0" width="{self.w}" height="{self.h}" fill="#ffffff" stroke="none"/>'
                + "".join(self.parts) + "</svg>")


def _fmt(v, nd=0) -> str:
    try:
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


# ---- 1. panels: series strings and parallel strings -------------------------------------------
def panel_strings_svg(n_series: int, n_parallel: int, panel_label: str, string_voc_cold: float, string_vmp: float,
                      isc: float, cable_mm2: float, fuse_a: float | None = None) -> str:
    """Each panel has − on the left and + on the right. In a string, + of one panel goes to − of the next
    (series: voltages add). Strings are joined + to + and − to − at the combiner / isolator (parallel: currents add)."""
    n_series, n_parallel = max(1, int(n_series)), max(1, int(n_parallel))
    per_row = min(n_series, 8)
    rows_per_string = -(-n_series // per_row)
    pw, ph, gap = 50, 34, 14
    x0, top = 30, 92
    string_h = rows_per_string * (ph + 30) + 24
    bus_x = x0 + per_row * (pw + gap) + 30
    height = top + n_parallel * string_h + 150
    s = _Svg(int(height))
    vmp_panel = string_vmp / n_series
    s.text(10, 18, "How to connect your panels", 14, INK, bold=True)
    s.lines(10, 36, [
        f"Each string: {n_series} panel(s) in SERIES (+ of one panel to - of the next): voltages add, "
        f"{n_series} x {vmp_panel:.1f} V = {string_vmp:.0f} V working (up to {string_voc_cold:.0f} V on a cold morning).",
        f"Current stays the same through a string: about {isc:.1f} A maximum (Isc)."
        + (f"  {n_parallel} strings in PARALLEL (+ to +, - to -): currents add, {n_parallel} x {isc:.1f} A = "
           f"{n_parallel * isc:.1f} A; voltage stays {string_vmp:.0f} V." if n_parallel > 1 else ""),
        f"Panel: {panel_label}.  Cable: {cable_mm2:g} mm2 solar cable, red for +, black for -."], 9.5, BLACK, step=14)
    plus_ends, minus_ends = [], []
    for j in range(n_parallel):
        sy = top + j * string_h
        s.text(x0, sy + 10, f"String {j + 1}", 10, INK, bold=True)
        prev_plus = None
        first_minus = None
        for k in range(n_series):
            r, c = divmod(k, per_row)
            px, py = x0 + c * (pw + gap), sy + 18 + r * (ph + 30)
            s.rect(px, py, pw, ph, fill=PANEL, ident=f"panel_{j + 1}_{k + 1}", rx=2)
            for gx in (px + pw / 3, px + 2 * pw / 3):
                s.line(gx, py + 2, gx, py + ph - 2, "#9bb7d4", 0.8)
            s.text(px + pw / 2, py + ph / 2 + 4, f"P{k + 1}", 9, INK, "middle", True)
            mx, my, plx, ply = px + 4, py + ph + 6, px + pw - 4, py + ph + 6
            s.dot(mx, my, 3.5, BLACK); s.text(mx, my + 13, "-", 11, BLACK, "middle", True)
            s.dot(plx, ply, 3.5, RED); s.text(plx, ply + 13, "+", 11, RED, "middle", True)
            if prev_plus is None:
                first_minus = (mx, my)
            else:
                if prev_plus[1] == my:
                    s.poly([prev_plus, (prev_plus[0], my + 8), (mx, my + 8), (mx, my)], RED, 1.6)
                else:   # wrap to next row of the same string
                    s.poly([prev_plus, (prev_plus[0], prev_plus[1] + 10), (x0 - 12, prev_plus[1] + 10),
                            (x0 - 12, my + 8), (mx, my + 8), (mx, my)], RED, 1.6)
            prev_plus = (plx, ply)
        plus_ends.append(prev_plus)
        minus_ends.append(first_minus)
        lead_y = sy + 18 + rows_per_string * (ph + 30) - 4
        s.poly([prev_plus, (prev_plus[0], prev_plus[1] + 4), (bus_x - 30, prev_plus[1] + 4), (bus_x, prev_plus[1] + 4)],
               RED, 2)
        s.poly([first_minus, (first_minus[0] - 10, first_minus[1]), (first_minus[0] - 10, lead_y),
                (bus_x + 20, lead_y)], BLACK, 2)
        if fuse_a:
            fx = bus_x - 26
            s.rect(fx, prev_plus[1] - 2, 18, 12, fill="#fff3d6", stroke=RED, sw=1, rx=1)
            s.text(fx + 9, prev_plus[1] - 6, f"{fuse_a:g} A", 8, RED, "middle")
        plus_ends[-1] = (bus_x, prev_plus[1] + 4)
        minus_ends[-1] = (bus_x + 20, lead_y)
    # combiner busbars (parallel) and onward to isolator / inverter
    y_top = min(p[1] for p in plus_ends) - 8
    y_bot = max(m[1] for m in minus_ends) + 8
    s.line(bus_x, y_top, bus_x, y_bot - 12, RED, 3)
    s.line(bus_x + 20, y_top + 10, bus_x + 20, y_bot, BLACK, 3)
    label = "Combiner (parallel point)" if n_parallel > 1 else "String ends"
    s.text(bus_x - 4, y_top - 6, label, 9, NOTE)
    iso_x, iso_y = min(bus_x + 60, WIDTH - 210), y_bot + 20
    s.box(iso_x, iso_y, 190, 52, "DC isolator + DC SPD", ["switch OFF before touching wires"], fill="#fff3d6")
    s.poly([(bus_x, y_bot - 12), (bus_x, iso_y + 18), (iso_x, iso_y + 18)], RED, 2)
    s.poly([(bus_x + 20, y_bot), (bus_x + 20, iso_y + 36), (iso_x, iso_y + 36)], BLACK, 2)
    inv_y = iso_y + 80
    s.box(iso_x, inv_y, 190, 44, "Inverter / controller PV input", ["PV+ (red)    PV- (black)"])
    s.arrow(iso_x + 70, iso_y + 52, iso_x + 70, inv_y, RED, 2)
    s.arrow(iso_x + 120, iso_y + 52, iso_x + 120, inv_y, BLACK, 2)
    s.lines(10, inv_y + 8, ["Check with a multimeter BEFORE connecting:",
                            f"each string reads no more than {string_voc_cold:.0f} V (Voc) and the",
                            "polarity is right (+ on red). Never join strings with",
                            "different voltages. Panels give power whenever there is light."], 9, NOTE, step=13)
    return s.svg()


# ---- 2. battery bank ---------------------------------------------------------------------------
def battery_bank_svg(n_series: int, n_parallel: int, module_label: str, bank_v: float, bank_kwh: float,
                     cable_mm2: float, fuse_a: float) -> str:
    """Modules in series raise the voltage; series strings in parallel add capacity. Main + is taken from
    the first string and main − from the last string (diagonal take-off, Boxwell §107) so every string
    carries the same current."""
    n_series, n_parallel = max(1, int(n_series)), max(1, int(n_parallel))
    bw, bh, gap = 74, 40, 26
    x0, top = 70, 96
    row_h = bh + 44
    pos_bus_x = x0 + n_series * (bw + gap) + 10
    neg_bus_x = x0 - 30
    height = top + n_parallel * row_h + 200
    s = _Svg(int(height))
    s.text(10, 18, "How to connect your batteries", 14, INK, bold=True)
    mod_v = bank_v / n_series
    s.lines(10, 36, [
        f"{n_series} module(s) in SERIES per string (+ of one to - of the next): {n_series} x {mod_v:g} V = {bank_v:g} V."
        + (f"  {n_parallel} strings in PARALLEL (+ to +, - to -): capacity adds." if n_parallel > 1 else ""),
        f"Bank: {bank_v:g} V, {bank_kwh:.1f} kWh. Module: {module_label}. Cable: {cable_mm2:g} mm2, crimped lugs.",
        "Use the same model and age for every module; make all links the same length; tighten to the datasheet torque."],
        9.5, BLACK, step=14)
    for j in range(n_parallel):
        y = top + j * row_h
        prev = None
        for k in range(n_series):
            bx = x0 + k * (bw + gap)
            s.rect(bx, y, bw, bh, fill=BATT, ident=f"battery_{j + 1}_{k + 1}")
            s.text(bx + bw / 2, y + 24, f"{mod_v:g} V", 10, INK, "middle", True)
            s.dot(bx + 10, y - 4, 4, BLACK); s.text(bx + 10, y - 10, "-", 11, BLACK, "middle", True)
            s.dot(bx + bw - 10, y - 4, 4, RED); s.text(bx + bw - 10, y - 10, "+", 11, RED, "middle", True)
            if prev is not None:
                s.poly([prev, (prev[0], y - 16), (bx + 10, y - 16), (bx + 10, y - 4)], RED, 2)
            prev = (bx + bw - 10, y - 4)
        # string ends to the busbars
        s.poly([prev, (prev[0], y + bh / 2), (pos_bus_x, y + bh / 2)], RED, 2.2)
        s.poly([(x0 + 10, y - 4), (x0 + 10, y + bh + 8), (neg_bus_x, y + bh + 8)], BLACK, 2.2)
        s.text(x0 - 60, y + 24, f"String {j + 1}", 9, NOTE)
    y_first, y_last = top + bh / 2, top + (n_parallel - 1) * row_h + bh + 8
    if n_parallel > 1:
        s.line(pos_bus_x, y_first, pos_bus_x, top + (n_parallel - 1) * row_h + bh / 2, RED, 3)
        s.line(neg_bus_x, top + bh + 8, neg_bus_x, y_last, BLACK, 3)
    # diagonal take-off: + from the first string (top), − from the last string (bottom)
    out_y = top + n_parallel * row_h + 20
    s.poly([(pos_bus_x, y_first), (pos_bus_x + 30, y_first), (pos_bus_x + 30, out_y)], RED, 2.5)
    s.rect(pos_bus_x + 14, out_y, 32, 22, fill="#fff3d6", stroke=RED, rx=2)
    s.text(pos_bus_x + 30, out_y + 15, f"{fuse_a:g} A", 9, RED, "middle", True)
    s.text(pos_bus_x + 52, out_y + 15, "Battery fuse (on + lead, close to the battery)", 9, NOTE)
    s.poly([(neg_bus_x, y_last), (neg_bus_x, out_y + 70)], BLACK, 2.5)
    iso_y = out_y + 50
    s.box(neg_bus_x + 40, iso_y, 230, 46, "Battery isolator / DC breaker", ["switch OFF before any work"],
          fill="#fff3d6")
    tx = min(max(pos_bus_x + 30, neg_bus_x + 70), neg_bus_x + 240)     # enter the isolator from the top
    s.poly([(pos_bus_x + 30, out_y + 22), (pos_bus_x + 30, out_y + 36), (tx, out_y + 36), (tx, iso_y)], RED, 2.5)
    s.poly([(neg_bus_x, out_y + 70), (neg_bus_x + 40, out_y + 70)], BLACK, 2.5)
    inv_y = iso_y + 76
    s.box(neg_bus_x + 40, inv_y, 230, 42, "Inverter battery terminals", ["BAT+ (red)      BAT- (black)"])
    s.arrow(neg_bus_x + 110, iso_y + 46, neg_bus_x + 110, inv_y, RED, 2.2)
    s.arrow(neg_bus_x + 200, iso_y + 46, neg_bus_x + 200, inv_y, BLACK, 2.2)
    if n_parallel > 1:
        s.text(pos_bus_x - 40, y_first - 22, "main + from FIRST string", 9, RED)
        s.text(neg_bus_x + 8, y_last + 22, "main - from LAST string (diagonal, book 107)", 9, BLACK)
    s.text(neg_bus_x + 290, inv_y + 20, "Connect the last link only after", 9, NOTE)
    s.text(neg_bus_x + 290, inv_y + 33, "checking voltage and polarity.", 9, NOTE)
    return s.svg()


# ---- helpers to read the install package --------------------------------------------------------
def _bom(pkg, prefix: str) -> str | None:
    for r in getattr(pkg, "bom", []):
        if str(r.get("Item", "")).startswith(prefix):
            return str(r.get("Specification", ""))
    return None


def _cable(pkg, prefix: str):
    for r in getattr(pkg, "cable_schedule", []):
        if str(r.get("Circuit", "")).startswith(prefix):
            return r
    return None


def _short(spec: str | None, n: int = 34) -> str:
    if not spec:
        return ""
    spec = _latin1(spec)
    return spec if len(spec) <= n else spec[:n - 3].rsplit(" ", 1)[0] + "..."


def _battery_earthed(pkg) -> bool:
    edges = getattr(pkg, "sld", {}).get("edges", [])
    return any("earthed" in str(e.get("label", "") if isinstance(e, dict) else e[2]) for e in edges)


# ---- 3. whole system ---------------------------------------------------------------------------
def system_overview_svg(mode: str, pkg) -> str:
    st = getattr(pkg, "strings", {}) or {}
    pv_c, bat_c, ac_c = _cable(pkg, "PV string"), _cable(pkg, "Battery cable"), _cable(pkg, "Inverter AC")
    pv_mm2 = pv_c["Chosen (mm²)"] if pv_c else "?"
    ac_mm2 = ac_c["Chosen (mm²)"] if ac_c else "?"
    ac_dev = ac_c["Protective device (A)"] if ac_c else "?"
    s = _Svg(700)
    titles = {"grid_tied": "Grid-tied system", "hybrid_backup": "Hybrid system with battery backup",
              "off_grid": "Off-grid system"}
    s.text(10, 18, f"Your whole system - {titles.get(mode, mode)}", 14, INK, bold=True)
    cx = 250
    # PV array
    s.box(cx - 110, 34, 220, 54, "Solar panels (roof)",
          [f"{st.get('panels', '?')} panels = {_fmt(st.get('kwp', 0), 2)} kWp",
           f"{st.get('modules_per_string', '?')} in series x {st.get('strings', '?')} string(s)"], fill=PANEL)
    s.box(cx - 110, 120, 220, 46, "DC isolator + DC SPD",
          [_short(_bom(pkg, "DC isolator"), 36)], fill="#fff3d6")
    s.arrow(cx, 88, cx, 120, RED, 2)
    s.text(cx + 8, 108, f"{pv_mm2} mm2 PV cable (+ red, - black)", 9, NOTE)
    if mode == "off_grid":
        s.box(cx - 110, 196, 220, 46, "MPPT charge controller", [_short(_bom(pkg, "MPPT charge"), 36)])
        s.arrow(cx, 166, cx, 196, RED, 2)
        bat_y, inv_y = 196, 300
        s.box(cx - 110, inv_y, 220, 46, "Off-grid inverter", [_short(_bom(pkg, "Off-grid inverter"), 36)])
    else:
        inv_y = 220
        name = "Hybrid inverter" if mode == "hybrid_backup" else "Grid-tied inverter"
        spec = _bom(pkg, "Hybrid inverter") if mode == "hybrid_backup" else _bom(pkg, "Grid-tied")
        s.box(cx - 110, inv_y, 220, 46, name, [_short(spec, 36)])
        s.arrow(cx, 166, cx, inv_y, RED, 2)
        bat_y = inv_y
    if mode in ("hybrid_backup", "off_grid"):
        bx = 500
        s.box(bx - 20, bat_y - 4, 190, 54, "Battery bank",
              [f"{st.get('battery_series', '?')} S x {st.get('battery_parallel', '?')} P = "
               f"{_fmt(st.get('battery_kwh', 0), 1)} kWh"], fill=BATT)
        s.box(bx - 20, bat_y + 70, 190, 40, "Fuse + battery isolator", [_short(_bom(pkg, "Battery fuse"), 30)],
              fill="#fff3d6")
        s.line(bx + 75, bat_y + 50, bx + 75, bat_y + 70, RED, 2.2)
        mm2 = bat_c["Chosen (mm²)"] if bat_c else "?"
        target_y = (bat_y + 23) if mode == "off_grid" else (inv_y + 23)
        s.poly([(bx - 20, bat_y + 90), (cx + 140, bat_y + 90), (cx + 140, target_y), (cx + 110, target_y)], RED, 2.2)
        s.text(cx + 146, bat_y + 104, f"{mm2} mm2 battery cable", 9, NOTE)
        if mode == "off_grid":
            s.poly([(cx + 110, bat_y + 30), (cx + 125, bat_y + 30), (cx + 125, inv_y + 23), (cx + 110, inv_y + 23)],
                   RED, 2.2)
            s.text(cx + 128, (bat_y + inv_y) / 2 + 30, "battery -> inverter", 9, NOTE)
    ac_y = inv_y + 84
    s.box(cx - 110, ac_y, 220, 46, "AC MCB + RCD 30 mA + AC SPD", [f"MCB {ac_dev} A, cable {ac_mm2} mm2"],
          fill="#fff3d6")
    s.arrow(cx, inv_y + 46, cx, ac_y, BROWN_L, 2)
    s.text(cx + 8, inv_y + 66, "AC: L brown, N blue, PE green/yellow", 9, NOTE)
    db_y = ac_y + 76
    if mode == "hybrid_backup":
        s.box(cx - 110, db_y, 220, 46, "Backup board (power-cut loads)", ["fed through the changeover switch"])
        s.box(30, db_y + 76, 180, 46, "Main distribution board", ["other house loads"])
        s.box(30, db_y + 150, 180, 40, "NEA bidirectional meter", [])
        s.arrow(cx, ac_y + 46, cx, db_y, BROWN_L, 2)
        s.poly([(cx - 130, db_y + 76), (cx - 130, inv_y + 23), (cx - 110, inv_y + 23)], BROWN_L, 2)
        s.text(cx - 226, inv_y + 16, "grid input (AC IN)", 9, NOTE)
        s.line(cx - 130, db_y + 122, cx - 130, db_y + 150, BROWN_L, 2)
        s.text(cx - 125, db_y + 214, "NEA grid 230 V, 50 Hz", 10, INK, bold=True)
        s.line(cx - 130, db_y + 190, cx - 130, db_y + 202, BROWN_L, 2)
    elif mode == "grid_tied":
        s.box(cx - 110, db_y, 220, 46, "Main distribution board", ["house loads"])
        s.box(cx - 110, db_y + 76, 220, 40, "NEA bidirectional meter", ["import / export"])
        s.arrow(cx, ac_y + 46, cx, db_y, BROWN_L, 2)
        s.line(cx, db_y + 46, cx, db_y + 76, BROWN_L, 2)
        s.text(cx, db_y + 140, "NEA grid 230 V, 50 Hz", 10, INK, "middle", True)
        s.line(cx, db_y + 116, cx, db_y + 128, BROWN_L, 2)
    else:
        s.box(cx - 110, db_y, 220, 46, "Distribution board", ["your appliances (no NEA connection)"])
        s.arrow(cx, ac_y + 46, cx, db_y, BROWN_L, 2)
    # earth (dashed green) to the electrode
    ex, ey = 440, 620
    s.rect(ex, ey, 150, 40, fill="#e9f7ee", stroke=EARTH)
    s.text(ex + 75, ey + 16, "Earth electrode", 10, EARTH, "middle", True)
    s.text(ex + 75, ey + 30, "16 mm2 to earth bar", 9, EARTH, "middle")
    bus = 14
    s.poly([(ex, ey + 20), (bus, ey + 20), (bus, 61)], EARTH, 1.6, dash="6,4")
    for (tx, ty) in ((cx - 110, 61), (cx - 110, inv_y + 30), (cx - 110, db_y + 30)):
        s.line(bus, ty, tx, ty, EARTH, 1.6, dash="6,4")
    if mode in ("hybrid_backup", "off_grid") and _battery_earthed(pkg):
        s.poly([(ex + 150, ey + 20), (676, ey + 20), (676, bat_y + 25), (670, bat_y + 25)], EARTH, 1.6, dash="6,4")
        s.text(ex + 75, ey - 8, "battery - earthed (book 109)", 9, EARTH, "middle")
    s.text(10, ey + 60, "Dashed green = earth wires (green/yellow insulation).", 9, NOTE)
    return s.svg()


# ---- 4. earthing -------------------------------------------------------------------------------
def earthing_svg(pkg) -> str:
    frame = _cable(pkg, "PV frame bonding")
    main = _cable(pkg, "Main earthing")
    pe = _cable(pkg, "Inverter / DB protective")
    f_mm2 = frame["Chosen (mm²)"] if frame else 6
    m_mm2 = main["Chosen (mm²)"] if main else 16
    pe_mm2 = pe["Chosen (mm²)"] if pe else "?"
    pit_len = main["Length (m)"] if main else "?"
    s = _Svg(420)
    s.text(10, 18, "How to earth your system", 14, INK, bold=True)
    s.lines(10, 36, ["All metal parts and the earth bar connect to ONE earth electrode. Use green/yellow cable only.",
                     "Measure the earth resistance after installation and write it in the test record."], 9.5, step=14)
    bar_x, bar_y = 250, 210
    s.rect(bar_x, bar_y, 180, 22, fill="#e9f7ee", stroke=EARTH)
    s.text(bar_x + 90, bar_y + 15, "Main earth bar (in DB)", 10, EARTH, "middle", True)
    items = [("Panel frames + rails", f"{f_mm2} mm2 bonding", 40, 80),
             ("Inverter PE terminal", f"{pe_mm2} mm2 PE", 250, 80),
             ("DB / sockets PE", "existing PE bar", 470, 80)]
    if _battery_earthed(pkg):
        items.append(("Battery negative", "per book 109 / maker", 470, 140))
    for name, size, x, y in items:
        s.rect(x, y, 170, 40, fill=FILL)
        s.text(x + 85, y + 17, name, 10, INK, "middle", True)
        s.text(x + 85, y + 31, size, 9, EARTH, "middle")
        s.poly([(x + 85, y + 40), (x + 85, bar_y - 12), (bar_x + 90, bar_y - 12), (bar_x + 90, bar_y)], EARTH, 2,
               dash="6,4")
    # ground, pit and rod
    gy = 320
    s.line(20, gy, WIDTH - 20, gy, "#8a6d3b", 2)
    for gx in range(30, WIDTH - 20, 18):
        s.line(gx, gy, gx - 8, gy + 8, "#8a6d3b", 1)
    s.rect(300, gy - 18, 80, 18, fill="#f4f4f4", stroke=NOTE, rx=1)
    s.text(340, gy - 6, "Earth pit", 9, NOTE, "middle")
    s.line(340, gy, 340, gy + 90, EARTH, 6)
    s.text(352, gy + 50, "Earth rod (electrode)", 10, EARTH, bold=True)
    s.text(352, gy + 64, "drive into moist soil", 9, NOTE)
    s.poly([(bar_x + 90, bar_y + 22), (bar_x + 90, gy - 30), (340, gy - 30), (340, gy - 18)], EARTH, 3)
    s.text(bar_x + 96, bar_y + 60, f"Main earth conductor {m_mm2} mm2, about {pit_len} m", 10, EARTH, bold=True)
    return s.svg()


# ---- 5. inverter terminals -----------------------------------------------------------------------
def inverter_terminals_svg(mode: str) -> str:
    groups = {
        "grid_tied": [("PV input", [("PV1+", RED), ("PV1-", BLACK), ("PV2+", RED), ("PV2-", BLACK)]),
                      ("AC output to grid", [("L", BROWN_L), ("N", BLUE_N), ("PE", EARTH)])],
        "hybrid_backup": [("PV", [("PV+", RED), ("PV-", BLACK)]), ("Battery", [("BAT+", RED), ("BAT-", BLACK)]),
                          ("GRID in", [("L", BROWN_L), ("N", BLUE_N), ("PE", EARTH)]),
                          ("LOAD / BACKUP", [("L", BROWN_L), ("N", BLUE_N), ("PE", EARTH)])],
        "off_grid": [("Battery", [("BAT+", RED), ("BAT-", BLACK)]),
                     ("AC OUT to loads", [("L", BROWN_L), ("N", BLUE_N), ("PE", EARTH)])],
    }[mode]
    s = _Svg(330 if mode != "off_grid" else 430)
    s.text(10, 18, "Inverter terminals - what goes where", 14, INK, bold=True)
    s.rect(60, 34, 560, 170, fill="#f7f9fc")
    s.rect(90, 50, 140, 60, fill="#dfe8f2", rx=2)
    s.text(160, 85, "display", 9, NOTE, "middle")
    s.text(340, 75, {"grid_tied": "Grid-tied inverter", "hybrid_backup": "Hybrid inverter",
                     "off_grid": "Off-grid inverter"}[mode], 13, INK, "middle", True)
    x = 80
    for gname, terms in groups:
        gw = len(terms) * 42
        s.rect(x - 6, 140, gw + 4, 56, fill="#ffffff", stroke=NOTE, sw=0.8, rx=2)
        s.text(x - 6 + (gw + 4) / 2, 136, gname, 9, INK, "middle", True)
        for i, (t, col) in enumerate(terms):
            tx = x + i * 42 + 16
            s.dot(tx, 166, 9, col)
            s.text(tx, 190, t, 9, col if col != EARTH else EARTH, "middle", True)
        x += gw + 14
    y = 226
    s.lines(10, y, ["Colours: DC + red, DC - black.  AC: L (line) brown, N (neutral) blue, PE (earth) green/yellow.",
                    "Check YOUR model's manual: terminal positions and labels vary between makes.",
                    "Connect in this order: earth (PE) first, then battery, then AC, then PV last; switch on battery -> inverter -> PV."],
            9.5, BLACK, step=15)
    if mode == "off_grid":
        s.rect(60, 290, 300, 100, fill="#f7f9fc")
        s.text(210, 312, "MPPT charge controller", 12, INK, "middle", True)
        for i, (t, col) in enumerate([("PV+", RED), ("PV-", BLACK), ("BAT+", RED), ("BAT-", BLACK)]):
            tx = 100 + i * 64
            s.dot(tx, 345, 9, col)
            s.text(tx, 372, t, 9, col, "middle", True)
        s.text(380, 330, "Connect the controller to the battery FIRST,", 9, NOTE)
        s.text(380, 344, "then the panels (most controllers need battery", 9, NOTE)
        s.text(380, 358, "voltage to start).", 9, NOTE)
    return s.svg()


# ---- solar farm: one drawing from strings to the NEA substation -------------------------------------------
def farm_sld_svg(pkg, n_series: int, string_voc_cold: float, string_vmp: float, module_wp: float,
                 inverter_kva: float) -> str:
    """Single-line wiring of a solar farm block: strings -> inverters -> AC combiner -> transformer ->
    11/33 kV switchgear -> NEA metering -> line -> NEA substation, with cable sizes and protection."""
    h = pkg.hierarchy or {}
    sched = {r["Level"]: r for r in pkg.cable_schedule}
    dc = next((r for k, r in sched.items() if k.startswith("PV string")), {})
    lv = next((r for k, r in sched.items() if k.startswith("Inverter AC")), {})
    line = next((r for k, r in sched.items() if k.startswith("Line to NEA")), {})
    n_inv = pkg.counts["inverters"]["value"]
    spi = h.get("strings_per_inverter", "?")
    n_str = pkg.counts["strings"]["value"]
    blk = pkg.blocks[0] if pkg.blocks else {}
    mv_kv = pkg.counts.get("mv_kv", {}).get("value", 11)
    fuse = next((r for r in pkg.boq if str(r.get("Item", "")).startswith("String fuses")), None)
    s = _Svg(860)
    s.text(20, 24, _latin1(f"Solar farm wiring - {pkg.counts['mwp_actual']['value']:g} MWp, {n_inv} inverters x "
                           f"{inverter_kva:g} kVA, {mv_kv:g} kV connection"), 13, INK, bold=True)
    # strings
    s.text(20, 52, _latin1(f"1. STRINGS: {n_series} panels in SERIES ({n_series} x {module_wp:g} W). "
                           f"{n_str} strings in total, {spi} per inverter (PARALLEL at the inverter inputs)."), 10, BLACK)
    x0 = 30
    for j in range(2):
        y = 70 + j * 46
        for i in range(6):
            s.rect(x0 + i * 52, y, 44, 26, fill=PANEL, ident=f"farm_panel_{j}_{i}")
            s.text(x0 + i * 52 + 22, y + 17, "PV", 9, INK, "middle")
            if i < 5:
                s.line(x0 + i * 52 + 44, y + 13, x0 + (i + 1) * 52, y + 13, RED, 1.6)
        s.text(x0 + 6 * 52 + 4, y + 17, _latin1(f"... {n_series} in series"), 9, NOTE)
        s.line(x0 + 6 * 52 + 110, y + 13, 470, y + 13, RED, 2)
        s.line(x0 - 6, y + 13, x0, y + 13, BLACK, 2)
    s.text(x0, 176, _latin1(f"(only 2 of the {spi} strings per inverter drawn)  String: {string_vmp:,.0f} V working, up to "
                            f"{string_voc_cold:,.0f} V on the coldest morning."), 9, NOTE)
    s.box(470, 66, 190, 96, "Inverter DC inputs (MPPTs)",
          [_latin1(f"{dc.get('Selected', '4 mm2 Cu')} solar cable"),
           _latin1(f"string fuse {fuse['Specification'].split(',')[0]}" if fuse else "no string fuse needed (<3 per input)"),
           "DC switch inside inverter", "DC SPD Type 2 at input"], fill="#fff3d6")
    # inverters
    s.text(20, 210, _latin1(f"2. INVERTERS: {n_inv} x {inverter_kva:g} kVA string inverters, 3-phase "
                            f"{lv.get('Voltage (V)', 800)} V AC output, on frames between table rows."), 10, BLACK)
    for i in range(min(n_inv, 4)):
        s.box(30 + i * 150, 224, 130, 46, f"Inverter {i + 1 if i < 3 or n_inv == 4 else n_inv}",
              [_latin1(f"{inverter_kva:g} kVA, {spi} strings")], size=9)
    if n_inv > 4:
        s.text(30 + 3 * 150 - 12, 252, "...", 14, INK, "middle", True)
    for i in range(min(n_inv, 4)):
        s.line(95 + i * 150, 270, 95 + i * 150, 300, BROWN_L, 2)
    s.line(95, 300, 95 + (min(n_inv, 4) - 1) * 150, 300, BROWN_L, 2)
    s.text(560, 292, _latin1(f"{lv.get('Selected', '')} 3-ph + PE"), 9, NOTE)
    s.text(560, 304, _latin1(f"{lv.get('Conductor length (km, est.)', '?')} km in total"), 9, NOTE)
    # AC combiner
    s.arrow(320, 300, 320, 330, BROWN_L, 2)
    s.box(200, 330, 240, 48, "3. AC combiner board (LV)",
          [_latin1(f"{n_inv} x {lv.get('Protective device (A)', '?')} A breakers, busbar, AC SPD")], fill="#fff3d6")
    s.arrow(320, 378, 320, 408, BROWN_L, 2.4)
    tx = blk.get("Transformer (kVA)", "?")
    s.box(200, 408, 240, 56, "4. Step-up transformer",
          [_latin1(f"{tx} kVA, {blk.get('Ratio', '0.8/11 kV')}, ONAN, Dyn11"), "neutral and tank to earth mesh"])
    s.arrow(320, 464, 320, 494, INK, 2.4)
    s.box(200, 494, 240, 56, _latin1(f"5. {mv_kv:g} kV switchgear (RMU / VCB)"),
          ["overcurrent + earth-fault relays", "anti-islanding / grid protection"], fill="#fff3d6")
    s.arrow(320, 550, 320, 580, INK, 2.4)
    s.box(200, 580, 240, 48, "6. NEA revenue metering", ["CT/PT metering panel (NEA approved)"])
    s.arrow(320, 628, 320, 668, INK, 2.4)
    s.text(332, 652, _latin1(f"{mv_kv:g} kV line {line.get('Conductor length (km, est.)', '?')} km"), 9, NOTE)
    s.box(200, 668, 240, 44, "7. NEA substation", ["connection agreement + PPA"])
    # earth
    s.poly([(470, 436), (560, 436), (560, 790)], EARTH, 1.8, dash="6,4")
    s.poly([(30, 270), (30, 790), (560, 790)], EARTH, 1.8, dash="6,4")
    s.box(450, 760, 210, 44, "Earth mesh + electrodes", ["frames, inverters, transformer"], fill=BATT)
    s.text(20, 740, "Legend: red = DC +, black = DC -, brown = AC phase conductors, green dashed = earth.", 9, NOTE)
    s.text(20, 754, _latin1("Every inverter, table frame, fence and the transformer are bonded to one earth system."), 9, NOTE)
    return s.svg()
