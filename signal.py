"""
TripleEdge — Dual-Engine Signal Bot (UPRO + UGL)
=================================================
Active strategy: 75% UPRO / 25% UGL.

UPRO Engine:
  - Regime:   SPY weekly close > SPY 65-week SMA
  - Re-entry: UPRO weekly close > UPRO 10-week SMA
  - Stop:     22% trailing stop from UPRO 52-week high

UGL Engine:
  - Regime:   GLD weekly close > GLD 100-week SMA
  - Re-entry: GLD weekly close > GLD 20-week SMA  (GLD, not UGL)
  - Stop:     28% trailing stop from UGL 52-week high

Portfolio:  75% UPRO / 25% UGL
Cash proxy: SGOV / T-bills while sidelined
Cadence:    Weekly — Friday close, Monday open execution
Data:       Tiingo API
"""

import os
import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# ── ENGINE PARAMETERS ─────────────────────────────────────────────────────────
# UPRO Engine  (SPY regime → UPRO re-entry → UPRO trailing stop)
UPRO_SMA_REGIME        = 65
UPRO_SMA_REENTRY       = 10
UPRO_TRAILING_STOP_PCT = 0.22

# UGL Engine   (GLD regime → GLD re-entry → UGL trailing stop)
UGL_SMA_REGIME         = 100
UGL_SMA_REENTRY        = 20
UGL_TRAILING_STOP_PCT  = 0.28

# Portfolio weights
UPRO_WEIGHT = 0.75
UGL_WEIGHT  = 0.25

USERS_FILE      = "users.json"
TIINGO_BASE_URL = "https://api.tiingo.com/tiingo/daily"
# ─────────────────────────────────────────────────────────────────────────────


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def fetch_tiingo(ticker, api_key, start_date):
    """Fetch weekly adjusted close prices from Tiingo."""
    url     = f"{TIINGO_BASE_URL}/{ticker}/prices"
    headers = {"Content-Type": "application/json"}
    params  = {"startDate": start_date, "token": api_key, "resampleFreq": "weekly"}
    resp    = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data    = resp.json()
    if not data:
        raise ValueError(f"No data returned for {ticker}")
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.set_index("date").sort_index()
    col = "adjClose" if "adjClose" in df.columns else "close"
    return df[col].dropna()


def fetch_data(api_key=None):
    """Fetch SPY, UPRO, GLD, UGL weekly price data from Tiingo.

    Returns (spy, upro, gld, ugl) as aligned pandas Series.
    """
    if api_key is None:
        api_key = os.environ.get("TIINGO_API_KEY")
    # 220 weeks covers the 100-week UGL regime SMA plus warm-up buffer
    start = (datetime.now() - timedelta(weeks=220)).strftime("%Y-%m-%d")

    print("  Fetching SPY...")
    spy  = fetch_tiingo("SPY",  api_key, start)
    print("  Fetching UPRO...")
    upro = fetch_tiingo("UPRO", api_key, start)
    print("  Fetching GLD...")
    gld  = fetch_tiingo("GLD",  api_key, start)
    print("  Fetching UGL...")
    ugl  = fetch_tiingo("UGL",  api_key, start)

    common_upro = spy.index.intersection(upro.index)
    spy, upro   = spy.loc[common_upro], upro.loc[common_upro]

    common_ugl = gld.index.intersection(ugl.index)
    gld, ugl   = gld.loc[common_ugl], ugl.loc[common_ugl]

    return spy, upro, gld, ugl


