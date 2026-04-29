#!/usr/bin/env python3
"""
TripleEdge UPRO - Phase 3: Final Validation
Walk-forward analysis, Monte Carlo simulation, DCA analysis, benchmark comparison.

Usage:
    python upro_final_validation.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import json
import os
import sys

# Import from optimizer
from upro_optimizer import (
    download_data, prepare_data, backtest, buy_and_hold_metrics,
    compute_metrics, RISK_FREE_RATE, WEEKLY_RF, TRANSACTION_COST,
    TRAIN_END, DATA_DIR
)

# =============================================================================
# LOAD WINNER PARAMS
# =============================================================================

def load_winner_params():
    """Load winning parameters from Phase 1/2."""
    params_path = os.path.join(DATA_DIR, "upro_winner_params.json")
    if os.path.exists(params_path):
        with open(params_path) as f:
            return json.load(f)
    else:
        print("ERROR: upro_winner_params.json not found. Run upro_optimizer.py first.")
        sys.exit(1)


# =============================================================================
# WALK-FORWARD ANALYSIS
# =============================================================================

def walk_forward_analysis(prepared_data, winner_params, n_periods=5):
    """Split data into non-overlapping periods, compute Sharpe in each."""
    print("\n" + "=" * 70)
    print("WALK-FORWARD ANALYSIS")
    print("=" * 70)

    spy_weekly = prepared_data["spy_weekly"]
    upro_weekly = prepared_data["upro_weekly"]

    # Determine warmup
    warmup_weeks = max(winner_params["regime_period"], winner_params["reentry_period"], 50) + 1
    start_date = spy_weekly.index[warmup_weeks]
    end_date = spy_weekly.index[-1]
    total_days = (end_date - start_date).days
    period_days = total_days // n_periods

    period_results = []
    for i in range(n_periods):
        p_start = start_date + pd.Timedelta(days=i * period_days)
        p_end = start_date + pd.Timedelta(days=(i + 1) * period_days)
        if i == n_periods - 1:
            p_end = end_date

        mask = (spy_weekly.index >= p_start) & (spy_weekly.index <= p_end)
        spy_period = spy_weekly[mask]
        upro_period = upro_weekly[mask]

        if len(spy_period) < 52:
            continue

        result = backtest(
            spy_weekly=spy_period,
            upro_weekly=upro_period,
            regime_sma_period=winner_params["regime_period"],
            reentry_sma_period=winner_params["reentry_period"],
            trailing_stop_pct=winner_params["trailing_stop_pct"],
            reentry_instrument=winner_params["reentry_instrument"],
            regime_type=winner_params.get("regime_type", "weekly_sma"),
            spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
        )

        if result is None:
            # If warmup is too long for the period, run on full data with period mask
            continue

        years = (p_end - p_start).days / 365.25
        period_results.append({
            "period": f"{p_start.date()} to {p_end.date()}",
            "years": years,
            "cagr": result["cagr"],
            "sharpe": result["sharpe"],
            "max_dd": result["max_dd"],
            "calmar": result["calmar"],
            "num_trades": result["num_trades"],
        })

    if not period_results:
        print("  No valid walk-forward periods (warmup too long). Running full-period split instead.")
        # Fallback: use train/test split
        return _train_test_walkforward(prepared_data, winner_params)

    period_df = pd.DataFrame(period_results)
    sharpe_std = period_df["sharpe"].std()
    sharpe_mean = period_df["sharpe"].mean()

    print(f"\n  {'Period':<30} {'Years':>6} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>7} {'Calmar':>7} {'Trades':>7}")
    print("  " + "-" * 100)
    for _, row in period_df.iterrows():
        print(f"  {row['period']:<30} {row['years']:>6.1f} {row['cagr']:>6.1%} "
              f"{row['sharpe']:>7.2f} {row['max_dd']:>6.1%} {row['calmar']:>7.2f} "
              f"{int(row['num_trades']):>7}")

    print(f"\n  Mean Sharpe across periods: {sharpe_mean:.2f}")
    print(f"  Std dev of Sharpe: {sharpe_std:.2f}")
    print(f"  Consistency score (mean/std): {sharpe_mean / sharpe_std:.2f}" if sharpe_std > 0 else "")

    # Train vs Test
    print(f"\n  Train (pre-2017) vs Test (2017+) comparison:")
    full_result = backtest(
        spy_weekly=prepared_data["spy_weekly"],
        upro_weekly=prepared_data["upro_weekly"],
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
    )
    if full_result:
        print(f"    Train: CAGR={full_result['train_cagr']:.1%}, Sharpe={full_result['train_sharpe']:.2f}, MaxDD={full_result['train_max_dd']:.1%}")
        print(f"    Test:  CAGR={full_result['test_cagr']:.1%}, Sharpe={full_result['test_sharpe']:.2f}, MaxDD={full_result['test_max_dd']:.1%}")
        print(f"    Train/Test Sharpe Ratio: {full_result['train_test_sharpe_ratio']:.2f}")

    return period_df


def _train_test_walkforward(prepared_data, winner_params):
    """Fallback: simple train/test split for walk-forward."""
    spy_weekly = prepared_data["spy_weekly"]
    upro_weekly = prepared_data["upro_weekly"]

    full_result = backtest(
        spy_weekly=spy_weekly,
        upro_weekly=upro_weekly,
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
    )

    if full_result:
        print(f"    Train: CAGR={full_result['train_cagr']:.1%}, Sharpe={full_result['train_sharpe']:.2f}")
        print(f"    Test:  CAGR={full_result['test_cagr']:.1%}, Sharpe={full_result['test_sharpe']:.2f}")
        print(f"    Train/Test Sharpe Ratio: {full_result['train_test_sharpe_ratio']:.2f}")

    return None


# =============================================================================
# MONTE CARLO SIMULATION
# =============================================================================

def monte_carlo_simulation(prepared_data, winner_params, n_sims=2000, horizon_years=5,
                           block_size=12):
    """
    Block bootstrap Monte Carlo simulation.
    Uses 12-week blocks to preserve autocorrelation in weekly returns.
    """
    print("\n" + "=" * 70)
    print(f"MONTE CARLO SIMULATION ({n_sims} sims, {horizon_years}-year horizon, {block_size}-week blocks)")
    print("=" * 70)

    # First, get the strategy's weekly returns from the full backtest
    full_result = backtest(
        spy_weekly=prepared_data["spy_weekly"],
        upro_weekly=prepared_data["upro_weekly"],
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
    )

    if full_result is None:
        print("  ERROR: Could not run full backtest.")
        return None

    returns = full_result["returns"].values
    # Skip warmup period zeros
    warmup = max(winner_params["regime_period"], winner_params["reentry_period"], 50) + 1
    returns = returns[warmup:]
    n_returns = len(returns)

    horizon_weeks = horizon_years * 52
    n_blocks = (horizon_weeks + block_size - 1) // block_size

    rng = np.random.RandomState(42)
    terminal_wealth = np.zeros(n_sims)

    for sim in range(n_sims):
        path = np.ones(horizon_weeks + 1)
        week_idx = 0
        for _ in range(n_blocks):
            # Pick a random starting point for this block
            start = rng.randint(0, max(1, n_returns - block_size))
            block = returns[start:start + block_size]
            for ret in block:
                if week_idx >= horizon_weeks:
                    break
                path[week_idx + 1] = path[week_idx] * (1 + ret)
                week_idx += 1

        terminal_wealth[sim] = path[horizon_weeks]

    # Compute percentiles
    percentiles = [5, 25, 50, 75, 95]
    pct_values = np.percentile(terminal_wealth, percentiles)

    print(f"\n  Terminal Wealth Multiple after {horizon_years} years:")
    print(f"  {'Percentile':>12} {'Multiple':>10} {'Ann. Return':>12}")
    print("  " + "-" * 40)
    for p, v in zip(percentiles, pct_values):
        ann_ret = v ** (1 / horizon_years) - 1
        print(f"  {p:>11}th {v:>10.2f}x {ann_ret:>11.1%}")

    # Probability of losing money
    prob_loss = (terminal_wealth < 1.0).mean()
    print(f"\n  P(losing money over {horizon_years} years): {prob_loss:.1%}")

    # Distribution stats
    print(f"  Mean terminal wealth: {terminal_wealth.mean():.2f}x")
    print(f"  Median terminal wealth: {np.median(terminal_wealth):.2f}x")

    return {
        "terminal_wealth": terminal_wealth,
        "percentiles": dict(zip(percentiles, pct_values)),
        "prob_loss": prob_loss,
    }


# =============================================================================
# DCA ANALYSIS
# =============================================================================

def dca_analysis(prepared_data, winner_params, weekly_contribution=500):
    """Simulate DCA into the strategy vs buy-and-hold UPRO vs buy-and-hold SPY."""
    print("\n" + "=" * 70)
    print(f"DCA ANALYSIS (${weekly_contribution}/week)")
    print("=" * 70)

    spy_weekly = prepared_data["spy_weekly"]
    upro_weekly = prepared_data["upro_weekly"]

    # Get strategy returns
    full_result = backtest(
        spy_weekly=spy_weekly,
        upro_weekly=upro_weekly,
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
    )

    if full_result is None:
        print("  ERROR: Could not run full backtest.")
        return None

    strategy_equity = full_result["equity"]
    strategy_returns = full_result["returns"]

    # DCA into strategy
    strat_dca = _simulate_dca(strategy_returns.values, weekly_contribution)

    # DCA into B&H UPRO
    upro_returns = upro_weekly.pct_change().fillna(0).values
    upro_dca = _simulate_dca(upro_returns, weekly_contribution)

    # DCA into B&H SPY
    spy_returns = spy_weekly.pct_change().fillna(0).values
    spy_dca = _simulate_dca(spy_returns, weekly_contribution)

    n_weeks = len(spy_weekly)
    total_invested = weekly_contribution * n_weeks

    print(f"\n  {'Metric':<30} {'TripleEdge':>15} {'B&H UPRO':>15} {'B&H SPY':>15}")
    print("  " + "-" * 80)
    print(f"  {'Total invested':<30} ${total_invested:>14,.0f} ${total_invested:>14,.0f} ${total_invested:>14,.0f}")
    print(f"  {'Terminal value':<30} ${strat_dca['terminal']:>14,.0f} ${upro_dca['terminal']:>14,.0f} ${spy_dca['terminal']:>14,.0f}")
    print(f"  {'Multiple of cost':<30} {strat_dca['terminal']/total_invested:>14.2f}x {upro_dca['terminal']/total_invested:>14.2f}x {spy_dca['terminal']/total_invested:>14.2f}x")
    print(f"  {'Max drawdown':<30} {strat_dca['max_dd']:>14.1%} {upro_dca['max_dd']:>14.1%} {spy_dca['max_dd']:>14.1%}")
    print(f"  {'DCA Sharpe':<30} {strat_dca['sharpe']:>14.2f} {upro_dca['sharpe']:>14.2f} {spy_dca['sharpe']:>14.2f}")

    return {
        "strategy": strat_dca,
        "upro_bh": upro_dca,
        "spy_bh": spy_dca,
        "total_invested": total_invested,
    }


def _simulate_dca(weekly_returns, contribution):
    """Simulate weekly DCA given a series of weekly returns."""
    n = len(weekly_returns)
    portfolio = np.zeros(n + 1)

    for i in range(n):
        # Existing portfolio grows by this week's return
        portfolio[i + 1] = (portfolio[i] + contribution) * (1 + weekly_returns[i])

    # Metrics
    terminal = portfolio[-1]
    total_invested = contribution * n

    # Max drawdown of portfolio value
    running_max = np.maximum.accumulate(portfolio[1:])
    dd = (portfolio[1:] - running_max) / np.where(running_max > 0, running_max, 1)
    max_dd = dd.min() if len(dd) > 0 else 0

    # Weekly portfolio returns (for Sharpe)
    port_returns = np.diff(portfolio[1:]) / np.where(portfolio[1:-1] > 0, portfolio[1:-1], 1)
    excess = port_returns - WEEKLY_RF
    sharpe = (excess.mean() / excess.std()) * np.sqrt(52) if len(excess) > 1 and excess.std() > 0 else 0

    return {"terminal": terminal, "max_dd": max_dd, "sharpe": sharpe}


# =============================================================================
# BENCHMARK COMPARISON
# =============================================================================

def benchmark_comparison(prepared_data, winner_params):
    """Compare the winner against all benchmarks."""
    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON")
    print("=" * 70)

    spy_weekly = prepared_data["spy_weekly"]
    upro_weekly = prepared_data["upro_weekly"]
    sso_weekly = prepared_data["sso_weekly"]

    # Run strategy on full data
    strat_result = backtest(
        spy_weekly=spy_weekly,
        upro_weekly=upro_weekly,
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
    )

    # B&H benchmarks
    spy_bh = buy_and_hold_metrics(spy_weekly, "B&H SPY")
    upro_bh = buy_and_hold_metrics(upro_weekly, "B&H UPRO")

    # SSO B&H - align dates
    common = spy_weekly.index.intersection(sso_weekly.index)
    sso_bh = buy_and_hold_metrics(sso_weekly.loc[common], "B&H SSO")

    # TripleEdge TQQQ (reference)
    tqqq_result = None
    if prepared_data["qqq_weekly"] is not None and prepared_data["tqqq_weekly"] is not None:
        qqq_w = prepared_data["qqq_weekly"]
        tqqq_w = prepared_data["tqqq_weekly"]
        # Align to same date range as SPY/UPRO
        common_dates = spy_weekly.index.intersection(qqq_w.index).intersection(tqqq_w.index)
        if len(common_dates) > 200:
            tqqq_result = backtest(
                spy_weekly=qqq_w.loc[common_dates],  # Use QQQ as "spy" equivalent
                upro_weekly=tqqq_w.loc[common_dates],  # Use TQQQ as "upro" equivalent
                regime_sma_period=200,
                reentry_sma_period=10,
                trailing_stop_pct=0.10,
                reentry_instrument="UPRO",  # Means TQQQ in this context
                regime_type="weekly_sma",
                spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
            )

    # Print comparison table
    benchmarks = []
    if strat_result:
        benchmarks.append(("TripleEdge UPRO", strat_result))
    benchmarks.append(("B&H UPRO", upro_bh))
    benchmarks.append(("B&H SPY", spy_bh))
    benchmarks.append(("B&H SSO (2x)", sso_bh))
    if tqqq_result:
        benchmarks.append(("TripleEdge TQQQ", tqqq_result))

    metrics_keys = [
        ("cagr", "CAGR", ".1%"),
        ("max_dd", "Max DD", ".1%"),
        ("sharpe", "Sharpe", ".2f"),
        ("sortino", "Sortino", ".2f"),
        ("calmar", "Calmar", ".2f"),
        ("ulcer_index", "Ulcer Idx", ".3f"),
        ("upi", "UPI", ".2f"),
        ("worst_1yr", "Worst 1yr", ".1%"),
        ("worst_3yr", "Worst 3yr", ".1%"),
        ("pct_3yr_negative", "%3yr Neg", ".1%"),
        ("recovery_weeks", "Recovery (wks)", ".0f"),
        ("num_trades", "Trades", ".0f"),
        ("pct_time_upro", "% in Equities", ".0%"),
        ("total_return", "Total Return", ".1f"),
        ("train_cagr", "Train CAGR", ".1%"),
        ("test_cagr", "Test CAGR", ".1%"),
        ("train_sharpe", "Train Sharpe", ".2f"),
        ("test_sharpe", "Test Sharpe", ".2f"),
    ]

    # Header
    header = f"  {'Metric':<20}"
    for label, _ in benchmarks:
        header += f" {label:>18}"
    print(f"\n{header}")
    print("  " + "-" * (20 + 19 * len(benchmarks)))

    for key, name, fmt in metrics_keys:
        row = f"  {name:<20}"
        for label, result in benchmarks:
            val = result.get(key, np.nan)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                row += f" {'N/A':>18}"
            elif np.isinf(val):
                row += f" {'Never':>18}"
            else:
                row += f" {format(val, fmt):>18}"
        print(row)

    return strat_result, benchmarks


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "#" * 70)
    print("#  TRIPLEEDGE UPRO - PHASE 3: FINAL VALIDATION")
    print("#" * 70)

    # Load winner params
    winner_params = load_winner_params()
    print(f"\n  Winner params: {json.dumps(winner_params, indent=2)}")

    # Download and prepare data
    data = download_data()
    prepared = prepare_data(data)

    # Walk-Forward Analysis
    wf_results = walk_forward_analysis(prepared, winner_params)

    # Monte Carlo Simulation
    mc_results = monte_carlo_simulation(prepared, winner_params, n_sims=2000,
                                         horizon_years=5, block_size=12)

    # DCA Analysis
    dca_results = dca_analysis(prepared, winner_params, weekly_contribution=500)

    # Benchmark Comparison
    strat_result, benchmarks = benchmark_comparison(prepared, winner_params)

    print("\n" + "#" * 70)
    print("#  PHASE 3 VALIDATION COMPLETE")
    print("#" * 70)

    return {
        "walk_forward": wf_results,
        "monte_carlo": mc_results,
        "dca": dca_results,
        "benchmarks": benchmarks,
        "strategy_result": strat_result,
    }


if __name__ == "__main__":
    main()
