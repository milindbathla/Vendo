"""
Configuration and thresholds for the Business Intel Agent.
All environment variables, severity levels, and anomaly thresholds live here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# Base repository directory
BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent

# Database configuration
DEMO_DB_PATH: Final[str] = os.environ.get(
    "DEMO_DB_PATH",
    str(BASE_DIR / "demo_data" / "demo.db")
)

# LLM mode: 'on' or 'off'. Default is 'off' for deterministic offline execution.
BI_LLM: Final[str] = os.environ.get("BI_LLM", "off").lower()
IS_LLM_ENABLED: Final[bool] = BI_LLM == "on"
BI_LLM_ENABLED: Final[bool] = IS_LLM_ENABLED

# Gemini LLM configuration
GEMINI_API_KEY: Final[str] = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: Final[str] = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MODEL_PRO: Final[str] = os.environ.get("GEMINI_MODEL_PRO", "gemini-2.5-pro")

# Orchestrator guardrails
MAX_TOOL_CALLS_PER_TURN: Final[int] = 5
TOOL_TIMEOUT_SECONDS: Final[float] = 5.0
MAX_SPEECH_WORDS: Final[int] = 45

# Analytics & Anomaly Detection Thresholds
ANOMALY_Z: Final[float] = 2.0  # Number of standard deviations for anomaly detection
ANOMALY_WINDOW_DAYS: Final[int] = 28  # Trailing window for rolling mean/std calculation
PRICE_HIKE_ALERT_PCT: Final[float] = 5.0  # Percentage price increase triggering alert
COGS_DIFF_PCT_THRESHOLD: Final[float] = 10.0  # Max acceptable delta between bottom-up vs reported COGS %
LOW_FORECAST_CONFIDENCE_THRESHOLD: Final[float] = 0.60  # Forecast confidence threshold for warnings

# Memory Policy
DEFAULT_OWNER_STATEMENT_CONFIDENCE: Final[float] = 0.40
DEFAULT_VERIFIED_RECORD_CONFIDENCE: Final[float] = 0.95

# Scope Definitions
IN_SCOPE_DOMAINS: Final[set[str]] = {"context", "analytics", "both"}
OUT_OF_SCOPE_ROUTING: Final[dict[str, str]] = {
    "procurement": "finance_and_procurement_agent",
    "affordability": "finance_and_procurement_agent",
    "capacity": "demand_and_capacity_agent",
    "forecast": "demand_and_capacity_agent",
    "reconciliation": "document_agent",
    "growth": "customer_growth_agent",
    "execution": "commerce_execution_agent",
}
