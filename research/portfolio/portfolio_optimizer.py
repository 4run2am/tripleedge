#!/usr/bin/env python3
"""
TripleEdge Portfolio Optimizer — Historical Research
=====================================================
Tested all capital allocation combinations across three engines to determine
the optimal UPRO / UGL split. TQQQ was included in the search but excluded
from the final strategy (see research/tqqq/TQQQ_RESEARCH_NOTES.md).

Final decision: 75% UPRO / 25% UGL (no TQQQ).
  - Mathematical optimum by Calmar: ~50/50 UPRO/UGL
  - 75/25 chosen for: younger investor, DCA, UPRO real-data outperformance

Engines tested:
  - TripleEdge TQQQ: QQQ > 200w SMA, TQQQ > 10w SMA, 10% stop
  - TripleEdge UPRO: SPY > 65w SMA, UPRO > 10w SMA, 22% stop
  - TripleEdge UGL:  GLD > 100w SMA, GLD > 20w SMA, 28% stop

Grid: every 5% increment → 231 allocations tested.
Then 1% fine-grid around the best region.

Usage:
    cd research/portfolio && python3 portfolio_optimizer.py
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import os

# Allow importing from the sibling ugl/ research directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ugl'))

import numpy as np
import pandas as pd
import yfinance as yf
from itertools import product
import json

from ugl_optimizer import (
    download_data, to_weekly, splice_series,
    build_synthetic_gld, build_synthetic_ugl,
    backtest, compute_metrics, buy_and_hold_metrics,
    RISK_FREE_RATE, WEEKLY_RF, TRANSACTION_COST,
)

# Save outputs to this directory (research/portfolio/), not research/ugl/
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

TRAIN_END = pd.Timestamp("2016-12-31")
STEP = 5   # percent increment for coarse grid


# =============================================================================
# PREPARE ALL THREE ENGINE SERIES
# =============================================================================

def prepare_all_engines(data):
    """
    Build weekly return series for all three engines over a common date range.
    Returns a dict with aligned return series and equity curves.
    """
    print("\n" + "=" * 70)
    print("PREPARING ALL THREE ENGINE RETURN SERIES")
    print("=" * 70)

    # ── GLD / UGL ──────────────────────────────────────────────────────────
    gold_daily   = data["GC=F"]
    real_gld     = data["GLD"]
    real_ugl     = data["UGL"]

    gld_daily    = build_synthetic_gld(gold_daily, real_gld)
    synth_ugl    = build_synthetic_ugl(gld_daily, real_ugl)
    ugl_daily    = splice_series(synth_ugl, real_ugl, "UGL")

    gld_weekly   = to_weekly(gld_daily)
    ugl_weekly   = to_weekly(ugl_daily)
    common_gu    = gld_weekly.index.intersection(ugl_weekly.index)
    gld_weekly   = gld_weekly.loc[common_gu]
    ugl_weekly   = ugl_weekly.loc[common_gu]

    # ── SPY / UPRO ─────────────────────────────────────────────────────────
    spy_daily    = data["SPY"]
    real_upro    = data["UPRO"]

    spy_ret      = spy_daily.pct_change().dropna()
    synth_upro   = 100.0 * (1 + 3.0 * spy_ret).cumprod()
    upro_daily   = splice_series(synth_upro, real_upro, "UPRO")

    spy_weekly   = to_weekly(spy_daily)
    upro_weekly  = to_weekly(upro_daily)
    common_su    = spy_weekly.index.intersection(upro_weekly.index)
    spy_weekly   = spy_weekly.loc[common_su]
    upro_weekly  = upro_weekly.loc[common_su]

    # ── QQQ / TQQQ ─────────────────────────────────────────────────────────
    qqq_daily    = data["QQQ"]
    real_tqqq    = data["TQQQ"]

    qqq_ret      = qqq_daily.pct_change().dropna()
    synth_tqqq   = 100.0 * (1 + 3.0 * qqq_ret).cumprod()
    tqqq_daily   = splice_series(synth_tqqq, real_tqqq, "TQQQ")

    qqq_weekly   = to_weekly(qqq_daily)
    tqqq_weekly  = to_weekly(tqqq_daily)
    common_qt    = qqq_weekly.index.intersection(tqqq_weekly.index)
    qqq_weekly   = qqq_weekly.loc[common_qt]
    tqqq_weekly  = tqqq_weekly.loc[common_qt]

    # ── Run each engine backtest ────────────────────────────────────────────
    print("  Running TripleEdge TQQQ backtest...")
    tqqq_result = backtest(
        gld_weekly=qqq_weekly, ugl_weekly=tqqq_weekly,
        regime_sma_period=200, reentry_sma_period=10,
        trailing_stop_pct=0.10, reentry_instrument="UGL",
        regime_type="weekly_sma",
    )

    print("  Running TripleEdge UPRO backtest...")
    upro_result = backtest(
        gld_weekly=spy_weekly, ugl_weekly=upro_weekly,
        regime_sma_period=65, reentry_sma_period=10,
        trailing_stop_pct=0.22, reentry_instrument="UGL",
        regime_type="weekly_sma",
    )

    print("  Running TripleEdge UGL backtest...")
    ugl_result = backtest(
        gld_weekly=gld_weekly, ugl_weekly=ugl_weekly,
        regime_sma_period=100, reentry_sma_period=20,
        trailing_stop_pct=0.28, reentry_instrument="GLD",
        regime_type="weekly_sma",
    )

    if any(r is None for r in [tqqq_result, upro_result, ugl_result]):
        raise RuntimeError("One or more engine backtests returned None.")

    tqqq_ret = tqqq_result["returns"]
    upro_ret = upro_result["returns"]
    ugl_ret  = ugl_result["returns"]

    # ── Align all three to a common date range ─────────────────────────────
    common = tqqq_ret.index.intersection(upro_ret.index).intersection(ugl_ret.index)
    tqqq_ret = tqqq_ret.loc[common]
    upro_ret = upro_ret.loc[common]
    ugl_ret  = ugl_ret.loc[common]

    years = (common[-1] - common[0]).days / 365.25
    print(f"\n  Common date range: {common[0].date()} → {common[-1].date()} "
          f"({len(common)} weeks, {years:.1f} years)")

    # Individual engine quick stats
    for label, ret in [("TQQQ", tqqq_ret), ("UPRO", upro_ret), ("UGL", ugl_ret)]:
        eq = (1 + ret).cumprod()
        tr = eq.iloc[-1]
        yrs = (common[-1] - common[0]).days / 365.25
        cagr = tr ** (1 / yrs) - 1
        rm = eq.cummax()
        dd = ((eq - rm) / rm).min()
        exc = ret - WEEKLY_RF
        sh = (exc.mean() / exc.std()) * np.sqrt(52) if exc.std() > 0 else 0
        print(f"  {label:5s}: CAGR={cagr:.1%}  MaxDD={dd:.1%}  Sharpe={sh:.2f}  "
              f"Total={tr:.1f}x")

    return {
        "tqqq": tqqq_ret,
        "upro": upro_ret,
        "ugl":  ugl_ret,
        "common": common,
    }


# =============================================================================
# PORTFOLIO METRICS
# =============================================================================

def portfolio_metrics(tqqq_ret, upro_ret, ugl_ret, w_tqqq, w_upro, w_ugl, dates):
    """Compute blended portfolio metrics for a given allocation."""
    combined = w_tqqq * tqqq_ret + w_upro * upro_ret + w_ugl * ugl_ret

    equity = (1 + combined).cumprod()
    equity.iloc[0] = 1.0

    years = (dates[-1] - dates[0]).days / 365.25
    total_return = equity.iloc[-1]
    cagr = total_return ** (1 / years) - 1 if years > 0 else 0

    rm = equity.cummax()
    dd = (equity - rm) / rm
    max_dd = dd.min()

    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    exc = combined - WEEKLY_RF
    sharpe = (exc.mean() / exc.std()) * np.sqrt(52) if exc.std() > 0 else 0

    downside = exc[exc < 0]
    ds_std = np.sqrt((downside ** 2).mean()) if len(downside) > 0 else 1e-10
    sortino = (exc.mean() / ds_std) * np.sqrt(52)

    ulcer = np.sqrt((dd ** 2).mean())
    upi = (cagr - RISK_FREE_RATE) / ulcer if ulcer > 0 else 0

    rolling_52 = equity.pct_change(52).dropna()
    worst_1yr = rolling_52.min() if len(rolling_52) > 0 else np.nan

    rolling_156 = equity.pct_change(156).dropna()
    worst_3yr = rolling_156.min() if len(rolling_156) > 0 else np.nan
    pct_3yr_neg = (rolling_156 < 0).mean() if len(rolling_156) > 0 else np.nan

    # Train/test split
    train_mask = dates <= TRAIN_END
    test_mask  = dates > TRAIN_END

    def _sub(m):
        e = equity[m]; r = combined[m]
        if len(e) < 10:
            return 0, 0, 0
        yrs = (e.index[-1] - e.index[0]).days / 365.25
        tr2 = e.iloc[-1] / e.iloc[0]
        cg = tr2 ** (1 / yrs) - 1 if yrs > 0 else 0
        exc2 = r - WEEKLY_RF
        sh = (exc2.mean() / exc2.std()) * np.sqrt(52) if exc2.std() > 0 else 0
        rm2 = e.cummax()
        dd2 = ((e - rm2) / rm2).min()
        return cg, sh, dd2

    tr_cagr, tr_sharpe, tr_dd = _sub(train_mask)
    te_cagr, te_sharpe, te_dd = _sub(test_mask)
    tt_ratio = (tr_sharpe / te_sharpe) if te_sharpe != 0 else np.nan

    return {
        "w_tqqq": w_tqqq, "w_upro": w_upro, "w_ugl": w_ugl,
        "cagr": cagr, "max_dd": max_dd, "sharpe": sharpe,
        "sortino": sortino, "calmar": calmar, "ulcer": ulcer, "upi": upi,
        "worst_1yr": worst_1yr, "worst_3yr": worst_3yr, "pct_3yr_neg": pct_3yr_neg,
        "total_return": total_return,
        "train_cagr": tr_cagr, "train_sharpe": tr_sharpe, "train_dd": tr_dd,
        "test_cagr":  te_cagr, "test_sharpe":  te_sharpe, "test_dd":  te_dd,
        "tt_sharpe_ratio": tt_ratio,
        "returns": combined,
    }


# =============================================================================
# COARSE GRID SEARCH (5% steps → 231 combinations)
# =============================================================================

def run_coarse_grid(engines):
    """Test all allocations at STEP% increments."""
    print("\n" + "=" * 70)
    print(f"COARSE GRID SEARCH ({STEP}% increments)")
    print("=" * 70)

    tqqq_ret = engines["tqqq"]
    upro_ret = engines["upro"]
    ugl_ret  = engines["ugl"]
    dates    = engines["common"]

    results = []
    steps = list(range(0, 101, STEP))
    total = sum(1 for wt in steps for wu in steps if wt + wu <= 100)
    print(f"  Testing {total} allocations...")

    for w_tqqq_pct in steps:
        for w_upro_pct in steps:
            w_ugl_pct = 100 - w_tqqq_pct - w_upro_pct
            if w_ugl_pct < 0:
                continue
            w_t = w_tqqq_pct / 100
            w_u = w_upro_pct / 100
            w_g = w_ugl_pct  / 100

            m = portfolio_metrics(tqqq_ret, upro_ret, ugl_ret, w_t, w_u, w_g, dates)
            results.append(m)

    df = pd.DataFrame(results)
    # Drop the 'returns' column for CSV (too large)
    df_csv = df.drop(columns=["returns"], errors="ignore")
    return df, df_csv


# =============================================================================
# FINE GRID SEARCH (1% steps around best region)
# =============================================================================

def run_fine_grid(engines, coarse_df, top_n=5):
    """1% fine grid around the best allocations from the coarse search."""
    print("\n" + "=" * 70)
    print("FINE GRID SEARCH (1% increments around best region)")
    print("=" * 70)

    tqqq_ret = engines["tqqq"]
    upro_ret = engines["upro"]
    ugl_ret  = engines["ugl"]
    dates    = engines["common"]

    # Find the centroid of the top-N Calmar allocations
    top = coarse_df.sort_values("calmar", ascending=False).head(top_n)
    ct = round(top["w_tqqq"].mean() * 100)
    cu = round(top["w_upro"].mean() * 100)
    cg = round(top["w_ugl"].mean()  * 100)
    print(f"  Centroid of top-{top_n}: TQQQ={ct}%, UPRO={cu}%, UGL={cg}%")

    # Fine grid: ±15% around centroid in 1% steps
    margin = 20
    t_range = range(max(0, ct - margin), min(100, ct + margin) + 1)
    u_range = range(max(0, cu - margin), min(100, cu + margin) + 1)

    results = []
    for w_tqqq_pct in t_range:
        for w_upro_pct in u_range:
            w_ugl_pct = 100 - w_tqqq_pct - w_upro_pct
            if w_ugl_pct < 0 or w_ugl_pct > 100:
                continue
            w_t = w_tqqq_pct / 100
            w_u = w_upro_pct / 100
            w_g = w_ugl_pct  / 100
            m = portfolio_metrics(tqqq_ret, upro_ret, ugl_ret, w_t, w_u, w_g, dates)
            results.append(m)

    fine_df = pd.DataFrame(results)
    print(f"  {len(fine_df)} fine-grid allocations tested.")
    return fine_df


# =============================================================================
# PRINTING HELPERS
# =============================================================================

def fmt_alloc(row):
    return f"TQQQ={row['w_tqqq']:.0%} / UPRO={row['w_upro']:.0%} / UGL={row['w_ugl']:.0%}"


def print_top(df, sort_by="calmar", n=20, label=""):
    if len(df) == 0:
        return None
    sd = df.sort_values(sort_by, ascending=False).head(n).copy()

    print(f"\n{'='*120}")
    print(f"TOP {n} BY {sort_by.upper()} {label}")
    print(f"{'='*120}")
    print(f"{'Rank':>4} {'Allocation':^32} {'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} "
          f"{'Calmar':>7} {'Sortino':>8} {'UPI':>6} {'Worst1yr':>9} "
          f"{'TrShp':>6} {'TeShp':>6} {'TT_Shp':>7}")
    print("-" * 120)

    for rank, (_, row) in enumerate(sd.iterrows(), 1):
        alloc = f"T{row['w_tqqq']:.0%} / U{row['w_upro']:.0%} / G{row['w_ugl']:.0%}"
        print(f"{rank:>4} {alloc:^32} {row['cagr']:>6.1%} {row['max_dd']:>6.1%} "
              f"{row['sharpe']:>7.2f} {row['calmar']:>7.2f} {row['sortino']:>8.2f} "
              f"{row['upi']:>6.2f} {row['worst_1yr']:>8.1%} "
              f"{row['train_sharpe']:>6.2f} {row['test_sharpe']:>6.2f} "
              f"{row['tt_sharpe_ratio']:>7.2f}")
    return sd


def print_no_tqqq(df, label=""):
    """Show best allocations with 0% TQQQ (UPRO + UGL only)."""
    sub = df[df["w_tqqq"] == 0.0].copy()
    if len(sub) == 0:
        print("  No 0% TQQQ allocations found.")
        return None
    print(f"\n{'='*100}")
    print(f"BEST ALLOCATIONS WITH 0% TQQQ (UPRO + UGL only) {label}")
    print(f"{'='*100}")
    print(f"{'Rank':>4} {'UPRO':>6} {'UGL':>6} {'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} "
          f"{'Calmar':>7} {'UPI':>6} {'Worst1yr':>9} {'TrShp':>6} {'TeShp':>6} {'TT_Shp':>7}")
    print("-" * 100)
    sd = sub.sort_values("calmar", ascending=False).head(15)
    for rank, (_, row) in enumerate(sd.iterrows(), 1):
        print(f"{rank:>4} {row['w_upro']:>5.0%} {row['w_ugl']:>5.0%} "
              f"{row['cagr']:>6.1%} {row['max_dd']:>6.1%} {row['sharpe']:>7.2f} "
              f"{row['calmar']:>7.2f} {row['upi']:>6.2f} {row['worst_1yr']:>8.1%} "
              f"{row['train_sharpe']:>6.2f} {row['test_sharpe']:>6.2f} "
              f"{row['tt_sharpe_ratio']:>7.2f}")
    return sd


def print_best_per_tqqq(df):
    """Best allocation at each TQQQ weight level."""
    print(f"\n{'='*110}")
    print("BEST ALLOCATION AT EACH TQQQ WEIGHT (by Calmar)")
    print(f"{'='*110}")
    print(f"{'TQQQ%':>6} {'UPRO%':>6} {'UGL%':>6} {'CAGR':>7} {'MaxDD':>7} "
          f"{'Sharpe':>7} {'Calmar':>7} {'UPI':>6} {'Worst1yr':>9} {'TrShp':>6} {'TeShp':>6}")
    print("-" * 90)
    for wt in sorted(df["w_tqqq"].unique()):
        sub = df[df["w_tqqq"] == wt]
        best = sub.sort_values("calmar", ascending=False).iloc[0]
        print(f"{wt:>5.0%} {best['w_upro']:>5.0%} {best['w_ugl']:>5.0%} "
              f"{best['cagr']:>6.1%} {best['max_dd']:>6.1%} {best['sharpe']:>7.2f} "
              f"{best['calmar']:>7.2f} {best['upi']:>6.2f} {best['worst_1yr']:>8.1%} "
              f"{best['train_sharpe']:>6.2f} {best['test_sharpe']:>6.2f}")


def print_comparison_benchmarks(engines, df):
    """Side-by-side: optimal vs equal-weight vs solo engines."""
    tqqq_ret = engines["tqqq"]
    upro_ret = engines["upro"]
    ugl_ret  = engines["ugl"]
    dates    = engines["common"]

    best_calmar = df.sort_values("calmar", ascending=False).iloc[0]
    best_sharpe = df.sort_values("sharpe", ascending=False).iloc[0]
    # Closest to 33/33/33
    eq_row = df.assign(_d=((df["w_tqqq"]-1/3)**2+(df["w_upro"]-1/3)**2+(df["w_ugl"]-1/3)**2)
                      ).sort_values("_d").iloc[0]

    print(f"\n{'='*100}")
    print("ALLOCATION COMPARISON SUMMARY")
    print(f"{'='*100}")

    rows = [
        ("Best Calmar",  best_calmar),
        ("Best Sharpe",  best_sharpe),
        ("Equal 33/33/33", eq_row),
    ]

    # Solo engines
    solo_t = portfolio_metrics(tqqq_ret, upro_ret, ugl_ret, 1.0, 0.0, 0.0, dates)
    solo_u = portfolio_metrics(tqqq_ret, upro_ret, ugl_ret, 0.0, 1.0, 0.0, dates)
    solo_g = portfolio_metrics(tqqq_ret, upro_ret, ugl_ret, 0.0, 0.0, 1.0, dates)

    metrics_order = [
        ("Allocation",   lambda r: fmt_alloc(r) if isinstance(r, pd.Series) else fmt_alloc(pd.Series(r))),
        ("CAGR",         lambda r: f"{r['cagr']:.1%}"),
        ("MaxDD",        lambda r: f"{r['max_dd']:.1%}"),
        ("Sharpe",       lambda r: f"{r['sharpe']:.2f}"),
        ("Calmar",       lambda r: f"{r['calmar']:.2f}"),
        ("Sortino",      lambda r: f"{r['sortino']:.2f}"),
        ("UPI",          lambda r: f"{r['upi']:.2f}"),
        ("Worst 1yr",    lambda r: f"{r['worst_1yr']:.1%}"),
        ("Worst 3yr",    lambda r: f"{r['worst_3yr']:.1%}"),
        ("Total Return", lambda r: f"{r['total_return']:.1f}x"),
        ("Train CAGR",   lambda r: f"{r['train_cagr']:.1%}"),
        ("Test CAGR",    lambda r: f"{r['test_cagr']:.1%}"),
        ("Train Sharpe", lambda r: f"{r['train_sharpe']:.2f}"),
        ("Test Sharpe",  lambda r: f"{r['test_sharpe']:.2f}"),
        ("TT Sharpe",    lambda r: f"{r['tt_sharpe_ratio']:.2f}"),
    ]

    all_cols = rows + [("Solo TQQQ",  solo_t), ("Solo UPRO", solo_u),
                       ("Solo UGL",   solo_g)]

    header = f"  {'Metric':<15}"
    for lbl, _ in all_cols:
        header += f" {lbl:>16}"
    print(header)
    print("  " + "-" * (15 + 17 * len(all_cols)))

    for metric_name, fn in metrics_order:
        row_str = f"  {metric_name:<15}"
        for lbl, data in all_cols:
            try:
                row_str += f" {fn(data):>16}"
            except Exception:
                row_str += f" {'N/A':>16}"
        print(row_str)


# =============================================================================
# WALK-FORWARD ON TOP ALLOCATIONS
# =============================================================================

def walk_forward_top(engines, df, n_top=5, n_periods=4):
    """Walk-forward analysis on the top N allocations by Calmar."""
    print(f"\n{'='*80}")
    print(f"WALK-FORWARD ANALYSIS — TOP {n_top} ALLOCATIONS")
    print(f"{'='*80}")

    tqqq_ret = engines["tqqq"]
    upro_ret = engines["upro"]
    ugl_ret  = engines["ugl"]
    dates    = engines["common"]

    # Also include best 0% TQQQ
    top_allocs = df.sort_values("calmar", ascending=False).head(n_top)
    no_tqqq_best = df[df["w_tqqq"] == 0.0].sort_values("calmar", ascending=False).head(1)
    top_allocs = pd.concat([top_allocs, no_tqqq_best]).drop_duplicates(
        subset=["w_tqqq", "w_upro", "w_ugl"])

    start = dates[0]
    end   = dates[-1]
    period_days = (end - start).days // n_periods

    period_borders = [start + pd.Timedelta(days=i * period_days) for i in range(n_periods + 1)]
    period_borders[-1] = end

    print(f"\n  {'Allocation':^32}", end="")
    for i in range(n_periods):
        label = f"{period_borders[i].year}-{period_borders[i+1].year}"
        print(f" {label:^12}", end="")
    print(f"  {'Mean':>6}  {'Std':>6}  {'Consist':>8}")
    print("  " + "-" * (32 + 13 * n_periods + 25))

    for _, alloc in top_allocs.iterrows():
        wt, wu, wg = alloc["w_tqqq"], alloc["w_upro"], alloc["w_ugl"]
        label = f"T{wt:.0%}/U{wu:.0%}/G{wg:.0%}"
        combined = wt * tqqq_ret + wu * upro_ret + wg * ugl_ret
        period_sharpes = []

        for i in range(n_periods):
            p_start = period_borders[i]
            p_end   = period_borders[i + 1]
            mask    = (dates >= p_start) & (dates < p_end)
            ret_p   = combined[mask]
            if len(ret_p) < 26:
                period_sharpes.append(np.nan)
                continue
            exc_p = ret_p - WEEKLY_RF
            sh = (exc_p.mean() / exc_p.std()) * np.sqrt(52) if exc_p.std() > 0 else 0
            period_sharpes.append(sh)

        print(f"  {label:^32}", end="")
        for sh in period_sharpes:
            if np.isnan(sh):
                print(f" {'N/A':^12}", end="")
            else:
                print(f" {sh:^12.2f}", end="")

        valid = [s for s in period_sharpes if not np.isnan(s)]
        if len(valid) >= 2:
            mn = np.mean(valid)
            sd = np.std(valid)
            cs = mn / sd if sd > 0 else np.inf
            print(f"  {mn:>6.2f}  {sd:>6.2f}  {cs:>8.2f}")
        else:
            print()


# =============================================================================
# EFFICIENT FRONTIER SUMMARY
# =============================================================================

def print_efficient_frontier(df):
    """Print the efficient frontier (best CAGR at each MaxDD level)."""
    print(f"\n{'='*80}")
    print("EFFICIENT FRONTIER (best CAGR at each MaxDD band)")
    print(f"{'='*80}")
    print(f"  {'MaxDD Band':^15} {'Best Allocation':^32} {'CAGR':>7} {'Sharpe':>7} {'Calmar':>7}")
    print("  " + "-" * 70)

    bands = [(-0.15, -0.10), (-0.20, -0.15), (-0.25, -0.20),
             (-0.30, -0.25), (-0.35, -0.30), (-0.40, -0.35),
             (-0.45, -0.40), (-0.50, -0.45), (-0.55, -0.50), (-0.60, -0.55)]

    for lo, hi in bands:
        band = df[(df["max_dd"] >= lo) & (df["max_dd"] < hi)]
        if len(band) == 0:
            continue
        best = band.sort_values("cagr", ascending=False).iloc[0]
        band_label = f"{lo:.0%} to {hi:.0%}"
        alloc = f"T{best['w_tqqq']:.0%}/U{best['w_upro']:.0%}/G{best['w_ugl']:.0%}"
        print(f"  {band_label:^15} {alloc:^32} {best['cagr']:>6.1%} "
              f"{best['sharpe']:>7.2f} {best['calmar']:>7.2f}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "#" * 70)
    print("#  TRIPLEEDGE PORTFOLIO OPTIMIZER")
    print("#  Finding optimal TQQQ / UPRO / UGL allocation")
    print("#" * 70)

    # Download data
    data = download_data()

    # Prepare all three engine return series
    engines = prepare_all_engines(data)

    # ── Coarse grid (5% steps) ─────────────────────────────────────────────
    coarse_df, coarse_csv = run_coarse_grid(engines)

    # Save coarse results
    coarse_path = os.path.join(DATA_DIR, "portfolio_results_coarse.csv")
    coarse_csv.to_csv(coarse_path, index=False)
    print(f"\n  Coarse grid saved to: {coarse_path}")

    # Print top 20 by Calmar
    top_calmar = print_top(coarse_df, "calmar", 20, "(Coarse Grid)")

    # Print top 20 by Sharpe
    top_sharpe = print_top(coarse_df, "sharpe", 20, "(Coarse Grid)")

    # Print top 20 by UPI
    top_upi = print_top(coarse_df, "upi", 20, "(Coarse Grid)")

    # Find overlap (Calmar + Sharpe top-20)
    if top_calmar is not None and top_sharpe is not None:
        oc = set(zip(top_calmar["w_tqqq"].round(2), top_calmar["w_upro"].round(2)))
        os2 = set(zip(top_sharpe["w_tqqq"].round(2), top_sharpe["w_upro"].round(2)))
        overlap = oc & os2
        if overlap:
            print(f"\n  *** {len(overlap)} allocations in BOTH top-20 Calmar AND top-20 Sharpe ***")
            for (wt, wu) in sorted(overlap):
                wg = 1.0 - wt - wu
                row = coarse_df[(coarse_df["w_tqqq"].round(2)==wt) &
                                (coarse_df["w_upro"].round(2)==wu)].iloc[0]
                print(f"    TQQQ={wt:.0%}  UPRO={wu:.0%}  UGL={wg:.0%} → "
                      f"CAGR={row['cagr']:.1%}  MaxDD={row['max_dd']:.1%}  "
                      f"Sharpe={row['sharpe']:.2f}  Calmar={row['calmar']:.2f}  "
                      f"TT_Shp={row['tt_sharpe_ratio']:.2f}")

    # Best per TQQQ weight
    print_best_per_tqqq(coarse_df)

    # 0% TQQQ analysis (user's hypothesis)
    no_tqqq = print_no_tqqq(coarse_df, "(Coarse Grid)")

    # Efficient frontier
    print_efficient_frontier(coarse_df)

    # ── Fine grid (1% steps around best region) ────────────────────────────
    fine_df = run_fine_grid(engines, coarse_df, top_n=5)
    fine_path = os.path.join(DATA_DIR, "portfolio_results_fine.csv")
    fine_df.drop(columns=["returns"], errors="ignore").to_csv(fine_path, index=False)
    print(f"\n  Fine grid saved to: {fine_path}")

    print_top(fine_df, "calmar", 20, "(Fine Grid — 1% steps)")
    print_top(fine_df, "sharpe", 15, "(Fine Grid — 1% steps)")
    print_no_tqqq(fine_df, "(Fine Grid)")

    # ── Walk-forward ───────────────────────────────────────────────────────
    # Use fine grid if available, else coarse
    best_df = fine_df if len(fine_df) > 0 else coarse_df
    walk_forward_top(engines, best_df, n_top=5, n_periods=4)

    # ── Comparison summary ─────────────────────────────────────────────────
    print_comparison_benchmarks(engines, best_df)

    # ── Final recommendation ───────────────────────────────────────────────
    overall_best = best_df.sort_values("calmar", ascending=False).iloc[0]
    print(f"\n{'#'*70}")
    print(f"#  FINAL RECOMMENDATION")
    print(f"{'#'*70}")
    print(f"\n  Optimal Allocation (by Calmar):")
    print(f"    TQQQ: {overall_best['w_tqqq']:.0%}")
    print(f"    UPRO: {overall_best['w_upro']:.0%}")
    print(f"    UGL:  {overall_best['w_ugl']:.0%}")
    print(f"\n  CAGR:       {overall_best['cagr']:.1%}")
    print(f"  MaxDD:      {overall_best['max_dd']:.1%}")
    print(f"  Sharpe:     {overall_best['sharpe']:.2f}")
    print(f"  Calmar:     {overall_best['calmar']:.2f}")
    print(f"  UPI:        {overall_best['upi']:.2f}")
    print(f"  Train Shp:  {overall_best['train_sharpe']:.2f}")
    print(f"  Test Shp:   {overall_best['test_sharpe']:.2f}")
    print(f"  TT Ratio:   {overall_best['tt_sharpe_ratio']:.2f}")

    no_tqqq_best = best_df[best_df["w_tqqq"] == 0.0].sort_values(
        "calmar", ascending=False)
    if len(no_tqqq_best) > 0:
        ntb = no_tqqq_best.iloc[0]
        print(f"\n  Best 0% TQQQ Allocation (UPRO + UGL only):")
        print(f"    UPRO: {ntb['w_upro']:.0%}")
        print(f"    UGL:  {ntb['w_ugl']:.0%}")
        print(f"    CAGR={ntb['cagr']:.1%}  MaxDD={ntb['max_dd']:.1%}  "
              f"Sharpe={ntb['sharpe']:.2f}  Calmar={ntb['calmar']:.2f}")
        calmar_diff = overall_best["calmar"] - ntb["calmar"]
        print(f"    vs optimal: Calmar diff = {calmar_diff:+.3f} "
              f"({'TQQQ adds value' if calmar_diff > 0.02 else 'no meaningful difference' if abs(calmar_diff) <= 0.02 else 'TQQQ hurts'})")

    # Save final recommendation
    rec = {
        "optimal_calmar": {
            "w_tqqq": float(overall_best["w_tqqq"]),
            "w_upro": float(overall_best["w_upro"]),
            "w_ugl":  float(overall_best["w_ugl"]),
            "cagr":   float(overall_best["cagr"]),
            "max_dd": float(overall_best["max_dd"]),
            "sharpe": float(overall_best["sharpe"]),
            "calmar": float(overall_best["calmar"]),
        }
    }
    if len(no_tqqq_best) > 0:
        ntb = no_tqqq_best.iloc[0]
        rec["best_no_tqqq"] = {
            "w_tqqq": 0.0,
            "w_upro": float(ntb["w_upro"]),
            "w_ugl":  float(ntb["w_ugl"]),
            "cagr":   float(ntb["cagr"]),
            "max_dd": float(ntb["max_dd"]),
            "sharpe": float(ntb["sharpe"]),
            "calmar": float(ntb["calmar"]),
        }

    rec_path = os.path.join(DATA_DIR, "portfolio_recommendation.json")
    with open(rec_path, "w") as f:
        json.dump(rec, f, indent=2)
    print(f"\n  Recommendation saved to: {rec_path}")

    print(f"\n{'#'*70}")
    print("#  PORTFOLIO OPTIMIZATION COMPLETE")
    print(f"{'#'*70}")

    return coarse_df, fine_df, engines


if __name__ == "__main__":
    main()