def _compute_engine_signal(
    regime_series, reentry_series, stop_series,
    sma_regime, sma_reentry, trailing_stop_pct,
    regime_ticker, reentry_ticker, stop_ticker,
):
    """Compute signal for one engine.

    regime_series  — unleveraged index for regime filter (e.g. SPY or GLD)
    reentry_series — series for re-entry confirmation (may equal regime_series)
    stop_series    — leveraged ETF for trailing stop tracking (e.g. UPRO or UGL)
    """
    # Regime filter
    reg_sma        = regime_series.rolling(sma_regime).mean()
    latest_reg     = float(regime_series.iloc[-1])
    latest_reg_sma = float(reg_sma.iloc[-1])
    regime_on      = latest_reg > latest_reg_sma
    reg_chg        = float((regime_series.iloc[-1] / regime_series.iloc[-2] - 1) * 100) if len(regime_series) > 1 else 0.0

    # Re-entry signal
    re_sma         = reentry_series.rolling(sma_reentry).mean()
    latest_re      = float(reentry_series.iloc[-1])
    latest_re_sma  = float(re_sma.iloc[-1])
    reentry_ok     = latest_re > latest_re_sma
    re_chg         = float((reentry_series.iloc[-1] / reentry_series.iloc[-2] - 1) * 100) if len(reentry_series) > 1 else 0.0

    # Trailing stop (on leveraged ETF)
    stop_52w       = float(stop_series.iloc[-52:].max()) if len(stop_series) >= 52 else float(stop_series.max())
    stop_level     = round(stop_52w * (1 - trailing_stop_pct), 2)
    latest_stop    = float(stop_series.iloc[-1])
    stop_distance  = round((latest_stop - stop_level) / latest_stop * 100, 1)
    stop_hit       = latest_stop <= stop_level

    if stop_hit:
        action, reason = "SELL", "Trailing stop hit — exit to SGOV/BIL"
    elif not regime_on:
        action, reason = "CASH", "Regime OFF — stay in SGOV/BIL"
    elif not reentry_ok:
        action, reason = "WAIT", "Regime ON but re-entry not confirmed yet"
    else:
        action, reason = "HOLD", "In position — conditions intact"

    return {
        "action":              action,
        "reason":              reason,
        "regime_on":           regime_on,
        "reentry_ok":          reentry_ok,
        "stop_hit":            stop_hit,
        "regime_ticker":       regime_ticker,
        "regime_price":        round(latest_reg, 2),
        "regime_sma":          round(latest_reg_sma, 2),
        "sma_regime":          sma_regime,
        "regime_chg":          round(reg_chg, 2),
        "reentry_ticker":      reentry_ticker,
        "reentry_price":       round(latest_re, 2),
        "reentry_sma":         round(latest_re_sma, 2),
        "sma_reentry":         sma_reentry,
        "reentry_chg":         round(re_chg, 2),
        "stop_ticker":         stop_ticker,
        "stop_price":          round(latest_stop, 2),
        "stop_52w_high":       round(stop_52w, 2),
        "stop_level":          stop_level,
        "stop_distance":       stop_distance,
        "trailing_stop_pct":   trailing_stop_pct,
        "same_regime_reentry": (regime_ticker == reentry_ticker),
    }


def compute_signal(spy, upro, gld, ugl):
    """Compute signals for both engines. Returns dict with 'upro', 'ugl', 'date'."""
    upro_sig = _compute_engine_signal(
        spy, upro, upro,
        UPRO_SMA_REGIME, UPRO_SMA_REENTRY, UPRO_TRAILING_STOP_PCT,
        "SPY", "UPRO", "UPRO",
    )
    ugl_sig = _compute_engine_signal(
        gld, gld, ugl,
        UGL_SMA_REGIME, UGL_SMA_REENTRY, UGL_TRAILING_STOP_PCT,
        "GLD", "GLD", "UGL",
    )
    return {
        "upro": upro_sig,
        "ugl":  ugl_sig,
        "date": datetime.now(timezone.utc).strftime("%a %b %d, %Y"),
    }


def _stop_bar(distance, max_distance):
    """Ten-cell visual bar showing distance to trailing stop."""
    filled = max(0, min(10, int((distance / max_distance) * 10)))
    color  = "🟩" if distance > max_distance * 0.4 else ("🟨" if distance > max_distance * 0.2 else "🟥")
    return color * filled + "⬜" * (10 - filled)


