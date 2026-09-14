"""Command-line daily check-in."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic

from . import config
from .agent import Coach
from .db import Database
from .prompt import load_manual
from .tools import set_database

OPENING = "Start today's check-in."
CLOSING = (
    "I'm done for today. If today's food, workout, measurement or session note are not "
    "saved yet, save them now with the tools, then sign off in one line."
)
HELP = """Commands:
  /quit     save anything unsaved and end the session
  /usage    show token usage for this session
  /help     this message
Anything else is sent to your coach."""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fitness-agent", description="Daily health coach check-in")
    p.add_argument("--db", type=Path, default=config.DB_PATH, help="SQLite file (default: data/fitness.db)")
    p.add_argument("--context", type=Path, default=config.CONTEXT_PATH, help="Operating manual markdown")
    p.add_argument("--no-opening", action="store_true", help="Don't have the coach open the check-in")
    p.add_argument("--show-tools", action="store_true", help="Print tool names as they run")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.context.exists():
        print(f"Context file not found: {args.context}", file=sys.stderr)
        return 2

    db = Database(args.db)
    set_database(db)
    coach = Coach(
        client=anthropic.Anthropic(),
        db=db,
        manual=load_manual(args.context),
        on_tool=(lambda name: print(f"  [tool: {name}]", flush=True)) if args.show_tools else None,
    )

    print(f"Fitness coach ({config.MODEL}, effort={config.EFFORT}). Type /help for commands.\n")
    had_user_turn = False
    try:
        if not args.no_opening:
            print("coach> ", end="", flush=True)
            coach.send(OPENING)
        while True:
            try:
                line = input("\nyou> ").strip()
            except EOFError:
                line = "/quit"
            if not line:
                continue
            if line == "/help":
                print(HELP)
                continue
            if line == "/usage":
                u = coach.usage
                print(
                    f"requests={u.requests} input={u.input_tokens} output={u.output_tokens} "
                    f"cache_read={u.cache_read_tokens} cache_write={u.cache_write_tokens}"
                )
                continue
            if line in {"/quit", "/exit", "/q"}:
                if had_user_turn:
                    print("\ncoach> ", end="", flush=True)
                    coach.send(CLOSING)
                break
            had_user_turn = True
            print("\ncoach> ", end="", flush=True)
            coach.send(line)
    except KeyboardInterrupt:
        print("\n(interrupted; unsaved calculations were not logged)")
    except anthropic.AuthenticationError:
        print("\nAuthentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
        return 1
    except anthropic.RateLimitError:
        print("\nRate limited by the API. Wait a minute and try again.", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError as exc:
        print(f"\nCould not reach the API: {exc}", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as exc:
        print(f"\nAPI error {exc.status_code}: {exc.message}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
