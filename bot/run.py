"""
TripleEdge Alpaca bot — main entry point.

Usage:
    python -m bot.run            # uses BOT_MODE from .env (default: alert_only)
    BOT_MODE=dry_run python -m bot.run
    BOT_MODE=execute python -m bot.run

Safety:
  - PAPER endpoint by default; live requires LIVE_TRADING=true AND
    LIVE_TRADING_CONFIRMED=true
  - ALERT_ONLY by default; no orders are submitted unless mode=execute
  - All keys loaded from env / .env (NEVER hardcoded)

Each run:
  1. Loads persisted bot state (trailing-stop peaks)
  2. Fetches weekly bars (Alpaca → Tiingo fallback)
  3. Computes per-engine signals via the validated engine.py logic
  4. Reconciles current Alpaca positions to the strategy target
  5. Logs to bot/logs/{run_log.csv, paper_track_record.csv}
  6. Optionally sends a Telegram summary
"""

import csv
import os
import sys
from datetime import datetime, timezone

# Allow running as `python bot/run.py` (script mode) or `python -m bot.run`
if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from bot.config  import load_config, print_startup_banner, BotConfig
    from bot.config  import MODE_ALERT_ONLY, MODE_DRY_RUN, MODE_EXECUTE
    from bot.config  import UPRO_SYMBOL, UGL_SYMBOL, W_UPRO, W_UGL
    from bot.state   import load_state, save_state
    from bot.signals import compute_engine_signals
    from bot.broker  import make_broker
    from bot.notify  import notify
else:
    from .config  import load_config, print_startup_banner, BotConfig
    from .config  import MODE_ALERT_ONLY, MODE_DRY_RUN, MODE_EXECUTE
    from .config  import UPRO_SYMBOL, UGL_SYMBOL, W_UPRO, W_UGL
    from .state   import load_state, save_state
    from .signals import compute_engine_signals
    from .broker  import make_broker
    from .notify  import notify


HERE        = os.path.dirname(os.path.abspath(__file__))
LOG_DIR     = os.path.join(HERE, "logs")
RUN_LOG     = os.path.join(LOG_DIR, "run_log.csv")
TRACK_LOG   = os.path.join(LOG_DIR, "paper_track_record.csv")

RUN_LOG_COLS = [
    "timestamp", "mode", "endpoint",
    "upro_action", "upro_regime_on", "upro_reentry_ok",
    "upro_in_position", "upro_peak", "upro_stop_level",
    "ugl_action",  "ugl_regime_on",  "ugl_reentry_ok",
    "ugl_in_position", "ugl_peak", "ugl_stop_level",
    "equity", "orders_intended", "orders_placed",
]

TRACK_LOG_COLS = [
    "timestamp", "equity", "upro_qty", "upro_value",
    "ugl_qty", "ugl_value", "cash_value",
]


# ────────────────────────────────────────────────────────────────────────────
# Reconciliation: target vs actual positions
# ────────────────────────────────────────────────────────────────────────────

