"""Build the public website (GitHub Pages) into site/.

  site/index.html      landing page with the worked examples (off-grid home, 500 kW and 1 MW farms)
  site/guide.html      Nepal solar PV component guide (from reports/)
  site/app/            the full app running inside the visitor's browser (stlite = Streamlit on Pyodide)
  site/samples/        example PDF reports
Run:  python scripts/build_site.py      then open site/index.html (or serve: python -m http.server -d site)
"""
from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import site_examples as ex  # noqa: E402

from ecalc import config  # noqa: E402
from ecalc.guide.requirement import with_requirement  # noqa: E402

SITE = ROOT / "site"
STLITE = "1.12.0"
REPO = "https://github.com/kesuj/electricalcalc-app"
GUIDE_MD = ROOT / "reports" / "Nepal solar PV component guide.md"
SAMPLES = ["OFFGRID_small_home_Jumla.pdf", "HOME_installation_report_Biratnagar.pdf",
           "FARM_500kW_cost_and_wiring.pdf", "FARM_1MW_cost_and_wiring.pdf",
           "FARM_construction_package_Nepalgunj_10MW.pdf"]
REQUIREMENTS = ["fpdf2", "altair", "pandas", "requests", "python-dotenv"]

CSS = """
:root{--bg:#f6f8fb;--surface:#fff;--ink:#111a2b;--muted:#566175;--line:#e2e7ef;--brand:#16406b;--brand-ink:#fff;
--sun:#f2a516;--sun-soft:#fff4dc;--ok:#1d7a4f;--warn:#a55a00;--code:#eef2f7;--shadow:0 1px 2px rgba(16,24,40,.06),0 4px 16px rgba(16,24,40,.06)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d131d;--surface:#151e2c;--ink:#e7edf6;--muted:#9aa7bb;
--line:#253247;--brand:#8ab8ea;--brand-ink:#0d131d;--sun:#f5b93a;--sun-soft:#2a2414;--ok:#5fd09a;--warn:#f0a548;--code:#1c2738;--shadow:none}}
:root[data-theme="dark"]{--bg:#0d131d;--surface:#151e2c;--ink:#e7edf6;--muted:#9aa7bb;--line:#253247;--brand:#8ab8ea;--brand-ink:#0d131d;
--sun:#f5b93a;--sun-soft:#2a2414;--ok:#5fd09a;--warn:#f0a548;--code:#1c2738;--shadow:none}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 "Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--brand)}img,svg{max-width:100%;height:auto}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
nav.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
nav.top .wrap{display:flex;align-items:center;gap:20px;height:58px}
.logo{font-weight:800;text-decoration:none;color:var(--ink);display:flex;gap:8px;align-items:center;white-space:nowrap}
.logo span{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:8px;background:var(--sun);color:#111}
nav.top .links{display:flex;gap:18px;margin-left:auto;overflow-x:auto}
nav.top .links a{color:var(--muted);text-decoration:none;font-size:.94rem;white-space:nowrap}nav.top .links a:hover{color:var(--ink)}
.hero{padding:72px 0 40px}
.eyebrow{display:inline-block;background:var(--sun-soft);color:var(--warn);font-weight:600;font-size:.82rem;padding:4px 10px;border-radius:99px}
h1{font-size:clamp(30px,5.4vw,52px);line-height:1.08;letter-spacing:-.02em;margin:16px 0 14px;max-width:820px}
.lead{font-size:clamp(1.05rem,2vw,1.22rem);color:var(--muted);max-width:700px;margin:0}
.btns{display:flex;flex-wrap:wrap;gap:12px;margin-top:28px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 20px;border-radius:10px;font-weight:650;text-decoration:none;border:1px solid var(--line);color:var(--ink);background:var(--surface)}
.btn.primary{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}
.facts{display:flex;flex-wrap:wrap;gap:10px 28px;margin-top:28px;color:var(--muted);font-size:.93rem}
.facts b{color:var(--ink)}
section{padding:44px 0;border-top:1px solid var(--line)}
h2{font-size:clamp(24px,3.4vw,32px);letter-spacing:-.01em;margin:0 0 8px}
h3{margin:0 0 6px;font-size:1.12rem}
.sub{color:var(--muted);margin:0 0 24px;max-width:720px}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:var(--shadow)}
.card p{margin:0;color:var(--muted)}.card ul{margin:8px 0 0;padding-left:18px;color:var(--muted)}
.icon{font-size:1.6rem;line-height:1;margin-bottom:10px}
.steps{counter-reset:s;display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.steps .card:before{counter-increment:s;content:counter(s);display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--sun);color:#111;font-weight:800;margin-bottom:10px}
.kpis{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));margin:18px 0}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .v{font-size:1.45rem;font-weight:750;letter-spacing:-.01em}.kpi .l{color:var(--muted);font-size:.86rem}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface);margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--code);font-weight:650;white-space:nowrap}tr:last-child td{border-bottom:0}
td.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
tr.total td{font-weight:750;background:var(--sun-soft)}
.basis{color:var(--muted);font-size:.8rem}
.tag{display:inline-block;font-size:.75rem;font-weight:650;padding:2px 8px;border-radius:99px;white-space:nowrap}
.tag.law{background:#fde7e7;color:#9b1c1c}.tag.safe{background:#fff1d6;color:#8a4b00}.tag.rec{background:#e3f1ff;color:#134a85}.tag.opt{background:#e8f6ee;color:#16603d}
:root[data-theme="dark"] .tag,.dark .tag{filter:none}
.drawing{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px;margin:12px 0;overflow-x:auto}
.drawing svg{display:block;margin:0 auto;min-width:560px}
figure{margin:0}figcaption{font-weight:650;margin:18px 0 4px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 16px}
.tabs button{font:inherit;padding:8px 16px;border-radius:99px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer}
.tabs button[aria-selected="true"]{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}
.panel[hidden]{display:none}
.note{border-left:4px solid var(--sun);background:var(--sun-soft);padding:12px 16px;border-radius:0 10px 10px 0;margin:16px 0;color:var(--ink)}
details{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:10px 0}
details summary{cursor:pointer;font-weight:650}
.wire li{margin:6px 0}
footer{padding:36px 0 56px;color:var(--muted);font-size:.9rem;border-top:1px solid var(--line)}
.prose{max-width:820px}.prose h1{font-size:clamp(28px,4.5vw,40px)}.prose h2{margin-top:44px;padding-top:12px;border-top:1px solid var(--line)}
.prose h3{margin-top:28px}.prose table{font-size:.86rem}.prose code{background:var(--code);padding:1px 5px;border-radius:5px}
.prose .tablewrap table{margin:0}
.toc{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:18px 0}
.toc ul{margin:0;padding-left:18px}
@media (max-width:640px){nav.top .links{gap:14px}.hero{padding-top:44px}}
"""

