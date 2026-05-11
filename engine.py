"""
TripleEdge — Dual-Engine Signal Bot (UPRO + UGL)
=================================================
Active strategy: 75% UPRO / 25% UGL.

UPRO Engine:
  - Regime:   SPY weekly close > SPY 65-week SMA
  - Re-entry: UPRO weekly close > UPRO 10-week SMA
  - Stop:     22% trailing stop from UPRO peak SINCE ENTRY

UGL Engine:
  - Regime:   GLD weekly close > GLD 100-week SMA
  - Re-entry: GLD weekly close > GLD 20-week SMA  (GLD, not UGL)
  - Stop:     28% trailing stop from UGL peak SINCE ENTRY

Portfolio:  75% UPRO / 25% UGL
Cash proxy: SGOV / T-bills while sidelined
Cadence:    Weekly — Friday close, Monday open execution
Data:       Tiingo API

State tracking
--------------
This module is stateful. Per-engine state is persisted to engine_state.json:
  - in_position:  bool — currently long the leveraged ETF?
  - peak_price:   float — highest price since entry (ratchets while in_position)
  - entry_price:  float — price at which the position was opened
  - entry_date:   ISO date string

State mutates only on the weekly signal run (run_weekly_signal). The /status
command computes a signal against the current persisted state but does NOT
write back. This matches the research backtest logic exactly:

    if in_position:
        peak_price = max(peak_price, current_price)
        stop_level = peak_price * (1 - trailing_stop_pct)
        if current_price <= stop_level or not regime_on:
            EXIT (in_position = False, clear peak)
        else:
            HOLD
    else:
        if regime_on and reentry_ok:
            ENTER (in_position = True, peak = current_price)
        elif regime_on:
            WAIT
        else:
            CASH
"""

import os
import json
import copy
import math
import tempfile
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# ── ENGINE PARAMETERS ─────────────────────────────────────────────────────────
# UPRO Engine  (SPY regime → UPRO re-entry → UPRO trailing stop from entry peak)
UPRO_SMA_REGIME        = 65
UPRO_SMA_REENTRY       = 10
UPRO_TRAILING_STOP_PCT = 0.22

# UGL Engine   (GLD regime → GLD re-entry → UGL trailing stop from entry peak)
UGL_SMA_REGIME         = 100
UGL_SMA_REENTRY        = 20
UGL_TRAILING_STOP_PCT  = 0.28

# Portfolio weights
UPRO_WEIGHT = 0.75
UGL_WEIGHT  = 0.25

USERS_FILE      = "users.json"
STATE_FILE      = "engine_state.json"
TIINGO_BASE_URL = "https://api.tiingo.com/tiingo/daily"
# ─────────────────────────────────────────────────────────────────────────────


def _atomic_write_json(path, data):
    """Write JSON to disk atomically.

    Writes to a temp file in the same directory, then renames. An interrupted
    process therefore can never leave a half-written JSON file that would
    cause loaders to fall back to default state.
    """
    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=dirpath)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt file — return empty so we don't crash; will be rewritten.
        return {}


def save_users(users):
    _atomic_write_json(USERS_FILE, users)


def default_engine_state():
    """Fresh state for a single engine — not in position, no entry recorded."""
    return {
        "in_position": False,
        "peak_price":  None,
        "entry_price": None,
        "entry_date":  None,
        "last_action": None,
        "last_updated": None,
    }


def default_state():
    """Default state file contents — both engines start out-of-position."""
    return {
        "upro": default_engine_state(),
        "ugl":  default_engine_state(),
    }


def load_state():
    """Load persisted engine state. Returns default state if file missing."""
    if not os.path.exists(STATE_FILE):
        return default_state()
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        # Backfill any missing engine keys (forward-compat)
        for engine in ("upro", "ugl"):
            if engine not in state:
                state[engine] = default_engine_state()
            else:
                # Ensure all expected keys exist
                for k, v in default_engine_state().items():
                    state[engine].setdefault(k, v)
        return state
    except (json.JSONDecodeError, OSError):
        return default_state()


