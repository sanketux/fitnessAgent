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
- `fitness_agent/telegram_bot.py` is the Telegram front end.

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

## Telegram bot

The same coach, reachable from your phone. It runs as a long-lived process on
any machine with internet access (a laptop that stays on, a Raspberry Pi, or a
small VPS).

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Install the Telegram extra and set the environment:

   ```bash
   pip install -e ".[telegram]"
   export ANTHROPIC_API_KEY=sk-ant-...
   export TELEGRAM_BOT_TOKEN=123456:ABC...
   ```

3. Start it and send `/start` to your bot. On the first message it replies with
   your numeric Telegram user id and refuses to coach until you lock it down:

   ```bash
   fitness-agent-telegram
   # then, after reading your id from the bot's reply:
   export TELEGRAM_ALLOWED_USER_IDS=<your id>
   fitness-agent-telegram
   ```

4. `/start` or `/checkin` opens the day's check-in. Plain messages go to the
   coach. `/new` resets the conversation (the database keeps the logs).

By default the bot also opens the check-in for you every day at 21:00
Asia/Kolkata. Change it with `TELEGRAM_CHECKIN_TIME=20:30`, or set it to an
empty string to turn it off. The reminder only starts once you have messaged
the bot at least once, because it needs your chat id.

Never commit the bot token. If it is ever exposed, revoke it in BotFather with
`/revoke` and set the new one.

### Keeping it running

A minimal systemd unit for a Linux server (adjust paths and user):

```ini
[Unit]
Description=Fitness coach Telegram bot
After=network-online.target

[Service]
User=sanket
WorkingDirectory=/home/sanket/fitnessAgent
EnvironmentFile=/home/sanket/fitnessAgent/.env
ExecStart=/home/sanket/fitnessAgent/.venv/bin/fitness-agent-telegram
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now fitness-coach
journalctl -u fitness-coach -f
```

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

- WhatsApp: put the WhatsApp Business Cloud API or Twilio in front of `CoachBot`.
- Add a weekly review command that runs `get_weekly_trends` and produces a
  Monday summary.
- Build a small eval set of realistic check-ins to test prompt changes against.
