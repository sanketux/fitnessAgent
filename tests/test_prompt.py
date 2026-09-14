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


def test_fallback_only_for_documented_models(monkeypatch):
    from fitness_agent import config
    from fitness_agent.agent import Coach

    monkeypatch.delenv("FITNESS_AGENT_FALLBACK", raising=False)
    assert config.use_fallback("claude-opus-5")
    assert config.use_fallback("claude-fable-5-1")
    assert not config.use_fallback("claude-sonnet-5")
    assert not config.use_fallback("claude-haiku-4-5")

    monkeypatch.setattr(config, "MODEL", "claude-sonnet-5")
    assert Coach.fallback_params() == {}
    monkeypatch.setattr(config, "MODEL", "claude-opus-5")
    assert Coach.fallback_params() == {"betas": [config.FALLBACK_BETA], "fallbacks": "default"}

    monkeypatch.setenv("FITNESS_AGENT_FALLBACK", "1")
    assert config.use_fallback("claude-sonnet-5")
    monkeypatch.setenv("FITNESS_AGENT_FALLBACK", "0")
    assert not config.use_fallback("claude-opus-5")
