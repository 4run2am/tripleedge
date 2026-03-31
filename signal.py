"""
TripleEdge — TQQQ Trend + Risk-Control Signal Bot
===================================================
Fetches weekly data, computes signal, and sends Telegram notification.
Can run in two modes:
  1. Weekly auto-signal (called by GitHub Actions every Monday)
  2. On-demand /status command (called by the bot handler)
"""

import os
import json
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ── CONFIG ────────────────────────────────────────────────────────────────────
SMA_REGIME          = 200
SMA_REENTRY         = 20
TRAILING_STOP_PCT   = 0.12
USERS_FILE          = "users.json"
# ─────────────────────────────────────────────────────────────────────────────


def load_users():
    """Load user data from users.json."""
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users):
    """Save user data to users.json."""
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def fetch_data():
    """Fetch QQQ, TQQQ, VIX weekly data."""
    qqq  = yf.download("QQQ",  period="5y", interval="1wk", auto_adjust=True, progress=False)["Close"].squeeze()
    tqqq = yf.download("TQQQ", period="5y", interval="1wk", auto_adjust=True, progress=False)["Close"].squeeze()
    vix  = yf.download("^VIX", period="5y", interval="1wk", auto_adjust=True, progress=False)["Close"].squeeze()

    # Align on common index
    common = qqq.index.intersection(tqqq.index)
    qqq    = qqq.loc[common]
    tqqq   = tqqq.loc[common]
    vix    = vix.reindex(common).ffill()
    return qqq, tqqq, vix


def compute_signal(qqq, tqqq, vix):
    """Compute current signal and key levels."""
    qqq_sma200  = qqq.rolling(SMA_REGIME).mean()
    tqqq_sma20  = tqqq.rolling(SMA_REENTRY).mean()

    latest_qqq       = float(qqq.iloc[-1])
    latest_tqqq      = float(tqqq.iloc[-1])
    latest_vix       = float(vix.iloc[-1])
    latest_qqq_sma   = float(qqq_sma200.iloc[-1])
    latest_tqqq_sma  = float(tqqq_sma20.iloc[-1])

    # Weekly change
    tqqq_weekly_chg  = float((tqqq.iloc[-1] / tqqq.iloc[-2] - 1) * 100)
    qqq_weekly_chg   = float((qqq.iloc[-1] / qqq.iloc[-2] - 1) * 100)

    regime_on   = latest_qqq > latest_qqq_sma
    reentry_ok  = latest_tqqq > latest_tqqq_sma

    # Trailing stop — use rolling 52-week high as proxy for peak
    tqqq_52w_high = float(tqqq.iloc[-52:].max())
    stop_level    = round(tqqq_52w_high * (1 - TRAILING_STOP_PCT), 2)
    stop_distance = round((latest_tqqq - stop_level) / latest_tqqq * 100, 1)

    # Determine action
    if regime_on and reentry_ok:
        if not regime_on:
            action = "SELL"
            reason = "Regime turned OFF"
        elif latest_tqqq <= stop_level:
            action = "SELL"
            reason = "Trailing stop hit"
        else:
            action = "HOLD"
            reason = "In position"
    else:
        if regime_on and not reentry_ok:
            action = "WAIT"
            reason = "Regime ON but re-entry not confirmed"
        elif not regime_on:
            action = "CASH"
            reason = "Regime OFF — stay in SGOV/BIL"
        else:
            action = "CASH"
            reason = "Conditions not met"

    # Override: check if stop is actually hit
    if latest_tqqq <= stop_level:
        action = "SELL"
        reason = "Trailing stop hit"

    return {
        "action":           action,
        "reason":           reason,
        "regime_on":        regime_on,
        "reentry_ok":       reentry_ok,
        "qqq_price":        round(latest_qqq, 2),
        "qqq_sma200":       round(latest_qqq_sma, 2),
        "tqqq_price":       round(latest_tqqq, 2),
        "tqqq_sma20":       round(latest_tqqq_sma, 2),
        "tqqq_52w_high":    round(tqqq_52w_high, 2),
        "stop_level":       stop_level,
        "stop_distance":    stop_distance,
        "tqqq_weekly_chg":  round(tqqq_weekly_chg, 2),
        "qqq_weekly_chg":   round(qqq_weekly_chg, 2),
        "vix":              round(latest_vix, 1),
        "date":             datetime.now(timezone.utc).strftime("%a %b %d, %Y"),
    }