def plan_orders(signals, equity, current_positions, broker, cfg):
    """Compute the orders needed to move current state → target state.

    Target state per engine:
      - If sig['in_position'] is True (engine is invested), target qty =
        floor((equity * weight) / latest_price). If 'action' is SELL, target=0.
      - If sig['action'] in {'BUY'}, target = floor((equity * weight) / latest_price).
      - Otherwise (WAIT/CASH/HOLD-but-out), target = 0.

    Returns a list of intended order dicts.
    """
    orders = []
    for engine_key, symbol, weight in [
        ("upro", UPRO_SYMBOL, W_UPRO),
        ("ugl",  UGL_SYMBOL,  W_UGL),
    ]:
        sig = signals[engine_key]
        action = sig["action"]
        current_qty = current_positions.get(symbol, {}).get("qty", 0.0)

        # Determine target qty
        if action == "BUY":
            try:
                price = broker.latest_price(symbol)
            except Exception as e:
                print(f"  WARN: cannot price {symbol} ({e}); skipping order plan")
                continue
            allocated_dollars = equity * weight
            target_qty = int(allocated_dollars // price)
        elif action in ("HOLD",):
            # Already in position — keep it. No reshape unless rebalance logic
            # is added later. For now we don't rebalance midway.
            target_qty = current_qty
        elif action in ("SELL",):
            target_qty = 0
        elif action in ("WAIT", "CASH"):
            target_qty = 0
        else:
            target_qty = current_qty  # unknown action — be conservative

        delta = target_qty - current_qty
        if abs(delta) < 1e-9:
            continue

        side = "buy" if delta > 0 else "sell"
        orders.append({
            "engine":      engine_key,
            "symbol":      symbol,
            "side":        side,
            "qty":         abs(delta),
            "current_qty": current_qty,
            "target_qty":  target_qty,
            "reason":      f"{action}: {sig['reason']}",
        })
    return orders


# ────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────

def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def append_run_log(row: dict):
    _ensure_log_dir()
    write_header = not os.path.exists(RUN_LOG)
    with open(RUN_LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUN_LOG_COLS)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in RUN_LOG_COLS})


def append_track_record(equity, positions):
    _ensure_log_dir()
    write_header = not os.path.exists(TRACK_LOG)
    upro = positions.get(UPRO_SYMBOL, {})
    ugl  = positions.get(UGL_SYMBOL,  {})
    cash = equity - upro.get("market_value", 0) - ugl.get("market_value", 0)
    row = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "equity":     round(equity, 2),
        "upro_qty":   upro.get("qty", 0),
        "upro_value": round(upro.get("market_value", 0), 2),
        "ugl_qty":    ugl.get("qty", 0),
        "ugl_value":  round(ugl.get("market_value", 0), 2),
        "cash_value": round(cash, 2),
    }
    with open(TRACK_LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRACK_LOG_COLS)
        if write_header:
            w.writeheader()
        w.writerow(row)


# ────────────────────────────────────────────────────────────────────────────
# Summary formatting
# ────────────────────────────────────────────────────────────────────────────

def _engine_line(label: str, sig: dict) -> str:
    """One-liner for a single engine."""
    parts = [f"{sig['action']}"]
    parts.append(f"regime {'ON' if sig['regime_on'] else 'OFF'}")
    parts.append(f"re-entry {'ON' if sig['reentry_ok'] else 'OFF'}")
    if sig["in_position"] and sig["stop_level"] is not None:
        parts.append(f"stop ${sig['stop_level']:.2f}")
    return f"{label}: " + ", ".join(parts)


def format_summary(signals, equity, positions, orders, cfg) -> str:
    L = [
        f"📊 *TripleEdge Bot* — {cfg.mode.upper()} on "
        f"{'LIVE' if cfg.live_trading else 'PAPER'}",
        f"_Equity: ${equity:,.2f}_",
        "",
        _engine_line("UPRO (75%)", signals["upro"]),
        _engine_line("UGL  (25%)", signals["ugl"]),
        "",
    ]
    if not orders:
        L.append("Orders: _none needed — at target_")
    else:
        L.append("Orders intended:")
        for o in orders:
            L.append(f"  • {o['side'].upper()} {o['qty']} {o['symbol']}  ({o['reason']})")
    return "\n".join(L)


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────

