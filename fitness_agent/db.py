"""SQLite persistence for logs, measurements and the coach's running state.

One connection per Database instance. All public methods return plain dicts
so the tool layer can serialise them straight to JSON.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS food_logs (
    day         TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    calories    REAL,
    protein_g   REAL,
    carbs_g     REAL,
    fat_g       REAL,
    fibre_g     REAL,
    notes       TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workout_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    day           TEXT NOT NULL,
    kind          TEXT NOT NULL,
    details       TEXT,
    est_calories  REAL,
    notes         TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS workout_logs_day ON workout_logs(day);

CREATE TABLE IF NOT EXISTS measurements (
    day        TEXT PRIMARY KEY,
    weight_kg  REAL,
    waist_in   REAL,
    notes      TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    day        TEXT NOT NULL,
    summary    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS session_notes_day ON session_notes(day);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ state
    def set_state(self, key: str, value: str) -> dict[str, Any]:
        self.conn.execute(
            "INSERT INTO state(key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, _now()),
        )
        self.conn.commit()
        return {"key": key, "value": value}

    def get_state(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM state ORDER BY key").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ------------------------------------------------------------------- food
    def upsert_food_day(
        self,
        day: str,
        description: str,
        calories: float | None,
        protein_g: float | None,
        carbs_g: float | None,
        fat_g: float | None,
        fibre_g: float | None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        self.conn.execute(
            """INSERT INTO food_logs(day, description, calories, protein_g, carbs_g, fat_g, fibre_g, notes, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(day) DO UPDATE SET
                 description=excluded.description, calories=excluded.calories,
                 protein_g=excluded.protein_g, carbs_g=excluded.carbs_g, fat_g=excluded.fat_g,
                 fibre_g=excluded.fibre_g, notes=excluded.notes, updated_at=excluded.updated_at""",
            (day, description, calories, protein_g, carbs_g, fat_g, fibre_g, notes, _now()),
        )
        self.conn.commit()
        return self.get_food_day(day) or {}

    def get_food_day(self, day: str) -> dict[str, Any] | None:
        return _row(self.conn.execute("SELECT * FROM food_logs WHERE day = ?", (day,)).fetchone())

    def food_between(self, start: str, end: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM food_logs WHERE day BETWEEN ? AND ? ORDER BY day", (start, end)
        ).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- workouts
    def add_workout(
        self,
        day: str,
        kind: str,
        details: list[dict[str, Any]] | str | None,
        est_calories: float | None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        details_json = json.dumps(details) if not isinstance(details, str) else details
        cur = self.conn.execute(
            "INSERT INTO workout_logs(day, kind, details, est_calories, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (day, kind, details_json, est_calories, notes, _now()),
        )
        self.conn.commit()
        return self.get_workout(cur.lastrowid)

    def get_workout(self, workout_id: int) -> dict[str, Any]:
        row = _row(self.conn.execute("SELECT * FROM workout_logs WHERE id = ?", (workout_id,)).fetchone())
        assert row is not None
        return self._decode_workout(row)

    def workouts_between(self, start: str, end: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM workout_logs WHERE day BETWEEN ? AND ? ORDER BY day, id", (start, end)
        ).fetchall()
        return [self._decode_workout(dict(r)) for r in rows]

    def exercise_history(self, exercise: str, limit: int = 10) -> list[dict[str, Any]]:
        """Most recent sessions that include an exercise whose name contains `exercise`."""
        needle = exercise.lower()
        rows = self.conn.execute("SELECT * FROM workout_logs ORDER BY day DESC, id DESC").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            w = self._decode_workout(dict(r))
            details = w.get("details")
            if not isinstance(details, list):
                continue
            hits = [d for d in details if needle in str(d.get("exercise", "")).lower()]
            if hits:
                out.append({"day": w["day"], "kind": w["kind"], "entries": hits})
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _decode_workout(row: dict[str, Any]) -> dict[str, Any]:
        raw = row.get("details")
        if isinstance(raw, str):
            try:
                row["details"] = json.loads(raw)
            except json.JSONDecodeError:
                pass
        return row

    # ----------------------------------------------------------- measurements
    def upsert_measurement(
        self, day: str, weight_kg: float | None, waist_in: float | None, notes: str | None = None
    ) -> dict[str, Any]:
        self.conn.execute(
            """INSERT INTO measurements(day, weight_kg, waist_in, notes, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(day) DO UPDATE SET
                 weight_kg=COALESCE(excluded.weight_kg, measurements.weight_kg),
                 waist_in=COALESCE(excluded.waist_in, measurements.waist_in),
                 notes=COALESCE(excluded.notes, measurements.notes),
                 updated_at=excluded.updated_at""",
            (day, weight_kg, waist_in, notes, _now()),
        )
        self.conn.commit()
        row = _row(self.conn.execute("SELECT * FROM measurements WHERE day = ?", (day,)).fetchone())
        assert row is not None
        return row

    def measurements(self, limit: int = 12) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM measurements ORDER BY day DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def latest_measurement(self) -> dict[str, Any] | None:
        return _row(self.conn.execute("SELECT * FROM measurements ORDER BY day DESC LIMIT 1").fetchone())

    # ---------------------------------------------------------- session notes
    def add_session_note(self, day: str, summary: str) -> dict[str, Any]:
        cur = self.conn.execute(
            "INSERT INTO session_notes(day, summary, created_at) VALUES (?, ?, ?)",
            (day, summary, _now()),
        )
        self.conn.commit()
        row = _row(self.conn.execute("SELECT * FROM session_notes WHERE id = ?", (cur.lastrowid,)).fetchone())
        assert row is not None
        return row

    def recent_session_notes(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM session_notes ORDER BY day DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ----------------------------------------------------------- aggregates
    def weekly_trends(self, weeks: int, today: date) -> list[dict[str, Any]]:
        """Per-week (Mon-Sun) averages ending with the week containing `today`."""
        out: list[dict[str, Any]] = []
        this_monday = today - timedelta(days=today.weekday())
        for i in range(weeks - 1, -1, -1):
            start = this_monday - timedelta(weeks=i)
            end = start + timedelta(days=6)
            s, e = start.isoformat(), end.isoformat()
            food = self.food_between(s, e)
            workouts = self.workouts_between(s, e)
            meas = self.conn.execute(
                "SELECT * FROM measurements WHERE day BETWEEN ? AND ? ORDER BY day", (s, e)
            ).fetchall()

            def avg(key: str) -> float | None:
                vals = [f[key] for f in food if f.get(key) is not None]
                return round(sum(vals) / len(vals), 1) if vals else None

            out.append(
                {
                    "week_start": s,
                    "week_end": e,
                    "days_logged": len(food),
                    "avg_calories": avg("calories"),
                    "avg_protein_g": avg("protein_g"),
                    "avg_carbs_g": avg("carbs_g"),
                    "avg_fat_g": avg("fat_g"),
                    "avg_fibre_g": avg("fibre_g"),
                    "workouts": len([w for w in workouts if w["kind"] != "rest"]),
                    "workout_calories": round(sum(w["est_calories"] or 0 for w in workouts)),
                    "measurements": [dict(m) for m in meas],
                }
            )
        return out
