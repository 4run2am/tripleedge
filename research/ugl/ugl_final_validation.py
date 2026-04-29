#!/usr/bin/env python3
"""
TripleEdge UGL - Phase 3: Final Validation
Walk-forward analysis, Monte Carlo simulation, DCA analysis, benchmark comparison,
correlation analysis with TQQQ/UPRO engines, and combined portfolio simulation.

Usage:
    python ugl_final_validation.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import json
import os
import sys

from ugl_optimizer import (
    download_data, prepare_data, backtest, buy_and_hold_metrics,
    compute_metrics, to_weekly,
    RISK_FREE_RATE, WEEKLY_RF, TRANSACTION_COST, TRAIN_END, DATA_DIR,
)


# =============================================================================
# LOAD WINNER PARAMS
# =============================================================================

def load_winner_params():
    """Load winning parameters from Phase 1/2."""
    params_path = os.path.join(DATA_DIR, "ugl_winner_params.json")
    if os.path.exists(params_path):
        with open(params_path) as f:
            return json.load(f)
    else:
        print("ERROR: ugl_winner_params.json not found. Run ugl_optimizer.py and ugl_structural_variants.py first.")
        sys.exit(1)


def run_winner_backtest(prepared_data, winner_params):
    """Run the backtest with the winner's parameters."""
    gld_weekly = prepared_data["gld_weekly"]
    ugl_weekly = prepared_data["ugl_weekly"]

    return backtest(
        gld_weekly=gld_weekly,
        ugl_weekly=ugl_weekly,
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        reentry_type=winner_params.get("reentry_type", "sma"),
    )


# =============================================================================
# WALK-FORWARD ANALYSIS
# =============================================================================

def walk_forward_analysis(prepared_data, winner_params, n_periods=5):
    """Split data into non-overlapping periods, compute metrics in each."""
    print("\n" + "=" * 70)
    print("WALK-FORWARD ANALYSIS")
    print("=" * 70)

    gld_weekly = prepared_data["gld_weekly"]
    ugl_weekly = prepared_data["ugl_weekly"]

    warmup_weeks = max(winner_params["regime_period"], winner_params["reentry_period"], 50) + 1
    start_date = gld_weekly.index[warmup_weeks]
    end_date = gld_weekly.index[-1]
    total_days = (end_date - start_date).days
    period_days = total_days // n_periods

    period_results = []
    for i in range(n_periods):
        p_start = start_date + pd.Timedelta(days=i * period_days)
        p_end = start_date + pd.Timedelta(days=(i + 1) * period_days)
        if i == n_periods - 1:
            p_end = end_date

        mask = (gld_weekly.index >= p_start) & (gld_weekly.index <= p_end)
        gld_period = gld_weekly[mask]
        ugl_period = ugl_weekly[mask]

        if len(gld_period) < 52:
            continue

        result = backtest(
            gld_weekly=gld_period,
            ugl_weekly=ugl_period,
            regime_sma_period=winner_params["regime_period"],
            reentry_sma_period=winner_params["reentry_period"],
            trailing_stop_pct=winner_params["trailing_stop_pct"],
            reentry_instrument=winner_params["reentry_instrument"],
            regime_type=winner_params.get("regime_type", "weekly_sma"),
            reentry_type=winner_params.get("reentry_type", "sma"),
        )

        if result is None:
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
        print("  No valid walk-forward periods (warmup too long).")
        # Fallback: train/test split
        full_result = run_winner_backtest(prepared_data, winner_params)
        if full_result:
            print(f"  Train: CAGR={full_result['train_cagr']:.1%}, Sharpe={full_result['train_sharpe']:.2f}")
            print(f"  Test:  CAGR={full_result['test_cagr']:.1%}, Sharpe={full_result['test_sharpe']:.2f}")
            print(f"  Train/Test Sharpe Ratio: {full_result['train_test_sharpe_ratio']:.2f}")
        return None

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
    if sharpe_std > 0:
        print(f"  Consistency score (mean/std): {sharpe_mean / sharpe_std:.2f}")

    # Full train/test
    full_result = run_winner_backtest(prepared_data, winner_params)
    if full_result:
        print(f"\n  Train (pre-2016) vs Test (2016+) comparison:")
        print(f"    Train: CAGR={full_result['train_cagr']:.1%}, Sharpe={full_result['train_sharpe']:.2f}, MaxDD={full_result['train_max_dd']:.1%}")
        print(f"    Test:  CAGR={full_result['test_cagr']:.1%}, Sharpe={full_result['test_sharpe']:.2f}, MaxDD={full_result['test_max_dd']:.1%}")
        print(f"    Train/Test Sharpe Ratio: {full_result['train_test_sharpe_ratio']:.2f}")

    return period_df


