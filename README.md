# Fitness Agent

A daily health and fitness coaching agent for Sanket, built on the Claude API.
Each day it asks what you ate and what training you did, calculates calories and
macros, compares them to your targets, gives one honest takeaway, and logs
everything to a local SQLite database so it remembers the trend week to week.

The coaching rules, targets, food reference values, training constraints and
wellbeing guardrails all live in one markdown file:
`context/sanket_health_agent_context.md`. Edit that file to change how the coach
behaves. The code does not need to change.

## How it works

```
you  ──chat──▶  Coach (fitness_agent/agent.py)
                  │  system prompt = operating manual (cached) + today's state
                  │  model: claude-opus-5, adaptive thinking, effort=medium
                  ▼
               Claude ──tool calls──▶ fitness_agent/tools.py ──▶ SQLite (data/fitness.db)
```

- `fitness_agent/prompt.py` builds the system prompt. The manual is a static
  block with a prompt-cache marker, so repeated turns re-read it cheaply.
- `fitness_agent/tools.py` defines the tools Claude can call: read state, log a
  day's food, log a workout, log weight/waist, fetch recent logs, weekly trends,
  exercise history, and append a session note.
- `fitness_agent/db.py` is the SQLite layer. One food row per day, one
  measurement row per day, any number of workouts.
- `fitness_agent/agent.py` runs one conversation with the SDK tool runner,
  streaming replies and mirroring the history so multi-turn chat works.
- `fitness_agent/cli.py` is the terminal check-in.

## Setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Authenticate with either an API key or the Anthropic CLI:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or: ant auth login
```

## Daily check-in

```bash
fitness-agent            # or: python -m fitness_agent
```

The coach opens by reading the database, greeting you, and asking about food and
training (plus weight and waist on Mondays). Answer in plain language. When you
are done type `/quit`; the coach saves anything it has not logged yet.

Useful flags:

| Flag | Purpose |
|---|---|
| `--show-tools` | Print each tool call as it happens |
| `--no-opening` | Skip the coach's opening question |
| `--db PATH` | Use a different SQLite file |
| `--context PATH` | Use a different operating manual |

Environment overrides: `FITNESS_AGENT_MODEL`, `FITNESS_AGENT_EFFORT`
(`low`/`medium`/`high`), `FITNESS_AGENT_DB`, `FITNESS_AGENT_CONTEXT`,
`FITNESS_AGENT_TZ`. See `.env.example`.

## Tests

```bash
pytest
```

The tests cover the database layer, every tool, and the prompt builder. They
use an in-memory database and make no API calls.

## Privacy

`context/sanket_health_agent_context.md` contains personal health information
and the database will contain daily logs. Keep this repository private. The
database (`data/`) is git-ignored.

## Next steps

- Wrap the `Coach` class in a Telegram bot or small web app for phone access.
- Add a weekly review command that runs `get_weekly_trends` and produces a
  Monday summary.
- Build a small eval set of realistic check-ins to test prompt changes against.
