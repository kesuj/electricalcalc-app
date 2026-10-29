# Changelog

## 0.7.0 - 2026-10-30
### Added
- **Public website (GitHub Pages)**: landing page, worked examples, component guide, sample reports and the full app running in the visitor's browser (stlite / Pyodide - no server; nothing typed leaves the computer). Build: `python scripts/build_site.py`.
- **Baked PVGIS data** (`scripts/bake_pvgis.py`, `web/pvgis_nepal.json`): real PVGIS v5.3 results for 27 Nepal cities x every roof tilt/direction the app asks for, because browsers cannot call PVGIS (no CORS). Nearest city/angle is used and named in the report; system loss is applied exactly.
- **Solar farm cost estimate** (`ecalc/calc/farm_cost.py`): itemised NPR low/central/high from the construction-package quantities, sources tagged [S]/[A], plus soft costs and contingency; shown in the Construction package and the PDF.
- **Whole-plant wiring drawing** for solar farms (strings -> inverters -> LV board -> transformer -> 11 kV switchgear -> NEA metering -> line), on screen and in the PDF.
- Worked examples: off-grid small home in Jumla; 500 kW and 1 MW farms near Nepalgunj (`scripts/site_examples.py`, PDFs in docs/samples).
- `?page=farm` link opens the Solar farm page directly.
### Fixed
- Farm package built more strings than asked (0.5 MW gave 0.585 MW); block DC kWp now uses the actual strings.

## 0.6.0 - 2026-10-30
### Added
- **Every part explained** (Home report section B): 15 component cards personalised to the user's numbers - what it does, types compared, best choice for this system, how to select, buying checks (NEPQA-2025, fake-product signs), series/parallel, how to connect, common mistakes.
- **Wiring drawings** of the user's exact system (SVG, on screen and in the PDF): panel strings with + / - links, battery bank with the diagonal take-off, whole system, earthing, inverter terminals.
- **Skills** section: multimeter, MC4 crimping, battery lugs, roof fixing, earth testing, inverter battery settings, switch-on/shutdown.
- **Compulsory or optional in Nepal**: a column on every shopping-list item and a summary table per system type.
- Deep research (6 researchers + report, reports/Nepal solar PV component guide.md) applied to the cards: NEPQA-2025 rules, AEPC earthing spec (2 electrodes, <= 10 ohm), lithium cold-charging limit with site warning, 10-20 kA battery fusing, PWM only below 20 A, second DC SPD for runs >= 10 m, NEA connection voltages.
### Fixed
- Legal wording: NEA approval is compulsory for grid connection/export; no Nepali licence law for house wiring was found (an electrician is recommended for 230 V work, not required).
- PDF drawings keep their heading on the same page; battery drawing no longer runs a cable through the isolator label.

