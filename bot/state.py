"""
Per-engine position state for the Alpaca bot.

State is persisted to bot/state/positions.json. The trailing stop tracks the
highest close since entry — so the peak MUST persist between weekly runs.
This file is gitignored.

State shape (mirrors engine.py for consistency):
{
  "upro": {
    "in_position": true,
    "entry_date":  "YYYY-MM-DD",
    "entry_price": 73.42,
    "peak_price":  89.41
  },
  "ugl": { ... }
}
"""

import json
import os
import tempfile
from datetime import datetime, timezone


HERE         = os.path.dirname(os.path.abspath(__file__))
STATE_DIR    = os.path.join(HERE, "state")
STATE_FILE   = os.path.join(STATE_DIR, "positions.json")


def default_engine_state() -> dict:
    return {
        "in_position":  False,
        "entry_date":   None,
        "entry_price":  None,
        "peak_price":   None,
    }


def default_state() -> dict:
    return {"upro": default_engine_state(), "ugl": default_engine_state()}


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return default_state()
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return default_state()
    # Forward-compatible backfill of any missing keys
    out = default_state()
    for engine in ("upro", "ugl"):
        if isinstance(state.get(engine), dict):
            for k in out[engine]:
                if k in state[engine]:
                    out[engine][k] = state[engine][k]
    return out


def save_state(state: dict) -> None:
    """Atomic JSON write — write to temp then rename, so a crash mid-write
    can never corrupt the state file."""
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="positions.", suffix=".json", dir=STATE_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def open_position(state: dict, engine_key: str, entry_price: float) -> dict:
    """Transition engine state from cash → in-position. Sets peak = entry."""
    state[engine_key] = {
        "in_position":  True,
        "entry_date":   datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "entry_price":  float(entry_price),
        "peak_price":   float(entry_price),
    }
    return state


def close_position(state: dict, engine_key: str) -> dict:
    """Transition engine state from in-position → cash. Clears entry+peak."""
    state[engine_key] = default_engine_state()
    return state


def ratchet_peak(state: dict, engine_key: str, current_price: float) -> dict:
    """If in position and current_price > stored peak, ratchet the peak up.
    Peak never goes down."""
    es = state.get(engine_key, default_engine_state())
    if es["in_position"] and es["peak_price"] is not None:
        if current_price > es["peak_price"]:
            es["peak_price"] = float(current_price)
            state[engine_key] = es
    return state
