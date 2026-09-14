"""Runtime configuration, overridable through environment variables."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL = os.environ.get("FITNESS_AGENT_MODEL", "claude-opus-5")
EFFORT = os.environ.get("FITNESS_AGENT_EFFORT", "medium")
MAX_TOKENS = int(os.environ.get("FITNESS_AGENT_MAX_TOKENS", "16000"))
TIMEZONE = os.environ.get("FITNESS_AGENT_TZ", "Asia/Kolkata")

DB_PATH = Path(os.environ.get("FITNESS_AGENT_DB", PROJECT_ROOT / "data" / "fitness.db"))
CONTEXT_PATH = Path(
    os.environ.get(
        "FITNESS_AGENT_CONTEXT",
        PROJECT_ROOT / "context" / "sanket_health_agent_context.md",
    )
)

# Server-side refusal fallback: if the safety classifiers decline a request,
# the API re-runs it on Anthropic's recommended fallback model in the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