def save_state(state):
    _atomic_write_json(STATE_FILE, state)


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
    if not api_key:
        raise RuntimeError("TIINGO_API_KEY not set")
    # 220 weeks covers the 100-week UGL regime SMA plus warm-up buffer
    start = (datetime.now(timezone.utc) - timedelta(weeks=220)).strftime("%Y-%m-%d")

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
    engine_state,
):
    """Compute signal for one engine using persistent state.

    Matches the research backtest logic exactly:
      - if in_position: peak ratchets up; exit on stop OR regime break
      - if not in_position: enter on regime_on AND reentry_ok

    Returns (signal_dict, new_engine_state).
    The caller decides whether to persist new_engine_state.
    """
    # --- Warmup guard ---
    if len(regime_series) < sma_regime:
        raise ValueError(
            f"Insufficient {regime_ticker} history for {sma_regime}-week SMA: "
            f"got {len(regime_series)} bars"
        )
    if len(reentry_series) < sma_reentry:
        raise ValueError(
            f"Insufficient {reentry_ticker} history for {sma_reentry}-week SMA: "
            f"got {len(reentry_series)} bars"
        )

    # --- Compute regime ---
    reg_sma        = regime_series.rolling(sma_regime).mean()
    latest_reg     = float(regime_series.iloc[-1])
    latest_reg_sma = float(reg_sma.iloc[-1])
    if math.isnan(latest_reg_sma):
        raise ValueError(
            f"{regime_ticker} {sma_regime}w SMA is NaN — data has gaps; aborting."
        )
    regime_on      = latest_reg > latest_reg_sma
    reg_chg        = float((regime_series.iloc[-1] / regime_series.iloc[-2] - 1) * 100) if len(regime_series) > 1 else 0.0

    # --- Compute re-entry ---
    re_sma        = reentry_series.rolling(sma_reentry).mean()
    latest_re     = float(reentry_series.iloc[-1])
    latest_re_sma = float(re_sma.iloc[-1])
    if math.isnan(latest_re_sma):
        raise ValueError(
            f"{reentry_ticker} {sma_reentry}w SMA is NaN — data has gaps; aborting."
        )
    reentry_ok    = latest_re > latest_re_sma
    re_chg        = float((reentry_series.iloc[-1] / reentry_series.iloc[-2] - 1) * 100) if len(reentry_series) > 1 else 0.0

    # --- Current price of the position instrument (used for trailing stop) ---
    latest_stop = float(stop_series.iloc[-1])

    # --- Apply state machine ---
    state = copy.deepcopy(engine_state)
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if state["in_position"]:
        # Ratchet peak — only ever ascends
        prior_peak = state["peak_price"] if state["peak_price"] is not None else latest_stop
        new_peak   = max(prior_peak, latest_stop)
        state["peak_price"] = new_peak

        stop_level = new_peak * (1 - trailing_stop_pct)
        stop_hit   = latest_stop <= stop_level

        if stop_hit:
            action, reason = "SELL", "Trailing stop hit — exit to SGOV/BIL"
            new_state = default_engine_state()
        elif not regime_on:
            action, reason = "SELL", "Regime broke — exit to SGOV/BIL"
            new_state = default_engine_state()
        else:
            action, reason = "HOLD", "In position — conditions intact"
            new_state = state
    else:
        # Out of position
        if not regime_on:
            action, reason = "CASH", "Regime OFF — stay in SGOV/BIL"
            new_state = state
        elif not reentry_ok:
            action, reason = "WAIT", "Regime ON but re-entry not confirmed yet"
            new_state = state
        else:
            action, reason = "BUY", "Regime ON + re-entry confirmed — enter position"
            new_state = {
                "in_position": True,
                "peak_price":  latest_stop,
                "entry_price": latest_stop,
                "entry_date":  today_iso,
                "last_action": None,
                "last_updated": None,
            }
        # When out of position, peak/stop are meaningless for display
        new_peak = None
        stop_level = None
        stop_hit = False

    new_state["last_action"]  = action
    new_state["last_updated"] = today_iso

    # --- Build display fields ---
    in_pos_now = state["in_position"]   # state at evaluation time
    if in_pos_now:
        stop_distance = round((latest_stop - stop_level) / latest_stop * 100, 1) if latest_stop > 0 else 0.0
    else:
        stop_distance = None

    sig = {
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
        # Position-aware fields (None when not in position)
        "in_position":         in_pos_now,
        "peak_price":          round(new_peak, 2) if new_peak is not None else None,
        "entry_price":         round(engine_state["entry_price"], 2) if engine_state.get("entry_price") else None,
        "entry_date":          engine_state.get("entry_date"),
        "stop_level":          round(stop_level, 2) if stop_level is not None else None,
        "stop_distance":       stop_distance,
        "trailing_stop_pct":   trailing_stop_pct,
        "same_regime_reentry": (regime_ticker == reentry_ticker),
    }

    return sig, new_state


