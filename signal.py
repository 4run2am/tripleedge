"""
TripleEdge — TQQQ Trend + Risk-Control Signal Bot
===================================================
Fetches weekly data, computes signal, and sends Telegram notification.
Can run in two modes:
  1. Weekly auto-signal (called by GitHub Actions every Monday)
  2. On-demand /status command (called by the bot handler)
Core strategy:
  - Regime filter:  QQQ weekly close > QQQ SMA200
  - Re-entry filter: TQQQ weekly close > TQQQ SMA20
  - Trailing stop:  12% from peak TQQQ price
  - Signal cadence: Every Monday 8AM ET via GitHub Actions
  - Data source:    Tiingo API (reliable in cloud environments)
"""

import os
import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
SMA_REGIME        = 200    # QQQ weekly SMA for regime filter
SMA_REENTRY       = 20     # TQQQ weekly SMA for re-entry confirmation
TRAILING_STOP_PCT = 0.12   # 12% trailing stop from peak
USERS_FILE        = "users.json"
TIINGO_BASE_URL   = "https://api.tiingo.com/tiingo/daily"
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


def fetch_tiingo(ticker, api_key, start_date):
    """
    Fetch daily price data from Tiingo for a given ticker.
    Returns a pandas Series of adjusted close prices indexed by date.
    """
    url = f"{TIINGO_BASE_URL}/{ticker}/prices"
    headers = {"Content-Type": "application/json"}
    params = {
        "startDate":   start_date,
        "token":       api_key,
        "resampleFreq": "weekly",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        raise ValueError(f"No data returned for {ticker}")

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.set_index("date").sort_index()

    # Use adjClose if available, fall back to close
    price_col = "adjClose" if "adjClose" in df.columns else "close"
    return df[price_col].dropna()


def fetch_data(api_key):
    """Fetch QQQ and TQQQ weekly price data from Tiingo."""
    # Need enough history for SMA200 (200 weeks ≈ 4 years, use 5 for safety)
    start_date = (datetime.now() - timedelta(weeks=220)).strftime("%Y-%m-%d")

    print("  Fetching QQQ...")
    qqq  = fetch_tiingo("QQQ",  api_key, start_date)
    print("  Fetching TQQQ...")
    tqqq = fetch_tiingo("TQQQ", api_key, start_date)

    # Align on common dates
    common = qqq.index.intersection(tqqq.index)
    return qqq.loc[common], tqqq.loc[common]


def compute_signal(qqq, tqqq):
    """Compute current signal and all key levels."""
    qqq_sma200 = qqq.rolling(SMA_REGIME).mean()
    tqqq_sma20 = tqqq.rolling(SMA_REENTRY).mean()

    latest_qqq      = float(qqq.iloc[-1])
    latest_tqqq     = float(tqqq.iloc[-1])
    latest_qqq_sma  = float(qqq_sma200.iloc[-1])
    latest_tqqq_sma = float(tqqq_sma20.iloc[-1])

    # Weekly change
    tqqq_weekly_chg = float((tqqq.iloc[-1] / tqqq.iloc[-2] - 1) * 100) if len(tqqq) > 1 else 0.0
    qqq_weekly_chg  = float((qqq.iloc[-1]  / qqq.iloc[-2]  - 1) * 100) if len(qqq)  > 1 else 0.0

    regime_on  = latest_qqq  > latest_qqq_sma
    reentry_ok = latest_tqqq > latest_tqqq_sma

    # Trailing stop — use rolling 52-week high as proxy for peak
    tqqq_52w_high = float(tqqq.iloc[-52:].max()) if len(tqqq) >= 52 else float(tqqq.max())
    stop_level    = round(tqqq_52w_high * (1 - TRAILING_STOP_PCT), 2)
    stop_distance = round((latest_tqqq - stop_level) / latest_tqqq * 100, 1)

    # Trailing stop hit
    stop_hit = latest_tqqq <= stop_level

    # Determine signal
    if stop_hit:
        action = "SELL"
        reason = "Trailing stop hit — exit to SGOV/BIL"
    elif not regime_on:
        action = "CASH"
        reason = "Regime OFF — stay in SGOV/BIL"
    elif regime_on and not reentry_ok:
        action = "WAIT"
        reason = "Regime ON but re-entry not confirmed yet"
    elif regime_on and reentry_ok:
        action = "HOLD"
        reason = "In position — conditions intact"
    else:
        action = "CASH"
        reason = "Conditions not met"

    return {
        "action":          action,
        "reason":          reason,
        "regime_on":       regime_on,
        "reentry_ok":      reentry_ok,
        "stop_hit":        stop_hit,
        "qqq_price":       round(latest_qqq, 2),
        "qqq_sma200":      round(latest_qqq_sma, 2),
        "tqqq_price":      round(latest_tqqq, 2),
        "tqqq_sma20":      round(latest_tqqq_sma, 2),
        "tqqq_52w_high":   round(tqqq_52w_high, 2),
        "stop_level":      stop_level,
        "stop_distance":   stop_distance,
        "tqqq_weekly_chg": round(tqqq_weekly_chg, 2),
        "qqq_weekly_chg":  round(qqq_weekly_chg, 2),
        "date":            datetime.now(timezone.utc).strftime("%a %b %d, %Y"),
    }


def build_stop_bar(distance):
    """Visual bar showing proximity to trailing stop."""
    total  = 10
    safe   = 20.0  # 20% distance = full green bar
    filled = max(0, min(total, int((distance / safe) * total)))
    empty  = total - filled
    color  = "🟩" if distance > 8 else ("🟨" if distance > 4 else "🟥")
    return color * filled + "⬜" * empty


def format_message(sig, portfolio_value=None, mode="weekly"):
    """Format the Telegram notification message."""
    action_map = {
        "HOLD": ("🟢", "HOLD — Stay in TQQQ"),
        "SELL": ("🚨", "SELL — Exit to SGOV/BIL now"),
        "WAIT": ("🟡", "WAIT — Regime ON, re-entry not confirmed"),
        "CASH": ("⚪️", "CASH — Stay in SGOV/BIL"),
        "BUY":  ("🔵", "BUY — Enter TQQQ"),
    }
    emoji, action_label = action_map.get(sig["action"], ("❓", sig["action"]))
    header = "📊 *TripleEdge Weekly Signal*" if mode == "weekly" else "📊 *TripleEdge Status*"

    regime_icon  = "✅" if sig["regime_on"]  else "❌"
    reentry_icon = "✅" if sig["reentry_ok"] else "❌"

    tqqq_arrow = "📈" if sig["tqqq_weekly_chg"] >= 0 else "📉"
    qqq_arrow  = "📈" if sig["qqq_weekly_chg"]  >= 0 else "📉"
    tqqq_chg   = f"+{sig['tqqq_weekly_chg']}%" if sig["tqqq_weekly_chg"] >= 0 else f"{sig['tqqq_weekly_chg']}%"
    qqq_chg    = f"+{sig['qqq_weekly_chg']}%"  if sig["qqq_weekly_chg"]  >= 0 else f"{sig['qqq_weekly_chg']}%"

    stop_bar = build_stop_bar(sig["stop_distance"])

    msg = (
        f"{header}\n"
        f"_{sig['date']}_\n\n"
        f"{emoji} *{action_label}*\n"
        f"_{sig['reason']}_\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"*QQQ*\n"
        f"  Price:   `${sig['qqq_price']}`  {qqq_arrow} {qqq_chg} this week\n"
        f"  SMA200:  `${sig['qqq_sma200']}`  {regime_icon} Regime {'ON' if sig['regime_on'] else 'OFF'}\n\n"
        f"*TQQQ*\n"
        f"  Price:   `${sig['tqqq_price']}`  {tqqq_arrow} {tqqq_chg} this week\n"
        f"  SMA20:   `${sig['tqqq_sma20']}`  {reentry_icon} Re-entry {'OK' if sig['reentry_ok'] else 'NOT OK'}\n\n"
        f"*Risk*\n"
        f"  52w High:  `${sig['tqqq_52w_high']}`\n"
        f"  Stop:      `${sig['stop_level']}` (12% trail)\n"
        f"  Distance:  `{sig['stop_distance']}%` to stop\n"
        f"  {stop_bar}\n"
    )

    if portfolio_value:
        try:
            pv = float(portfolio_value)
            msg += (
                f"\n*Portfolio*\n"
                f"  Starting:  `${pv:,.0f}`\n"
                f"  Stop loss: `${pv * (1 - TRAILING_STOP_PCT):,.0f}` worst case\n"
            )
        except Exception:
            pass

    msg += f"\n━━━━━━━━━━━━━━━━\n_TripleEdge — TQQQ Trend System_"
    return msg


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
    """Called by GitHub Actions every Monday — sends signal to all registered users."""
    bot_token  = os.environ.get("TELEGRAM_BOT_TOKEN")
    tiingo_key = os.environ.get("TIINGO_API_KEY")

    if not bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return
    if not tiingo_key:
        print("ERROR: TIINGO_API_KEY not set")
        return

    print("Fetching market data...")
    qqq, tqqq = fetch_data(tiingo_key)
    print(f"  QQQ bars: {len(qqq)} | TQQQ bars: {len(tqqq)}")

    sig = compute_signal(qqq, tqqq)
    print(f"  Signal: {sig['action']} — {sig['reason']}")
    print(f"  QQQ: ${sig['qqq_price']} | SMA200: ${sig['qqq_sma200']} | Regime: {'ON' if sig['regime_on'] else 'OFF'}")
    print(f"  TQQQ: ${sig['tqqq_price']} | SMA20: ${sig['tqqq_sma20']} | Stop: ${sig['stop_level']} ({sig['stop_distance']}% away)")

    users = load_users()
    if not users:
        print("No users registered yet — message the bot /start to register.")
        return

    for chat_id, user_data in users.items():
        portfolio_value = user_data.get("portfolio_value")
        msg = format_message(sig, portfolio_value=portfolio_value, mode="weekly")
        ok  = send_telegram(bot_token, chat_id, msg)
        name = user_data.get("first_name", chat_id)
        print(f"  Sent to {name} ({chat_id}): {'✅ OK' if ok else '❌ FAILED'}")


if __name__ == "__main__":
    run_weekly_signal()