# =============================================================================
# MONTE CARLO SIMULATION
# =============================================================================

def monte_carlo_simulation(prepared_data, winner_params, n_sims=2000, horizon_years=5,
                           block_size=12):
    """Block bootstrap Monte Carlo simulation with 12-week blocks."""
    print("\n" + "=" * 70)
    print(f"MONTE CARLO SIMULATION ({n_sims} sims, {horizon_years}-year horizon, {block_size}-week blocks)")
    print("=" * 70)

    full_result = run_winner_backtest(prepared_data, winner_params)
    if full_result is None:
        print("  ERROR: Could not run full backtest.")
        return None

    returns = full_result["returns"].values
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
            start = rng.randint(0, max(1, n_returns - block_size))
            block = returns[start:start + block_size]
            for ret in block:
                if week_idx >= horizon_weeks:
                    break
                path[week_idx + 1] = path[week_idx] * (1 + ret)
                week_idx += 1
        terminal_wealth[sim] = path[horizon_weeks]

    percentiles = [5, 25, 50, 75, 95]
    pct_values = np.percentile(terminal_wealth, percentiles)

    print(f"\n  Terminal Wealth Multiple after {horizon_years} years:")
    print(f"  {'Percentile':>12} {'Multiple':>10} {'Ann. Return':>12}")
    print("  " + "-" * 40)
    for p, v in zip(percentiles, pct_values):
        ann_ret = v ** (1 / horizon_years) - 1
        print(f"  {p:>11}th {v:>10.2f}x {ann_ret:>11.1%}")

    prob_loss = (terminal_wealth < 1.0).mean()
    print(f"\n  P(losing money over {horizon_years} years): {prob_loss:.1%}")
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
    """Simulate DCA into the strategy vs buy-and-hold UGL vs buy-and-hold GLD."""
    print("\n" + "=" * 70)
    print(f"DCA ANALYSIS (${weekly_contribution}/week)")
    print("=" * 70)

    gld_weekly = prepared_data["gld_weekly"]
    ugl_weekly = prepared_data["ugl_weekly"]

    full_result = run_winner_backtest(prepared_data, winner_params)
    if full_result is None:
        print("  ERROR: Could not run full backtest.")
        return None

    strategy_returns = full_result["returns"]

    # DCA into strategy
    strat_dca = _simulate_dca(strategy_returns.values, weekly_contribution)

    # DCA into B&H UGL
    ugl_returns = ugl_weekly.pct_change().fillna(0).values
    ugl_dca = _simulate_dca(ugl_returns, weekly_contribution)

    # DCA into B&H GLD
    gld_returns = gld_weekly.pct_change().fillna(0).values
    gld_dca = _simulate_dca(gld_returns, weekly_contribution)

    n_weeks = len(gld_weekly)
    total_invested = weekly_contribution * n_weeks

    print(f"\n  {'Metric':<30} {'TripleEdge UGL':>15} {'B&H UGL':>15} {'B&H GLD':>15}")
    print("  " + "-" * 80)
    print(f"  {'Total invested':<30} ${total_invested:>14,.0f} ${total_invested:>14,.0f} ${total_invested:>14,.0f}")
    print(f"  {'Terminal value':<30} ${strat_dca['terminal']:>14,.0f} ${ugl_dca['terminal']:>14,.0f} ${gld_dca['terminal']:>14,.0f}")
    print(f"  {'Multiple of cost':<30} {strat_dca['terminal']/total_invested:>14.2f}x {ugl_dca['terminal']/total_invested:>14.2f}x {gld_dca['terminal']/total_invested:>14.2f}x")
    print(f"  {'Max drawdown':<30} {strat_dca['max_dd']:>14.1%} {ugl_dca['max_dd']:>14.1%} {gld_dca['max_dd']:>14.1%}")
    print(f"  {'DCA Sharpe':<30} {strat_dca['sharpe']:>14.2f} {ugl_dca['sharpe']:>14.2f} {gld_dca['sharpe']:>14.2f}")

    return {
        "strategy": strat_dca,
        "ugl_bh": ugl_dca,
        "gld_bh": gld_dca,
        "total_invested": total_invested,
    }


