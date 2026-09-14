"""Runtime configuration, overridable through environment variables."""

from __future__ import annotations

import os
from pathlib import Path

# In a source checkout, paths default to the repo root. When the package is
# installed into site-packages (e.g. in Docker), fall back to the working directory.
_PACKAGE_PARENT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = _PACKAGE_PARENT if (_PACKAGE_PARENT / "pyproject.toml").exists() else Path.cwd()

MODEL = os.environ.get("FITNESS_AGENT_MODEL", "claude-sonnet-5")
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

# Telegram bot (see fitness_agent/telegram_bot.py). The token is read only from
# the environment and must never be committed.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USER_IDS = frozenset(
    int(x) for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").replace(",", " ").split() if x.strip()
)
# Daily check-in reminder, local time in TIMEZONE. Set to "" to disable.
TELEGRAM_CHECKIN_TIME = os.environ.get("TELEGRAM_CHECKIN_TIME", "21:00")

# Server-side refusal fallback: if the safety classifiers decline a request,
# the API re-runs it on Anthropic's recommended fallback model in the same call.
# Documented for the Opus 5 and Fable families; off for other models unless
# FITNESS_AGENT_FALLBACK=1 forces it (or =0 disables it).
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def use_fallback(model: str = MODEL) -> bool:
    forced = os.environ.get("FITNESS_AGENT_FALLBACK")
    if forced is not None:
        return forced.strip() not in {"", "0", "false", "no"}
    return model.startswith(("claude-opus-5", "claude-fable"))
