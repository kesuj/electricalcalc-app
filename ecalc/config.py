"""Application configuration, read from environment variables (.env supported).

Nothing secret is ever stored in this module; API keys are read on demand by the
provider classes and never logged or displayed.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


APP_NAME = os.getenv("ECALC_APP_NAME", "ElectricalCalc AI")
APP_TAGLINE = os.getenv("ECALC_APP_TAGLINE", "Intelligent Electrical Engineering Assistant")
DATA_DIR = Path(os.getenv("ECALC_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "ecalc.db"

# Cost controls. A monthly budget of 0 means paid AI providers are blocked entirely.
MONTHLY_AI_BUDGET_USD = _float("ECALC_MONTHLY_BUDGET_USD", 0.0)
MAX_COST_PER_REQUEST_USD = _float("ECALC_MAX_COST_PER_REQUEST_USD", 0.05)
AI_TIMEOUT_SECONDS = _float("ECALC_AI_TIMEOUT_SECONDS", 60.0)

# Upload limits for the document assistant.
MAX_UPLOAD_MB = _float("ECALC_MAX_UPLOAD_MB", 20.0)
ALLOWED_UPLOAD_EXTENSIONS = (".pdf", ".txt", ".md")


# Public demo mode: on automatically on Streamlit Community Cloud (app is cloned under /mount/src),
# or set ECALC_PUBLIC_DEMO=1. Disables document uploads and shows a shared-data warning.
PUBLIC_DEMO = os.getenv("ECALC_PUBLIC_DEMO", "") == "1" or str(PROJECT_ROOT).startswith("/mount/src")


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
