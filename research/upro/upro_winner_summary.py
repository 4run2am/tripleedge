#!/usr/bin/env python3
"""
TripleEdge UPRO - Winner Summary
Clean printout of final rules, all metrics, and current market status.

Usage:
    python upro_winner_summary.py
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

from upro_optimizer import (
    download_data, prepare_data, backtest, buy_and_hold_metrics,
    RISK_FREE_RATE, DATA_DIR, to_weekly
)

def load_winner_params():
    params_path = os.path.join(DATA_DIR, "upro_winner_params.json")
    if os.path.exists(params_path):
        with open(params_path) as f:
            return json.load(f)
    else:
        print("ERROR: upro_winner_params.json not found. Run upro_optimizer.py first.")
        sys.exit(1)


def current_status(prepared_data, winner_params):
    """Check current market conditions and recommend action."""
    spy_weekly = prepared_data["spy_weekly"]
    upro_weekly = prepared_data["upro_weekly"]

    # Current prices
    spy_price = spy_weekly.iloc[-1]
    upro_price = upro_weekly.iloc[-1]
    date = spy_weekly.index[-1]

    # Regime filter
    regime_period = winner_params["regime_period"]
    regime_type = winner_params.get("regime_type", "weekly_sma")

    if regime_type == "weekly_sma":
        spy_sma = spy_weekly.rolling(regime_period).mean().iloc[-1]
        regime_on = spy_price > spy_sma
        regime_label = f"SPY {regime_period}-week SMA"
    elif regime_type == "daily_200_sma":
        spy_daily_sma200 = prepared_data["spy_daily"].rolling(200).mean()
        spy_sma = spy_daily_sma200.iloc[-1]
        regime_on = spy_price > spy_sma
        regime_label = "SPY 200-day SMA"
    else:
        spy_sma = spy_weekly.rolling(regime_period).mean().iloc[-1]
        regime_on = spy_price > spy_sma
        regime_label = f"SPY {regime_period}-week SMA"

    # Re-entry signal
    reentry_period = winner_params["reentry_period"]
    reentry_inst = winner_params["reentry_instrument"]
    if reentry_inst == "UPRO":
        reentry_series = upro_weekly
        reentry_price = upro_price
    else:
        reentry_series = spy_weekly
        reentry_price = spy_price

    reentry_sma = reentry_series.rolling(reentry_period).mean().iloc[-1]
    reentry_ok = reentry_price > reentry_sma

    # Trailing stop
    stop_pct = winner_params["trailing_stop_pct"]
    # Use 52-week high as proxy for peak
    peak_52w = upro_weekly.iloc[-52:].max() if len(upro_weekly) >= 52 else upro_weekly.max()
    stop_level = peak_52w * (1 - stop_pct)
    stop_hit = upro_price <= stop_level
    stop_distance = (upro_price - stop_level) / upro_price * 100

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
        "spy_price": spy_price,
        "upro_price": upro_price,
        "regime_label": regime_label,
        "spy_sma": spy_sma,
        "regime_on": regime_on,
        "reentry_inst": reentry_inst,
        "reentry_period": reentry_period,
        "reentry_price": reentry_price,
        "reentry_sma": reentry_sma,
        "reentry_ok": reentry_ok,
        "peak_52w": peak_52w,
        "stop_level": stop_level,
        "stop_hit": stop_hit,
        "stop_distance": stop_distance,
        "action": action,
    }


def print_summary(winner_params, strat_result, benchmarks, status):
    """Print the complete winner summary."""
    print("\n")
    print("=" * 70)
    print("  TRIPLEEDGE UPRO - FINAL STRATEGY SUMMARY")
    print("=" * 70)

    # The Strategy
    regime_type = winner_params.get("regime_type", "weekly_sma")
    if regime_type == "daily_200_sma":
        regime_desc = "SPY weekly close > SPY 200-DAY SMA"
    else:
        regime_desc = f"SPY weekly close > SPY {winner_params['regime_period']}-WEEK SMA"

    reentry_inst = winner_params["reentry_instrument"]
    reentry_per = winner_params["reentry_period"]
    stop_pct = winner_params["trailing_stop_pct"]

    print(f"""
  ENTRY RULES (all must be true):
    1. Regime filter:  {regime_desc}
    2. Re-entry signal: {reentry_inst} weekly close > {reentry_inst} {reentry_per}-WEEK SMA
    3. No trailing stop hit

  EXIT RULES (any triggers full exit):
    1. Trailing stop: UPRO drops {stop_pct:.0%} from highest close since entry
    2. Regime break:  SPY weekly close <= regime SMA

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
            ("% Time in UPRO", f"{strat_result['pct_time_upro']:.0%}"),
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
    print(f"    SPY Price:            ${status['spy_price']:.2f}")
    print(f"    UPRO Price:           ${status['upro_price']:.2f}")
    print(f"    Regime ({status['regime_label']}):")
    print(f"      SMA Value:          ${status['spy_sma']:.2f}")
    print(f"      Regime ON:          {'YES' if status['regime_on'] else 'NO'}")
    print(f"    Re-entry ({status['reentry_inst']} {status['reentry_period']}-wk SMA):")
    print(f"      SMA Value:          ${status['reentry_sma']:.2f}")
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
        spy_weekly=prepared["spy_weekly"],
        upro_weekly=prepared["upro_weekly"],
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        spy_daily_sma200_weekly=prepared["spy_daily_sma200_weekly"],
    )

    # Benchmarks
    spy_bh = buy_and_hold_metrics(prepared["spy_weekly"], "B&H SPY")
    upro_bh = buy_and_hold_metrics(prepared["upro_weekly"], "B&H UPRO")

    # Current status
    status = current_status(prepared, winner_params)

    # Print everything
    print_summary(winner_params, strat_result, [spy_bh, upro_bh], status)


if __name__ == "__main__":
    main()