def _format_engine_block(sig, label):
    """Format one engine's signal block for Telegram Markdown."""
    action_map = {
        "HOLD": ("🟢", "HOLD — Stay in position"),
        "SELL": ("🚨", "SELL — Exit to SGOV/BIL now"),
        "WAIT": ("🟡", "WAIT — Regime ON, re-entry not confirmed"),
        "CASH": ("⚪️", "CASH — Stay in SGOV/BIL"),
        "BUY":  ("🔵", "BUY — Enter position"),
    }
    emoji, action_label = action_map.get(sig["action"], ("❓", sig["action"]))
    regime_icon  = "✅" if sig["regime_on"]  else "❌"
    reentry_icon = "✅" if sig["reentry_ok"] else "❌"

    def chg_str(v): return f"+{v}%" if v >= 0 else f"{v}%"
    def arrow(v):   return "📈" if v >= 0 else "📉"

    stop_bar = _stop_bar(sig["stop_distance"], sig["trailing_stop_pct"] * 100)
    stop_pct = f"{sig['trailing_stop_pct']:.0%}"

    if sig["same_regime_reentry"]:
        # UGL engine: GLD fills both regime and re-entry roles → one compact block
        block = (
            f"{emoji} *{label}: {action_label}*\n"
            f"_{sig['reason']}_\n\n"
            f"*{sig['regime_ticker']}*\n"
            f"  Price:   `${sig['regime_price']}`  {arrow(sig['regime_chg'])} {chg_str(sig['regime_chg'])}\n"
            f"  SMA{sig['sma_regime']}:  `${sig['regime_sma']}`  {regime_icon} Regime {'ON' if sig['regime_on'] else 'OFF'}\n"
            f"  SMA{sig['sma_reentry']}:   `${sig['reentry_sma']}`  {reentry_icon} Re-entry {'OK' if sig['reentry_ok'] else 'NOT OK'}\n\n"
            f"*Risk ({sig['stop_ticker']})*\n"
            f"  52w High:  `${sig['stop_52w_high']}`\n"
            f"  Stop:      `${sig['stop_level']}` ({stop_pct} trail)\n"
            f"  Distance:  `{sig['stop_distance']}%` to stop\n"
            f"  {stop_bar}\n"
        )
    else:
        # UPRO engine: separate regime ticker (SPY) and position ticker (UPRO)
        block = (
            f"{emoji} *{label}: {action_label}*\n"
            f"_{sig['reason']}_\n\n"
            f"*{sig['regime_ticker']}* (Regime)\n"
            f"  Price:   `${sig['regime_price']}`  {arrow(sig['regime_chg'])} {chg_str(sig['regime_chg'])}\n"
            f"  SMA{sig['sma_regime']}:  `${sig['regime_sma']}`  {regime_icon} Regime {'ON' if sig['regime_on'] else 'OFF'}\n\n"
            f"*{sig['reentry_ticker']}* (Position)\n"
            f"  Price:   `${sig['reentry_price']}`  {arrow(sig['reentry_chg'])} {chg_str(sig['reentry_chg'])}\n"
            f"  SMA{sig['sma_reentry']}:   `${sig['reentry_sma']}`  {reentry_icon} Re-entry {'OK' if sig['reentry_ok'] else 'NOT OK'}\n\n"
            f"*Risk*\n"
            f"  52w High:  `${sig['stop_52w_high']}`\n"
            f"  Stop:      `${sig['stop_level']}` ({stop_pct} trail)\n"
            f"  Distance:  `{sig['stop_distance']}%` to stop\n"
            f"  {stop_bar}\n"
        )
    return block


def format_message(sig, portfolio_value=None, mode="weekly"):
    """Build the full dual-engine Telegram message."""
    header = "📊 *TripleEdge Weekly Signal*" if mode == "weekly" else "📊 *TripleEdge Status*"

    msg  = f"{header}\n_{sig['date']}_\n\n"
    msg += "━━━━━━━━━━━━━━━━\n"
    msg += _format_engine_block(sig["upro"], "UPRO (75%)")
    msg += "\n━━━━━━━━━━━━━━━━\n"
    msg += _format_engine_block(sig["ugl"],  "UGL (25%)")

    if portfolio_value:
        try:
            pv = float(portfolio_value)
            msg += (
                f"\n━━━━━━━━━━━━━━━━\n"
                f"*Your Portfolio* (`${pv:,.0f}`)\n"
                f"  UPRO 75%:  `${pv * UPRO_WEIGHT:,.0f}`\n"
                f"  UGL  25%:  `${pv * UGL_WEIGHT:,.0f}`\n"
                f"  Cash out:  park in SGOV for inactive engine(s)\n"
            )
        except Exception:
            pass

    msg += f"\n━━━━━━━━━━━━━━━━\n_TripleEdge · UPRO + UGL · Not financial advice_"
    return msg


def send_telegram(bot_token, chat_id, message):
    url  = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
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
    spy, upro, gld, ugl = fetch_data(tiingo_key)
    print(f"  SPY: {len(spy)} bars | UPRO: {len(upro)} bars")
    print(f"  GLD: {len(gld)} bars | UGL:  {len(ugl)} bars")

    sig = compute_signal(spy, upro, gld, ugl)
    u, g = sig["upro"], sig["ugl"]

    print(f"  UPRO ({u['action']}): SPY ${u['regime_price']} vs SMA{u['sma_regime']} ${u['regime_sma']} | "
          f"UPRO ${u['reentry_price']} vs SMA{u['sma_reentry']} ${u['reentry_sma']} | "
          f"Stop ${u['stop_level']} ({u['stop_distance']}% away)")
    print(f"  UGL  ({g['action']}): GLD ${g['regime_price']} vs SMA{g['sma_regime']} ${g['regime_sma']} (regime), "
          f"SMA{g['sma_reentry']} ${g['reentry_sma']} (re-entry) | "
          f"UGL ${g['stop_price']} stop ${g['stop_level']} ({g['stop_distance']}% away)")

    users = load_users()
    if not users:
        print("No users registered. Message the bot /start to register.")
        return

    for chat_id, user_data in users.items():
        portfolio_value = user_data.get("portfolio_value")
        msg = format_message(sig, portfolio_value=portfolio_value, mode="weekly")
        ok  = send_telegram(bot_token, chat_id, msg)
        name = user_data.get("first_name", chat_id)
        print(f"  Sent to {name} ({chat_id}): {'✅ OK' if ok else '❌ FAILED'}")


if __name__ == "__main__":
    run_weekly_signal()
