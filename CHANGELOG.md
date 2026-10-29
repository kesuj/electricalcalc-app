# Changelog

## 0.1.0 - 2026-10-29
### Added
- Deterministic calculation engine (`ecalc/calc`): fundamentals, cable voltage drop (IEC 60228), solar PV sizing (grid-tied / hybrid).
- PVGIS v5.3 client with SQLite cache; real Kathmandu response bundled for the demo and tests.
- Streamlit UI with 10 pages: Home & projects, Solar, Electrical tools, Cable, Reports & history, AI assistant, Documents, Settings, Usage & costs, Help.
- PDF and Markdown draft reports with review record and disclaimer; separate AI commentary section.
- AI layer: Offline, Ollama, Gemini, OpenRouter (`:free` only), Anthropic (official SDK); budget guard, usage log, no silent fallback.
- Document assistant: upload validation, page-level extraction, BM25 search with citations, prompt-injection screening, deletion.
- Demonstration project (clearly labelled), sample report, screenshots.
- 87 automated tests.

## 0.2.1 - 2026-10-29
### Fixed
- Peak-sun-hours mode defaulted to 14% losses (the PVGIS *system*-loss default), which ignored temperature and reflection losses and overestimated generation by about 10%. It now asks for *total* losses, defaulting to 23% (PR ≈ 0.77), with explanatory help text.

## 0.2.0 - 2026-10-29
### Added
- **New project design** start page: one form → load schedule, PV sizing, inverter AC current, AC cable, battery DC current and DC cable → full PDF/Markdown report; project auto-saved.
- Load schedule calculation (connected load, maximum demand with diversity, critical/backup energy, motor surge warning).
- 10 new tests (98 total), including an end-to-end run of the new page.

## 0.1.1 - 2026-10-29
### Added
- Public-demo mode for hosted deployments (shared-data warning, uploads disabled); fonts for Linux PDF rendering.
