#!/usr/bin/env python3
"""
TripleEdge UGL - Winner Summary
Clean printout of final rules, all metrics, and current market status.

Usage:
    python ugl_winner_summary.py
"""

import warnings
warnings.filterwarnings("ignore")

import json
import os
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

from ugl_optimizer import (
    download_data, prepare_data, backtest, buy_and_hold_metrics,
    RISK_FREE_RATE, DATA_DIR, to_weekly,
)


def load_winner_params():
    params_path = os.path.join(DATA_DIR, "ugl_winner_params.json")
    if os.path.exists(params_path):
        with open(params_path) as f:
            return json.load(f)
    else:
        print("ERROR: ugl_winner_params.json not found. Run ugl_optimizer.py first.")
        sys.exit(1)


def current_status(prepared_data, winner_params):
    """Check current market conditions and recommend action."""
    gld_weekly = prepared_data["gld_weekly"]
    ugl_weekly = prepared_data["ugl_weekly"]

    # Current prices
    gld_price = gld_weekly.iloc[-1]
    ugl_price = ugl_weekly.iloc[-1]
    date = gld_weekly.index[-1]

    # Regime filter (on GLD)
    regime_period = winner_params["regime_period"]
    regime_type = winner_params.get("regime_type", "weekly_sma")

    if regime_type == "weekly_sma":
        gld_sma = gld_weekly.rolling(regime_period).mean().iloc[-1]
        regime_on = gld_price > gld_sma
        regime_label = f"GLD {regime_period}-week SMA"
    elif regime_type == "weekly_ema":
        gld_sma = gld_weekly.ewm(span=regime_period, adjust=False).mean().iloc[-1]
        regime_on = gld_price > gld_sma
        regime_label = f"GLD {regime_period}-week EMA"
    elif regime_type == "golden_cross":
        gld_sma50 = gld_weekly.rolling(50).mean().iloc[-1]
        gld_sma200 = gld_weekly.rolling(200).mean().iloc[-1]
        regime_on = gld_sma50 > gld_sma200
        gld_sma = gld_sma50  # For display
        regime_label = "GLD 50w SMA > 200w SMA"
    else:
        gld_sma = gld_weekly.rolling(regime_period).mean().iloc[-1]
        regime_on = gld_price > gld_sma
        regime_label = f"GLD {regime_period}-week SMA"

    # Re-entry signal
    reentry_period = winner_params["reentry_period"]
    reentry_inst = winner_params["reentry_instrument"]
    reentry_type = winner_params.get("reentry_type", "sma")

    if reentry_inst == "UGL":
        reentry_series = ugl_weekly
        reentry_price = ugl_price
    else:
        reentry_series = gld_weekly
        reentry_price = gld_price

    if reentry_type == "ema":
        reentry_sma = reentry_series.ewm(span=reentry_period, adjust=False).mean().iloc[-1]
    else:
        reentry_sma = reentry_series.rolling(reentry_period).mean().iloc[-1]
    reentry_ok = reentry_price > reentry_sma

    # Trailing stop
    stop_pct = winner_params["trailing_stop_pct"]
    peak_52w = ugl_weekly.iloc[-52:].max() if len(ugl_weekly) >= 52 else ugl_weekly.max()
    stop_level = peak_52w * (1 - stop_pct)
    stop_hit = ugl_price <= stop_level
    stop_distance = (ugl_price - stop_level) / ugl_price * 100

    # Determine action
    if stop_hit:
        action = "SELL"
    elif not regime_on:
        action = "CASH"
    elif regime_on and not reentry_ok:
        action = "WAIT"
    elif regime_on and reentry_ok:
        action = "BUY / HOLD"
    else:
        action = "UNKNOWN"

    return {
        "date": date,
        "gld_price": gld_price,
        "ugl_price": ugl_price,
        "regime_label": regime_label,
        "gld_sma": gld_sma,
        "regime_on": regime_on,
        "reentry_inst": reentry_inst,
        "reentry_period": reentry_period,
        "reentry_type": reentry_type,
        "reentry_price": reentry_price,
        "reentry_sma": reentry_sma,
        "reentry_ok": reentry_ok,
        "peak_52w": peak_52w,
        "stop_level": stop_level,
        "stop_hit": stop_hit,
        "stop_distance": stop_distance,
        "action": action,
    }


