#!/usr/bin/env python3
"""
TripleEdge UGL Optimizer
Phase 1: Grid search over regime filter (on GLD), re-entry signal (UGL or GLD),
         and trailing stop parameters for UGL (2x Gold).

Builds synthetic GLD (from gold futures pre-2004) and synthetic UGL (2x daily GLD
returns pre-2008) to extend the backtest to ~1998.

Usage:
    python ugl_optimizer.py
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
import json

# =============================================================================
# CONSTANTS
# =============================================================================
RISK_FREE_RATE = 0.052          # 5.2% annualized (T-bill/SGOV proxy)
WEEKLY_RF = (1 + RISK_FREE_RATE) ** (1 / 52) - 1
TRANSACTION_COST = 0.0005       # 0.05% per trade (one-way)
GLD_INCEPTION = pd.Timestamp("2004-11-18")
UGL_INCEPTION = pd.Timestamp("2008-12-02")
TRAIN_END = pd.Timestamp("2015-12-31")   # ~60-65% of data; gold bear 2011-2018 straddles this
DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# =============================================================================
# DATA DOWNLOAD & SYNTHETIC CONSTRUCTION
# =============================================================================

def download_data():
    """Download GLD, UGL, gold futures, and benchmark data from yfinance."""
    print("=" * 70)
    print("DOWNLOADING DATA")
    print("=" * 70)

    tickers = {
        "GC=F":  "1995-01-01",   # Gold futures (for synthetic GLD pre-2004)
        "GLD":   "2004-11-01",   # SPDR Gold Shares
        "UGL":   "2008-12-01",   # ProShares Ultra Gold (2x)
        "SPY":   "1996-01-01",   # S&P 500 ETF (benchmark)
        "QQQ":   "1999-03-01",   # Nasdaq-100 ETF (for TQQQ benchmark)
        "UPRO":  "2009-06-01",   # 3x S&P (for UPRO benchmark)
        "TQQQ":  "2010-02-01",   # 3x Nasdaq (for TQQQ benchmark)
    }

    data = {}
    for ticker, start in tickers.items():
        print(f"  Downloading {ticker} from {start}...")
        try:
            df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            series = df["Close"].dropna()
            if len(series) > 0:
                data[ticker] = series
                print(f"    -> {len(series)} daily bars, {series.index[0].date()} to {series.index[-1].date()}")
            else:
                print(f"    -> WARNING: No data for {ticker}")
        except Exception as e:
            print(f"    -> ERROR downloading {ticker}: {e}")

    # Fallback: if GC=F failed, try alternative gold tickers
    if "GC=F" not in data or len(data["GC=F"]) < 100:
        print("  Gold futures (GC=F) sparse/missing. Trying alternatives...")
        for alt_ticker in ["^XAUUSD", "XAUUSD=X"]:
            try:
                df = yf.download(alt_ticker, start="1995-01-01", auto_adjust=True, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                series = df["Close"].dropna()
                if len(series) > 100:
                    data["GC=F"] = series
                    print(f"    -> Using {alt_ticker}: {len(series)} bars")
                    break
            except Exception:
                continue

    return data


def build_synthetic_gld(gold_daily, real_gld_daily):
    """
    Build synthetic GLD for the pre-2004 period using gold futures data.
    Normalize gold futures to match GLD's price at GLD's inception date.
    """
    # Find GLD's first valid date
    gld_start = real_gld_daily.index[0]

    # Get gold futures data before GLD inception
    gold_before = gold_daily[gold_daily.index < gld_start]
    if len(gold_before) == 0:
        print("  WARNING: No gold futures data before GLD inception.")
        return real_gld_daily

    # Find the last gold futures price before/at GLD inception
    # and the first GLD price
    gld_first_price = real_gld_daily.iloc[0]

    # Find closest gold futures price to GLD start
    gold_at_splice = gold_daily.loc[:gld_start]
    if len(gold_at_splice) == 0:
        return real_gld_daily
    gold_splice_price = gold_at_splice.iloc[-1]

    # Scale factor: make gold futures match GLD at the splice point
    scale = gld_first_price / gold_splice_price
    synthetic_gld = gold_before * scale

    # Combine: synthetic before GLD inception, real GLD after
    combined = pd.concat([synthetic_gld, real_gld_daily])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.sort_index(inplace=True)

    return combined


def build_synthetic_ugl(gld_daily, real_ugl_daily):
    """
    Build synthetic UGL: 2x daily returns of GLD, compounded.
    Splice real UGL from its inception date onward.
    """
    gld_returns = gld_daily.pct_change().dropna()
    synthetic_returns = 2.0 * gld_returns

    # Start at 100 and compound forward
    synthetic_price = 100.0 * (1 + synthetic_returns).cumprod()
    # Ensure first value is set
    first_idx = synthetic_price.index[0]
    synthetic_price.loc[first_idx] = 100.0
    synthetic_price = synthetic_price.sort_index()
    synthetic_price = 100.0 * (1 + synthetic_returns).cumprod()

    return synthetic_price


def splice_series(synthetic, real, label=""):
    """Splice real data onto synthetic. Scale synthetic to match real at splice point."""
    overlap_start = real.index[0]

    # Scale synthetic to match real at the splice point
    synth_at_splice = synthetic.loc[:overlap_start]
    if len(synth_at_splice) == 0:
        print(f"  WARNING: No synthetic data before {label} inception.")
        return real

    scale = real.iloc[0] / synth_at_splice.iloc[-1]
    synthetic_scaled = synthetic * scale

    # Use synthetic before real inception, real after
    before = synthetic_scaled[synthetic_scaled.index < overlap_start]
    combined = pd.concat([before, real])
    combined = combined[~combined.index.duplicated(keep="last")]
    combined.sort_index(inplace=True)
    return combined


def validate_synthetic(synthetic, real, label="UGL"):
    """Check synthetic vs real tracking during overlap period."""
    overlap = synthetic.index.intersection(real.index)
    if len(overlap) < 20:
        print(f"  WARNING: Only {len(overlap)} overlap days for {label}")
        return 0.0

    syn = synthetic.loc[overlap]
    real_s = real.loc[overlap]

    # Normalize both to 1.0 at start
    syn_norm = syn / syn.iloc[0]
    real_norm = real_s / real_s.iloc[0]

    corr = syn_norm.corr(real_norm)
    tracking_error = (syn_norm / real_norm - 1).std() * 100

    print(f"\n  Synthetic vs Real {label} Validation ({overlap[0].date()} to {overlap[-1].date()}):")
    print(f"    Correlation: {corr:.4f}")
    print(f"    Tracking error (std of ratio-1): {tracking_error:.2f}%")
    print(f"    Synthetic final: {syn_norm.iloc[-1]:.4f}, Real final: {real_norm.iloc[-1]:.4f}")
    drift = syn_norm.iloc[-1] / real_norm.iloc[-1]
    print(f"    Drift ratio: {drift:.4f}")

    if corr < 0.95:
        print(f"    *** CONCERN: Correlation {corr:.4f} < 0.95 — synthetic data quality may be poor ***")

    return corr


def to_weekly(daily_series):
    """Resample daily prices to weekly (Friday close)."""
    weekly = daily_series.resample("W-FRI").last().dropna()
    return weekly


def prepare_data(data):
    """Prepare all weekly series needed for backtesting."""
    print("\n" + "=" * 70)
    print("PREPARING DATA")
    print("=" * 70)

    # --- Gold data ---
    gold_daily = data.get("GC=F")
    real_gld_daily = data.get("GLD")
    real_ugl_daily = data.get("UGL")

    if gold_daily is None or real_gld_daily is None or real_ugl_daily is None:
        print("  FATAL: Missing required gold data (GC=F, GLD, or UGL).")
        sys.exit(1)

    # Build synthetic GLD (gold futures normalized to GLD prices, pre-2004)
    gld_daily = build_synthetic_gld(gold_daily, real_gld_daily)
    print(f"  GLD (synthetic+real): {len(gld_daily)} daily bars, {gld_daily.index[0].date()} to {gld_daily.index[-1].date()}")

    # Validate synthetic GLD vs real GLD
    validate_synthetic(gld_daily, real_gld_daily, "GLD")

    # Build synthetic UGL (2x daily GLD returns, compounded)
    synthetic_ugl_daily = build_synthetic_ugl(gld_daily, real_ugl_daily)
    print(f"  Synthetic UGL: {len(synthetic_ugl_daily)} daily bars")

    # Splice: synthetic UGL before inception, real UGL after
    ugl_daily = splice_series(synthetic_ugl_daily, real_ugl_daily, "UGL")
    print(f"  UGL (spliced): {len(ugl_daily)} daily bars, {ugl_daily.index[0].date()} to {ugl_daily.index[-1].date()}")

    # Validate synthetic UGL vs real UGL
    ugl_corr = validate_synthetic(synthetic_ugl_daily, real_ugl_daily, "UGL")

    # Convert to weekly
    gld_weekly = to_weekly(gld_daily)
    ugl_weekly = to_weekly(ugl_daily)

    # Align on common dates
    common = gld_weekly.index.intersection(ugl_weekly.index)
    gld_weekly = gld_weekly.loc[common]
    ugl_weekly = ugl_weekly.loc[common]

    print(f"\n  GLD weekly: {len(gld_weekly)} bars, {gld_weekly.index[0].date()} to {gld_weekly.index[-1].date()}")
    print(f"  UGL weekly: {len(ugl_weekly)} bars")

    # --- Benchmark data ---
    spy_daily = data.get("SPY")
    spy_weekly = to_weekly(spy_daily) if spy_daily is not None else None

    # Build synthetic UPRO (3x SPY)
    upro_weekly = None
    if spy_daily is not None:
        real_upro = data.get("UPRO")
        spy_ret = spy_daily.pct_change().dropna()
        synth_upro = 100.0 * (1 + 3.0 * spy_ret).cumprod()
        if real_upro is not None and len(real_upro) > 0:
            upro_daily = splice_series(synth_upro, real_upro, "UPRO")
        else:
            upro_daily = synth_upro
        upro_weekly = to_weekly(upro_daily)
        if spy_weekly is not None:
            common_upro = spy_weekly.index.intersection(upro_weekly.index)
            upro_weekly = upro_weekly.loc[common_upro]

    # Build synthetic TQQQ (3x QQQ)
    qqq_weekly = None
    tqqq_weekly = None
    qqq_daily = data.get("QQQ")
    if qqq_daily is not None:
        real_tqqq = data.get("TQQQ")
        qqq_ret = qqq_daily.pct_change().dropna()
        synth_tqqq = 100.0 * (1 + 3.0 * qqq_ret).cumprod()
        if real_tqqq is not None and len(real_tqqq) > 0:
            tqqq_daily = splice_series(synth_tqqq, real_tqqq, "TQQQ")
        else:
            tqqq_daily = synth_tqqq
        qqq_weekly = to_weekly(qqq_daily)
        tqqq_weekly = to_weekly(tqqq_daily)
        common_tqqq = qqq_weekly.index.intersection(tqqq_weekly.index)
        qqq_weekly = qqq_weekly.loc[common_tqqq]
        tqqq_weekly = tqqq_weekly.loc[common_tqqq]

    return {
        "gld_weekly": gld_weekly,
        "ugl_weekly": ugl_weekly,
        "gld_daily": gld_daily,
        "ugl_daily": ugl_daily,
        "spy_weekly": spy_weekly,
        "upro_weekly": upro_weekly,
        "qqq_weekly": qqq_weekly,
        "tqqq_weekly": tqqq_weekly,
        "ugl_corr": ugl_corr,
    }


# =============================================================================
# BACKTESTING ENGINE
# =============================================================================

def backtest(gld_weekly, ugl_weekly, regime_sma_period, reentry_sma_period,
             trailing_stop_pct, reentry_instrument="UGL",
             regime_type="weekly_sma",
             reentry_type="sma",
             stop_type="fixed", stop_extra=None,
             extra_filter=None, extra_filter_data=None, extra_filter_params=None,
             partial_exit=False, partial_exit_params=None):
    """
    Run a single backtest of the TripleEdge UGL strategy.

    Regime filter is ALWAYS on GLD (unleveraged gold).
    Re-entry signal is on UGL or GLD (configurable).
    Trailing stop is on UGL price.

    Returns a dict of performance metrics + equity curve, or None if warmup too long.
    """
    n = len(gld_weekly)
    dates = gld_weekly.index

    # --- Compute regime filter (on GLD) ---
    if regime_type == "weekly_sma":
        regime_ma = gld_weekly.rolling(regime_sma_period).mean()
        regime_signal = gld_weekly > regime_ma
    elif regime_type == "weekly_ema":
        regime_ma = gld_weekly.ewm(span=regime_sma_period, adjust=False).mean()
        regime_signal = gld_weekly > regime_ma
    elif regime_type == "golden_cross":
        gld_sma50 = gld_weekly.rolling(50).mean()
        gld_sma200 = gld_weekly.rolling(200).mean()
        regime_signal = gld_sma50 > gld_sma200
    else:
        raise ValueError(f"Unknown regime_type: {regime_type}")

    # --- Compute re-entry signal ---
    if reentry_instrument == "UGL":
        reentry_series = ugl_weekly
    else:
        reentry_series = gld_weekly

    if reentry_type == "sma":
        reentry_ma = reentry_series.rolling(reentry_sma_period).mean()
        reentry_signal = reentry_series > reentry_ma
    elif reentry_type == "ema":
        reentry_ma = reentry_series.ewm(span=reentry_sma_period, adjust=False).mean()
        reentry_signal = reentry_series > reentry_ma
    else:
        raise ValueError(f"Unknown reentry_type: {reentry_type}")

    # --- Extra filter (optional) ---
    extra_ok = pd.Series(True, index=dates)
    if extra_filter == "dxy_below_sma" and extra_filter_data is not None:
        dxy_sma_period = extra_filter_params.get("period", 40) if extra_filter_params else 40
        dxy = extra_filter_data.reindex(dates).ffill()
        dxy_sma = dxy.rolling(dxy_sma_period).mean()
        extra_ok = dxy < dxy_sma
    elif extra_filter == "tip_above_sma" and extra_filter_data is not None:
        tip_sma_period = extra_filter_params.get("period", 20) if extra_filter_params else 20
        tip = extra_filter_data.reindex(dates).ffill()
        tip_sma = tip.rolling(tip_sma_period).mean()
        extra_ok = tip > tip_sma
    elif extra_filter == "gdx_above_sma" and extra_filter_data is not None:
        gdx_sma_period = extra_filter_params.get("period", 10) if extra_filter_params else 10
        gdx = extra_filter_data.reindex(dates).ffill()
        gdx_sma = gdx.rolling(gdx_sma_period).mean()
        extra_ok = gdx > gdx_sma
    elif extra_filter == "gld_low_vol" and extra_filter_data is not None:
        # extra_filter_data is GLD daily for vol calc
        gld_daily_for_vol = extra_filter_data
        gld_vol_20d = gld_daily_for_vol.pct_change().rolling(20).std()
        gld_vol_252d = gld_daily_for_vol.pct_change().rolling(252).std()
        low_vol_signal = gld_vol_20d < gld_vol_252d
        low_vol_weekly = low_vol_signal.resample("W-FRI").last().fillna(False)
        extra_ok = low_vol_weekly.reindex(dates).fillna(True)
    elif extra_filter == "ugl_above_sma50":
        ugl_sma50 = ugl_weekly.rolling(50).mean()
        extra_ok = ugl_weekly > ugl_sma50

    # Fill NaN in extra_ok with True (before filter data starts)
    extra_ok = extra_ok.fillna(True)

    # --- ATR for ATR-based stops ---
    atr_values = None
    if stop_type == "atr":
        ugl_returns = ugl_weekly.pct_change().abs()
        atr_values = ugl_returns.rolling(14).mean() * ugl_weekly
        atr_multiplier = stop_extra.get("multiplier", 2.0) if stop_extra else 2.0

    # --- Warmup period ---
    warmup = max(
        regime_sma_period if regime_type in ("weekly_sma", "weekly_ema") else 200,
        reentry_sma_period,
        50
    ) + 1
    if warmup >= n:
        return None

    # --- Simulation ---
    equity = np.ones(n)
    in_position = False
    peak_price = 0.0
    entry_price = 0.0
    trade_count = 0
    weeks_in_ugl = 0
    weeks_in_cash = 0
    weekly_returns = np.zeros(n)
    trade_log = []

    # Partial exit state
    partial_sold = False
    position_fraction = 1.0

    for i in range(1, n):
        date = dates[i]
        ugl_price = ugl_weekly.iloc[i]
        ugl_prev = ugl_weekly.iloc[i - 1]
        ugl_return = (ugl_price / ugl_prev) - 1.0

        if i < warmup:
            cash_return = WEEKLY_RF
            equity[i] = equity[i - 1] * (1 + cash_return)
            weekly_returns[i] = cash_return
            weeks_in_cash += 1
            continue

        regime_on = bool(regime_signal.iloc[i]) if i < len(regime_signal) else False
        reentry_ok = bool(reentry_signal.iloc[i]) if i < len(reentry_signal) else False
        filter_ok = bool(extra_ok.iloc[i]) if i < len(extra_ok) else True

        if pd.isna(regime_on):
            regime_on = False
        if pd.isna(reentry_ok):
            reentry_ok = False
        if pd.isna(filter_ok):
            filter_ok = True

        if in_position:
            # Update peak
            if ugl_price > peak_price:
                peak_price = ugl_price

            # Check trailing stop
            if stop_type == "fixed":
                stop_level = peak_price * (1 - trailing_stop_pct)
                stop_hit = ugl_price <= stop_level
            elif stop_type == "atr":
                atr_val = atr_values.iloc[i] if (atr_values is not None and i < len(atr_values)
                                                  and not np.isnan(atr_values.iloc[i])) else 0
                stop_level = peak_price - atr_multiplier * atr_val
                stop_hit = ugl_price <= stop_level
            else:
                stop_level = peak_price * (1 - trailing_stop_pct)
                stop_hit = ugl_price <= stop_level

            # Check regime break
            regime_break = not regime_on

            should_exit = stop_hit or regime_break

            if should_exit:
                if partial_exit and not partial_sold:
                    partial_sold = True
                    position_fraction = 0.5
                    wider_stop = partial_exit_params.get("wider_stop", 0.15) if partial_exit_params else 0.15
                    week_ret = ugl_return * 1.0
                    equity[i] = equity[i - 1] * (1 + week_ret)
                    equity[i] *= (1 - TRANSACTION_COST * 0.5)
                    weekly_returns[i] = (equity[i] / equity[i - 1]) - 1
                    weeks_in_ugl += 1
                    trade_count += 1
                    continue
                else:
                    # Full exit — CRITICAL: return reflects actual price change
                    week_ret = ugl_return * position_fraction
                    cost = TRANSACTION_COST * position_fraction
                    equity[i] = equity[i - 1] * (1 + week_ret) * (1 - cost)
                    weekly_returns[i] = (equity[i] / equity[i - 1]) - 1
                    trade_count += 1
                    in_position = False
                    partial_sold = False
                    position_fraction = 1.0
                    weeks_in_ugl += 1
                    trade_log.append(("EXIT", str(date.date()), ugl_price,
                                      "stop" if stop_hit else "regime"))
                    continue

            # Normal hold
            week_ret = ugl_return * position_fraction
            if position_fraction < 1.0:
                week_ret += WEEKLY_RF * (1 - position_fraction)
            equity[i] = equity[i - 1] * (1 + week_ret)
            weekly_returns[i] = week_ret
            weeks_in_ugl += 1

        else:
            # Not in position — check for entry
            if regime_on and reentry_ok and filter_ok:
                # Enter: this week we pay transaction cost, actual UGL exposure starts next week
                equity[i] = equity[i - 1] * (1 + WEEKLY_RF) * (1 - TRANSACTION_COST)
                weekly_returns[i] = (equity[i] / equity[i - 1]) - 1
                in_position = True
                entry_price = ugl_price
                peak_price = ugl_price
                trade_count += 1
                weeks_in_cash += 1
                trade_log.append(("ENTER", str(date.date()), ugl_price, ""))
            else:
                # Stay in cash
                cash_return = WEEKLY_RF
                equity[i] = equity[i - 1] * (1 + cash_return)
                weekly_returns[i] = cash_return
                weeks_in_cash += 1

    # --- Compute Metrics ---
    equity_series = pd.Series(equity, index=dates)
    return_series = pd.Series(weekly_returns, index=dates)

    metrics = compute_metrics(equity_series, return_series, weeks_in_ugl, weeks_in_cash,
                              trade_count, dates)
    metrics["equity"] = equity_series
    metrics["returns"] = return_series
    metrics["trade_log"] = trade_log

    return metrics


def compute_metrics(equity_series, return_series, weeks_in_ugl, weeks_in_cash,
                    trade_count, dates):
    """Compute all performance metrics from equity curve and returns."""
    n = len(equity_series)
    total_weeks = weeks_in_ugl + weeks_in_cash
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
        "pct_time_ugl": weeks_in_ugl / total_weeks if total_weeks > 0 else 0,
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


def buy_and_hold_metrics(weekly_prices, label=""):
    """Compute buy-and-hold metrics for a weekly price series."""
    equity = weekly_prices / weekly_prices.iloc[0]
    returns = weekly_prices.pct_change().fillna(0)

    metrics = compute_metrics(
        equity_series=equity,
        return_series=returns,
        weeks_in_ugl=len(equity),
        weeks_in_cash=0,
        trade_count=0,
        dates=equity.index,
    )
    metrics["label"] = label
    return metrics


# =============================================================================
# PHASE 1: GRID SEARCH
# =============================================================================

def run_phase1(prepared_data):
    """Run full grid search over all parameter combinations."""
    print("\n" + "=" * 70)
    print("PHASE 1: GRID SEARCH (~2,816 combinations)")
    print("=" * 70)

    gld_weekly = prepared_data["gld_weekly"]
    ugl_weekly = prepared_data["ugl_weekly"]

    # Parameter grids — intentionally wide for gold
    regime_periods = [20, 26, 30, 35, 40, 45, 50, 55, 60, 65, 75, 100, 125, 150, 175, 200]
    reentry_instruments = ["UGL", "GLD"]
    reentry_periods = [5, 8, 10, 12, 15, 20, 25, 30]
    stop_pcts = [0.06, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30]

    total = len(regime_periods) * len(reentry_instruments) * len(reentry_periods) * len(stop_pcts)
    print(f"  Testing {total} combinations...")

    results = []
    count = 0

    for regime_per, reentry_inst, reentry_per, stop_pct in product(
        regime_periods, reentry_instruments, reentry_periods, stop_pcts
    ):
        count += 1
        if count % 200 == 0 or count == 1:
            print(f"  Running combination {count}/{total}...")

        result = backtest(
            gld_weekly=gld_weekly,
            ugl_weekly=ugl_weekly,
            regime_sma_period=regime_per,
            reentry_sma_period=reentry_per,
            trailing_stop_pct=stop_pct,
            reentry_instrument=reentry_inst,
            regime_type="weekly_sma",
        )

        if result is None:
            continue

        row = {
            "regime_type": "weekly_sma",
            "regime_period": regime_per,
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
            "pct_time_ugl": result["pct_time_ugl"],
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

    # Check if results are weak and need grid extension
    if len(df) > 0:
        best_calmar = df["calmar"].max()
        print(f"  Best Calmar: {best_calmar:.3f}")
        if best_calmar < 0.20:
            print("  *** Results are weak (best Calmar < 0.20). Expanding grid... ***")
            df = _expand_grid(df, gld_weekly, ugl_weekly)

    return df


def _expand_grid(existing_df, gld_weekly, ugl_weekly):
    """Expand grid in promising directions if initial results are weak."""
    print("\n  EXPANDING GRID: Testing additional regime/stop combinations...")

    # Identify best regime period
    best_row = existing_df.sort_values("calmar", ascending=False).iloc[0]
    best_regime = int(best_row["regime_period"])

    # Add finer granularity around best regime
    extra_regime_periods = list(range(max(15, best_regime - 10), best_regime + 15, 3))
    extra_regime_periods = [p for p in extra_regime_periods if p not in
                            existing_df["regime_period"].unique()]

    # Also test some intermediate stops
    extra_stops = [0.07, 0.09, 0.11, 0.13, 0.14, 0.16, 0.17, 0.19, 0.21, 0.23, 0.24, 0.26, 0.27]
    reentry_instruments = ["UGL", "GLD"]
    reentry_periods = [5, 8, 10, 12, 15, 20, 25, 30]

    new_results = []
    count = 0
    total = len(extra_regime_periods) * len(reentry_instruments) * len(reentry_periods) * len(extra_stops)
    print(f"  Testing {total} additional combinations...")

    for regime_per, reentry_inst, reentry_per, stop_pct in product(
        extra_regime_periods, reentry_instruments, reentry_periods, extra_stops
    ):
        count += 1
        if count % 200 == 0:
            print(f"    Expansion {count}/{total}...")

        result = backtest(
            gld_weekly=gld_weekly,
            ugl_weekly=ugl_weekly,
            regime_sma_period=regime_per,
            reentry_sma_period=reentry_per,
            trailing_stop_pct=stop_pct,
            reentry_instrument=reentry_inst,
            regime_type="weekly_sma",
        )

        if result is None:
            continue

        new_results.append({
            "regime_type": "weekly_sma",
            "regime_period": regime_per,
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
            "pct_time_ugl": result["pct_time_ugl"],
            "pct_time_cash": result["pct_time_cash"],
            "train_cagr": result["train_cagr"],
            "train_sharpe": result["train_sharpe"],
            "train_max_dd": result["train_max_dd"],
            "test_cagr": result["test_cagr"],
            "test_sharpe": result["test_sharpe"],
            "test_max_dd": result["test_max_dd"],
            "train_test_sharpe_ratio": result["train_test_sharpe_ratio"],
        })

    if new_results:
        expansion_df = pd.DataFrame(new_results)
        combined = pd.concat([existing_df, expansion_df], ignore_index=True)
        print(f"  Expansion complete: {len(combined)} total combinations.")
        return combined

    return existing_df


def print_top_results(df, sort_by="calmar", n=20, label=""):
    """Print top N results sorted by a metric."""
    if len(df) == 0:
        print("  No results to display.")
        return None

    sorted_df = df.sort_values(sort_by, ascending=False).head(n)

    print(f"\n{'=' * 130}")
    print(f"TOP {n} BY {sort_by.upper()} {label}")
    print(f"{'=' * 130}")
    print(f"{'Rank':>4} {'RegPer':>6} {'ReInst':>6} {'RePer':>5} {'Stop':>5} "
          f"{'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} {'Calmar':>7} {'Sortino':>8} "
          f"{'TrCAGR':>7} {'TeCAGR':>7} {'TrShp':>6} {'TeShp':>6} {'TT_Shp':>7} {'Trades':>6}")
    print("-" * 130)

    for rank, (idx, row) in enumerate(sorted_df.iterrows(), 1):
        print(f"{rank:>4} {int(row['regime_period']):>6} "
              f"{row['reentry_instrument']:>6} {int(row['reentry_period']):>5} "
              f"{row['trailing_stop_pct']:>5.0%} "
              f"{row['cagr']:>6.1%} {row['max_dd']:>6.1%} {row['sharpe']:>7.2f} "
              f"{row['calmar']:>7.2f} {row['sortino']:>8.2f} "
              f"{row['train_cagr']:>6.1%} {row['test_cagr']:>6.1%} "
              f"{row['train_sharpe']:>6.2f} {row['test_sharpe']:>6.2f} "
              f"{row['train_test_sharpe_ratio']:>7.2f} {int(row['num_trades']):>6}")

    return sorted_df


def print_best_per_regime(df):
    """Print best configuration at each regime period."""
    if len(df) == 0:
        return

    print(f"\n{'=' * 130}")
    print("BEST CONFIGURATION PER REGIME PERIOD (by Calmar)")
    print(f"{'=' * 130}")
    print(f"{'RegPer':>6} {'ReInst':>6} {'RePer':>5} {'Stop':>5} "
          f"{'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} {'Calmar':>7} {'Sortino':>8} "
          f"{'TrShp':>6} {'TeShp':>6} {'TT_Shp':>7} {'Trades':>6} {'%UGL':>5}")
    print("-" * 110)

    for regime_per in sorted(df["regime_period"].unique()):
        subset = df[df["regime_period"] == regime_per]
        best = subset.sort_values("calmar", ascending=False).iloc[0]
        print(f"{int(regime_per):>6} "
              f"{best['reentry_instrument']:>6} {int(best['reentry_period']):>5} "
              f"{best['trailing_stop_pct']:>5.0%} "
              f"{best['cagr']:>6.1%} {best['max_dd']:>6.1%} {best['sharpe']:>7.2f} "
              f"{best['calmar']:>7.2f} {best['sortino']:>8.2f} "
              f"{best['train_sharpe']:>6.2f} {best['test_sharpe']:>6.2f} "
              f"{best['train_test_sharpe_ratio']:>7.2f} {int(best['num_trades']):>6} "
              f"{best['pct_time_ugl']:>4.0%}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "#" * 70)
    print("#  TRIPLEEDGE UGL OPTIMIZER")
    print("#  Phase 1: Grid Search for 2x Gold (UGL)")
    print("#" * 70)

    # Download data
    data = download_data()

    # Prepare weekly series
    prepared = prepare_data(data)

    # Sanity checks
    print("\n" + "=" * 70)
    print("SANITY CHECKS")
    print("=" * 70)

    gld_w = prepared["gld_weekly"]
    ugl_w = prepared["ugl_weekly"]

    gld_years = (gld_w.index[-1] - gld_w.index[0]).days / 365.25
    gld_total = gld_w.iloc[-1] / gld_w.iloc[0]
    gld_cagr = gld_total ** (1 / gld_years) - 1
    print(f"  GLD B&H CAGR: {gld_cagr:.1%} (expect ~7-9%)")

    ugl_bh = buy_and_hold_metrics(ugl_w, "B&H UGL")
    print(f"  UGL B&H MaxDD: {ugl_bh['max_dd']:.1%} (expect -50% to -75%)")
    print(f"  UGL B&H CAGR: {ugl_bh['cagr']:.1%}")

    print(f"  Data range: {gld_w.index[0].date()} to {gld_w.index[-1].date()} ({gld_years:.1f} years)")
    print(f"  Synthetic UGL correlation: {prepared['ugl_corr']:.4f}")

    # PHASE 1: Grid Search
    phase1_df = run_phase1(prepared)

    # Save to CSV
    csv_path = os.path.join(DATA_DIR, "ugl_results.csv")
    phase1_df.to_csv(csv_path, index=False)
    print(f"\n  Phase 1 results saved to: {csv_path}")

    # Print top 20 by Calmar
    top_calmar = print_top_results(phase1_df, "calmar", 20, "(Phase 1)")

    # Print top 20 by Sharpe
    top_sharpe = print_top_results(phase1_df, "sharpe", 20, "(Phase 1)")

    # Find overlap
    if top_calmar is not None and top_sharpe is not None:
        calmar_idx = set(top_calmar.index)
        sharpe_idx = set(top_sharpe.index)
        overlap = calmar_idx & sharpe_idx
        if overlap:
            print(f"\n  *** {len(overlap)} combinations appear in BOTH top-20 lists ***")
            overlap_df = phase1_df.loc[list(overlap)].sort_values("calmar", ascending=False)
            for _, row in overlap_df.iterrows():
                print(f"    -> GLD {int(row['regime_period'])}w SMA | "
                      f"{row['reentry_instrument']} SMA{int(row['reentry_period'])} | "
                      f"Stop {row['trailing_stop_pct']:.0%} | "
                      f"CAGR={row['cagr']:.1%} MaxDD={row['max_dd']:.1%} "
                      f"Sharpe={row['sharpe']:.2f} Calmar={row['calmar']:.2f} "
                      f"TT_Sharpe={row['train_test_sharpe_ratio']:.2f}")
        else:
            print("\n  No overlap between top-20 Calmar and top-20 Sharpe lists.")

    # Best per regime period
    print_best_per_regime(phase1_df)

    # Determine winner
    winner = phase1_df.sort_values("calmar", ascending=False).iloc[0]
    winner_params = {
        "regime_period": int(winner["regime_period"]),
        "reentry_instrument": winner["reentry_instrument"],
        "reentry_period": int(winner["reentry_period"]),
        "trailing_stop_pct": float(winner["trailing_stop_pct"]),
        "regime_type": "weekly_sma",
    }

    # Summary
    print("\n" + "=" * 70)
    print("PHASE 1 WINNER (by Calmar)")
    print("=" * 70)
    print(f"  Regime: GLD > {winner_params['regime_period']}-week SMA")
    print(f"  Re-entry: {winner_params['reentry_instrument']} > {winner_params['reentry_period']}-week SMA")
    print(f"  Trailing stop: {winner_params['trailing_stop_pct']:.0%}")
    print(f"  CAGR: {winner['cagr']:.1%} | MaxDD: {winner['max_dd']:.1%} | "
          f"Sharpe: {winner['sharpe']:.2f} | Calmar: {winner['calmar']:.2f}")
    print(f"  Train: CAGR={winner['train_cagr']:.1%}, Sharpe={winner['train_sharpe']:.2f}")
    print(f"  Test:  CAGR={winner['test_cagr']:.1%}, Sharpe={winner['test_sharpe']:.2f}")
    print(f"  Train/Test Sharpe Ratio: {winner['train_test_sharpe_ratio']:.2f}")
    print(f"  Trades: {int(winner['num_trades'])} | Time in UGL: {winner['pct_time_ugl']:.0%}")

    # Save winner params
    winner_path = os.path.join(DATA_DIR, "ugl_winner_params.json")
    with open(winner_path, "w") as f:
        json.dump(winner_params, f, indent=2)
    print(f"\n  Winner params saved to: {winner_path}")

    print("\n" + "#" * 70)
    print("#  PHASE 1 COMPLETE")
    print("#  Run ugl_structural_variants.py for Phase 2.")
    print("#" * 70)

    return phase1_df, winner_params, prepared


if __name__ == "__main__":
    main()
