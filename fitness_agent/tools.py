"""Tools the coach can call. Each returns a JSON string.

Tools never raise: failures come back as {"error": ...} so the model can
recover instead of the whole turn failing.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import wraps
from typing import Any, Callable
from zoneinfo import ZoneInfo

from anthropic import beta_tool

from . import config
from .db import Database

_db: Database | None = None


def set_database(db: Database | None) -> None:
    """Point the tools at a specific Database (used by the CLI and tests)."""
    global _db
    _db = db


def get_database() -> Database:
    global _db
    if _db is None:
        _db = Database(config.DB_PATH)
    return _db


def today() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def _resolve_day(day: str | None) -> str:
    if not day or day.lower() == "today":
        return today().isoformat()
    if day.lower() == "yesterday":
        return (today() - timedelta(days=1)).isoformat()
    return date.fromisoformat(day).isoformat()  # validates the format


def _safe(fn: Callable[..., Any]) -> Callable[..., str]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return json.dumps(fn(*args, **kwargs), default=str)
        except Exception as exc:  # noqa: BLE001 - surfaced to the model as data
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    return wrapper


@beta_tool
@_safe
def get_current_state() -> dict[str, Any]:
    """Get Sanket's current coaching state: stored state keys (back recovery, notes,
    targets overrides), the latest weight/waist measurement, and the last 7 days of
    food and workout logs. Call this at the start of a session before giving feedback.
    """
    db = get_database()
    end = today()
    start = end - timedelta(days=6)
    return {
        "today": end.isoformat(),
        "weekday": end.strftime("%A"),
        "state": db.get_state(),
        "latest_measurement": db.latest_measurement(),
        "last_7_days_food": db.food_between(start.isoformat(), end.isoformat()),
        "last_7_days_workouts": db.workouts_between(start.isoformat(), end.isoformat()),
        "recent_session_notes": db.recent_session_notes(limit=3),
    }


@beta_tool
@_safe
def update_current_state(key: str, value: str) -> dict[str, Any]:
    """Save or update a piece of ongoing coaching state that should persist across days.

    Args:
        key: Short snake_case key, e.g. "back_recovery", "cheat_meal_this_week",
            "current_focus", "calorie_target", "supplement_changes".
        value: Free-text value, e.g. "~90% recovered, no pain on seated row".
    """
    return get_database().set_state(key.strip().lower(), value.strip())


@beta_tool
@_safe
def log_food_day(
    description: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    fibre_g: float,
    day: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Log (or overwrite) the day's total food intake after you have calculated it.
    One entry per day: if he adds a snack later, call again with the updated totals.

    Args:
        description: Compact list of what he ate with rough portions.
        calories: Total kcal for the day (rounded is fine).
        protein_g: Total protein in grams.
        carbs_g: Total carbohydrates in grams.
        fat_g: Total fat in grams.
        fibre_g: Total fibre in grams.
        day: ISO date (YYYY-MM-DD), "today" or "yesterday". Defaults to today.
        notes: Optional one-line note, e.g. "cheat meal Saturday" or "estimated portions".
    """
    return get_database().upsert_food_day(
        _resolve_day(day), description, calories, protein_g, carbs_g, fat_g, fibre_g, notes
    )


@beta_tool
@_safe
def log_workout(
    kind: str,
    est_calories: float,
    details: list[dict[str, Any]] | None = None,
    day: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Log a training session, sport, or a rest day.

    Args:
        kind: One of "gym", "badminton", "walk", "cardio", "skipping", "other", "rest".
        est_calories: Estimated calories burned (0 for rest days).
        details: For gym sessions, a list of {"exercise": str, "sets": int, "reps": str,
            "weight_kg": float, "note": str}. For sport/cardio, a single entry with
            {"exercise": "badminton", "minutes": 60}. Omit for rest days.
        day: ISO date (YYYY-MM-DD), "today" or "yesterday". Defaults to today.
        notes: Optional note, e.g. "no back pain", "skipped finisher".
    """
    return get_database().add_workout(_resolve_day(day), kind.strip().lower(), details or [], est_calories, notes)


@beta_tool
@_safe
def log_measurement(
    weight_kg: float | None = None,
    waist_in: float | None = None,
    day: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Log the weekly weight and/or waist measurement (normally Monday, fasted).

    Args:
        weight_kg: Body weight in kilograms.
        waist_in: Waist at navel in inches, relaxed, tape parallel to floor.
        day: ISO date (YYYY-MM-DD), "today" or "yesterday". Defaults to today.
        notes: Optional note on conditions, e.g. "after a salty dinner".
    """
    if weight_kg is None and waist_in is None:
        return {"error": "Provide weight_kg, waist_in, or both."}
    return get_database().upsert_measurement(_resolve_day(day), weight_kg, waist_in, notes)


@beta_tool
@_safe
def get_recent_logs(days: int = 7) -> dict[str, Any]:
    """Fetch food, workout and measurement logs for the last N days.

    Args:
        days: How many days back to include (1-60). Default 7.
    """
    days = max(1, min(int(days), 60))
    db = get_database()
    end = today()
    start = end - timedelta(days=days - 1)
    s, e = start.isoformat(), end.isoformat()
    return {
        "from": s,
        "to": e,
        "food": db.food_between(s, e),
        "workouts": db.workouts_between(s, e),
        "measurements": [m for m in db.measurements(limit=60) if s <= m["day"] <= e],
    }


@beta_tool
@_safe
def get_weekly_trends(weeks: int = 4) -> dict[str, Any]:
    """Weekly averages (calories, protein, carbs, fat, fibre), workout counts and the
    weight/waist series for the last N weeks. Use for the Monday weekly review and
    before suggesting any calorie adjustment (adjust on a 2-week trend, never one reading).

    Args:
        weeks: Number of weeks including the current one (1-12). Default 4.
    """
    weeks = max(1, min(int(weeks), 12))
    return {"weeks": get_database().weekly_trends(weeks, today())}


@beta_tool
@_safe
def get_exercise_history(exercise: str, limit: int = 8) -> dict[str, Any]:
    """Look up recent logged sets for one exercise, for progressive-overload decisions.

    Args:
        exercise: Exercise name or fragment, e.g. "leg press", "bench".
        limit: Max sessions to return. Default 8.
    """
    return {"exercise": exercise, "sessions": get_database().exercise_history(exercise, limit)}


@beta_tool
@_safe
def add_session_note(summary: str, day: str | None = None) -> dict[str, Any]:
    """Append the day's running-log line once the check-in is complete. Use the format:
    "~X kcal, Xg P / Xg C / Xg F / Xg fibre | Workout: ... | Deficit ~X | Verdict: ... | Focus: ...".
    Keep it to 1-3 lines. This is what you will read back at the start of the next session.

    Args:
        summary: The log line(s).
        day: ISO date (YYYY-MM-DD), "today" or "yesterday". Defaults to today.
    """
    return get_database().add_session_note(_resolve_day(day), summary.strip())


ALL_TOOLS = [
    get_current_state,
    update_current_state,
    log_food_day,
    log_workout,
    log_measurement,
    get_recent_logs,
    get_weekly_trends,
    get_exercise_history,
    add_session_note,
]