def format_message(sig, portfolio_value=None, mode="weekly"):
    """Format the Telegram message."""

    # Action emoji + header
    action_map = {
        "HOLD": ("🟢", "HOLD — Stay in TQQQ"),
        "SELL": ("🚨", "SELL — Exit to SGOV/BIL"),
        "WAIT": ("🟡", "WAIT — Regime ON, no re-entry yet"),
        "CASH": ("⚪️", "CASH — Stay in SGOV/BIL"),
        "BUY":  ("🔵", "BUY — Enter TQQQ"),
    }
    emoji, action_label = action_map.get(sig["action"], ("❓", sig["action"]))

    header = "📊 *TripleEdge Weekly Signal*" if mode == "weekly" else "📊 *TripleEdge Status*"

    regime_icon  = "✅" if sig["regime_on"]  else "❌"
    reentry_icon = "✅" if sig["reentry_ok"] else "❌"

    tqqq_chg_icon = "📈" if sig["tqqq_weekly_chg"] >= 0 else "📉"
    qqq_chg_icon  = "📈" if sig["qqq_weekly_chg"]  >= 0 else "📉"

    tqqq_chg_str = f"+{sig['tqqq_weekly_chg']}%" if sig["tqqq_weekly_chg"] >= 0 else f"{sig['tqqq_weekly_chg']}%"
    qqq_chg_str  = f"+{sig['qqq_weekly_chg']}%"  if sig["qqq_weekly_chg"]  >= 0 else f"{sig['qqq_weekly_chg']}%"

    stop_bar = build_stop_bar(sig["stop_distance"])

    msg = (
        f"{header}\n"
        f"_{sig['date']}_\n\n"
        f"{emoji} *{action_label}*\n"
        f"_{sig['reason']}_\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"*QQQ*\n"
        f"  Price:   `${sig['qqq_price']}`  {qqq_chg_icon} {qqq_chg_str} this week\n"
        f"  SMA200:  `${sig['qqq_sma200']}`  {regime_icon} Regime {'ON' if sig['regime_on'] else 'OFF'}\n\n"
        f"*TQQQ*\n"
        f"  Price:   `${sig['tqqq_price']}`  {tqqq_chg_icon} {tqqq_chg_str} this week\n"
        f"  SMA20:   `${sig['tqqq_sma20']}`  {reentry_icon} Re-entry {'OK' if sig['reentry_ok'] else 'NOT OK'}\n\n"
        f"*Risk*\n"
        f"  52w High:  `${sig['tqqq_52w_high']}`\n"
        f"  Stop:      `${sig['stop_level']}` (12% trail)\n"
        f"  Distance:  `{sig['stop_distance']}%` to stop\n"
        f"  {stop_bar}\n"
        f"  VIX:       `{sig['vix']}`\n"
    )

    if portfolio_value:
        try:
            pv = float(portfolio_value)
            msg += (
                f"\n*Portfolio*\n"
                f"  Starting:  `${pv:,.0f}`\n"
                f"  Stop loss: `${pv * (1 - TRAILING_STOP_PCT):,.0f}` at max drawdown\n"
            )
        except Exception:
            pass

    msg += f"\n━━━━━━━━━━━━━━━━\n_TripleEdge — TQQQ Trend System_"
    return msg


def build_stop_bar(distance):
    """Visual progress bar showing distance to stop."""
    total_bars = 10
    safe_zone  = 20.0  # 20% = full bar
    filled     = max(0, min(total_bars, int((distance / safe_zone) * total_bars)))
    empty      = total_bars - filled
    color      = "🟩" if distance > 8 else ("🟨" if distance > 4 else "🟥")
    return color * filled + "⬜" * empty


def send_telegram(bot_token, chat_id, message):
    """Send a Telegram message."""
    url  = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
    }
    resp = requests.post(url, data=data, timeout=10)
    return resp.ok


def run_weekly_signal():
    """Called by GitHub Actions every Monday — sends signal to all users."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return

    print("Fetching market data...")
    qqq, tqqq, vix = fetch_data()
    sig = compute_signal(qqq, tqqq, vix)

    print(f"Signal: {sig['action']} — {sig['reason']}")

    users = load_users()
    if not users:
        print("No users registered yet.")
        return

    for chat_id, user_data in users.items():
        portfolio_value = user_data.get("portfolio_value")
        msg = format_message(sig, portfolio_value=portfolio_value, mode="weekly")
        ok  = send_telegram(bot_token, chat_id, msg)
        print(f"  Sent to {chat_id}: {'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    run_weekly_signal()