THEME_JS = """<script>try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}catch(e){}</script>"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def page(title: str, desc: str, body: str, active: str = "") -> str:
    def link(href, label, key):
        cur = ' aria-current="page" style="color:var(--ink);font-weight:650"' if key == active else ""
        return f'<a href="{href}"{cur}>{label}</a>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%9A%A1%3C/text%3E%3C/svg%3E">
{THEME_JS}<style>{CSS}</style></head><body>
<nav class="top"><div class="wrap"><a class="logo" href="index.html"><span>⚡</span>{esc(config.APP_NAME)}</a>
<div class="links">{link("index.html#tools", "Tools", "tools")}{link("index.html#examples", "Examples", "examples")}
{link("guide.html", "Component guide", "guide")}{link("index.html#reports", "Sample reports", "reports")}
{link("app/", "Open the app →", "app")}</div></div></nav>
{body}
<footer><div class="wrap">
<p><b>{esc(config.APP_NAME)}</b> - free, open-source solar design for Nepal. Code: <a href="{REPO}">{REPO.replace("https://", "")}</a>.</p>
<p>Every report is a <b>preliminary calculation</b>, not a certified, approved or stamped design. Prices are indicative
(2026) and marked with their source; get supplier quotes before you buy. Grid connection needs NEA approval. This site
gives engineering information only - not legal, tax or financial advice.</p>
<p>Sunshine data: PVGIS v5.3 © European Union (JRC). Standards quoted: NEPQA-2025 (AEPC), IEC 62548, IEC 60364, IEC 62446.</p>
</div></footer></body></html>"""


