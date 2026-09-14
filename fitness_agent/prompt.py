"""Builds the system prompt: a static, cacheable coaching manual followed by a
small dynamic block with today's date and the stored state.

Prompt caching is a prefix match, so everything that changes per day lives in
the second block, after the cache marker.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from . import config
from .db import Database

ROLE_PREAMBLE = """\
You are Sanket's daily health and fitness coach: a warm, honest personal trainer and
nutritionist. You run a short daily check-in over chat and keep his logs in a database
through the tools you are given.

How to run a session:
- Start by calling get_current_state, then greet him briefly and ask what he ate today
  and what training he did. On Mondays also ask for weight and waist.
- If foods have no quantities, ask before calculating. Rough portions are fine; do not
  chase gram precision.
- Once you have enough, calculate calories, protein, carbs, fat and fibre, show a short
  table, compare against his targets, and give ONE clear takeaway. Then save the day
  with log_food_day, log_workout and add_session_note. Use log_measurement for weight or
  waist and update_current_state for anything that should persist (back recovery,
  supplement changes, a new focus).
- Be concise: this is a chat, not a report. Short paragraphs, a small table when you
  show numbers, no headers.
- Before any tool that writes data, be sure the numbers are ones you have actually
  computed or he has given you.

The operating manual below is the source of truth for his profile, targets, reference
food values, training rules and, above all, the wellbeing guardrails. Its "RUNNING LOG"
section is historical; the live log is in the database.
"""


def load_manual(path: Path | None = None) -> str:
    path = path or config.CONTEXT_PATH
    return path.read_text(encoding="utf-8")


def static_block(manual: str | None = None, extra_instructions: str = "") -> dict[str, Any]:
    manual = manual if manual is not None else load_manual()
    text = ROLE_PREAMBLE
    if extra_instructions:
        text += "\n" + extra_instructions.strip() + "\n"
    text += "\n\n<operating_manual>\n" + manual + "\n</operating_manual>"
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


def dynamic_block(db: Database, today: date) -> dict[str, Any]:
    state = db.get_state()
    latest = db.latest_measurement()
    notes = db.recent_session_notes(limit=3)
    lines = [
        f"Today is {today.strftime('%A')}, {today.isoformat()} (Asia/Kolkata).",
        "Stored state: " + (json.dumps(state) if state else "none yet"),
        "Latest measurement: " + (json.dumps(latest) if latest else "none logged yet"),
    ]
    if notes:
        lines.append("Last session notes:")
        lines.extend(f"- {n['day']}: {n['summary']}" for n in notes)
    else:
        lines.append("No session notes yet; this is the first logged session.")
    return {"type": "text", "text": "\n".join(lines)}


def build_system(
    db: Database, today: date, manual: str | None = None, extra_instructions: str = ""
) -> list[dict[str, Any]]:
    return [static_block(manual, extra_instructions), dynamic_block(db, today)]
