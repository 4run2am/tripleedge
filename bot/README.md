# TripleEdge Alpaca Bot

Out-of-sample forward-testing harness for the TripleEdge 75/25 strategy.
Connects to **Alpaca paper trading**, computes signals via the same validated
`engine.py` the backtest uses, and tracks weekly performance so you can compare
live behavior vs the backtest's expected behavior.

> **This bot is for paper-trading validation. Live trading is OFF by default
> and requires multiple explicit safety overrides to enable.**

---

## Safety model

| Setting | Default | Effect |
|---|---|---|
| `BOT_MODE` | `alert_only` | Compute + log signals. **No orders are placed.** |
| `LIVE_TRADING` | (unset) | Paper endpoint only. Setting `true` switches to live URL. |
| `LIVE_TRADING_CONFIRMED` | (unset) | Hard requirement — bot refuses to start in live mode without it. |

Three bot modes:

| Mode | Behavior |
|---|---|
| `alert_only` (default) | Computes signals, logs to CSV, optionally notifies, places nothing |
| `dry_run`              | Shows what order WOULD be submitted (request payload only) |
| `execute`              | Actually submits market orders to whichever endpoint is active |

**Paper endpoint is hardcoded** at `https://paper-api.alpaca.markets`. The only
way to point at the live endpoint is to set both `LIVE_TRADING=true` AND
`LIVE_TRADING_CONFIRMED=true`. Either alone fails fast.

---

## Setup

```bash
# 1. From the repo root, install bot deps
pip install -r requirements.txt

# 2. Copy the template and add your PAPER keys from app.alpaca.markets
cp .env.example .env

# 3. Edit .env:
#     ALPACA_API_KEY=...
#     ALPACA_SECRET_KEY=...
#     TIINGO_API_KEY=...        # fallback for long-history bars
#     BOT_MODE=alert_only       # default — leave this alone for first run

# 4. Verify .env is gitignored — this should print the path
git check-ignore .env
# expected output:  .env

# 5. First run in alert_only mode
python -m bot.run
```

The first run prints a header showing the endpoint (must say PAPER), the mode,
fetches weekly bars, computes signals, reads your Alpaca paper account, and
prints what it WOULD do — but submits no orders.

---

## Files & state

```
bot/
├── run.py        # entry point — orchestrates a single run
├── signals.py    # thin wrapper over engine.py (no strategy math here)
├── broker.py     # Alpaca SDK wrapper, paper-by-default
├── state.py      # trailing-stop peak persistence
├── notify.py     # optional Telegram one-liner
├── config.py     # env loading + safety flags
├── state/        # GITIGNORED — positions.json with in_position/peak/entry
└── logs/         # GITIGNORED
    ├── run_log.csv            # every run: signal states, intended/placed orders
    └── paper_track_record.csv # weekly equity + position values — for compare vs backtest
```

State is persisted in `bot/state/positions.json` and ratcheted every run.
**The trailing-stop peak ratchets up only — it never falls.** A new weekly
high lifts the peak; otherwise the stored peak is kept across runs.

---

## How to read the logs

`logs/run_log.csv` — one row per bot run with columns:
- `timestamp`, `mode`, `endpoint`
- per engine: `_action`, `_regime_on`, `_reentry_ok`, `_in_position`, `_peak`, `_stop_level`
- `equity`, `orders_intended`, `orders_placed`

`logs/paper_track_record.csv` — one row per run with portfolio snapshot:
- `timestamp`, `equity`, per-engine qty + market value, cash

After ~10+ weeks of data this CSV can be compared against the backtest's
expected weekly returns to detect divergence (slippage, execution timing).

---

## Switching to `execute` (paper)

Once you trust the signals from `alert_only`:

```bash
BOT_MODE=execute python -m bot.run
```

The bot will reconcile positions and submit market orders. **Still paper** —
no real money at risk.

---

## Switching to LIVE trading (real money)

⚠ Read this twice. Required steps:

1. Edit `.env`:
   ```
   LIVE_TRADING=true
   LIVE_TRADING_CONFIRMED=true
   BOT_MODE=execute
   ```
2. Replace `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` with **live** keys
   (the paper ones won't authenticate against the live endpoint).
3. Run the bot. It will print a 5-second countdown — Ctrl-C to abort.

There is no command-line flag to enable live trading. It's environment-only,
and requires two separate `true` values. This is intentional.

---

## Cadence — running it

Run manually each Friday after US market close:

```bash
python -m bot.run
```

The strategy expects you to **act on Monday open** (the next trading day).
The bot computes the signal based on the Friday close; if you set
`BOT_MODE=execute`, orders go in as DAY orders to fill at the next session.

### Optional automation (commented examples — leave OFF for now)

**Cron** (uncomment when ready):
```cron
# Every Friday at 16:30 ET (after market close) — adjust for your timezone
# 30 16 * * 5  cd /path/to/tripleedge && BOT_MODE=execute /path/to/python -m bot.run >> bot/logs/cron.log 2>&1
```

**GitHub Actions** — see `.github/workflows/` examples. If you create one,
keys MUST come from repository secrets (`secrets.ALPACA_API_KEY` /
`secrets.ALPACA_SECRET_KEY`), NEVER committed values.

---

## Notifications

If you set `TELEGRAM_BOT_TOKEN` and `BOT_NOTIFY_CHAT_ID` in `.env`, each run
sends a one-line Markdown summary to that chat. If either is missing, the
bot silently skips notification (no error, no crash).

The summary looks like:

```
📊 TripleEdge Bot — ALERT_ONLY on PAPER
Equity: $100,000.00

UPRO (75%): HOLD, regime ON, re-entry ON, stop $116.50
UGL  (25%): WAIT, regime ON, re-entry OFF

Orders: none needed — at target
```

---

## What this bot is for

To validate that the strategy works on **truly out-of-sample data** — the
future, the only data that wasn't used to fit the parameters. The repo's
research scripts have already done in-sample and walk-forward backtesting.
Paper trading on Alpaca gives you live data with zero risk.

Run this for a few months in `alert_only`, then `execute` (paper), and
compare `paper_track_record.csv` against the backtest's expected weekly
returns. Material divergence is a yellow flag worth investigating before
risking real money.