def table(rows: list[dict], cols: list[str] | None = None, num: tuple[str, ...] = (), total: dict | None = None,
          fmt=None) -> str:
    if not rows:
        return ""
    cols = cols or list(rows[0])
    out = ["<div class='tablewrap'><table><thead><tr>", *[f"<th>{esc(c)}</th>" for c in cols], "</tr></thead><tbody>"]
    for r in rows + ([total] if total else []):
        cls = " class='total'" if r is total else ""
        out.append(f"<tr{cls}>")
        for c in cols:
            v = r.get(c, "")
            v = fmt(c, v) if fmt else esc(v)
            out.append(f"<td class='n'>{v}</td>" if c in num else f"<td>{v}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def tag(level: str) -> str:
    cls = {"Compulsory (law / NEA)": "law", "Compulsory (safety)": "safe", "Strongly recommended": "rec"}.get(level, "opt")
    return f"<span class='tag {cls}'>{esc(level)}</span>"


def drawing(title: str, svg: str) -> str:
    return f"<figure><figcaption>{esc(title)}</figcaption><div class='drawing'>{svg}</div></figure>"


# ---------------------------------------------------------------------------------------------------------------
def offgrid_block(h: dict) -> str:
    o = h["design"].outputs
    loads = "".join(f"<li>{q} × {esc(r['name'])} ({r['power_w']:g} W) for {r['hours_per_day']:g} h a day</li>"
                    for r, q in ((r, r["qty"]) for r in h["loads"]))
    bom = with_requirement(h["pkg"].bom, "off_grid")
    bom_html = table(bom, ["Item", "Compulsory or optional?", "Specification", "Qty"],
                     fmt=lambda c, v: tag(v) if c == "Compulsory or optional?" else esc(v))
    cables = table(h["pkg"].cable_schedule, ["Circuit", "From → To", "Length (m)", "Design current (A)",
                                             "Protective device (A)", "Chosen (mm²)", "Voltage drop (%)"],
                   num=("Length (m)", "Design current (A)", "Protective device (A)", "Chosen (mm²)", "Voltage drop (%)"))
    st_ = h["pkg"].strings or {}
    draw = "".join(drawing(t, s) for t, s in h["svgs"])
    kpi = lambda v, l: f"<div class='kpi'><div class='v'>{v}</div><div class='l'>{l}</div></div>"  # noqa: E731
    return f"""
<h3>Small off-grid home in Jumla (Karnali) - no NEA line</h3>
<p class="sub">A family with no grid connection wants lights, a TV, phone charging, a laptop and Wi-Fi, and power for
<b>2 days without sun</b>. Jumla is cold (record low about −15 °C), so the battery lives indoors.</p>
<div class="grid"><div class="card"><h3>What they use</h3><ul>{loads}</ul>
<p style="margin-top:8px">Total about <b>{o['daily_wh'].value:,.0f} Wh a day</b> (≈ {o['daily_wh'].value * 30 / 1000:.0f} units a month).</p></div>
<div class="card"><h3>What the app designed</h3><ul>
<li><b>{o['installed_w'].value / 550:.0f} × 550 W panel</b> on a metal frame tilted {round(ex.NEPAL_SITES['Jumla'][0])}° facing south</li>
<li><b>MPPT charge controller</b> (NEPQA-2025 allows PWM only below 20 A; MPPT harvests more in the cold)</li>
<li><b>LiFePO4 battery {o['system_v'].value} V</b>, about {o['battery_ah'].value:.0f} Ah ({o['battery_kwh_nominal'].value:.1f} kWh) with BMS - kept indoors above 5 °C</li>
<li><b>Pure-sine inverter</b> of at least {o['inverter_w'].value:.0f} W continuous (the smallest common size, 500 VA-1 kVA, is fine)</li>
<li>Fuse at the battery, DC isolator, DC surge protector, AC breaker + 30 mA RCD, 2 earth pits</li></ul></div></div>
<div class="kpis">{kpi(f"{o['installed_w'].value:,.0f} W", "panels")}{kpi(f"{o['battery_kwh_nominal'].value:.1f} kWh", "LiFePO4 battery")}
{kpi(f"{o['system_v'].value} V", "battery voltage")}{kpi(f"Rs {h['capex']:,.0f}", "indicative cost (get quotes)")}</div>
<h3>Detailed wiring</h3>
<ol class="wire">
<li><b>Panel → controller:</b> the panel's MC4 leads go on {st_.get('modules_per_string', 1)} string of solar cable (4 mm² H1Z2Z2-K, red +, black −)
down to a <b>DC isolator</b> and a <b>DC surge protector</b>, then into the MPPT controller's PV terminals. Cover the panel while wiring - it is live in daylight.</li>
<li><b>Battery first:</b> connect the controller's battery terminals to the battery <b>through the battery fuse</b> (fuse within 30 cm of the battery +) and isolator.
Always connect the battery to the controller <i>before</i> the panel, and disconnect the panel first.</li>
<li><b>Battery → inverter:</b> short, thick cables (size in the cable table) from the same battery bus, through the fuse/isolator.</li>
<li><b>Inverter → house:</b> inverter AC output → AC breaker → 30 mA RCD → the house circuits (brown live, blue neutral, green-yellow earth).</li>
<li><b>Earthing:</b> panel frame, mounting frame, controller and inverter cases → earth bar → two earth pits (≤ 10 Ω, AEPC spec).</li></ol>
{draw}
<details><summary>Shopping list with "compulsory or optional in Nepal" ({len(bom)} items)</summary>{bom_html}</details>
<details><summary>Cables, fuses and breakers</summary>{cables}</details>
<p><a class="btn" href="samples/OFFGRID_small_home_Jumla.pdf">⬇ Full off-grid report (PDF) - parts explained, installation steps, tests</a></p>
"""


def farm_block(f: dict) -> str:
    c, pkg = f["cost"], f["pkg"]
    cnt = {k: v["value"] for k, v in pkg.counts.items()}
    rows = c.tables["Cost breakdown"]
    tot = {"Item": "Total (incl. engineering/permits and contingency)",
           "Low (NPR lakh)": f"{c.out('total_low_crore') * 100:,.1f}",
           "Central (NPR lakh)": f"{c.out('total_central_crore') * 100:,.1f}",
           "High (NPR lakh)": f"{c.out('total_high_crore') * 100:,.1f}"}

    def fmt(col, v):
        if col == "Item":
            r = next((r for r in rows if r["Item"] == v), None)
            return esc(v) + (f"<div class='basis'>{esc(r['Basis'])}</div>" if r and r.get("Basis") else "")
        if isinstance(v, float):
            return f"{v:,.1f}"
        return esc(v)
    cost_tbl = table(rows, ["Item", "Quantity", "Unit", "Rate (central, NPR)", "Low (NPR lakh)", "Central (NPR lakh)",
                            "High (NPR lakh)"], num=("Quantity", "Rate (central, NPR)", "Low (NPR lakh)",
                                                     "Central (NPR lakh)", "High (NPR lakh)"), total=tot, fmt=fmt)
    sr = f["sr"]
    n_s = int(sr.out("modules_per_string"))
    kpi = lambda v, l: f"<div class='kpi'><div class='v'>{v}</div><div class='l'>{l}</div></div>"  # noqa: E731
    name = "500 kW" if f["mwp"] < 1 else "1 MW"
    pdf = "FARM_500kW_cost_and_wiring.pdf" if f["mwp"] < 1 else "FARM_1MW_cost_and_wiring.pdf"
    return f"""
<div class="kpis">{kpi(f"NPR {c.out('total_central_crore'):.2f} crore", f"central estimate (range {c.out('total_low_crore'):.2f}-{c.out('total_high_crore'):.2f})")}
{kpi(f"NPR {c.out('per_kwp_central'):,.0f}", "per kWp (central)")}{kpi(f"{f['fr'].out('annual_mwh'):,.0f} MWh", "per year (PVGIS, before P90)")}
{kpi(f"{cnt['modules']:,} × 550 W", f"panels = {cnt['mwp_actual'] * 1000:,.0f} kWp")}{kpi(f"{cnt['inverters']} × 100 kVA", "string inverters")}
{kpi(f"{cnt['transformer_kva_total']:,.0f} kVA", "0.8/11 kV transformer")}</div>
<h3>Itemised cost - {name}</h3>{cost_tbl}
<p class="basis">[S] = secondary source, [A] = assumption where no Nepali price was found - replace with quotes. Land, financing and VAT recovery not included.
Land needed about {f['fr'].out('land_ha'):.2f} ha (Nepal projects often use ~2 ha/MW with roads and setbacks).</p>
<h3>Detailed wiring - {name}</h3>
<ol class="wire">
<li><b>Strings:</b> {n_s} panels in series per string (≈ {n_s * ex.MOD.vmp:,.0f} V working, up to {sr.out('string_voc_cold_v'):,.0f} V on the coldest morning - below the 1,100 V inverter limit); {cnt['strings']} strings in total, 4 mm² H1Z2Z2-K solar cable with genuine MC4s.</li>
<li><b>Strings → inverters:</b> up to {-(-cnt['strings'] // cnt['inverters'])} strings into each 100 kVA inverter's MPPT inputs, with gPV string fuses where 3+ strings share an input and a Type 2 DC SPD per inverter.</li>
<li><b>Inverters → AC combiner:</b> each inverter through its own breaker on 70 mm² copper (3-phase 400 V) to the LV panel next to the transformer.</li>
<li><b>Step-up:</b> LV panel → {cnt['transformer_kva_total']:,.0f} kVA 0.8/11 kV ONAN transformer → 11 kV RMU/VCB with protection relays.</li>
<li><b>To the grid:</b> NEA revenue metering → 2 km 11 kV line → NEA substation. Earth mesh joins every frame, inverter, transformer neutral and fence.</li></ol>
{drawing(f"Whole-plant wiring - {name}", f['sld'])}
<p><a class="btn" href="samples/{pdf}">⬇ Full {name} report (PDF) - BOQ, cable schedule, construction steps, tests</a></p>
"""


def index(h: dict, f500: dict, f1: dict) -> str:
    body = f"""
<header class="hero"><div class="wrap">
<span class="eyebrow">Free · Made for Nepal · Runs in your browser</span>
<h1>Design your own solar system - from panel to battery to switch-on.</h1>
<p class="lead">Answer a few plain questions about your home or project. You get a complete report: what to buy, which parts are
compulsory in Nepal, how every wire connects, step-by-step installation, tests, and the cost.</p>
<div class="btns"><a class="btn primary" href="app/">🏠 Design a home system</a><a class="btn" href="app/?page=farm">🏭 Plan a solar farm</a>
<a class="btn" href="guide.html">📘 Component guide</a></div>
<div class="facts"><span><b>27</b> Nepal cities with real PVGIS sunshine data</span><span><b>NEPQA-2025</b> rules built in</span>
<span><b>Every equation</b> shown in the report</span><span><b>No sign-up</b>, nothing leaves your computer</span></div>
</div></header>

<section id="tools"><div class="wrap">
<h2>Two tools, one goal: a system you can install and trust</h2>
<p class="sub">Choose the one that fits. Both ask only what you can answer and explain how to find each number.</p>
<div class="grid">
<div class="card"><div class="icon">🏠</div><h3>Home solar</h3><p>Grid-tied, hybrid with battery backup for load-shedding, or fully off-grid.</p>
<ul><li>Sizes panels, battery, inverter and MPPT from your NEA bill or appliance list</li><li>Month-by-month energy and your NEA bill with solar</li>
<li>Panel strings, battery bank, system and earthing drawings</li><li>Shopping list marked compulsory / optional in Nepal</li></ul>
<p style="margin-top:12px"><a href="app/">Open Home solar →</a></p></div>
<div class="card"><div class="icon">🏭</div><h3>Solar farm</h3><p>Feasibility and construction package for 100 kW to 50 MW plants.</p>
<ul><li>Energy (PVGIS + P90), row spacing, land and layout</li><li>String/inverter matching for cold mornings</li>
<li>BOQ, cable schedule, 11 kV connection, construction steps</li><li>Itemised cost estimate with low/central/high range</li></ul>
<p style="margin-top:12px"><a href="app/?page=farm">Open Solar farm →</a></p></div>
<div class="card"><div class="icon">📘</div><h3>Component guide</h3><p>Every part in plain language: panels, inverters, MPPT vs PWM,
batteries, cables, MC4, protection, earthing, monitoring - with Nepal prices and what is compulsory.</p>
<p style="margin-top:12px"><a href="guide.html">Read the guide →</a></p></div>
</div></div></section>

<section><div class="wrap">
<h2>How it works</h2><p class="sub">Three minutes of questions, then a report you can follow.</p>
<div class="steps">
<div class="card"><h3>Tell it about your site</h3><p>Nearest city (or exact map point), roof type, and what you want: lower bill, backup, or off-grid.</p></div>
<div class="card"><h3>Tell it what you use</h3><p>Units from your NEA bill, or pick your appliances. Hints under every box say how to measure it.</p></div>
<div class="card"><h3>Get your report</h3><p>Sizes, drawings, shopping list, cable sizes, installation steps, tests and money - on screen and as a PDF.</p></div>
<div class="card"><h3>Buy, install, test</h3><p>Check equipment against the NEPQA list, wire it as drawn, run the tests, and apply to NEA before connecting.</p></div>
</div></div></section>

<section id="examples"><div class="wrap">
<h2>Worked examples</h2>
<p class="sub">Real outputs of this app with real PVGIS data - the same thing you get for your own project.</p>
<div class="tabs" role="tablist">
<button role="tab" aria-selected="true" data-p="p1">Off-grid small home</button>
<button role="tab" aria-selected="false" data-p="p2">500 kW solar farm</button>
<button role="tab" aria-selected="false" data-p="p3">1 MW solar farm</button></div>
<div class="panel" id="p1">{offgrid_block(h)}</div>
<div class="panel" id="p2" hidden><h3>500 kW solar farm near Nepalgunj (Banke) - 11 kV, 2 km to the NEA substation</h3>{farm_block(f500)}</div>
<div class="panel" id="p3" hidden><h3>1 MW solar farm near Nepalgunj (Banke) - 11 kV, 2 km to the NEA substation</h3>{farm_block(f1)}</div>
<div class="note">Why is 500 kW dearer per kWp than 1 MW? The transformer, 11 kV switchgear, metering and the 2 km line cost
almost the same for both, so they weigh more on the smaller plant.</div>
</div></section>

<section id="reports"><div class="wrap">
<h2>Sample reports</h2><p class="sub">Download and see exactly what you will get.</p>
<div class="grid">
{''.join(f'<a class="card" style="text-decoration:none;color:inherit" href="samples/{s}"><div class="icon">📄</div><h3>{esc(s.rsplit(".", 1)[0].replace("_", " "))}</h3><p>PDF</p></a>' for s in SAMPLES)}
</div></div></section>

<section><div class="wrap">
<h2>Honest by design</h2>
<div class="grid">
<div class="card"><h3>Calculations are deterministic</h3><p>Every number comes from a formula you can read in the report (Boxwell's Solar Electricity Handbook,
Neill et al.'s Solar Farms, IEC standards) - never from AI guesses.</p></div>
<div class="card"><h3>Sources and dates shown</h3><p>Prices and rules carry their source and date. Assumptions are labelled. Data that could not be verified is said to be unverified.</p></div>
<div class="card"><h3>Know the stop-points</h3><p>The report tells you what NEA must approve, what is compulsory for safety, and when to get help with 230 V wiring.</p></div>
</div></div></section>
<script>
document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>{{
 document.querySelectorAll('.tabs button').forEach(x=>x.setAttribute('aria-selected',x===b));
 document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==b.dataset.p);}}));
</script>"""
    return page(f"{config.APP_NAME} - solar design for Nepal",
                "Free solar PV design for Nepal homes and solar farms: sizing, wiring drawings, shopping list, "
                "installation steps and cost.", body, "tools")


def guide() -> str:
    md = markdown.Markdown(extensions=["tables", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2"}})
    content = md.convert(GUIDE_MD.read_text(encoding="utf-8"))
    content = content.replace("<table>", "<div class='tablewrap'><table>").replace("</table>", "</table></div>")
    body = f"""<main class="wrap"><article class="prose" style="padding:40px 0">
<p class="eyebrow">Researched October 2026 · sources cited inline</p>
<div class="toc"><b>Contents</b>{md.toc}</div>{content}
<div class="note">Use this guide together with your report from the <a href="app/">app</a>. Prices are indicative; standards
and NEA procedures change - confirm with AEPC/NEA before you rely on them.</div></article></main>"""
    return page("Nepal solar component guide", "Which solar panels, inverters, MPPT/PWM controllers, batteries, cables, "
                "connectors, protection and monitoring to buy in Nepal - and which are compulsory.", body, "guide")


def app_files() -> dict[str, str]:
    files = ["app.py"] + sorted(str(p.relative_to(ROOT)).replace("\\", "/") for d in ("ecalc", "ui")
                                for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)
    return {f: f for f in files} | {"offline_pvgis.py": "web/offline_pvgis.py", "pvgis_nepal.json": "web/pvgis_nepal.json",
                                    "streamlit_app.py": "web/streamlit_app.py"}


def app_page(files: dict[str, str]) -> str:
    cfg = {"requirements": REQUIREMENTS, "entrypoint": "streamlit_app.py",
           "files": {k: {"url": f"./src/{k}"} for k in files},
           "streamlitConfig": {"theme.primaryColor": "#16406b", "client.toolbarMode": "viewer",
                               "browser.gatherUsageStats": False}}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(config.APP_NAME)} - app</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@{STLITE}/build/stlite.css">
<style>body{{margin:0;font-family:system-ui,sans-serif}}#boot{{max-width:560px;margin:18vh auto;padding:0 16px;text-align:center;color:#334}}
#boot .bar{{height:6px;background:#e6ebf2;border-radius:9px;overflow:hidden;margin:18px 0}}#boot .bar i{{display:block;height:100%;width:35%;background:#f2a516;animation:m 1.4s infinite ease-in-out}}
@keyframes m{{0%{{margin-left:-35%}}100%{{margin-left:100%}}}}</style></head>
<body><div id="root"><div id="boot"><h2>⚡ Loading the solar designer…</h2><div class="bar"><i></i></div>
<p>The whole app runs inside your browser (about 30-60 s the first time, faster after). Nothing you type is sent anywhere.</p>
<p><a href="../">← Back to the website</a></p></div></div>
<script type="module">
import {{ mount }} from "https://cdn.jsdelivr.net/npm/@stlite/browser@{STLITE}/build/stlite.js";
mount({json.dumps(cfg)}, document.getElementById("root"));
</script></body></html>"""


def main() -> None:
    SITE.mkdir(exist_ok=True)
    for item in SITE.iterdir():   # clear old build (keep the folder itself)
        shutil.rmtree(item) if item.is_dir() else item.unlink()
    (SITE / "app" / "src").mkdir(parents=True)
    (SITE / "samples").mkdir()
    files = app_files()
    for dst, src in files.items():
        (SITE / "app" / "src" / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / src, SITE / "app" / "src" / dst)
    (SITE / "app" / "index.html").write_text(app_page(files), encoding="utf-8")
    for s in SAMPLES:
        shutil.copy2(ROOT / "docs" / "samples" / s, SITE / "samples" / s)
    h, f500, f1 = ex.offgrid_jumla(), ex.farm_example(0.5), ex.farm_example(1.0)
    (SITE / "index.html").write_text(index(h, f500, f1), encoding="utf-8")
    (SITE / "guide.html").write_text(guide(), encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"Built {SITE} ({len(files)} app files, {size:.1f} MB)")


if __name__ == "__main__":
    main()
