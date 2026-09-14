"""Telegram front end for the coach.

Run with `fitness-agent-telegram`. Requires TELEGRAM_BOT_TOKEN in the environment
and, after the first message, TELEGRAM_ALLOWED_USER_IDS so only you can talk to it.

One Coach conversation per chat, kept in memory. `/new` starts a fresh one; the
database keeps the long-term memory either way. An optional daily job opens the
evening check-in for you.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import time as dtime
from zoneinfo import ZoneInfo

import anthropic

from . import config
from .agent import Coach
from .db import Database
from .prompt import load_manual
from .tools import set_database

log = logging.getLogger("fitness_agent.telegram")

TELEGRAM_MAX_CHARS = 4096
CHAT_ID_STATE_KEY = "telegram_chat_id"

OPENING = "Start today's check-in."
TELEGRAM_STYLE = """\
Channel: Telegram on a phone. Keep replies short and skimmable. Do not use markdown
tables, headers, or code blocks: they do not render there. Show macro totals as a few
short lines like "Protein 128 g (target 150)". Emoji sparingly."""


# ----------------------------------------------------------------- helpers
def split_message(text: str, limit: int = TELEGRAM_MAX_CHARS) -> list[str]:
    """Split text into Telegram-sized chunks, preferring paragraph then line breaks."""
    text = text.strip()
    if not text:
        return ["(no reply)"]
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    chunks.append(text)
    return chunks


def is_allowed(user_id: int | None, allowed: frozenset[int]) -> bool:
    return user_id is not None and user_id in allowed


def parse_checkin_time(value: str) -> dtime | None:
    value = (value or "").strip()
    if not value:
        return None
    hour, _, minute = value.partition(":")
    return dtime(int(hour), int(minute or 0), tzinfo=ZoneInfo(config.TIMEZONE))


# --------------------------------------------------------------------- bot
class CoachBot:
    def __init__(self, db: Database, manual: str):
        self.db = db
        self.manual = manual
        self.client = anthropic.Anthropic()
        self.coaches: dict[int, Coach] = {}
        self.locks: dict[int, asyncio.Lock] = {}

    def coach_for(self, chat_id: int) -> Coach:
        if chat_id not in self.coaches:
            self.coaches[chat_id] = Coach(
                client=self.client,
                db=self.db,
                manual=self.manual,
                extra_instructions=TELEGRAM_STYLE,
                on_text=lambda _s: None,
            )
        return self.coaches[chat_id]

    def lock_for(self, chat_id: int) -> asyncio.Lock:
        return self.locks.setdefault(chat_id, asyncio.Lock())

    async def ask(self, chat_id: int, text: str) -> str:
        """Send a user turn to the chat's coach, off the event loop."""
        async with self.lock_for(chat_id):
            coach = self.coach_for(chat_id)
            try:
                return await asyncio.to_thread(coach.send, text)
            except anthropic.RateLimitError:
                return "The API is rate limiting us. Try again in a minute."
            except anthropic.APIConnectionError:
                return "I couldn't reach the API just now. Try again shortly."
            except anthropic.APIStatusError as exc:
                log.exception("API error")
                return f"API error {exc.status_code}. Try again, or /new to reset the conversation."


def build_application(bot: CoachBot, token: str, allowed: frozenset[int]):
    from telegram import Update
    from telegram.constants import ChatAction
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    async def reply(update: Update, text: str) -> None:
        assert update.effective_message is not None
        for chunk in split_message(text):
            await update.effective_message.reply_text(chunk)

    async def guard(update: Update) -> bool:
        user = update.effective_user
        uid = user.id if user else None
        if is_allowed(uid, allowed):
            return True
        if not allowed:
            await reply(
                update,
                f"Hi. This bot is locked to one person. Your Telegram user id is {uid}.\n"
                f"Set TELEGRAM_ALLOWED_USER_IDS={uid} and restart the bot.",
            )
        else:
            log.warning("Ignoring message from unauthorised user %s", uid)
        return False

    async def run_turn(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        assert update.effective_chat is not None
        chat_id = update.effective_chat.id
        bot.db.set_state(CHAT_ID_STATE_KEY, str(chat_id))
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        answer = await bot.ask(chat_id, text)
        await reply(update, answer)

    async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await guard(update):
            await run_turn(update, context, OPENING)

    async def on_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        assert update.effective_chat is not None
        bot.coaches.pop(update.effective_chat.id, None)
        await reply(update, "Fresh conversation. Your logs are safe in the database.")

    async def on_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        assert update.effective_chat is not None
        u = bot.coach_for(update.effective_chat.id).usage
        await reply(
            update,
            f"This conversation: {u.requests} requests, {u.input_tokens} input, "
            f"{u.output_tokens} output, {u.cache_read_tokens} cached tokens.",
        )

    async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        await reply(
            update,
            "/start or /checkin - open today's check-in\n"
            "/new - start a fresh conversation (logs are kept)\n"
            "/usage - token usage this conversation\n"
            "Anything else goes straight to your coach.",
        )

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        assert update.effective_message is not None and update.effective_message.text
        await run_turn(update, context, update.effective_message.text)

    async def daily_checkin(context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = bot.db.get_state().get(CHAT_ID_STATE_KEY)
        if not chat_id:
            log.info("Daily check-in skipped: nobody has messaged the bot yet")
            return
        cid = int(chat_id)
        bot.coaches.pop(cid, None)  # a new day, a new conversation
        answer = await bot.ask(cid, OPENING)
        for chunk in split_message(answer):
            await context.bot.send_message(chat_id=cid, text=chunk)

    async def post_init(app: Application) -> None:
        await app.bot.set_my_commands(
            [
                ("start", "Open today's check-in"),
                ("checkin", "Open today's check-in"),
                ("new", "Start a fresh conversation"),
                ("usage", "Token usage this conversation"),
                ("help", "How to use the coach"),
            ]
        )

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler(["start", "checkin"], on_start))
    app.add_handler(CommandHandler("new", on_new))
    app.add_handler(CommandHandler("usage", on_usage))
    app.add_handler(CommandHandler("help", on_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    checkin_at = parse_checkin_time(config.TELEGRAM_CHECKIN_TIME)
    if checkin_at is not None and app.job_queue is not None:
        app.job_queue.run_daily(daily_checkin, time=checkin_at, name="daily_checkin")
        log.info("Daily check-in scheduled at %s %s", checkin_at.strftime("%H:%M"), config.TIMEZONE)
    return app


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not config.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set.", file=sys.stderr)
        return 2
    if not config.CONTEXT_PATH.exists():
        print(f"Context file not found: {config.CONTEXT_PATH}", file=sys.stderr)
        return 2
    if not config.TELEGRAM_ALLOWED_USER_IDS:
        log.warning("TELEGRAM_ALLOWED_USER_IDS is empty: the bot will only tell users their id")

    db = Database(config.DB_PATH)
    set_database(db)
    bot = CoachBot(db, load_manual(config.CONTEXT_PATH))
    app = build_application(bot, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_ALLOWED_USER_IDS)
    log.info("Coach bot starting (model=%s, effort=%s)", config.MODEL, config.EFFORT)
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