def print_summary(winner_params, strat_result, status):
    """Print the complete winner summary."""
    print("\n")
    print("=" * 70)
    print("  TRIPLEEDGE UGL - FINAL STRATEGY SUMMARY")
    print("=" * 70)

    # The Strategy
    regime_type = winner_params.get("regime_type", "weekly_sma")
    reentry_type = winner_params.get("reentry_type", "sma")

    if regime_type == "weekly_ema":
        regime_desc = f"GLD weekly close > GLD {winner_params['regime_period']}-WEEK EMA"
    elif regime_type == "golden_cross":
        regime_desc = "GLD 50-week SMA > GLD 200-week SMA"
    else:
        regime_desc = f"GLD weekly close > GLD {winner_params['regime_period']}-WEEK SMA"

    reentry_inst = winner_params["reentry_instrument"]
    reentry_per = winner_params["reentry_period"]

    if reentry_type == "ema":
        reentry_desc = f"{reentry_inst} weekly close > {reentry_inst} {reentry_per}-WEEK EMA"
    else:
        reentry_desc = f"{reentry_inst} weekly close > {reentry_inst} {reentry_per}-WEEK SMA"

    stop_pct = winner_params["trailing_stop_pct"]

    extra_filter = winner_params.get("extra_filter")
    extra_desc = ""
    if extra_filter == "dxy_below_sma":
        period = winner_params.get("extra_filter_period", 40)
        extra_desc = f"\n    4. DXY filter:   DXY < DXY {period}-WEEK SMA (dollar weakening)"
    elif extra_filter == "tip_above_sma":
        period = winner_params.get("extra_filter_period", 20)
        extra_desc = f"\n    4. TIP filter:   TIP > TIP {period}-WEEK SMA (falling real rates)"
    elif extra_filter == "gdx_above_sma":
        period = winner_params.get("extra_filter_period", 10)
        extra_desc = f"\n    4. GDX filter:   GDX > GDX {period}-WEEK SMA (miners confirming)"
    elif extra_filter == "gld_low_vol":
        extra_desc = "\n    4. Vol filter:   GLD 20-day vol < GLD 252-day vol (trending, not choppy)"
    elif extra_filter == "ugl_above_sma50":
        extra_desc = "\n    4. Extra filter: UGL > UGL 50-WEEK SMA"

    print(f"""
  ENTRY RULES (all must be true):
    1. Regime filter:  {regime_desc}
    2. Re-entry signal: {reentry_desc}
    3. No trailing stop hit{extra_desc}

  EXIT RULES (any triggers full exit):
    1. Trailing stop: UGL drops {stop_pct:.0%} from highest close since entry
    2. Regime break:  GLD weekly close <= regime MA

  WHILE OUT: 100% cash earning ~5.2% annualized (SGOV/T-bills)
  CADENCE:   Weekly - check Friday close, act Monday
  FRICTION:  0.05% per trade (one-way)
""")

    # Performance Table
    if strat_result:
        print("  FULL-PERIOD PERFORMANCE:")
        print("  " + "-" * 50)
        metrics = [
            ("Total Return", f"{strat_result['total_return']:.1f}x"),
            ("CAGR", f"{strat_result['cagr']:.1%}"),
            ("Max Drawdown", f"{strat_result['max_dd']:.1%}"),
            ("Sharpe Ratio", f"{strat_result['sharpe']:.2f}"),
            ("Sortino Ratio", f"{strat_result['sortino']:.2f}"),
            ("Calmar Ratio", f"{strat_result['calmar']:.2f}"),
            ("Ulcer Index", f"{strat_result['ulcer_index']:.3f}"),
            ("UPI", f"{strat_result['upi']:.2f}"),
            ("Recovery (weeks)", f"{strat_result['recovery_weeks']:.0f}" if not np.isinf(strat_result['recovery_weeks']) else "Never"),
            ("Worst 1-yr Return", f"{strat_result['worst_1yr']:.1%}"),
            ("Worst 3-yr Return", f"{strat_result['worst_3yr']:.1%}"),
            ("% 3yr Negative", f"{strat_result['pct_3yr_negative']:.1%}"),
            ("Number of Trades", f"{strat_result['num_trades']}"),
            ("% Time in UGL", f"{strat_result['pct_time_ugl']:.0%}"),
            ("% Time in Cash", f"{strat_result['pct_time_cash']:.0%}"),
            ("Train CAGR", f"{strat_result['train_cagr']:.1%}"),
            ("Test CAGR", f"{strat_result['test_cagr']:.1%}"),
            ("Train Sharpe", f"{strat_result['train_sharpe']:.2f}"),
            ("Test Sharpe", f"{strat_result['test_sharpe']:.2f}"),
            ("Train/Test Sharpe Ratio", f"{strat_result['train_test_sharpe_ratio']:.2f}"),
        ]
        for name, val in metrics:
            print(f"    {name:<25} {val:>15}")

    # Current Status
    print(f"\n  CURRENT STATUS (as of {status['date'].date()}):")
    print("  " + "-" * 50)
    print(f"    GLD Price:            ${status['gld_price']:.2f}")
    print(f"    UGL Price:            ${status['ugl_price']:.2f}")
    print(f"    Regime ({status['regime_label']}):")
    print(f"      MA Value:           ${status['gld_sma']:.2f}")
    print(f"      Regime ON:          {'YES' if status['regime_on'] else 'NO'}")
    reentry_type_label = "EMA" if status['reentry_type'] == "ema" else "SMA"
    print(f"    Re-entry ({status['reentry_inst']} {status['reentry_period']}-wk {reentry_type_label}):")
    print(f"      MA Value:           ${status['reentry_sma']:.2f}")
    print(f"      Re-entry OK:        {'YES' if status['reentry_ok'] else 'NO'}")
    print(f"    Trailing Stop:")
    print(f"      52-week Peak:       ${status['peak_52w']:.2f}")
    print(f"      Stop Level:         ${status['stop_level']:.2f}")
    print(f"      Distance to Stop:   {status['stop_distance']:.1f}%")
    print(f"      Stop Hit:           {'YES' if status['stop_hit'] else 'NO'}")
    print(f"\n    >>> ACTION: {status['action']} <<<")

    print("\n" + "=" * 70)


def main():
    winner_params = load_winner_params()

    print(f"\n  Loading data and running full backtest...")
    data = download_data()
    prepared = prepare_data(data)

    # Run full backtest
    strat_result = backtest(
        gld_weekly=prepared["gld_weekly"],
        ugl_weekly=prepared["ugl_weekly"],
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        reentry_type=winner_params.get("reentry_type", "sma"),
    )

    # Current status
    status = current_status(prepared, winner_params)

    # Print everything
    print_summary(winner_params, strat_result, status)


if __name__ == "__main__":
    main()