def _simulate_dca(weekly_returns, contribution):
    """Simulate weekly DCA given a series of weekly returns."""
    n = len(weekly_returns)
    portfolio = np.zeros(n + 1)

    for i in range(n):
        portfolio[i + 1] = (portfolio[i] + contribution) * (1 + weekly_returns[i])

    terminal = portfolio[-1]
    total_invested = contribution * n

    running_max = np.maximum.accumulate(portfolio[1:])
    dd = (portfolio[1:] - running_max) / np.where(running_max > 0, running_max, 1)
    max_dd = dd.min() if len(dd) > 0 else 0

    port_returns = np.diff(portfolio[1:]) / np.where(portfolio[1:-1] > 0, portfolio[1:-1], 1)
    excess = port_returns - WEEKLY_RF
    sharpe = (excess.mean() / excess.std()) * np.sqrt(52) if len(excess) > 1 and excess.std() > 0 else 0

    return {"terminal": terminal, "max_dd": max_dd, "sharpe": sharpe}


# =============================================================================
# BENCHMARK COMPARISON
# =============================================================================

def benchmark_comparison(prepared_data, winner_params):
    """Compare the winner against all benchmarks including TripleEdge TQQQ and UPRO."""
    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON")
    print("=" * 70)

    gld_weekly = prepared_data["gld_weekly"]
    ugl_weekly = prepared_data["ugl_weekly"]
    spy_weekly = prepared_data["spy_weekly"]

    # Run UGL strategy
    strat_result = run_winner_backtest(prepared_data, winner_params)

    # Align all series to the same date range (UGL strategy dates)
    start_date = gld_weekly.index[0]
    end_date = gld_weekly.index[-1]

    benchmarks = []
    if strat_result:
        benchmarks.append(("TripleEdge UGL", strat_result))

    # B&H UGL
    benchmarks.append(("B&H UGL", buy_and_hold_metrics(ugl_weekly, "B&H UGL")))

    # B&H GLD
    benchmarks.append(("B&H GLD", buy_and_hold_metrics(gld_weekly, "B&H GLD")))

    # B&H SPY (aligned to gold date range)
    if spy_weekly is not None:
        common_spy = spy_weekly.index.intersection(gld_weekly.index)
        if len(common_spy) > 100:
            benchmarks.append(("B&H SPY", buy_and_hold_metrics(spy_weekly.loc[common_spy], "B&H SPY")))

    # TripleEdge TQQQ (QQQ > 200w SMA, TQQQ > 10w SMA, 10% stop)
    tqqq_result = _run_tqqq_benchmark(prepared_data)
    if tqqq_result:
        benchmarks.append(("TripleEdge TQQQ", tqqq_result))

    # TripleEdge UPRO (SPY > 65w SMA, UPRO > 10w SMA, 22% stop)
    upro_result = _run_upro_benchmark(prepared_data)
    if upro_result:
        benchmarks.append(("TripleEdge UPRO", upro_result))

    # Print comparison table
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
        ("pct_time_ugl", "% Time Invested", ".0%"),
        ("total_return", "Total Return", ".1f"),
        ("train_cagr", "Train CAGR", ".1%"),
        ("test_cagr", "Test CAGR", ".1%"),
        ("train_sharpe", "Train Sharpe", ".2f"),
        ("test_sharpe", "Test Sharpe", ".2f"),
    ]

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


def _run_tqqq_benchmark(prepared_data):
    """Run TripleEdge TQQQ: QQQ > 200w SMA, TQQQ > 10w SMA, 10% stop."""
    qqq_weekly = prepared_data.get("qqq_weekly")
    tqqq_weekly = prepared_data.get("tqqq_weekly")

    if qqq_weekly is None or tqqq_weekly is None:
        return None

    # Align to gold date range
    gld_dates = prepared_data["gld_weekly"].index
    common = qqq_weekly.index.intersection(tqqq_weekly.index).intersection(gld_dates)
    if len(common) < 250:
        return None

    # Use the backtest engine — QQQ is the "GLD" equivalent, TQQQ is the "UGL" equivalent
    result = backtest(
        gld_weekly=qqq_weekly.loc[common],
        ugl_weekly=tqqq_weekly.loc[common],
        regime_sma_period=200,
        reentry_sma_period=10,
        trailing_stop_pct=0.10,
        reentry_instrument="UGL",  # Means TQQQ in this context
        regime_type="weekly_sma",
    )
    return result


