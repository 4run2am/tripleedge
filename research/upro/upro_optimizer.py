#!/usr/bin/env python3
"""
TripleEdge UPRO Optimizer
Phase 1: Grid search over regime filter, re-entry signal, and trailing stop parameters.
Phase 2: Structural variants on top winners.

Usage:
    python upro_optimizer.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
from itertools import product
from datetime import datetime, timedelta
import os
import sys

# =============================================================================
# CONSTANTS
# =============================================================================
RISK_FREE_RATE = 0.052          # 5.2% annualized (T-bill/SGOV proxy)
WEEKLY_RF = (1 + RISK_FREE_RATE) ** (1 / 52) - 1
TRANSACTION_COST = 0.0005       # 0.05% per trade (one-way)
UPRO_INCEPTION = pd.Timestamp("2009-06-25")
TRAIN_END = pd.Timestamp("2016-12-31")
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# =============================================================================
# DATA DOWNLOAD & SYNTHETIC UPRO
# =============================================================================

def download_data():
    """Download SPY, UPRO, QQQ, TQQQ, VIX data from yfinance."""
    print("=" * 70)
    print("DOWNLOADING DATA")
    print("=" * 70)

    tickers = {
        "SPY": "1996-01-01",
        "UPRO": "2009-06-01",
        "QQQ": "1999-03-01",
        "TQQQ": "2010-02-01",
        "^VIX": "1996-01-01",
    }

    data = {}
    for ticker, start in tickers.items():
        print(f"  Downloading {ticker} from {start}...")
        df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        data[ticker] = df["Close"].dropna()
        print(f"    -> {len(data[ticker])} daily bars, {data[ticker].index[0].date()} to {data[ticker].index[-1].date()}")

    return data


def build_synthetic_upro(spy_daily):
    """Build synthetic UPRO: 3x daily returns of SPY, compounded."""
    spy_returns = spy_daily.pct_change().dropna()
    synthetic_returns = 3.0 * spy_returns
    # Start at 100 and compound forward
    synthetic_price = 100.0 * (1 + synthetic_returns).cumprod()
    # Set first available date
    synthetic_price.iloc[0] = 100.0
    return synthetic_price


def splice_upro(synthetic_upro, real_upro):
    """Splice real UPRO data onto synthetic. Scale synthetic to match real at splice point."""
    # Find first overlapping date
    overlap_start = real_upro.index[0]
    # Scale synthetic so it matches real at the splice point
    scale = real_upro.iloc[0] / synthetic_upro.loc[:overlap_start].iloc[-1]
    synthetic_scaled = synthetic_upro * scale

    # Use synthetic before real inception, real after
    before = synthetic_scaled[synthetic_scaled.index < overlap_start]
    combined = pd.concat([before, real_upro])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.sort_index(inplace=True)
    return combined


def validate_synthetic(synthetic_upro, real_upro, label="UPRO"):
    """Check synthetic vs real tracking during overlap."""
    overlap = synthetic_upro.index.intersection(real_upro.index)
    if len(overlap) < 20:
        print(f"  WARNING: Only {len(overlap)} overlap days for {label}")
        return

    syn = synthetic_upro.loc[overlap]
    real = real_upro.loc[overlap]

    # Normalize both to 1.0 at start
    syn_norm = syn / syn.iloc[0]
    real_norm = real / real.iloc[0]

    corr = syn_norm.corr(real_norm)
    tracking_error = (syn_norm / real_norm - 1).std() * 100

    print(f"\n  Synthetic vs Real {label} Validation ({overlap[0].date()} to {overlap[-1].date()}):")
    print(f"    Correlation: {corr:.4f}")
    print(f"    Tracking error (std of ratio-1): {tracking_error:.2f}%")
    print(f"    Synthetic final: {syn_norm.iloc[-1]:.4f}, Real final: {real_norm.iloc[-1]:.4f}")
    ratio = syn_norm.iloc[-1] / real_norm.iloc[-1]
    print(f"    Drift ratio: {ratio:.4f}")


def to_weekly(daily_series):
    """Resample daily prices to weekly (Friday close)."""
    weekly = daily_series.resample("W-FRI").last().dropna()
    return weekly


def prepare_data(data):
    """Prepare all weekly series needed for backtesting."""
    print("\n" + "=" * 70)
    print("PREPARING DATA")
    print("=" * 70)

    spy_daily = data["SPY"]
    real_upro_daily = data["UPRO"]

    # Build synthetic UPRO
    synthetic_upro_daily = build_synthetic_upro(spy_daily)
    print(f"  Synthetic UPRO: {len(synthetic_upro_daily)} daily bars")

    # Validate synthetic vs real
    validate_synthetic(synthetic_upro_daily, real_upro_daily)

    # Splice: synthetic before UPRO inception, real after
    upro_daily = splice_upro(synthetic_upro_daily, real_upro_daily)
    print(f"  Spliced UPRO: {len(upro_daily)} daily bars, {upro_daily.index[0].date()} to {upro_daily.index[-1].date()}")

    # Convert to weekly
    spy_weekly = to_weekly(spy_daily)
    upro_weekly = to_weekly(upro_daily)

    # Align on common dates
    common = spy_weekly.index.intersection(upro_weekly.index)
    spy_weekly = spy_weekly.loc[common]
    upro_weekly = upro_weekly.loc[common]

    print(f"  SPY weekly: {len(spy_weekly)} bars, {spy_weekly.index[0].date()} to {spy_weekly.index[-1].date()}")
    print(f"  UPRO weekly: {len(upro_weekly)} bars")

    # Also prepare daily SPY SMA for 200-day regime test
    spy_daily_sma200 = spy_daily.rolling(200).mean()
    # For weekly comparison: resample the daily SMA to weekly
    spy_daily_sma200_weekly = spy_daily_sma200.resample("W-FRI").last().dropna()

    # VIX weekly
    vix_weekly = None
    if "^VIX" in data and len(data["^VIX"]) > 0:
        vix_weekly = to_weekly(data["^VIX"])

    # For TQQQ benchmark comparison
    qqq_weekly = None
    tqqq_weekly = None
    if "QQQ" in data and "TQQQ" in data:
        qqq_daily = data["QQQ"]
        real_tqqq_daily = data["TQQQ"]
        # Build synthetic TQQQ
        qqq_returns = qqq_daily.pct_change().dropna()
        synth_tqqq = 100.0 * (1 + 3.0 * qqq_returns).cumprod()
        synth_tqqq.iloc[0] = 100.0
        tqqq_daily = splice_upro(synth_tqqq, real_tqqq_daily)
        qqq_weekly = to_weekly(qqq_daily)
        tqqq_weekly = to_weekly(tqqq_daily)
        # Align
        common_tqqq = qqq_weekly.index.intersection(tqqq_weekly.index)
        qqq_weekly = qqq_weekly.loc[common_tqqq]
        tqqq_weekly = tqqq_weekly.loc[common_tqqq]

    # SSO (2x S&P) - build synthetic
    sso_daily = 100.0 * (1 + 2.0 * spy_daily.pct_change().dropna()).cumprod()
    sso_daily.iloc[0] = 100.0
    sso_weekly = to_weekly(sso_daily)

    return {
        "spy_weekly": spy_weekly,
        "upro_weekly": upro_weekly,
        "spy_daily_sma200_weekly": spy_daily_sma200_weekly,
        "vix_weekly": vix_weekly,
        "qqq_weekly": qqq_weekly,
        "tqqq_weekly": tqqq_weekly,
        "sso_weekly": sso_weekly,
        "spy_daily": spy_daily,
        "upro_daily": upro_daily,
    }


# =============================================================================
# BACKTESTING ENGINE
# =============================================================================

def backtest(spy_weekly, upro_weekly, regime_sma_period, reentry_sma_period,
             trailing_stop_pct, reentry_instrument="UPRO",
             regime_type="weekly_sma", regime_extra=None,
             reentry_type="sma", reentry_extra=None,
             stop_type="fixed", stop_extra=None,
             spy_daily_sma200_weekly=None, vix_weekly=None,
             extra_filter=None, extra_filter_params=None,
             partial_exit=False, partial_exit_params=None):
    """
    Run a single backtest of the TripleEdge strategy.

    Returns a dict of performance metrics + equity curve.
    """

    n = len(spy_weekly)
    dates = spy_weekly.index

    # --- Compute regime filter ---
    if regime_type == "weekly_sma":
        regime_sma = spy_weekly.rolling(regime_sma_period).mean()
        regime_signal = spy_weekly > regime_sma
    elif regime_type == "weekly_ema":
        regime_sma = spy_weekly.ewm(span=regime_sma_period, adjust=False).mean()
        regime_signal = spy_weekly > regime_sma
    elif regime_type == "daily_200_sma":
        # Use pre-computed daily 200-SMA resampled to weekly
        regime_signal = pd.Series(index=dates, dtype=bool)
        for d in dates:
            if d in spy_daily_sma200_weekly.index:
                # SPY weekly close > SPY 200-day SMA (resampled to weekly)
                spy_val = spy_weekly.loc[d]
                sma_val = spy_daily_sma200_weekly.loc[d] if d in spy_daily_sma200_weekly.index else np.nan
                regime_signal.loc[d] = spy_val > sma_val if not np.isnan(sma_val) else False
            else:
                regime_signal.loc[d] = False
    elif regime_type == "golden_cross":
        spy_sma50 = spy_weekly.rolling(50).mean()
        spy_sma200 = spy_weekly.rolling(200).mean()
        regime_signal = spy_sma50 > spy_sma200
    else:
        raise ValueError(f"Unknown regime_type: {regime_type}")

    # --- Compute re-entry signal ---
    if reentry_instrument == "UPRO":
        reentry_series = upro_weekly
    else:
        reentry_series = spy_weekly

    if reentry_type == "sma":
        reentry_sma = reentry_series.rolling(reentry_sma_period).mean()
        reentry_signal = reentry_series > reentry_sma
    elif reentry_type == "ema":
        reentry_sma = reentry_series.ewm(span=reentry_sma_period, adjust=False).mean()
        reentry_signal = reentry_series > reentry_sma
    else:
        raise ValueError(f"Unknown reentry_type: {reentry_type}")

    # --- Extra filter (optional) ---
    extra_ok = pd.Series(True, index=dates)
    if extra_filter == "vix_below" and vix_weekly is not None:
        threshold = extra_filter_params.get("threshold", 30)
        aligned_vix = vix_weekly.reindex(dates).ffill()
        extra_ok = aligned_vix < threshold
    elif extra_filter == "upro_above_sma50":
        upro_sma50 = upro_weekly.rolling(50).mean()
        extra_ok = upro_weekly > upro_sma50

    # --- ATR for ATR-based stops ---
    atr_values = None
    if stop_type == "atr":
        # ATR(14 weeks) on UPRO
        high_w = upro_weekly  # Approximation using close (we don't have H/L weekly)
        low_w = upro_weekly
        # Use weekly return range as ATR proxy
        upro_returns = upro_weekly.pct_change().abs()
        atr_values = upro_returns.rolling(14).mean() * upro_weekly
        atr_multiplier = stop_extra.get("multiplier", 2.0) if stop_extra else 2.0

    # --- Warmup period ---
    warmup = max(regime_sma_period if regime_type in ("weekly_sma", "weekly_ema") else 200,
                 reentry_sma_period, 50) + 1
    if warmup >= n:
        return None

    # --- Simulation ---
    equity = np.ones(n)
    in_position = False
    peak_price = 0.0
    entry_price = 0.0
    trade_count = 0
    weeks_in_upro = 0
    weeks_in_cash = 0
    weekly_returns = np.zeros(n)
    trade_log = []

    # Partial exit state
    partial_sold = False
    position_fraction = 1.0

    for i in range(1, n):
        date = dates[i]
        prev_date = dates[i - 1]
        upro_price = upro_weekly.iloc[i]
        upro_prev = upro_weekly.iloc[i - 1]
        upro_return = (upro_price / upro_prev) - 1.0

        if i < warmup:
            # Still in warmup - stay in cash
            cash_return = WEEKLY_RF
            equity[i] = equity[i - 1] * (1 + cash_return)
            weekly_returns[i] = cash_return
            weeks_in_cash += 1
            continue

        regime_on = bool(regime_signal.iloc[i]) if i < len(regime_signal) else False
        reentry_ok = bool(reentry_signal.iloc[i]) if i < len(reentry_signal) else False
        filter_ok = bool(extra_ok.iloc[i]) if i < len(extra_ok) else True

        if in_position:
            # Update peak
            if upro_price > peak_price:
                peak_price = upro_price

            # Check trailing stop
            if stop_type == "fixed":
                stop_level = peak_price * (1 - trailing_stop_pct)
                stop_hit = upro_price <= stop_level
            elif stop_type == "atr":
                atr_val = atr_values.iloc[i] if i < len(atr_values) and not np.isnan(atr_values.iloc[i]) else 0
                stop_level = peak_price - atr_multiplier * atr_val
                stop_hit = upro_price <= stop_level
            else:
                stop_level = peak_price * (1 - trailing_stop_pct)
                stop_hit = upro_price <= stop_level

            # Check regime break
            regime_break = not regime_on

            should_exit = stop_hit or regime_break

            if should_exit:
                if partial_exit and not partial_sold:
                    # Sell 50%, keep remaining with wider stop
                    partial_sold = True
                    position_fraction = 0.5
                    wider_stop = partial_exit_params.get("wider_stop", 0.15) if partial_exit_params else 0.15
                    # Apply the return for this week on the full position
                    # Then exit half
                    week_ret = upro_return * 1.0  # Full position this week
                    equity[i] = equity[i - 1] * (1 + week_ret)
                    # Apply transaction cost for partial sell
                    equity[i] *= (1 - TRANSACTION_COST * 0.5)
                    weekly_returns[i] = (equity[i] / equity[i - 1]) - 1
                    weeks_in_upro += 1
                    trade_count += 1
                    # Update trailing stop to wider
                    trailing_stop_pct_active = wider_stop
                    continue
                else:
                    # Full exit
                    # CRITICAL: The return this week reflects the actual price move
                    # The stop fires based on Friday close, we exit Monday open
                    # Approximate: use this week's actual return
                    week_ret = upro_return * position_fraction
                    cost = TRANSACTION_COST * position_fraction
                    equity[i] = equity[i - 1] * (1 + week_ret) * (1 - cost)
                    weekly_returns[i] = (equity[i] / equity[i - 1]) - 1
                    trade_count += 1
                    in_position = False
                    partial_sold = False
                    position_fraction = 1.0
                    weeks_in_upro += 1
                    trade_log.append(("EXIT", str(date.date()), upro_price, "stop" if stop_hit else "regime"))
                    continue

            # Normal hold - apply UPRO return
            week_ret = upro_return * position_fraction
            # If partial, the other half earns cash
            if position_fraction < 1.0:
                week_ret += WEEKLY_RF * (1 - position_fraction)
            equity[i] = equity[i - 1] * (1 + week_ret)
            weekly_returns[i] = week_ret
            weeks_in_upro += 1

        else:
            # Not in position - check for entry
            if regime_on and reentry_ok and filter_ok:
                # Enter position next week (we act Monday after Friday signal)
                # This week's return: we were in cash, entering at end of week
                # Actually: signal fires on Friday, we buy Monday. So this week = cash.
                # The UPRO return accrues starting next week.
                # Simplified: we enter at this week's close, experience next week's return
                equity[i] = equity[i - 1] * (1 + WEEKLY_RF) * (1 - TRANSACTION_COST)
                weekly_returns[i] = (equity[i] / equity[i - 1]) - 1
                in_position = True
                entry_price = upro_price
                peak_price = upro_price
                trade_count += 1
                weeks_in_cash += 1
                trade_log.append(("ENTER", str(date.date()), upro_price, ""))
            else:
                # Stay in cash
                cash_return = WEEKLY_RF
                equity[i] = equity[i - 1] * (1 + cash_return)
                weekly_returns[i] = cash_return
                weeks_in_cash += 1

    # --- Compute Metrics ---
    equity_series = pd.Series(equity, index=dates)
    return_series = pd.Series(weekly_returns, index=dates)

    metrics = compute_metrics(equity_series, return_series, weeks_in_upro, weeks_in_cash,
                              trade_count, dates)
    metrics["equity"] = equity_series
    metrics["returns"] = return_series
    metrics["trade_log"] = trade_log

    return metrics


def compute_metrics(equity_series, return_series, weeks_in_upro, weeks_in_cash,
                    trade_count, dates):
    """Compute all performance metrics from equity curve and returns."""

    n = len(equity_series)
    total_weeks = weeks_in_upro + weeks_in_cash
    years = (dates[-1] - dates[0]).days / 365.25

    # Total return
    total_return = equity_series.iloc[-1] / equity_series.iloc[0]

    # CAGR
    cagr = total_return ** (1 / years) - 1 if years > 0 else 0

    # Max Drawdown
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_dd = drawdown.min()

    # Recovery time from max drawdown
    dd_end_idx = drawdown.idxmin()
    post_dd = equity_series.loc[dd_end_idx:]
    peak_at_dd = running_max.loc[dd_end_idx]
    recovered = post_dd[post_dd >= peak_at_dd]
    if len(recovered) > 0:
        recovery_weeks = (recovered.index[0] - dd_end_idx).days / 7
    else:
        recovery_weeks = np.inf

    # Sharpe Ratio (weekly returns, annualized)
    excess_returns = return_series.iloc[1:] - WEEKLY_RF
    sharpe = 0.0
    if excess_returns.std() > 0:
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(52)

    # Sortino Ratio
    downside = excess_returns[excess_returns < 0]
    downside_std = np.sqrt((downside ** 2).mean()) if len(downside) > 0 else 1e-10
    sortino = (excess_returns.mean() / downside_std) * np.sqrt(52) if downside_std > 0 else 0

    # Calmar Ratio
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    # Ulcer Index
    dd_sq = drawdown ** 2
    ulcer_index = np.sqrt(dd_sq.mean())

    # UPI (Ulcer Performance Index)
    upi = (cagr - RISK_FREE_RATE) / ulcer_index if ulcer_index > 0 else 0

    # Rolling returns
    rolling_52w = equity_series.pct_change(52).dropna()
    rolling_156w = equity_series.pct_change(156).dropna()  # 3 years

    worst_1yr = rolling_52w.min() if len(rolling_52w) > 0 else np.nan
    worst_3yr = rolling_156w.min() if len(rolling_156w) > 0 else np.nan

    # % of 3-year windows negative
    pct_3yr_negative = (rolling_156w < 0).mean() if len(rolling_156w) > 0 else np.nan

    # Train/Test split
    train_mask = dates <= TRAIN_END
    test_mask = dates > TRAIN_END

    train_metrics = _period_metrics(equity_series[train_mask], return_series[train_mask])
    test_metrics = _period_metrics(equity_series[test_mask], return_series[test_mask])

    train_test_sharpe_ratio = (train_metrics["sharpe"] / test_metrics["sharpe"]
                               if test_metrics["sharpe"] != 0 else np.nan)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "ulcer_index": ulcer_index,
        "upi": upi,
        "recovery_weeks": recovery_weeks,
        "worst_1yr": worst_1yr,
        "worst_3yr": worst_3yr,
        "pct_3yr_negative": pct_3yr_negative,
        "num_trades": trade_count,
        "pct_time_upro": weeks_in_upro / total_weeks if total_weeks > 0 else 0,
        "pct_time_cash": weeks_in_cash / total_weeks if total_weeks > 0 else 0,
        "train_cagr": train_metrics["cagr"],
        "train_sharpe": train_metrics["sharpe"],
        "train_max_dd": train_metrics["max_dd"],
        "test_cagr": test_metrics["cagr"],
        "test_sharpe": test_metrics["sharpe"],
        "test_max_dd": test_metrics["max_dd"],
        "train_test_sharpe_ratio": train_test_sharpe_ratio,
    }


def _period_metrics(equity_slice, return_slice):
    """Compute basic metrics for a sub-period."""
    if len(equity_slice) < 10:
        return {"cagr": 0, "sharpe": 0, "max_dd": 0}

    years = (equity_slice.index[-1] - equity_slice.index[0]).days / 365.25
    total_ret = equity_slice.iloc[-1] / equity_slice.iloc[0]
    cagr = total_ret ** (1 / years) - 1 if years > 0 else 0

    running_max = equity_slice.cummax()
    dd = (equity_slice - running_max) / running_max
    max_dd = dd.min()

    excess = return_slice - WEEKLY_RF
    sharpe = 0.0
    if len(excess) > 1 and excess.std() > 0:
        sharpe = (excess.mean() / excess.std()) * np.sqrt(52)

    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd}


# =============================================================================
# PHASE 1: GRID SEARCH
# =============================================================================

def run_phase1(prepared_data):
    """Run full grid search over all parameter combinations."""
    print("\n" + "=" * 70)
    print("PHASE 1: GRID SEARCH (420+ combinations)")
    print("=" * 70)

    spy_weekly = prepared_data["spy_weekly"]
    upro_weekly = prepared_data["upro_weekly"]
    spy_daily_sma200_weekly = prepared_data["spy_daily_sma200_weekly"]

    # Parameter grids
    regime_configs = [
        ("weekly_sma", 150), ("weekly_sma", 175), ("weekly_sma", 200),
        ("weekly_sma", 225), ("weekly_sma", 250),
        ("daily_200_sma", 200),  # 200-day SMA for regime
    ]
    reentry_instruments = ["UPRO", "SPY"]
    reentry_periods = [8, 10, 12, 15, 20, 25, 30]
    stop_pcts = [0.06, 0.08, 0.10, 0.12, 0.15, 0.18]

    results = []
    total = len(regime_configs) * len(reentry_instruments) * len(reentry_periods) * len(stop_pcts)
    count = 0

    for (regime_type_label, regime_period), reentry_inst, reentry_per, stop_pct in product(
        regime_configs, reentry_instruments, reentry_periods, stop_pcts
    ):
        count += 1
        if count % 50 == 0 or count == 1:
            print(f"  Running combination {count}/{total}...")

        # Map regime config
        if regime_type_label == "daily_200_sma":
            regime_type = "daily_200_sma"
            regime_sma_period = 200  # Not used directly but needed for warmup
        else:
            regime_type = "weekly_sma"
            regime_sma_period = regime_period

        result = backtest(
            spy_weekly=spy_weekly,
            upro_weekly=upro_weekly,
            regime_sma_period=regime_sma_period,
            reentry_sma_period=reentry_per,
            trailing_stop_pct=stop_pct,
            reentry_instrument=reentry_inst,
            regime_type=regime_type,
            spy_daily_sma200_weekly=spy_daily_sma200_weekly,
        )

        if result is None:
            continue

        row = {
            "regime_type": regime_type_label,
            "regime_period": regime_period,
            "reentry_instrument": reentry_inst,
            "reentry_period": reentry_per,
            "trailing_stop_pct": stop_pct,
            "total_return": result["total_return"],
            "cagr": result["cagr"],
            "max_dd": result["max_dd"],
            "sharpe": result["sharpe"],
            "sortino": result["sortino"],
            "calmar": result["calmar"],
            "ulcer_index": result["ulcer_index"],
            "upi": result["upi"],
            "recovery_weeks": result["recovery_weeks"],
            "worst_1yr": result["worst_1yr"],
            "worst_3yr": result["worst_3yr"],
            "pct_3yr_negative": result["pct_3yr_negative"],
            "num_trades": result["num_trades"],
            "pct_time_upro": result["pct_time_upro"],
            "pct_time_cash": result["pct_time_cash"],
            "train_cagr": result["train_cagr"],
            "train_sharpe": result["train_sharpe"],
            "train_max_dd": result["train_max_dd"],
            "test_cagr": result["test_cagr"],
            "test_sharpe": result["test_sharpe"],
            "test_max_dd": result["test_max_dd"],
            "train_test_sharpe_ratio": result["train_test_sharpe_ratio"],
        }
        results.append(row)

    df = pd.DataFrame(results)
    print(f"\n  Completed {len(df)} valid combinations out of {total} attempted.")
    return df


def print_top_results(df, sort_by="calmar", n=20, label=""):
    """Print top N results sorted by a metric."""
    if len(df) == 0:
        print("  No results to display.")
        return

    sorted_df = df.sort_values(sort_by, ascending=False).head(n)

    print(f"\n{'=' * 100}")
    print(f"TOP {n} BY {sort_by.upper()} {label}")
    print(f"{'=' * 100}")
    print(f"{'Rank':>4} {'Regime':>12} {'Per':>4} {'ReInst':>6} {'RePer':>5} {'Stop':>5} "
          f"{'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} {'Calmar':>7} {'Sortino':>8} "
          f"{'TrCAGR':>7} {'TeCAGR':>7} {'TrShp':>6} {'TeShp':>6} {'TT_Shp':>7} {'Trades':>6}")
    print("-" * 130)

    for rank, (idx, row) in enumerate(sorted_df.iterrows(), 1):
        regime_label = f"{row['regime_type']}_{int(row['regime_period'])}"
        print(f"{rank:>4} {regime_label:>12} {int(row['regime_period']):>4} "
              f"{row['reentry_instrument']:>6} {int(row['reentry_period']):>5} "
              f"{row['trailing_stop_pct']:>5.0%} "
              f"{row['cagr']:>6.1%} {row['max_dd']:>6.1%} {row['sharpe']:>7.2f} "
              f"{row['calmar']:>7.2f} {row['sortino']:>8.2f} "
              f"{row['train_cagr']:>6.1%} {row['test_cagr']:>6.1%} "
              f"{row['train_sharpe']:>6.2f} {row['test_sharpe']:>6.2f} "
              f"{row['train_test_sharpe_ratio']:>7.2f} {int(row['num_trades']):>6}")

    return sorted_df


# =============================================================================
# PHASE 2: STRUCTURAL VARIANTS
# =============================================================================

def run_phase2(prepared_data, phase1_df):
    """Test structural modifications on top Phase 1 winners."""
    print("\n" + "=" * 70)
    print("PHASE 2: STRUCTURAL VARIANTS")
    print("=" * 70)

    spy_weekly = prepared_data["spy_weekly"]
    upro_weekly = prepared_data["upro_weekly"]
    spy_daily_sma200_weekly = prepared_data["spy_daily_sma200_weekly"]
    vix_weekly = prepared_data["vix_weekly"]

    # Get top 5 winners by Calmar
    top5 = phase1_df.sort_values("calmar", ascending=False).head(5)

    all_variant_results = []

    for idx, winner in top5.iterrows():
        regime_period = int(winner["regime_period"])
        reentry_inst = winner["reentry_instrument"]
        reentry_per = int(winner["reentry_period"])
        stop_pct = winner["trailing_stop_pct"]
        regime_type_label = winner["regime_type"]

        # Determine base regime type
        if regime_type_label == "daily_200_sma":
            base_regime_type = "daily_200_sma"
        else:
            base_regime_type = "weekly_sma"

        base_label = f"R{regime_period}_{reentry_inst}_{reentry_per}_S{stop_pct:.0%}"
        print(f"\n  Testing variants on: {base_label}")
        print(f"    Base: CAGR={winner['cagr']:.1%}, MaxDD={winner['max_dd']:.1%}, "
              f"Sharpe={winner['sharpe']:.2f}, Calmar={winner['calmar']:.2f}")

        # Baseline metrics for comparison
        base_metrics = {
            "cagr": winner["cagr"], "max_dd": winner["max_dd"],
            "sharpe": winner["sharpe"], "calmar": winner["calmar"],
        }

        # --- Variant 1: EMA regime filter ---
        if base_regime_type == "weekly_sma":
            v1 = backtest(spy_weekly, upro_weekly, regime_period, reentry_per,
                          stop_pct, reentry_inst, regime_type="weekly_ema",
                          spy_daily_sma200_weekly=spy_daily_sma200_weekly)
            if v1:
                _add_variant(all_variant_results, "EMA_regime", base_label, v1, base_metrics,
                             regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 2: EMA re-entry signal ---
        v2 = backtest(spy_weekly, upro_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type=base_regime_type,
                      reentry_type="ema",
                      spy_daily_sma200_weekly=spy_daily_sma200_weekly)
        if v2:
            _add_variant(all_variant_results, "EMA_reentry", base_label, v2, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 3: ATR-based trailing stop ---
        for mult in [1.5, 2.0, 2.5, 3.0]:
            v3 = backtest(spy_weekly, upro_weekly, regime_period, reentry_per,
                          stop_pct, reentry_inst, regime_type=base_regime_type,
                          stop_type="atr", stop_extra={"multiplier": mult},
                          spy_daily_sma200_weekly=spy_daily_sma200_weekly)
            if v3:
                _add_variant(all_variant_results, f"ATR_stop_{mult}x", base_label, v3,
                             base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 4: Golden cross regime ---
        v4 = backtest(spy_weekly, upro_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type="golden_cross",
                      spy_daily_sma200_weekly=spy_daily_sma200_weekly)
        if v4:
            _add_variant(all_variant_results, "golden_cross", base_label, v4, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 5: Partial exit ---
        v5 = backtest(spy_weekly, upro_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type=base_regime_type,
                      partial_exit=True, partial_exit_params={"wider_stop": 0.15},
                      spy_daily_sma200_weekly=spy_daily_sma200_weekly)
        if v5:
            _add_variant(all_variant_results, "partial_exit_15pct", base_label, v5, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 6: VIX filter ---
        if vix_weekly is not None:
            for vix_thresh in [25, 30, 35]:
                v6 = backtest(spy_weekly, upro_weekly, regime_period, reentry_per,
                              stop_pct, reentry_inst, regime_type=base_regime_type,
                              extra_filter="vix_below",
                              extra_filter_params={"threshold": vix_thresh},
                              spy_daily_sma200_weekly=spy_daily_sma200_weekly,
                              vix_weekly=vix_weekly)
                if v6:
                    _add_variant(all_variant_results, f"VIX_below_{vix_thresh}", base_label,
                                 v6, base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 7: Extra UPRO > SMA50 filter ---
        v7 = backtest(spy_weekly, upro_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type=base_regime_type,
                      extra_filter="upro_above_sma50",
                      spy_daily_sma200_weekly=spy_daily_sma200_weekly)
        if v7:
            _add_variant(all_variant_results, "UPRO_above_SMA50", base_label, v7, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

    variant_df = pd.DataFrame(all_variant_results)

    if len(variant_df) > 0:
        print(f"\n  Phase 2 complete: {len(variant_df)} variant tests run.")
        print(f"\n{'=' * 110}")
        print("PHASE 2 RESULTS (sorted by Calmar)")
        print(f"{'=' * 110}")
        print(f"{'Variant':<25} {'Base':<30} {'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} "
              f"{'Calmar':>7} {'vs Base CAGR':>12} {'vs Base Calmar':>14}")
        print("-" * 120)

        for _, row in variant_df.sort_values("calmar", ascending=False).head(30).iterrows():
            print(f"{row['variant']:<25} {row['base_label']:<30} "
                  f"{row['cagr']:>6.1%} {row['max_dd']:>6.1%} {row['sharpe']:>7.2f} "
                  f"{row['calmar']:>7.2f} {row['cagr_delta']:>+11.1%} {row['calmar_delta']:>+13.2f}")

    return variant_df


def _add_variant(results_list, variant_name, base_label, result, base_metrics,
                 regime_period, reentry_inst, reentry_per, stop_pct):
    """Add a variant result to the results list."""
    results_list.append({
        "variant": variant_name,
        "base_label": base_label,
        "regime_period": regime_period,
        "reentry_instrument": reentry_inst,
        "reentry_period": reentry_per,
        "trailing_stop_pct": stop_pct,
        "cagr": result["cagr"],
        "max_dd": result["max_dd"],
        "sharpe": result["sharpe"],
        "sortino": result["sortino"],
        "calmar": result["calmar"],
        "ulcer_index": result["ulcer_index"],
        "upi": result["upi"],
        "num_trades": result["num_trades"],
        "train_cagr": result["train_cagr"],
        "test_cagr": result["test_cagr"],
        "train_sharpe": result["train_sharpe"],
        "test_sharpe": result["test_sharpe"],
        "train_test_sharpe_ratio": result["train_test_sharpe_ratio"],
        "cagr_delta": result["cagr"] - base_metrics["cagr"],
        "calmar_delta": result["calmar"] - base_metrics["calmar"],
    })


# =============================================================================
# BUY-AND-HOLD BENCHMARK BACKTEST
# =============================================================================

def buy_and_hold_metrics(weekly_prices, label=""):
    """Compute buy-and-hold metrics for a weekly price series."""
    equity = weekly_prices / weekly_prices.iloc[0]
    returns = weekly_prices.pct_change().fillna(0)

    metrics = compute_metrics(
        equity_series=equity,
        return_series=returns,
        weeks_in_upro=len(equity),
        weeks_in_cash=0,
        trade_count=0,
        dates=equity.index,
    )
    metrics["label"] = label
    return metrics


# =============================================================================
# 2x LEVERAGE VARIANT (SSO)
# =============================================================================

def run_2x_variant(prepared_data, winner_params):
    """Test 2x leverage (SSO) with the winning parameters."""
    print("\n  Testing 2x S&P (SSO) variant...")
    spy_weekly = prepared_data["spy_weekly"]
    sso_weekly = prepared_data["sso_weekly"]

    # Align
    common = spy_weekly.index.intersection(sso_weekly.index)
    spy_w = spy_weekly.loc[common]
    sso_w = sso_weekly.loc[common]

    result = backtest(
        spy_weekly=spy_w,
        upro_weekly=sso_w,  # Use SSO instead of UPRO
        regime_sma_period=winner_params["regime_period"],
        reentry_sma_period=winner_params["reentry_period"],
        trailing_stop_pct=winner_params["trailing_stop_pct"],
        reentry_instrument=winner_params["reentry_instrument"],
        regime_type=winner_params.get("regime_type", "weekly_sma"),
        spy_daily_sma200_weekly=prepared_data["spy_daily_sma200_weekly"],
    )
    return result


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "#" * 70)
    print("#  TRIPLEEDGE UPRO OPTIMIZER")
    print("#  Phase 1: Grid Search | Phase 2: Structural Variants")
    print("#" * 70)

    # Download data
    data = download_data()

    # Prepare weekly series
    prepared = prepare_data(data)

    # Sanity checks
    print("\n" + "=" * 70)
    print("SANITY CHECKS")
    print("=" * 70)
    spy_w = prepared["spy_weekly"]
    upro_w = prepared["upro_weekly"]

    spy_years = (spy_w.index[-1] - spy_w.index[0]).days / 365.25
    spy_total = spy_w.iloc[-1] / spy_w.iloc[0]
    spy_cagr = spy_total ** (1 / spy_years) - 1
    print(f"  SPY B&H CAGR: {spy_cagr:.1%} (expect ~10-11%)")

    upro_bh = buy_and_hold_metrics(upro_w, "B&H UPRO")
    print(f"  UPRO B&H MaxDD: {upro_bh['max_dd']:.1%} (expect -70% to -95%)")
    print(f"  UPRO B&H CAGR: {upro_bh['cagr']:.1%}")

    # PHASE 1
    phase1_df = run_phase1(prepared)

    # Save to CSV
    csv_path = os.path.join(DATA_DIR, "upro_results.csv")
    phase1_df.to_csv(csv_path, index=False)
    print(f"\n  Phase 1 results saved to: {csv_path}")

    # Print top 20 by Calmar
    top_calmar = print_top_results(phase1_df, "calmar", 20, "(Phase 1)")

    # Print top 20 by Sharpe
    top_sharpe = print_top_results(phase1_df, "sharpe", 20, "(Phase 1)")

    # Find overlap between top 20 Calmar and top 20 Sharpe
    if top_calmar is not None and top_sharpe is not None:
        calmar_idx = set(top_calmar.index)
        sharpe_idx = set(top_sharpe.index)
        overlap = calmar_idx & sharpe_idx
        if overlap:
            print(f"\n  *** {len(overlap)} combinations appear in BOTH top-20 lists ***")
            overlap_df = phase1_df.loc[list(overlap)]
            for _, row in overlap_df.iterrows():
                regime_label = f"{row['regime_type']}_{int(row['regime_period'])}"
                print(f"    -> {regime_label} | {row['reentry_instrument']} SMA{int(row['reentry_period'])} | "
                      f"Stop {row['trailing_stop_pct']:.0%} | "
                      f"CAGR={row['cagr']:.1%} MaxDD={row['max_dd']:.1%} "
                      f"Sharpe={row['sharpe']:.2f} Calmar={row['calmar']:.2f}")
        else:
            print("\n  No overlap between top-20 Calmar and top-20 Sharpe lists.")

    # PHASE 2
    variant_df = run_phase2(prepared, phase1_df)

    # Save variant results
    if len(variant_df) > 0:
        variant_csv_path = os.path.join(DATA_DIR, "upro_variant_results.csv")
        variant_df.to_csv(variant_csv_path, index=False)
        print(f"\n  Phase 2 results saved to: {variant_csv_path}")

    # 2x leverage variant on the winner
    winner = phase1_df.sort_values("calmar", ascending=False).iloc[0]
    winner_params = {
        "regime_period": int(winner["regime_period"]),
        "reentry_instrument": winner["reentry_instrument"],
        "reentry_period": int(winner["reentry_period"]),
        "trailing_stop_pct": winner["trailing_stop_pct"],
        "regime_type": "daily_200_sma" if winner["regime_type"] == "daily_200_sma" else "weekly_sma",
    }
    sso_result = run_2x_variant(prepared, winner_params)
    if sso_result:
        print(f"\n  SSO (2x) variant: CAGR={sso_result['cagr']:.1%}, MaxDD={sso_result['max_dd']:.1%}, "
              f"Sharpe={sso_result['sharpe']:.2f}, Calmar={sso_result['calmar']:.2f}")
        print(f"  UPRO (3x) winner: CAGR={winner['cagr']:.1%}, MaxDD={winner['max_dd']:.1%}, "
              f"Sharpe={winner['sharpe']:.2f}, Calmar={winner['calmar']:.2f}")

    # Summary
    print("\n" + "=" * 70)
    print("PHASE 1 WINNER (by Calmar)")
    print("=" * 70)
    regime_per = int(winner["regime_period"])
    regime_desc = "daily 200-SMA" if winner["regime_type"] == "daily_200_sma" else f"weekly {regime_per}-week SMA"
    print(f"  Regime: SPY {regime_desc}")
    print(f"  Re-entry: {winner['reentry_instrument']} > {int(winner['reentry_period'])}-week SMA")
    print(f"  Trailing stop: {winner['trailing_stop_pct']:.0%}")
    print(f"  CAGR: {winner['cagr']:.1%} | MaxDD: {winner['max_dd']:.1%} | "
          f"Sharpe: {winner['sharpe']:.2f} | Calmar: {winner['calmar']:.2f}")
    print(f"  Train: CAGR={winner['train_cagr']:.1%}, Sharpe={winner['train_sharpe']:.2f}")
    print(f"  Test:  CAGR={winner['test_cagr']:.1%}, Sharpe={winner['test_sharpe']:.2f}")
    print(f"  Train/Test Sharpe Ratio: {winner['train_test_sharpe_ratio']:.2f}")
    print(f"  Trades: {int(winner['num_trades'])} | Time in UPRO: {winner['pct_time_upro']:.0%}")

    # Save winner params for Phase 3
    winner_path = os.path.join(DATA_DIR, "upro_winner_params.json")
    import json
    with open(winner_path, "w") as f:
        json.dump(winner_params, f, indent=2)
    print(f"\n  Winner params saved to: {winner_path}")

    print("\n" + "#" * 70)
    print("#  OPTIMIZATION COMPLETE")
    print("#  Run upro_final_validation.py for Phase 3 validation.")
    print("#" * 70)

    return phase1_df, variant_df, winner_params, prepared


if __name__ == "__main__":
    main()
