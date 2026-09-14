import json

from fitness_agent import tools


def call(tool, **kwargs):
    return json.loads(tool.call(kwargs))


def test_log_food_day_defaults_to_today(db):
    out = call(tools.log_food_day, description="eggs", calories=1500, protein_g=150, carbs_g=80, fat_g=55, fibre_g=25)
    assert out["day"] == tools.today().isoformat()
    assert out["protein_g"] == 150


def test_invalid_date_is_returned_as_error_not_raised(db):
    out = call(tools.log_measurement, weight_kg=92.0, day="14/09/2026")
    assert "error" in out


def test_measurement_requires_a_value(db):
    assert "error" in call(tools.log_measurement)


def test_workout_and_history(db):
    call(tools.log_workout, kind="Gym", est_calories=350, day="2026-09-10",
         details=[{"exercise": "Bench", "sets": 3, "reps": "8", "weight_kg": 50}])
    out = call(tools.get_exercise_history, exercise="bench")
    assert out["sessions"][0]["entries"][0]["weight_kg"] == 50


def test_current_state_shape(db):
    call(tools.update_current_state, key="Back_Recovery", value="90%")
    call(tools.add_session_note, summary="~1500 kcal | Verdict: good day", day="yesterday")
    out = call(tools.get_current_state)
    assert out["state"] == {"back_recovery": "90%"}
    assert out["recent_session_notes"][0]["summary"].startswith("~1500")
    assert set(out) >= {"today", "weekday", "latest_measurement", "last_7_days_food", "last_7_days_workouts"}


def test_weekly_trends_clamps_weeks(db):
    out = call(tools.get_weekly_trends, weeks=50)
    assert len(out["weeks"]) == 12


def test_every_tool_has_a_description_and_schema():
    for t in tools.ALL_TOOLS:
        d = t.to_dict()
        assert d["description"].strip(), t.name
        assert d["input_schema"]["type"] == "object", t.name
