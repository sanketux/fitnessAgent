from datetime import date

from fitness_agent.prompt import build_system


def test_system_prompt_has_cached_manual_then_dynamic_block(db):
    db.set_state("back_recovery", "90%")
    blocks = build_system(db, date(2026, 9, 14), manual="# MANUAL BODY")
    assert len(blocks) == 2
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert "# MANUAL BODY" in blocks[0]["text"]
    assert "cache_control" not in blocks[1]
    assert "Monday, 2026-09-14" in blocks[1]["text"]
    assert "back_recovery" in blocks[1]["text"]


def test_static_block_is_stable_across_days(db):
    a = build_system(db, date(2026, 9, 14), manual="x")[0]
    b = build_system(db, date(2026, 9, 15), manual="x")[0]
    assert a == b
