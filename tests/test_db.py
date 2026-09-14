from datetime import date

from fitness_agent.db import Database


def test_state_upsert(db: Database):
    db.set_state("back_recovery", "80%")
    db.set_state("back_recovery", "95%")
    assert db.get_state() == {"back_recovery": "95%"}


def test_food_day_is_overwritten_not_duplicated(db: Database):
    db.upsert_food_day("2026-09-14", "eggs, paneer", 1400, 120, 80, 50, 14)
    db.upsert_food_day("2026-09-14", "eggs, paneer, guava", 1470, 121, 95, 50, 19)
    rows = db.food_between("2026-09-01", "2026-09-30")
    assert len(rows) == 1
    assert rows[0]["fibre_g"] == 19


def test_workout_details_round_trip_and_history(db: Database):
    db.add_workout("2026-09-10", "gym", [{"exercise": "Leg Press", "sets": 3, "reps": "12", "weight_kg": 70}], 350)
    db.add_workout("2026-09-12", "gym", [{"exercise": "leg press", "sets": 3, "reps": "12", "weight_kg": 75}], 360)
    db.add_workout("2026-09-13", "rest", [], 0)
    hist = db.exercise_history("leg press")
    assert [h["day"] for h in hist] == ["2026-09-12", "2026-09-10"]
    assert hist[0]["entries"][0]["weight_kg"] == 75


def test_measurement_merge_keeps_missing_fields(db: Database):
    db.upsert_measurement("2026-09-14", 92.4, None)
    db.upsert_measurement("2026-09-14", None, 40.5)
    m = db.latest_measurement()
    assert m["weight_kg"] == 92.4 and m["waist_in"] == 40.5


def test_weekly_trends_average_and_bucket(db: Database):
    # Week of Mon 2026-09-07 .. Sun 2026-09-13, and current week starting 2026-09-14.
    db.upsert_food_day("2026-09-08", "a", 1500, 140, 80, 55, 20)
    db.upsert_food_day("2026-09-09", "b", 1700, 120, 100, 65, 14)
    db.add_workout("2026-09-08", "gym", [], 350)
    db.upsert_measurement("2026-09-07", 93.0, 41.0)
    db.upsert_food_day("2026-09-14", "c", 1450, 150, 70, 55, 26)

    weeks = db.weekly_trends(2, date(2026, 9, 14))
    assert [w["week_start"] for w in weeks] == ["2026-09-07", "2026-09-14"]
    last, current = weeks
    assert last["days_logged"] == 2
    assert last["avg_calories"] == 1600
    assert last["avg_protein_g"] == 130
    assert last["workouts"] == 1
    assert last["measurements"][0]["waist_in"] == 41.0
    assert current["avg_fibre_g"] == 26


def test_session_notes_order(db: Database):
    db.add_session_note("2026-09-12", "first")
    db.add_session_note("2026-09-13", "second")
    assert [n["summary"] for n in db.recent_session_notes(limit=5)] == ["first", "second"]
