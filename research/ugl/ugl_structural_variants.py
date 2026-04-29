#!/usr/bin/env python3
"""
TripleEdge UGL - Phase 2: Structural Variants
Tests structural modifications on top Phase 1 winners, including gold-specific
filters (DXY, real rates, GDX, inverse volatility).

Usage:
    python ugl_structural_variants.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import json
import os
import sys

from ugl_optimizer import (
    download_data, prepare_data, backtest, buy_and_hold_metrics,
    compute_metrics, to_weekly,
    RISK_FREE_RATE, WEEKLY_RF, TRANSACTION_COST, TRAIN_END, DATA_DIR,
)


# =============================================================================
# DOWNLOAD EXTRA DATA FOR GOLD-SPECIFIC FILTERS
# =============================================================================

def download_extra_data():
    """Download DXY, TIP, GDX for gold-specific structural variant filters."""
    print("\n" + "=" * 70)
    print("DOWNLOADING EXTRA DATA FOR GOLD-SPECIFIC FILTERS")
    print("=" * 70)

    extra = {}

    # DXY (Dollar Index) — gold inversely correlated with USD
    for dxy_ticker in ["DX-Y.NYB", "DX=F"]:
        try:
            print(f"  Downloading DXY ({dxy_ticker})...")
            df = yf.download(dxy_ticker, start="1995-01-01", auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            series = df["Close"].dropna()
            if len(series) > 100:
                extra["DXY"] = to_weekly(series)
                print(f"    -> {len(extra['DXY'])} weekly bars")
                break
        except Exception as e:
            print(f"    -> Failed: {e}")

    # TIP (iShares TIPS Bond ETF) — proxy for real rates
    try:
        print(f"  Downloading TIP...")
        df = yf.download("TIP", start="2003-01-01", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        series = df["Close"].dropna()
        if len(series) > 100:
            extra["TIP"] = to_weekly(series)
            print(f"    -> {len(extra['TIP'])} weekly bars")
    except Exception as e:
        print(f"    -> Failed: {e}")

    # GDX (VanEck Gold Miners ETF) — miners often lead gold
    try:
        print(f"  Downloading GDX...")
        df = yf.download("GDX", start="2006-05-01", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        series = df["Close"].dropna()
        if len(series) > 100:
            extra["GDX"] = to_weekly(series)
            print(f"    -> {len(extra['GDX'])} weekly bars")
    except Exception as e:
        print(f"    -> Failed: {e}")

    return extra


# =============================================================================
# PHASE 2: STRUCTURAL VARIANTS
# =============================================================================

def run_phase2(prepared_data, phase1_csv_path, extra_data, n_top=5):
    """Test structural modifications on top Phase 1 winners."""
    print("\n" + "=" * 70)
    print("PHASE 2: STRUCTURAL VARIANTS")
    print("=" * 70)

    # Load Phase 1 results
    phase1_df = pd.read_csv(phase1_csv_path)
    print(f"  Loaded {len(phase1_df)} Phase 1 results.")

    gld_weekly = prepared_data["gld_weekly"]
    ugl_weekly = prepared_data["ugl_weekly"]
    gld_daily = prepared_data["gld_daily"]

    # Get top N winners by Calmar
    top_n = phase1_df.sort_values("calmar", ascending=False).head(n_top)

    all_variant_results = []

    for idx, winner in top_n.iterrows():
        regime_period = int(winner["regime_period"])
        reentry_inst = winner["reentry_instrument"]
        reentry_per = int(winner["reentry_period"])
        stop_pct = float(winner["trailing_stop_pct"])

        base_label = f"R{regime_period}_{reentry_inst}_{reentry_per}_S{stop_pct:.0%}"
        print(f"\n  Testing variants on: {base_label}")
        print(f"    Base: CAGR={winner['cagr']:.1%}, MaxDD={winner['max_dd']:.1%}, "
              f"Sharpe={winner['sharpe']:.2f}, Calmar={winner['calmar']:.2f}")

        base_metrics = {
            "cagr": winner["cagr"], "max_dd": winner["max_dd"],
            "sharpe": winner["sharpe"], "calmar": winner["calmar"],
        }

        # --- Variant 1: EMA regime filter ---
        print("    [1/10] EMA regime filter...")
        v1 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type="weekly_ema")
        if v1:
            _add_variant(all_variant_results, "EMA_regime", base_label, v1, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 2: EMA re-entry signal ---
        print("    [2/10] EMA re-entry signal...")
        v2 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type="weekly_sma",
                      reentry_type="ema")
        if v2:
            _add_variant(all_variant_results, "EMA_reentry", base_label, v2, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 3: ATR-based trailing stop ---
        print("    [3/10] ATR-based trailing stops...")
        for mult in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
            v3 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                          stop_pct, reentry_inst, regime_type="weekly_sma",
                          stop_type="atr", stop_extra={"multiplier": mult})
            if v3:
                _add_variant(all_variant_results, f"ATR_stop_{mult}x", base_label, v3,
                             base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 4: Golden cross regime ---
        print("    [4/10] Golden cross regime...")
        v4 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type="golden_cross")
        if v4:
            _add_variant(all_variant_results, "golden_cross", base_label, v4, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 5: Partial exit ---
        print("    [5/10] Partial exit (50/50 with wider stop)...")
        v5 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                      stop_pct, reentry_inst, regime_type="weekly_sma",
                      partial_exit=True, partial_exit_params={"wider_stop": 0.15})
        if v5:
            _add_variant(all_variant_results, "partial_exit_15pct", base_label, v5, base_metrics,
                         regime_period, reentry_inst, reentry_per, stop_pct)

        # --- Variant 6: DXY filter (dollar weakening) ---
        if "DXY" in extra_data:
            print("    [6/10] DXY filter (enter only when dollar weakening)...")
            dxy_weekly = extra_data["DXY"]
            v6 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                          stop_pct, reentry_inst, regime_type="weekly_sma",
                          extra_filter="dxy_below_sma", extra_filter_data=dxy_weekly,
                          extra_filter_params={"period": 40})
            if v6:
                _add_variant(all_variant_results, "DXY_below_SMA40", base_label, v6,
                             base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)
        else:
            print("    [6/10] DXY filter — SKIPPED (no data)")

        # --- Variant 7: TIP filter (real rates proxy) ---
        if "TIP" in extra_data:
            print("    [7/10] TIP filter (enter only when TIP > SMA20)...")
            tip_weekly = extra_data["TIP"]
            v7 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                          stop_pct, reentry_inst, regime_type="weekly_sma",
                          extra_filter="tip_above_sma", extra_filter_data=tip_weekly,
                          extra_filter_params={"period": 20})
            if v7:
                _add_variant(all_variant_results, "TIP_above_SMA20", base_label, v7,
                             base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)
        else:
            print("    [7/10] TIP filter — SKIPPED (no data)")

        # --- Variant 8: GDX confirmation (gold miners lead gold) ---
        if "GDX" in extra_data:
            print("    [8/10] GDX confirmation (GDX > 10-week SMA)...")
            gdx_weekly = extra_data["GDX"]
            v8 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                          stop_pct, reentry_inst, regime_type="weekly_sma",
                          extra_filter="gdx_above_sma", extra_filter_data=gdx_weekly,
                          extra_filter_params={"period": 10})
            if v8:
                _add_variant(all_variant_results, "GDX_above_SMA10", base_label, v8,
                             base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)
        else:
            print("    [8/10] GDX filter — SKIPPED (no data)")

        # --- Variant 9: Inverse volatility filter ---
        if gld_daily is not None:
            print("    [9/10] Inverse volatility filter (GLD 20d vol < 252d vol)...")
            v9 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                          stop_pct, reentry_inst, regime_type="weekly_sma",
                          extra_filter="gld_low_vol", extra_filter_data=gld_daily)
            if v9:
                _add_variant(all_variant_results, "GLD_low_vol", base_label, v9,
                             base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)
        else:
            print("    [9/10] Vol filter — SKIPPED (no daily GLD data)")

        # --- Variant 10: UGL > SMA50 extra filter ---
        print("    [10/10] UGL > SMA50 extra filter...")
        v10 = backtest(gld_weekly, ugl_weekly, regime_period, reentry_per,
                       stop_pct, reentry_inst, regime_type="weekly_sma",
                       extra_filter="ugl_above_sma50")
        if v10:
            _add_variant(all_variant_results, "UGL_above_SMA50", base_label, v10,
                         base_metrics, regime_period, reentry_inst, reentry_per, stop_pct)

    variant_df = pd.DataFrame(all_variant_results)

    if len(variant_df) > 0:
        print(f"\n  Phase 2 complete: {len(variant_df)} variant tests run.")

        print(f"\n{'=' * 130}")
        print("PHASE 2 RESULTS (sorted by Calmar)")
        print(f"{'=' * 130}")
        print(f"{'Variant':<25} {'Base':<30} {'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} "
              f"{'Calmar':>7} {'TrShp':>6} {'TeShp':>6} {'TT_Shp':>7} "
              f"{'vs CAGR':>8} {'vs Calmar':>10}")
        print("-" * 130)

        for _, row in variant_df.sort_values("calmar", ascending=False).head(40).iterrows():
            print(f"{row['variant']:<25} {row['base_label']:<30} "
                  f"{row['cagr']:>6.1%} {row['max_dd']:>6.1%} {row['sharpe']:>7.2f} "
                  f"{row['calmar']:>7.2f} "
                  f"{row['train_sharpe']:>6.2f} {row['test_sharpe']:>6.2f} "
                  f"{row['train_test_sharpe_ratio']:>7.2f} "
                  f"{row['cagr_delta']:>+7.1%} {row['calmar_delta']:>+9.2f}")

        # Summarize which variants helped
        print(f"\n{'=' * 70}")
        print("VARIANT VERDICT SUMMARY")
        print(f"{'=' * 70}")

        variant_names = variant_df["variant"].str.replace(r"_\d+(\.\d+)?x$", "", regex=True).unique()
        for vname in sorted(set(variant_df["variant"].apply(lambda x: x.split("_")[0] if "ATR" not in x else "ATR_stop"))):
            subset = variant_df[variant_df["variant"].str.startswith(vname)]
            if len(subset) == 0:
                continue
            avg_calmar_delta = subset["calmar_delta"].mean()
            best_calmar_delta = subset["calmar_delta"].max()
            if avg_calmar_delta > 0.02:
                verdict = "HELPED"
            elif avg_calmar_delta < -0.02:
                verdict = "HURT"
            else:
                verdict = "NEUTRAL"
            print(f"  {vname:<25} Avg Calmar delta: {avg_calmar_delta:>+.3f}  "
                  f"Best: {best_calmar_delta:>+.3f}  -> {verdict}")

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
# DETERMINE FINAL WINNER
# =============================================================================

def determine_final_winner(phase1_csv_path, variant_df):
    """
    Compare Phase 1 winner to best variant. If a variant improves BOTH
    train and test metrics, adopt it. Otherwise stick with Phase 1 winner.
    """
    print("\n" + "=" * 70)
    print("DETERMINING FINAL WINNER")
    print("=" * 70)

    phase1_df = pd.read_csv(phase1_csv_path)
    p1_winner = phase1_df.sort_values("calmar", ascending=False).iloc[0]

    p1_params = {
        "regime_period": int(p1_winner["regime_period"]),
        "reentry_instrument": p1_winner["reentry_instrument"],
        "reentry_period": int(p1_winner["reentry_period"]),
        "trailing_stop_pct": float(p1_winner["trailing_stop_pct"]),
        "regime_type": "weekly_sma",
    }

    print(f"  Phase 1 winner: GLD {p1_params['regime_period']}w SMA | "
          f"{p1_params['reentry_instrument']} {p1_params['reentry_period']}w SMA | "
          f"Stop {p1_params['trailing_stop_pct']:.0%}")
    print(f"    Calmar={p1_winner['calmar']:.3f}, Sharpe={p1_winner['sharpe']:.3f}, "
          f"TrSharpe={p1_winner['train_sharpe']:.3f}, TeSharpe={p1_winner['test_sharpe']:.3f}")

    final_params = p1_params.copy()
    final_variant = None

    if len(variant_df) > 0:
        # Check if any variant beats Phase 1 winner on BOTH train and test Sharpe
        better = variant_df[
            (variant_df["train_sharpe"] > p1_winner["train_sharpe"]) &
            (variant_df["test_sharpe"] > p1_winner["test_sharpe"]) &
            (variant_df["calmar"] > p1_winner["calmar"])
        ]

        if len(better) > 0:
            best_variant = better.sort_values("calmar", ascending=False).iloc[0]
            print(f"\n  Better variant found: {best_variant['variant']}")
            print(f"    Calmar={best_variant['calmar']:.3f}, Sharpe={best_variant['sharpe']:.3f}, "
                  f"TrSharpe={best_variant['train_sharpe']:.3f}, TeSharpe={best_variant['test_sharpe']:.3f}")

            final_variant = best_variant["variant"]

            # Update params based on variant type
            if "EMA_regime" in final_variant:
                final_params["regime_type"] = "weekly_ema"
            elif "EMA_reentry" in final_variant:
                final_params["reentry_type"] = "ema"
            elif "golden_cross" in final_variant:
                final_params["regime_type"] = "golden_cross"
            # For filter-based variants, note in params
            if "DXY" in str(final_variant):
                final_params["extra_filter"] = "dxy_below_sma"
                final_params["extra_filter_period"] = 40
            elif "TIP" in str(final_variant):
                final_params["extra_filter"] = "tip_above_sma"
                final_params["extra_filter_period"] = 20
            elif "GDX" in str(final_variant):
                final_params["extra_filter"] = "gdx_above_sma"
                final_params["extra_filter_period"] = 10
            elif "low_vol" in str(final_variant):
                final_params["extra_filter"] = "gld_low_vol"
            elif "SMA50" in str(final_variant):
                final_params["extra_filter"] = "ugl_above_sma50"
        else:
            print("\n  No variant beats Phase 1 winner on both train AND test metrics.")
            print("  Sticking with Phase 1 winner.")
    else:
        print("  No variant results to compare.")

    # Save final winner params
    winner_path = os.path.join(DATA_DIR, "ugl_winner_params.json")
    with open(winner_path, "w") as f:
        json.dump(final_params, f, indent=2)
    print(f"\n  Final winner params saved to: {winner_path}")
    print(f"  Final params: {json.dumps(final_params, indent=2)}")

    return final_params, final_variant


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "#" * 70)
    print("#  TRIPLEEDGE UGL - PHASE 2: STRUCTURAL VARIANTS")
    print("#" * 70)

    # Check for Phase 1 results
    csv_path = os.path.join(DATA_DIR, "ugl_results.csv")
    if not os.path.exists(csv_path):
        print(f"  ERROR: {csv_path} not found. Run ugl_optimizer.py first.")
        sys.exit(1)

    # Download main data
    data = download_data()
    prepared = prepare_data(data)

    # Download extra data for gold-specific filters
    extra = download_extra_data()

    # Run Phase 2
    variant_df = run_phase2(prepared, csv_path, extra)

    # Save variant results
    if len(variant_df) > 0:
        variant_csv = os.path.join(DATA_DIR, "ugl_variant_results.csv")
        variant_df.to_csv(variant_csv, index=False)
        print(f"\n  Phase 2 results saved to: {variant_csv}")

    # Determine final winner
    final_params, final_variant = determine_final_winner(csv_path, variant_df)

    print("\n" + "#" * 70)
    print("#  PHASE 2 COMPLETE")
    print("#  Run ugl_final_validation.py for Phase 3.")
    print("#" * 70)

    return variant_df, final_params


if __name__ == "__main__":
    main()
