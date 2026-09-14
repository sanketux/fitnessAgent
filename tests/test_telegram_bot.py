from datetime import time as dtime

from fitness_agent import telegram_bot as tb


def test_split_short_message_unchanged():
    assert tb.split_message("hello") == ["hello"]


def test_split_prefers_paragraph_breaks():
    para = "x" * 3000
    text = para + "\n\n" + para
    chunks = tb.split_message(text)
    assert chunks == [para, para]


def test_split_hard_cuts_when_no_breaks():
    text = "y" * 9000
    chunks = tb.split_message(text)
    assert all(len(c) <= tb.TELEGRAM_MAX_CHARS for c in chunks)
    assert "".join(chunks) == text


def test_empty_reply_placeholder():
    assert tb.split_message("   ") == ["(no reply)"]


def test_is_allowed():
    assert tb.is_allowed(42, frozenset({42}))
    assert not tb.is_allowed(43, frozenset({42}))
    assert not tb.is_allowed(None, frozenset({42}))
    assert not tb.is_allowed(42, frozenset())


def test_parse_checkin_time():
    t = tb.parse_checkin_time("21:30")
    assert (t.hour, t.minute) == (21, 30)
    assert t.tzinfo is not None
    assert tb.parse_checkin_time("7") == dtime(7, 0, tzinfo=tb.parse_checkin_time("7").tzinfo)
    assert tb.parse_checkin_time("") is None


def test_coach_gets_telegram_style_and_no_stdout(db, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    bot = tb.CoachBot(db, manual="MANUAL")
    coach = bot.coach_for(1)
    assert coach is bot.coach_for(1)
    assert "Telegram" in coach.extra_instructions
    coach.on_text("should not print")
    assert capsys.readouterr().out == ""


def test_build_application_registers_handlers_and_job(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(tb.config, "TELEGRAM_CHECKIN_TIME", "21:00")
    bot = tb.CoachBot(db, manual="MANUAL")
    app = tb.build_application(bot, "123:abc", frozenset({1}))
    assert len(app.handlers[0]) == 5
    assert [j.name for j in app.job_queue.jobs()] == ["daily_checkin"]