## 0.5.0 - 2026-10-30
### Changed
- The site now has **just two sections: 🏠 Home solar and 🏭 Solar farm**.
- Home: new Step 7 installation questions (cable routes, inverter location, earth pit) and panel datasheet values in Engineer settings.
### Added
- **Installation guide (Home)** - first tab and front of the PDF: shopping list with exact ratings (NEPQA-2025 floors), string and battery layout, wiring diagram, cable/fuse/breaker schedule (larger of current-rating and voltage-drop sizes), safety, step-by-step installation (Boxwell §104-§130), commissioning record with expected values, maintenance and troubleshooting.
- **Construction package (Farm)** for the EPC contractor: plant hierarchy and counts, block single-line diagram, bill of quantities, cable schedule, switchgear/protection/earthing/NEA interconnection, construction sequence, IEC 62446 tests, O&M, Nepal permits.
- **📘 Book method tabs** on both pages: the books' steps worked with the user's numbers and their charts recreated with Nepal data (sun at five tilts, sun path, roof-direction loss, temperature, shading heat-map, battery cycles; inverter I-V window, voltage ladder, 5-step flowchart, lifetime energy, cost stack, the book's protection/testing tables).
- Cable current ratings (IEC 60364-5-52 method B1, conservative) and Ib ≤ In ≤ Iz device coordination.
- PDF reports can carry installation sections and a wiring diagram that follows real connections only, plus a full connection table.

## 0.4.0 - 2026-10-29
### Added
- **🏠 Home solar** rebuilt on the method of Boxwell, *Solar Electricity Handbook* (step order, formulas, worked example as tests), with modern Nepal data: PVGIS site sunshine, LiFePO4, NEPQA-2025 floors, three system types (grid-tied, hybrid with load-shedding backup, off-grid).
- Month-by-month **NEA bill** with and without solar (ERC 2078 slab tariff, net-billing export credit), from an hourly simulation of an average day per month (PVGIS daily profiles, Nepal time).
- Interactive tabs: monthly chart and bills, **a day with a power cut** (month / start / length / usage-shape sliders), **money** (price rise, panel ageing, discount sliders; payback, IRR, 25-year gain; battery replacement), engineering details, report.
- **🏭 Solar farm** page on the method of Neill, Stapleton & Martell, *Solar Farms*: energy (P50/P90), layout & land (ha / bigha / ropani, row-spacing diagram, shade-free window), 5-step string & inverter matching with cold-morning safety check, editable losses with waterfall, LCOE / IRR / NPV vs NEA PPA rate, report.
- Nepal data module with sources and tags; 27 Nepal sites; string sizing (IEC 62548 approach); finance module (cash flow, IRR, LCOE).
### Fixed
- Errors in both books' printed examples corrected (see ENGINEERING_METHODS.md E-F).
- Grid-tied systems now correctly supply nothing during a power cut (anti-islanding).
- Hybrid inverter now sized for the whole array, not only the backup loads.
- Appliance form no longer submits when Enter is pressed in a box.
- Negative values (e.g. falling prices) accepted where valid.

## 0.3.1 - 2026-10-29
### Changed
- **Solar PV sizing**, **Cable voltage drop** and **Power-factor correction** pages: every box now starts empty with short grey hint text saying where to find or measure the value (full explanation on each box's ? icon); results appear only when the required boxes are filled, and the still-empty ones are listed.
- In-box hints shortened so they fit narrow boxes; detailed guidance kept in tooltips.

## 0.3.0 - 2026-10-29
### Changed
- Start page rebuilt as **Plan a solar system** for non-engineers: five plain-language steps; every question box starts empty with grey hint text saying how to find or measure the value; required answers are checked and missing ones listed.
- Roof answered as flat/sloping + compass direction + steepness (converted to tilt/azimuth); location by nearest city or exact Google Maps coordinates.
- Appliance picker with typical wattages (marked "typical - check label"); backup sized from "longest power cut (hours)" × appliances needed during cuts.
- Technical values (panel datasheet, DC/AC ratio, depth of discharge, coincidence factor, voltage-drop limits, losses) moved to **Engineer settings** with standard values, all printed in the report. Default AC voltage-drop limit is 1.5% (grid-tied voltage-rise risk).
- Cable checks run only when a cable length is entered; skipped checks are stated in the report.
### Added
- Plain-words summary at the top of the results and in the PDF/Markdown report.

## 0.2.4 - 2026-10-29
### Changed
- Removed the six-tab "Electrical tools" page; the app stays focused on solar design. The engine functions remain (tested, used internally).
- New **Extra tools → Power-factor correction** page. The existing PF can be derived from kWh and kVArh meter or bill readings (PF = kWh/√(kWh²+kVArh²)), with maximum demand kW as the sizing basis.

## 0.2.3 - 2026-10-29
### Changed
- Merged "Home & projects" and "Reports & history" into one page, **My projects & reports** (project list, empty-project creation, demo loader, report download, deletion).
### Fixed
- Pressing **Calculate everything** again for the same project updated it instead of creating a duplicate project.

## 0.2.2 - 2026-10-29
### Fixed
- Renamed "diversity factor" (≤ 1) to the correct term **coincidence (simultaneity) factor**; the report also shows the equivalent textbook diversity factor (its inverse).
- Default changed from 0.8 to 1.0: with few loads, 0.8 could undersize the inverter. A warning is shown when a value below 1 is used with fewer than 10 load types.

## 0.2.1 - 2026-10-29
### Fixed
- Peak-sun-hours mode defaulted to 14% losses (the PVGIS *system*-loss default), which ignored temperature and reflection losses and overestimated generation by about 10%. It now asks for *total* losses, defaulting to 23% (PR ≈ 0.77), with explanatory help text.

## 0.2.0 - 2026-10-29
### Added
- **New project design** start page: one form → load schedule, PV sizing, inverter AC current, AC cable, battery DC current and DC cable → full PDF/Markdown report; project auto-saved.
- Load schedule calculation (connected load, maximum demand with coincidence factor, critical/backup energy, motor surge warning).
- 10 new tests (98 total), including an end-to-end run of the new page.

## 0.1.1 - 2026-10-29
### Added
- Public-demo mode for hosted deployments (shared-data warning, uploads disabled); fonts for Linux PDF rendering.

## 0.1.0 - 2026-10-29
### Added
- Deterministic calculation engine (`ecalc/calc`): fundamentals, cable voltage drop (IEC 60228), solar PV sizing (grid-tied / hybrid).
- PVGIS v5.3 client with SQLite cache; real Kathmandu response bundled for the demo and tests.
- Streamlit UI with 10 pages: Home & projects (merged into My projects & reports in 0.2.3), Solar, Electrical tools, Cable, Reports & history, AI assistant, Documents, Settings, Usage & costs, Help.
- PDF and Markdown draft reports with review record and disclaimer; separate AI commentary section.
- AI layer: Offline, Ollama, Gemini, OpenRouter (`:free` only), Anthropic (official SDK); budget guard, usage log, no silent fallback.
- Document assistant: upload validation, page-level extraction, BM25 search with citations, prompt-injection screening, deletion.
- Demonstration project (clearly labelled), sample report, screenshots.
- 87 automated tests.
