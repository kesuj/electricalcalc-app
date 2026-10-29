# Architecture

## Principle: the calculator is the source of truth, the AI only explains

```
             ┌────────────────────────── Streamlit UI (ui/) ───────────────────────────┐
             │ Home  Solar  Electrical  Cable  Reports  AI assistant  Documents  ...   │
             └──────┬───────────────┬─────────────────┬──────────────┬─────────────────┘
                    │               │                 │              │
        ecalc/calc/ (pure Python)   ecalc/reports.py  ecalc/ai.py     ecalc/documents.py
        fundamentals, cable,        PDF + Markdown    providers +     upload checks, text
        solar → CalcResult          from CalcResult   budget guard    extraction, BM25
                    │                                 │
        ecalc/solar_data.py (PVGIS) ──┐               └─ Offline | Ollama | Gemini | OpenRouter | Anthropic
                                      ▼
                         ecalc/storage.py: SQLite (projects, calculations, AI usage, PVGIS cache, documents)
```

### Key design decisions (in plain English)

| Decision | Why |
|---|---|
| **Python + Streamlit**, no React, Docker or cloud | You can read and change it as a beginner. One language, one command to run, and it costs nothing locally. |
| **Every calculation returns a `CalcResult`** (inputs, equations, outputs, assumptions, warnings, references, tables) | Reports, the UI and the AI all read the same audited object, so a number can never "drift" between screens. |
| **No AI code inside `ecalc/calc/`** | Engineering values come only from tested deterministic code. |
| **AI providers behind one small interface** (`Provider.chat`) | Switching provider changes one setting. Local Ollama or a future fine-tuned model can be added without touching calculations. |
| **Plain REST for Gemini, OpenRouter and Ollama; the official SDK for Anthropic** | Fewer dependencies, while still following the vendor guidance for Claude. |
| **SQLite file** | No server to run, easy to back up (copy one file), and enough for one user or a small team. Can move to Postgres when hosted. |
| **BM25 keyword search instead of a vector database** | No embedding costs and no extra service. Good for datasheets full of exact terms ("MPPT", "IP65"). Embeddings can be added later if retrieval quality demands it. |
| **fpdf2 for PDFs** | Pure Python, no system dependencies, and works on Windows and Linux hosting. |

### Extending
- **New calculation:** add a function in `ecalc/calc/` returning `CalcResult`, then hand-calculated tests in `tests/`, then a UI tab. Reports and the AI pick it up automatically.
- **New AI provider:** subclass `Provider`, implement `status()` and `chat()`, register it in `PROVIDERS`, and add a price to `PRICES` if it is paid.