def _run_upro_benchmark(prepared_data):
    """Run TripleEdge UPRO: SPY > 65w SMA, UPRO > 10w SMA, 22% stop."""
    spy_weekly = prepared_data.get("spy_weekly")
    upro_weekly = prepared_data.get("upro_weekly")

    if spy_weekly is None or upro_weekly is None:
        return None

    # Align to gold date range
    gld_dates = prepared_data["gld_weekly"].index
    common = spy_weekly.index.intersection(upro_weekly.index).intersection(gld_dates)
    if len(common) < 250:
        return None

    result = backtest(
        gld_weekly=spy_weekly.loc[common],
        ugl_weekly=upro_weekly.loc[common],
        regime_sma_period=65,
        reentry_sma_period=10,
        trailing_stop_pct=0.22,
        reentry_instrument="UGL",  # Means UPRO in this context
        regime_type="weekly_sma",
    )
    return result


# =============================================================================
# CORRELATION ANALYSIS (CRITICAL for portfolio construction)
# =============================================================================

def correlation_analysis(prepared_data, winner_params):
    """
    Compute correlations between TripleEdge UGL, TQQQ, and UPRO weekly returns.
    This is the core reason for building the UGL engine — uncorrelated returns.
    """
    print("\n" + "=" * 70)
    print("CORRELATION ANALYSIS")
    print("=" * 70)

    # Get strategy returns for all three engines
    ugl_result = run_winner_backtest(prepared_data, winner_params)
    tqqq_result = _run_tqqq_benchmark(prepared_data)
    upro_result = _run_upro_benchmark(prepared_data)

    if ugl_result is None:
        print("  ERROR: UGL strategy backtest failed.")
        return None

    ugl_returns = ugl_result["returns"]
    results = {"ugl_returns": ugl_returns}

    # --- Weekly return correlations ---
    print("\n  WEEKLY RETURN CORRELATIONS:")
    print("  " + "-" * 50)

    if tqqq_result is not None:
        tqqq_returns = tqqq_result["returns"]
        common = ugl_returns.index.intersection(tqqq_returns.index)
        if len(common) > 52:
            corr_tqqq = ugl_returns.loc[common].corr(tqqq_returns.loc[common])
            print(f"    UGL strategy vs TQQQ strategy: {corr_tqqq:.3f}")
            results["corr_tqqq"] = corr_tqqq
        else:
            print(f"    UGL vs TQQQ: insufficient overlap ({len(common)} weeks)")

    if upro_result is not None:
        upro_returns = upro_result["returns"]
        common = ugl_returns.index.intersection(upro_returns.index)
        if len(common) > 52:
            corr_upro = ugl_returns.loc[common].corr(upro_returns.loc[common])
            print(f"    UGL strategy vs UPRO strategy: {corr_upro:.3f}")
            results["corr_upro"] = corr_upro

            if corr_upro < 0.3:
                print(f"    >>> EXCELLENT: Correlation {corr_upro:.3f} < 0.30 — strong diversification benefit")
            elif corr_upro < 0.5:
                print(f"    >>> GOOD: Correlation {corr_upro:.3f} < 0.50 — meaningful diversification")
            else:
                print(f"    >>> CONCERN: Correlation {corr_upro:.3f} >= 0.50 — weak diversification thesis")
        else:
            print(f"    UGL vs UPRO: insufficient overlap ({len(common)} weeks)")

    if tqqq_result is not None and upro_result is not None:
        tqqq_ret = tqqq_result["returns"]
        upro_ret = upro_result["returns"]
        common = tqqq_ret.index.intersection(upro_ret.index)
        if len(common) > 52:
            corr_eq = tqqq_ret.loc[common].corr(upro_ret.loc[common])
            print(f"    TQQQ strategy vs UPRO strategy: {corr_eq:.3f} (for reference)")

    # --- Rolling 52-week correlation ---
    if upro_result is not None:
        upro_returns = upro_result["returns"]
        common = ugl_returns.index.intersection(upro_returns.index)
        if len(common) > 104:
            ugl_c = ugl_returns.loc[common]
            upro_c = upro_returns.loc[common]
            rolling_corr = ugl_c.rolling(52).corr(upro_c).dropna()
            # Filter out inf/nan from warmup periods
            rolling_corr = rolling_corr.replace([np.inf, -np.inf], np.nan).dropna()

            print(f"\n  ROLLING 52-WEEK CORRELATION (UGL vs UPRO strategy):")
            print("  " + "-" * 50)
            if len(rolling_corr) > 0:
                print(f"    Mean: {rolling_corr.mean():.3f}")
                print(f"    Std:  {rolling_corr.std():.3f}")
                print(f"    Min:  {rolling_corr.min():.3f}")
                print(f"    Max:  {rolling_corr.max():.3f}")
            else:
                print(f"    No valid rolling correlation data.")

            # Show by year
            for year in sorted(rolling_corr.index.year.unique()):
                yearly = rolling_corr[rolling_corr.index.year == year]
                if len(yearly) > 0:
                    print(f"    {year}: {yearly.mean():.3f}")

            results["rolling_corr"] = rolling_corr

    # --- Overlap analysis ---
    print(f"\n  OVERLAP ANALYSIS (all three engines):")
    print("  " + "-" * 50)

    if tqqq_result is not None and upro_result is not None:
        ugl_equity = ugl_result["equity"]
        tqqq_equity = tqqq_result["equity"]
        upro_equity = upro_result["equity"]

        # Determine position status from weekly returns
        # If return ~= WEEKLY_RF, likely in cash; otherwise in position
        common = ugl_returns.index.intersection(
            tqqq_result["returns"].index
        ).intersection(
            upro_result["returns"].index
        )

        if len(common) > 52:
            ugl_in = (ugl_returns.loc[common].abs() > WEEKLY_RF * 2)  # Rough: big moves = in position
            tqqq_in = (tqqq_result["returns"].loc[common].abs() > WEEKLY_RF * 2)
            upro_in = (upro_result["returns"].loc[common].abs() > WEEKLY_RF * 2)

            # More accurate: check if returns differ significantly from cash return
            # Use equity curve slope instead
            ugl_ret = ugl_returns.loc[common]
            tqqq_ret = tqqq_result["returns"].loc[common]
            upro_ret = upro_result["returns"].loc[common]

            # Approximate: if weekly return is within 0.5% of risk-free, assume cash
            cash_threshold = WEEKLY_RF * 1.5
            ugl_invested = (ugl_ret - WEEKLY_RF).abs() > 0.005
            tqqq_invested = (tqqq_ret - WEEKLY_RF).abs() > 0.005
            upro_invested = (upro_ret - WEEKLY_RF).abs() > 0.005

            all_invested = (ugl_invested & tqqq_invested & upro_invested).mean()
            all_cash = (~ugl_invested & ~tqqq_invested & ~upro_invested).mean()
            mixed = 1.0 - all_invested - all_cash

            print(f"    All 3 invested simultaneously:  {all_invested:.1%}")
            print(f"    All 3 in cash simultaneously:   {all_cash:.1%}")
            print(f"    Mixed (diversified):            {mixed:.1%}")
            print(f"    >>> {'GOOD' if mixed > 0.4 else 'OK'}: {mixed:.0%} of time at least one engine diverges")

            results["overlap"] = {
                "all_invested": all_invested,
                "all_cash": all_cash,
                "mixed": mixed,
            }

    return results