def main():
    cfg = load_config()
    print_startup_banner(cfg)

    # 1. Load state (trailing-stop peaks)
    state = load_state()
    print(f"[1/5] State loaded: UPRO in_position={state['upro']['in_position']}, "
          f"peak={state['upro']['peak_price']} | "
          f"UGL in_position={state['ugl']['in_position']}, "
          f"peak={state['ugl']['peak_price']}")

    # 2. Build broker + fetch data
    broker = make_broker(cfg)
    print("[2/5] Fetching weekly bars (Alpaca → Tiingo fallback)...")
    bars = broker.fetch_weekly_bars(["SPY", UPRO_SYMBOL, "GLD", UGL_SYMBOL])
    spy, upro, gld, ugl = bars["SPY"], bars[UPRO_SYMBOL], bars["GLD"], bars[UGL_SYMBOL]
    print(f"      SPY={len(spy)} bars | UPRO={len(upro)} | GLD={len(gld)} | UGL={len(ugl)}")

    # 3. Compute signals + new state
    print("[3/5] Computing engine signals...")
    signals, new_state = compute_engine_signals(spy, upro, gld, ugl, state)
    u, g = signals["upro"], signals["ugl"]
    print(f"      UPRO: {u['action']} (regime={u['regime_on']}, re-entry={u['reentry_ok']}, "
          f"in_pos={u['in_position']}, stop={u['stop_level']})")
    print(f"      UGL:  {g['action']} (regime={g['regime_on']}, re-entry={g['reentry_ok']}, "
          f"in_pos={g['in_position']}, stop={g['stop_level']})")

    # 4. Reconcile: account + positions + planned orders
    print("[4/5] Reading Alpaca account + positions...")
    try:
        equity = broker.get_equity()
        positions = broker.get_positions()
        print(f"      Equity: ${equity:,.2f}  |  Positions: {list(positions.keys()) or 'none'}")
    except Exception as e:
        print(f"      ERROR reading account: {e}")
        sys.exit(4)

    orders = plan_orders(signals, equity, positions, broker, cfg)

    # 5. Act on orders depending on mode
    orders_placed = []
    if cfg.mode == MODE_ALERT_ONLY:
        print("[5/5] Mode = alert_only — placing NO orders.")
    elif cfg.mode == MODE_DRY_RUN:
        print("[5/5] Mode = dry_run — simulating orders:")
        for o in orders:
            sim = broker.submit_market_order(o["symbol"], o["qty"], o["side"], dry_run=True)
            print(f"        DRY: {sim}")
            orders_placed.append(sim)
    elif cfg.mode == MODE_EXECUTE:
        print("[5/5] Mode = execute — SUBMITTING orders to Alpaca:")
        for o in orders:
            try:
                res = broker.submit_market_order(o["symbol"], o["qty"], o["side"])
                print(f"        SUBMITTED: {res}")
                orders_placed.append(res)
            except Exception as e:
                print(f"        FAILED {o['symbol']} {o['side']} {o['qty']}: {e}")

    # ── Persist state only when we actually act (or always log paper) ─────
    # Save new_state even in alert_only — the peak should ratchet up so a
    # later switch to execute won't reset to a stale peak.
    save_state(new_state)

    # ── Logs ──────────────────────────────────────────────────────────────
    append_run_log({
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "mode":              cfg.mode,
        "endpoint":          cfg.endpoint,
        "upro_action":       u["action"],
        "upro_regime_on":    u["regime_on"],
        "upro_reentry_ok":   u["reentry_ok"],
        "upro_in_position":  u["in_position"],
        "upro_peak":         u["peak_price"],
        "upro_stop_level":   u["stop_level"],
        "ugl_action":        g["action"],
        "ugl_regime_on":     g["regime_on"],
        "ugl_reentry_ok":    g["reentry_ok"],
        "ugl_in_position":   g["in_position"],
        "ugl_peak":          g["peak_price"],
        "ugl_stop_level":    g["stop_level"],
        "equity":            equity,
        "orders_intended":   str(orders),
        "orders_placed":     str(orders_placed),
    })
    append_track_record(equity, positions)

    # ── Notify ────────────────────────────────────────────────────────────
    summary = format_summary(signals, equity, positions, orders, cfg)
    print()
    print(summary)
    notify(cfg, summary)
    print("\nDone.")


if __name__ == "__main__":
    main()
