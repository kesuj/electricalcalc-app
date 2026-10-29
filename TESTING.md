# Testing

Run: `.venv\Scripts\python -m pytest`

## Test report: 2026-10-29, v0.1.0 (Windows 11, Python 3.14.7)
**99 passed, 0 failed** (v0.2.3; the separate Home page and its render test were removed; adds load-schedule and full-design workflow tests with hand-calculated values, and an end-to-end run of the New project design page).

| File | Tests | Covers |
|---|---|---|
| `test_fundamentals.py` | 13 | Ohm's law, 1φ/3φ power, power triangle, load current, PF correction (kvar, µF delta/star), energy cost, unit conversions, invalid inputs (negative, NaN, PF > 1, wrong phase count) |
| `test_cable.py` | 15 | IEC 60228 resistance + temperature correction, 1φ / 3φ (with reactance) / DC drop, aluminium, limit pass/fail, ampacity and reactance warnings, minimum-size search, impossible case, 6 invalid-input cases |
| `test_solar.py` | 16 | Grid-tied hand calc (yield, kWp, panels, generation, inverter, savings, payback), area limit, missing tariff/cost not invented, hybrid battery usable vs nominal vs Ah, invalid inputs, **real PVGIS response parsing** (monthly sum = annual within 0.5%), PVGIS-based sizing, malformed response, hemisphere azimuth, network failure, cache |
| `test_platform.py` | 31 | SQLite round trip + cascade delete, monthly spend, PDF report (demo label, disclaimer, AI section separated, never says "certified by"), Markdown report, PDF font fallback, **budget blocks paid AI at $0**, monthly and per-request caps, unknown price blocked, free providers skip budget, missing keys, OpenRouter paid models refused, HTTP 429/401/402/500/400 mapped to clear errors and logged **without the API key**, timeout, successful call logged, Ollama down, offline explanation, document upload → retrieval → **page citation**, no-match returns nothing, duplicate upload, deletion, upload type/size/signature validation, prompt-injection detection and tag escaping |
| `test_ui.py` | 13 | Every one of the 10 pages renders headless without exceptions; demo-project flow through the Home button; cable page displays the hand-calculated 2.878%; public-demo mode disables uploads |

## How the expected values were obtained
Expected values were calculated by hand from first principles (see the table in ENGINEERING_METHODS.md) **before** comparing them with the code. No expected value was changed to make a test pass. Two test failures during development were test or harness issues, not engineering errors:
1. fpdf2's table API needed a heading style (a code fix).
2. The UI test assumed PF = 1.0, but the page defaults to 0.9. The page showed 2.59% = 2.878% × 0.9, which is correct, so the test now sets PF = 1.0 explicitly.

## Manual/live checks performed
- PVGIS live API (Kathmandu, 27° and 28° tilt): HTTP 200; 1426.64 and 1428.35 kWh/kWp/yr.
- Real browser run (Edge via Playwright): PVGIS fetch → calculate → results rendered; screenshots in `docs/screenshots/`.
- Sample PDF rendered and visually inspected (`docs/samples/`).

- **Live AI call, Ollama llama3.2:3b (2026-10-29):** asked about the 1φ 4 mm² voltage-drop result; the answer quoted 6.619 V and 2.878% exactly and listed the unchecked items (ampacity, protection, short-circuit). 26.6 s, $0.

## Not yet tested (known gaps)
- Gemini, OpenRouter and Anthropic have not had a live call (no keys configured); they are tested against simulated HTTP responses only.
- No comparison against a second independent tool (e.g. PVWatts or PVsyst) for the full solar workflow. PVsyst is installed on this computer, so a cross-check of one case is a good next step.
- No OCR or scanned-PDF handling; no load or performance testing; no multi-user testing.
