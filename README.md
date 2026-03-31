# TripleEdge 📊

A rules-based, weekly signal bot for trading TQQQ (3x Nasdaq ETF) — designed to capture the upside of leveraged exposure while avoiding catastrophic drawdowns through a trend-following regime filter and trailing stop system.

Signals delivered automatically every Monday morning via Telegram.

---

## Strategy

| Parameter | Value |
|---|---|
| Signal source | QQQ weekly close vs SMA200 |
| Trade instrument | TQQQ |
| Entry | QQQ > SMA200 AND TQQQ > SMA20 |
| Exit | QQQ ≤ SMA200 OR 12% trailing stop from peak |
| Cash position | SGOV / BIL while sidelined |
| Cadence | Weekly (Friday close signal, Monday execution) |

### Backtest Results (1999–Present)

| | Strategy | B&H TQQQ | B&H QQQ |
|---|---|---|---|
| CAGR | 19.5% | 27.6% | 15.0% |
| Max Drawdown | -60.9% | -93.6% | -51.4% |
| Sharpe | 0.40 | 0.39 | 0.53 |
| Calmar | 0.32 | 0.29 | 0.29 |

**Out-of-sample (2017–present):** 34.2% CAGR · -45.9% max drawdown · 0.72 Sharpe

> Not financial advice. Past performance does not guarantee future results.

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Register for weekly Monday signals |
| `/status` | Get the current signal on demand |
| `/setportfolio <amount>` | Set your portfolio value for estimates |
| `/help` | List all commands |

---

## Project Structure

```
tripleedge/
├── signal.py              # Signal engine — fetches data, computes BUY/SELL/HOLD
├── weekly_broadcast.py    # Sends Monday signal to all registered users
├── bot_listener.py        # Polls Telegram and handles commands
├── users.json             # Registered users and portfolio values
├── requirements.txt       # Python dependencies
└── .github/
    └── workflows/
        ├── weekly_signal.yml   # Runs every Monday 8am ET
        └── bot_listener.yml    # Polls every 10 minutes for commands
```

---

## Setup

### 1. Create a Telegram Bot
- Message [@BotFather](https://t.me/BotFather) on Telegram
- Run `/newbot` and follow the prompts
- Save your bot token

### 2. Fork this repo (keep it private)

### 3. Add GitHub Secret
Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your token from BotFather |

### 4. Enable GitHub Actions
Go to the **Actions** tab → enable workflows → run **TripleEdge Weekly Signal** manually to test.

### 5. Register
Message your bot `/start` → then `/setportfolio 10000`

---

## How It Works

```
Every Monday 8am ET
        │
        ▼
GitHub Actions triggers weekly_broadcast.py
        │
        ▼
signal.py fetches QQQ, TQQQ, VIX from Yahoo Finance
        │
        ▼
Computes regime filter + SMA20 re-entry + trailing stop
        │
        ▼
Sends BUY / SELL / HOLD to all registered users

Every 10 minutes
        │
        ▼
bot_listener.py polls Telegram for new messages
        │
        ▼
Handles /status, /setportfolio, /help
```

---

## Dependencies

- [yfinance](https://github.com/ranaroussi/yfinance) — market data
- [pandas](https://pandas.pydata.org) — data manipulation
- [numpy](https://numpy.org) — numerical computation
- [requests](https://requests.readthedocs.io) — Telegram API calls

---

_TripleEdge · Rules-based · Not financial advice_
