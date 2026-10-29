# Changelog

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