def compute_signal(spy, upro, gld, ugl, state=None):
    """Compute signals for both engines.

    state — optional dict from load_state(). If None, a fresh state is used.

    Returns (signal_dict, new_state). Caller persists new_state on weekly run.
    """
    if state is None:
        state = default_state()

    upro_sig, upro_state = _compute_engine_signal(
        spy, upro, upro,
        UPRO_SMA_REGIME, UPRO_SMA_REENTRY, UPRO_TRAILING_STOP_PCT,
        "SPY", "UPRO", "UPRO",
        state["upro"],
    )
    ugl_sig, ugl_state = _compute_engine_signal(
        gld, gld, ugl,
        UGL_SMA_REGIME, UGL_SMA_REENTRY, UGL_TRAILING_STOP_PCT,
        "GLD", "GLD", "UGL",
        state["ugl"],
    )

    sig = {
        "upro": upro_sig,
        "ugl":  ugl_sig,
        "date": datetime.now(timezone.utc).strftime("%a %b %d, %Y"),
    }
    new_state = {"upro": upro_state, "ugl": ugl_state}
    return sig, new_state


def compute_signal_readonly(spy, upro, gld, ugl):
    """Read state from disk, compute signal, do NOT mutate persisted state.

    Used by /status command. Returns the signal dict only.
    """
    state = load_state()
    sig, _ = compute_signal(spy, upro, gld, ugl, state)
    return sig


def _stop_bar(distance, max_distance):
    """Ten-cell visual bar showing distance to trailing stop."""
    if distance is None or max_distance <= 0:
        return "⬜" * 10
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

    stop_pct = f"{sig['trailing_stop_pct']:.0%}"

    # Risk block depends on whether we're in position
    if sig["in_position"]:
        stop_bar = _stop_bar(sig["stop_distance"], sig["trailing_stop_pct"] * 100)
        risk_block = (
            f"*Risk ({sig['stop_ticker']})*\n"
            f"  Entry:     `${sig['entry_price']}` ({sig['entry_date']})\n"
            f"  Peak:      `${sig['peak_price']}` (since entry)\n"
            f"  Current:   `${sig['stop_price']}`\n"
            f"  Stop:      `${sig['stop_level']}` ({stop_pct} trail)\n"
            f"  Distance:  `{sig['stop_distance']}%` to stop\n"
            f"  {stop_bar}\n"
        )
    else:
        risk_block = (
            f"*Risk ({sig['stop_ticker']})*\n"
            f"  Not in position — trailing stop activates on BUY signal\n"
            f"  Configured trail: {stop_pct} from entry peak\n"
        )

    if sig["same_regime_reentry"]:
        # UGL engine: GLD fills both regime and re-entry roles → one compact block
        block = (
            f"{emoji} *{label}: {action_label}*\n"
            f"_{sig['reason']}_\n\n"
            f"*{sig['regime_ticker']}*\n"
            f"  Price:   `${sig['regime_price']}`  {arrow(sig['regime_chg'])} {chg_str(sig['regime_chg'])}\n"
            f"  SMA{sig['sma_regime']}:  `${sig['regime_sma']}`  {regime_icon} Regime {'ON' if sig['regime_on'] else 'OFF'}\n"
            f"  SMA{sig['sma_reentry']}:   `${sig['reentry_sma']}`  {reentry_icon} Re-entry {'OK' if sig['reentry_ok'] else 'NOT OK'}\n\n"
            f"{risk_block}"
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
            f"{risk_block}"
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
    """Called by GitHub Actions every Monday — computes signal, mutates state,
    sends to all registered users."""
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

    state = load_state()

    def _fmt(v):
        return f"${v}" if v is not None else "—"

    print(f"Loaded state: UPRO in_position={state['upro']['in_position']} "
          f"peak={_fmt(state['upro']['peak_price'])} | "
          f"UGL in_position={state['ugl']['in_position']} "
          f"peak={_fmt(state['ugl']['peak_price'])}")

    sig, new_state = compute_signal(spy, upro, gld, ugl, state)
    u, g = sig["upro"], sig["ugl"]

    print(f"  UPRO ({u['action']}): regime_on={u['regime_on']} reentry_ok={u['reentry_ok']} "
          f"in_pos={u['in_position']} peak={_fmt(u['peak_price'])} stop={_fmt(u['stop_level'])}")
    print(f"  UGL  ({g['action']}): regime_on={g['regime_on']} reentry_ok={g['reentry_ok']} "
          f"in_pos={g['in_position']} peak={_fmt(g['peak_price'])} stop={_fmt(g['stop_level'])}")

    # Persist new state BEFORE sending messages so a partial send failure
    # doesn't lose the transition.
    save_state(new_state)
    print(f"State saved: UPRO in_position={new_state['upro']['in_position']} | "
          f"UGL in_position={new_state['ugl']['in_position']}")

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
