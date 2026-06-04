"""
Signal computation wrapper.

This module is INTENTIONALLY a thin layer over the validated engine in
engine.py — it does NOT reimplement the strategy. It exists to:

  1. Translate weekly price bars from Alpaca's data API into the
     pandas Series shape engine._compute_engine_signal expects.
  2. Plug in the bot's persistent state (from bot/state.py) rather than
     the live signal's state file.
  3. Decide BUY / HOLD / SELL / WAIT / CASH per engine using the SAME
     state-machine logic the research backtest used.

If you find yourself adding strategy math here — stop. It belongs in engine.py.
"""

import os
import sys

# Pull in the validated engine from the repo root
HERE      = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from engine import (  # noqa: E402
    UPRO_SMA_REGIME, UPRO_SMA_REENTRY, UPRO_TRAILING_STOP_PCT,
    UGL_SMA_REGIME,  UGL_SMA_REENTRY,  UGL_TRAILING_STOP_PCT,
    _compute_engine_signal,
)


def compute_engine_signals(spy_weekly, upro_weekly, gld_weekly, ugl_weekly,
                            bot_state):
    """Apply the engine.py state machine to bot_state.

    bot_state is the dict from bot.state.load_state(). The engine returns
    (signal_dict, new_engine_state) for each engine; we collect both.

    Returns (signal_dict_per_engine, new_bot_state).
    """
    upro_sig, upro_new = _compute_engine_signal(
        spy_weekly, upro_weekly, upro_weekly,
        UPRO_SMA_REGIME, UPRO_SMA_REENTRY, UPRO_TRAILING_STOP_PCT,
        "SPY", "UPRO", "UPRO",
        _engine_state_to_engine(bot_state["upro"]),
    )
    ugl_sig, ugl_new = _compute_engine_signal(
        gld_weekly, gld_weekly, ugl_weekly,
        UGL_SMA_REGIME, UGL_SMA_REENTRY, UGL_TRAILING_STOP_PCT,
        "GLD", "GLD", "UGL",
        _engine_state_to_engine(bot_state["ugl"]),
    )

    new_bot_state = {
        "upro": _engine_to_bot_state(upro_new),
        "ugl":  _engine_to_bot_state(ugl_new),
    }
    return {"upro": upro_sig, "ugl": ugl_sig}, new_bot_state


def _engine_state_to_engine(bot_engine_state: dict) -> dict:
    """Convert bot-side state shape to the engine.py state shape."""
    return {
        "in_position":  bool(bot_engine_state["in_position"]),
        "peak_price":   bot_engine_state["peak_price"],
        "entry_price":  bot_engine_state["entry_price"],
        "entry_date":   bot_engine_state["entry_date"],
        "last_action":  None,
        "last_updated": None,
    }


def _engine_to_bot_state(engine_new_state: dict) -> dict:
    """Convert engine.py state shape back to bot-side state shape."""
    return {
        "in_position":  bool(engine_new_state.get("in_position", False)),
        "entry_date":   engine_new_state.get("entry_date"),
        "entry_price":  engine_new_state.get("entry_price"),
        "peak_price":   engine_new_state.get("peak_price"),
    }