# =============================================================================
# COMBINED PORTFOLIO SIMULATION
# =============================================================================

def combined_portfolio_simulation(prepared_data, winner_params):
    """
    Simulate combined portfolios of all three TripleEdge engines.
    Each engine runs independently — when it goes to cash, that slice earns 5.2%.
    """
    print("\n" + "=" * 70)
    print("COMBINED PORTFOLIO SIMULATION")
    print("=" * 70)

    ugl_result = run_winner_backtest(prepared_data, winner_params)
    tqqq_result = _run_tqqq_benchmark(prepared_data)
    upro_result = _run_upro_benchmark(prepared_data)

    if ugl_result is None:
        print("  ERROR: UGL backtest failed.")
        return None

    ugl_returns = ugl_result["returns"]

    # Find common date range for all available engines
    engines = {"UGL": ugl_returns}
    if tqqq_result is not None:
        engines["TQQQ"] = tqqq_result["returns"]
    if upro_result is not None:
        engines["UPRO"] = upro_result["returns"]

    # Find common dates
    common_dates = ugl_returns.index
    for name, ret in engines.items():
        common_dates = common_dates.intersection(ret.index)

    if len(common_dates) < 52:
        print("  ERROR: Insufficient common date range for combined portfolio.")
        return None

    print(f"  Common date range: {common_dates[0].date()} to {common_dates[-1].date()} ({len(common_dates)} weeks)")

    # Align all returns to common dates
    aligned = {}
    for name, ret in engines.items():
        aligned[name] = ret.loc[common_dates]

    # Test different allocations
    allocations = [
        ("Equal weight (33/33/33)", {"TQQQ": 1/3, "UPRO": 1/3, "UGL": 1/3}),
        ("Custom (50/30/20)", {"TQQQ": 0.50, "UPRO": 0.30, "UGL": 0.20}),
        ("Equity heavy (40/40/20)", {"TQQQ": 0.40, "UPRO": 0.40, "UGL": 0.20}),
        ("Gold tilt (25/25/50)", {"TQQQ": 0.25, "UPRO": 0.25, "UGL": 0.50}),
    ]

    portfolio_results = []

    for alloc_name, weights in allocations:
        # Skip if we don't have all engines
        has_all = all(eng in aligned for eng in weights.keys())
        if not has_all:
            # Adjust weights for available engines
            available_weight = sum(w for eng, w in weights.items() if eng in aligned)
            if available_weight == 0:
                continue
            adj_weights = {eng: w / available_weight for eng, w in weights.items() if eng in aligned}
        else:
            adj_weights = weights

        # Compute combined returns
        combined_returns = pd.Series(0.0, index=common_dates)
        for eng, weight in adj_weights.items():
            combined_returns += weight * aligned[eng]

        # Build equity curve
        equity = (1 + combined_returns).cumprod()
        equity.iloc[0] = 1.0

        # Compute metrics
        years = (common_dates[-1] - common_dates[0]).days / 365.25
        total_return = equity.iloc[-1]
        cagr = total_return ** (1 / years) - 1 if years > 0 else 0

        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_dd = drawdown.min()

        excess = combined_returns - WEEKLY_RF
        sharpe = (excess.mean() / excess.std()) * np.sqrt(52) if excess.std() > 0 else 0

        calmar = cagr / abs(max_dd) if max_dd != 0 else 0

        portfolio_results.append({
            "allocation": alloc_name,
            "cagr": cagr,
            "max_dd": max_dd,
            "sharpe": sharpe,
            "calmar": calmar,
            "total_return": total_return,
        })

    # Also add individual engines for comparison
    for eng_name, ret in aligned.items():
        eq = (1 + ret).cumprod()
        eq.iloc[0] = 1.0
        years = (common_dates[-1] - common_dates[0]).days / 365.25
        tr = eq.iloc[-1]
        cagr_i = tr ** (1 / years) - 1 if years > 0 else 0
        rm = eq.cummax()
        dd = ((eq - rm) / rm).min()
        exc = ret - WEEKLY_RF
        sh = (exc.mean() / exc.std()) * np.sqrt(52) if exc.std() > 0 else 0
        cal = cagr_i / abs(dd) if dd != 0 else 0

        portfolio_results.append({
            "allocation": f"Solo {eng_name}",
            "cagr": cagr_i,
            "max_dd": dd,
            "sharpe": sh,
            "calmar": cal,
            "total_return": tr,
        })

    # Print results
    print(f"\n  {'Allocation':<30} {'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} {'Calmar':>7} {'Total Ret':>10}")
    print("  " + "-" * 75)
    for pr in portfolio_results:
        print(f"  {pr['allocation']:<30} {pr['cagr']:>6.1%} {pr['max_dd']:>6.1%} "
              f"{pr['sharpe']:>7.2f} {pr['calmar']:>7.2f} {pr['total_return']:>9.1f}x")

    return portfolio_results


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "#" * 70)
    print("#  TRIPLEEDGE UGL - PHASE 3: FINAL VALIDATION")
    print("#" * 70)

    winner_params = load_winner_params()
    print(f"\n  Winner params: {json.dumps(winner_params, indent=2)}")

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

    # Correlation Analysis
    corr_results = correlation_analysis(prepared, winner_params)

    # Combined Portfolio Simulation
    portfolio_results = combined_portfolio_simulation(prepared, winner_params)

    print("\n" + "#" * 70)
    print("#  PHASE 3 VALIDATION COMPLETE")
    print("#" * 70)

    return {
        "walk_forward": wf_results,
        "monte_carlo": mc_results,
        "dca": dca_results,
        "benchmarks": benchmarks,
        "strategy_result": strat_result,
        "correlations": corr_results,
        "portfolio": portfolio_results,
    }


if __name__ == "__main__":
    main()
