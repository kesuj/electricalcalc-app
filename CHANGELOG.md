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

## 0.1.1 - 2026-10-29
### Added
- Public-demo mode for hosted deployments (shared-data warning, uploads disabled); fonts for Linux PDF rendering.
