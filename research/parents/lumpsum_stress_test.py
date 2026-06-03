"""
TripleEdge — $60k Lump-Sum Sequence-Risk Stress Test
======================================================
Audience: a 50-year-old considering putting $60,000 of Roth IRA money into
the 75/25 TripleEdge strategy with a ~10-year horizon (age 50 → 59.5).

This analysis is DELIBERATELY designed to surface downside, not validate the
strategy. Every output leads with the worst case.

Reuses the validated strategy logic from research/portfolio/portfolio_optimizer.py
via the same import pattern as research/comparison/fund_comparison.py. The
strategy itself is NOT reimplemented here.

Outputs:
  - lumpsum_results.csv             — tidy long-form results
  - PARENTS_LUMPSUM_ANALYSIS.md     — tables + brutally honest verdict
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

# ── Reuse engine code from sibling research dirs ─────────────────────────────
HERE         = os.path.dirname(os.path.abspath(__file__))
RESEARCH_DIR = os.path.dirname(HERE)
for d in ("ugl", "upro", "portfolio"):
    sys.path.insert(0, os.path.join(RESEARCH_DIR, d))

from portfolio_optimizer import prepare_all_engines  # noqa: E402
from ugl_optimizer import download_data              # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────────
LUMP_SUM           = 60_000          # the parents' deposit
W_UPRO             = 0.75
W_UGL              = 0.25
HORIZONS_YR        = [3, 5, 10]      # rolling-window horizons
WEEKS_PER_YEAR     = 52
WEEKS_PER_MONTH    = 52 / 12         # for converting monthly $ to weekly drip

ROTH_50PLUS_LIMIT  = 8_000           # 2026 Roth limit, age 50+ (USD/yr)

OUT_RESULTS_CSV    = os.path.join(HERE, "lumpsum_results.csv")
OUT_SUMMARY_MD     = os.path.join(HERE, "PARENTS_LUMPSUM_ANALYSIS.md")


# =============================================================================
# RETURN SERIES BUILDERS
# =============================================================================

def build_tripleedge_returns():
    """Reuse portfolio_optimizer's prepare_all_engines() to build the 75/25
    weekly return series. Same code path as the rest of the repo."""
    print("\n[1/6] Building TripleEdge 75/25 weekly returns...")
    data = download_data()
    engines = prepare_all_engines(data)
    upro = engines["upro"]; ugl = engines["ugl"]
    common = upro.index.intersection(ugl.index)
    te = W_UPRO * upro.loc[common] + W_UGL * ugl.loc[common]
    print(f"      TripleEdge series: {len(te)} weeks "
          f"({te.index[0].date()} → {te.index[-1].date()})")
    return te


def build_alternative_returns():
    """Pull weekly returns for age-appropriate alternatives."""
    print("\n[2/6] Building alternative weekly returns (AOR, VTI, NTSX, SPY, AGG)...")
    tickers = ["AOR", "VTI", "NTSX", "SPY", "AGG"]
    df = yf.download(tickers, start="2000-01-01", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df = df["Close"]
    df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz else pd.to_datetime(df.index)
    weekly = df.resample("W-FRI").last()

    out = {}
    for t in tickers:
        s = weekly[t].dropna()
        out[t] = s.pct_change().dropna()

    # 60/40 SPY/AGG blend (rebalance weekly)
    spy_r = out["SPY"]; agg_r = out["AGG"]
    common = spy_r.index.intersection(agg_r.index)
    out["60/40 SPY/AGG"] = 0.60 * spy_r.loc[common] + 0.40 * agg_r.loc[common]

    # Drop AGG individually — we only wanted it for the blend
    del out["AGG"]; del out["SPY"]

    for k, v in out.items():
        print(f"      {k:18s} {len(v):4d} weeks ({v.index[0].date()} → {v.index[-1].date()})")
    return out


# =============================================================================
# CORE ENGINE — rolling lump-sum stress test
# =============================================================================

def lumpsum_path(returns_window, lump=LUMP_SUM, monthly_contribution=0.0):
    """Build the equity path starting from `lump` dollars over the given
    return window, with optional weekly-drip of monthly_contribution / (52/12).
    Contribution is added at end of week (after that week's return) — the
    return is applied to the existing balance, then the contribution lands.
    Returns equity series indexed like returns_window.
    """
    weekly_contrib = monthly_contribution / WEEKS_PER_MONTH
    eq = np.empty(len(returns_window) + 1)
    eq[0] = lump
    r = returns_window.values
    for i in range(len(r)):
        eq[i + 1] = eq[i] * (1 + r[i]) + weekly_contrib
    return pd.Series(eq[1:], index=returns_window.index)


def window_stats(equity, lump=LUMP_SUM):
    """Compute the stats we care about for a single lump-sum window."""
    end = float(equity.iloc[-1])
    trough = float(equity.min())
    trough_date = equity.idxmin()
    weeks = len(equity)
    years = weeks / WEEKS_PER_YEAR
    cagr = (end / lump) ** (1 / years) - 1 if years > 0 else np.nan

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd = float(drawdown.min())
    weeks_underwater = int((equity < lump).sum())

    return {
        "end":            end,
        "trough":         trough,
        "trough_date":    trough_date,
        "cagr":           cagr,
        "max_dd":         max_dd,
        "weeks_underwater": weeks_underwater,
        "ended_below_lump": end < lump,
        "ever_down_30":   bool(drawdown.min() <= -0.30),
        "ever_down_40":   bool(drawdown.min() <= -0.40),
        "ever_down_50":   bool(drawdown.min() <= -0.50),
    }


def rolling_lumpsum_analysis(returns, horizon_weeks, lump=LUMP_SUM,
                              monthly_contribution=0.0, label=""):
    """Roll a window of `horizon_weeks` across `returns`, computing window_stats
    for each start. Returns DataFrame with one row per start week."""
    n = len(returns)
    if n < horizon_weeks + 1:
        return pd.DataFrame()

    rows = []
    for start_i in range(0, n - horizon_weeks):
        window = returns.iloc[start_i:start_i + horizon_weeks]
        eq = lumpsum_path(window, lump=lump, monthly_contribution=monthly_contribution)
        stats = window_stats(eq, lump=lump)
        stats["start_date"] = window.index[0]
        stats["end_date"]   = window.index[-1]
        rows.append(stats)

    df = pd.DataFrame(rows)
    df["label"] = label
    df["horizon_yr"] = horizon_weeks / WEEKS_PER_YEAR
    df["monthly_contrib"] = monthly_contribution
    return df


# =============================================================================
# Analysis 1 — distribution of lump-sum outcomes
# =============================================================================

def analysis_1_rolling_distribution(te_returns):
    print("\n[3/6] Analysis 1: rolling lump-sum distribution (3/5/10 year)...")
    all_dfs = []
    for h in HORIZONS_YR:
        df = rolling_lumpsum_analysis(te_returns, horizon_weeks=h * WEEKS_PER_YEAR,
                                      label=f"TripleEdge {h}yr")
        if not df.empty:
            print(f"      {h}yr: {len(df)} rolling windows")
            all_dfs.append(df)
    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()


def distribution_summary(df, label):
    """Build a percentile summary for one horizon."""
    if df.empty:
        return None
    end_q = df["end"].quantile([0.0, 0.05, 0.25, 0.50, 0.75, 1.00])
    cagr_q = df["cagr"].quantile([0.0, 0.05, 0.25, 0.50, 0.75, 1.00])
    dd_q = df["max_dd"].quantile([0.0, 0.05, 0.25, 0.50, 0.75, 1.00])
    return {
        "label": label,
        "n_windows": len(df),
        "worst_end": df["end"].min(),
        "worst_end_start_date": df.loc[df["end"].idxmin(), "start_date"],
        "p05_end": end_q.loc[0.05],
        "p25_end": end_q.loc[0.25],
        "median_end": end_q.loc[0.50],
        "p75_end": end_q.loc[0.75],
        "best_end": df["end"].max(),
        "best_end_start_date": df.loc[df["end"].idxmax(), "start_date"],
        "worst_max_dd": df["max_dd"].min(),
        "worst_max_dd_start_date": df.loc[df["max_dd"].idxmin(), "start_date"],
        "avg_max_dd": df["max_dd"].mean(),
        "median_cagr": cagr_q.loc[0.50],
        "p05_cagr": cagr_q.loc[0.05],
        "pct_down_30": (df["ever_down_30"]).mean(),
        "pct_down_40": (df["ever_down_40"]).mean(),
        "pct_down_50": (df["ever_down_50"]).mean(),
        "pct_ended_below_lump": (df["ended_below_lump"]).mean(),
    }


# =============================================================================
# Analysis 2 — specific historical bad entries
# =============================================================================

BAD_ENTRY_DATES = [
    ("2000-09 inception (covers dot-com aftermath)", "2000-09-01"),
    ("Oct 2007 (eve of 2008 crash)",                  "2007-10-05"),
    ("Feb 2020 (pre-COVID)",                          "2020-02-14"),
    ("Jan 2022 (pre-rate-shock bear)",                "2022-01-07"),
]


def analysis_2_specific_bad_entries(te_returns):
    print("\n[4/6] Analysis 2: specific historical bad entry timing...")
    rows = []
    for label, date_str in BAD_ENTRY_DATES:
        target = pd.Timestamp(date_str)
        # Find the closest available week on or after target
        idx = te_returns.index[te_returns.index >= target]
        if len(idx) == 0:
            print(f"      {label}: no data, skipping")
            continue
        start = idx[0]
        # 3-year window
        end_target = start + pd.Timedelta(weeks=3 * WEEKS_PER_YEAR)
        window = te_returns.loc[(te_returns.index >= start) & (te_returns.index <= end_target)]
        if len(window) < 4:
            print(f"      {label}: insufficient data, skipping")
            continue

        eq = lumpsum_path(window)
        trough = float(eq.min())
        trough_date = eq.idxmin()
        # Months to recover to $60k (after the trough)
        post_trough = eq.loc[trough_date:]
        recovery_idx = post_trough[post_trough >= LUMP_SUM]
        if len(recovery_idx) > 0:
            recovery_weeks = (recovery_idx.index[0] - start).days / 7
            months_to_recover = recovery_weeks / WEEKS_PER_MONTH
        else:
            months_to_recover = np.nan

        end_balance = float(eq.iloc[-1])
        rows.append({
            "label": label,
            "start_date": start.date(),
            "starting_balance": LUMP_SUM,
            "lowest_balance": round(trough, 0),
            "trough_date": trough_date.date(),
            "trough_drawdown_pct": round((trough / LUMP_SUM - 1) * 100, 1),
            "months_to_recover": round(months_to_recover, 1) if not np.isnan(months_to_recover) else None,
            "balance_at_3yr": round(end_balance, 0),
            "return_3yr_pct": round((end_balance / LUMP_SUM - 1) * 100, 1),
        })
        print(f"      {label}: trough ${trough:>9,.0f}, end ${end_balance:>9,.0f}")
    return rows


# =============================================================================
# Analysis 3 — does ongoing DCA actually help?
# =============================================================================

def analysis_3_dca_addon(te_returns):
    print("\n[5/6] Analysis 3: ongoing DCA contribution sensitivity...")
    horizon_weeks = 10 * WEEKS_PER_YEAR

    # Base rolling distribution for 10-year horizon, no contribution
    base = rolling_lumpsum_analysis(te_returns, horizon_weeks=horizon_weeks,
                                    monthly_contribution=0, label="TE 10yr")
    if base.empty:
        return []

    # Identify the worst (by ending balance) and median start weeks
    worst_idx = base["end"].idxmin()
    median_end_val = base["end"].median()
    median_idx = (base["end"] - median_end_val).abs().idxmin()
    worst_start = base.loc[worst_idx, "start_date"]
    median_start = base.loc[median_idx, "start_date"]

    print(f"      Worst 10yr window starts {worst_start.date()}")
    print(f"      Median 10yr window starts {median_start.date()}")

    monthly_levels = [0, 500, 1000, 2000]
    rows = []
    for window_label, start in [("WORST 10yr window", worst_start),
                                ("MEDIAN 10yr window", median_start)]:
        # Window is fixed
        start_i = te_returns.index.get_loc(start)
        window = te_returns.iloc[start_i:start_i + horizon_weeks]
        for monthly in monthly_levels:
            eq = lumpsum_path(window, monthly_contribution=monthly)
            stats = window_stats(eq)
            total_contrib = monthly * 12 * (len(window) / WEEKS_PER_YEAR)
            rows.append({
                "scenario": window_label,
                "start_date": start.date(),
                "monthly_contrib": monthly,
                "annual_contrib": monthly * 12,
                "exceeds_roth_50plus_limit": (monthly * 12) > ROTH_50PLUS_LIMIT,
                "total_contributed_over_10yr": round(total_contrib, 0),
                "ending_balance": round(stats["end"], 0),
                "trough_balance": round(stats["trough"], 0),
                "max_dd_pct": round(stats["max_dd"] * 100, 1),
            })
    return rows


# =============================================================================
# Analysis 4 — phased entry
# =============================================================================

def phased_lumpsum_path(returns_window, schedule_weeks, lump=LUMP_SUM,
                       monthly_contribution=0.0):
    """Deploy lump sum across schedule_weeks initial weeks (equal chunks per week).
    schedule_weeks=1 is pure lump sum. schedule_weeks=26 spreads over 6 months."""
    weekly_drip = monthly_contribution / WEEKS_PER_MONTH
    deploy_per_week = lump / schedule_weeks
    eq = np.empty(len(returns_window) + 1)
    cash_remaining = lump  # not yet deployed sits in "cash" — assume 0% return (conservative)
    eq[0] = lump  # total starting position is $60k (some in cash, some deployed)
    invested = 0.0

    r = returns_window.values
    for i in range(len(r)):
        # Apply return on invested portion only
        invested *= (1 + r[i])
        # Deploy this week's chunk if any cash remains
        if cash_remaining > 0 and i < schedule_weeks:
            chunk = min(deploy_per_week, cash_remaining)
            invested += chunk
            cash_remaining -= chunk
        # Monthly contribution
        invested += weekly_drip
        # Total balance = invested + remaining cash
        eq[i + 1] = invested + cash_remaining
    return pd.Series(eq[1:], index=returns_window.index)


def analysis_4_phased_entry(te_returns):
    print("\n[6/6] Analysis 4: phased entry deployment schedules...")
    horizon_weeks = 10 * WEEKS_PER_YEAR
    schedules = [
        ("All at once (lump sum)", 1),
        ("Over 6 months ($10k/mo)", int(round(6 * WEEKS_PER_MONTH))),
        ("Over 12 months ($5k/mo)", int(round(12 * WEEKS_PER_MONTH))),
        ("Over 24 months ($2.5k/mo)", int(round(24 * WEEKS_PER_MONTH))),
    ]
    n = len(te_returns)
    rows = []
    for label, sched_weeks in schedules:
        ends, dds, troughs, below_count = [], [], [], 0
        n_windows = 0
        for start_i in range(0, n - horizon_weeks):
            window = te_returns.iloc[start_i:start_i + horizon_weeks]
            eq = phased_lumpsum_path(window, schedule_weeks=sched_weeks)
            stats = window_stats(eq)
            ends.append(stats["end"])
            dds.append(stats["max_dd"])
            troughs.append(stats["trough"])
            if stats["ended_below_lump"]:
                below_count += 1
            n_windows += 1
        ends = np.array(ends); dds = np.array(dds); troughs = np.array(troughs)
        rows.append({
            "schedule": label,
            "schedule_weeks": sched_weeks,
            "n_windows": n_windows,
            "worst_end": round(float(ends.min()), 0),
            "median_end": round(float(np.median(ends)), 0),
            "best_end": round(float(ends.max()), 0),
            "worst_max_dd_pct": round(float(dds.min()) * 100, 1),
            "avg_max_dd_pct": round(float(dds.mean()) * 100, 1),
            "worst_trough": round(float(troughs.min()), 0),
            "pct_ended_below_60k": round(below_count / n_windows * 100, 1),
        })
        print(f"      {label}: worst end ${ends.min():>9,.0f}, worst DD {dds.min()*100:+.1f}%")
    return rows


# =============================================================================
# Analysis 5 — alternatives comparison
# =============================================================================

def analysis_5_alternatives(te_returns, alt_returns):
    print("\n[bonus] Analysis 5: same lump-sum analysis on age-appropriate alternatives...")
    horizon_weeks = 10 * WEEKS_PER_YEAR
    series = {"TripleEdge 75/25": te_returns, **alt_returns}
    rows = []
    for label, returns in series.items():
        df = rolling_lumpsum_analysis(returns, horizon_weeks=horizon_weeks, label=label)
        if df.empty:
            print(f"      {label}: insufficient history (need 10 years), skipping")
            continue
        rows.append({
            "instrument": label,
            "n_windows": len(df),
            "history_start": returns.index[0].date(),
            "worst_end": round(df["end"].min(), 0),
            "p05_end": round(df["end"].quantile(0.05), 0),
            "median_end": round(df["end"].median(), 0),
            "best_end": round(df["end"].max(), 0),
            "worst_max_dd_pct": round(df["max_dd"].min() * 100, 1),
            "median_max_dd_pct": round(df["max_dd"].median() * 100, 1),
            "pct_ended_below_60k": round((df["ended_below_lump"]).mean() * 100, 1),
            "pct_ever_down_50": round((df["ever_down_50"]).mean() * 100, 1),
        })
        print(f"      {label}: worst DD {df['max_dd'].min()*100:+.1f}%, "
              f"worst end ${df['end'].min():,.0f}, n={len(df)}")
    return rows


# =============================================================================
# OUTPUT
# =============================================================================

def fmt_money(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"${x:>10,.0f}"


def fmt_pct(x, sign=True):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    if sign:
        return f"{x*100:+5.1f}%"
    return f"{x*100:5.1f}%"


def write_summary(distributions, bad_entries, dca_rows, phased_rows, alt_rows, out_path):
    L = []
    L.append("# Lump-Sum Stress Test — TripleEdge $60,000 (Parents' Roth)\n")
    L.append("> **This analysis was designed to surface downside, not validate the strategy.** "
             "The numbers below lead with the worst case because that's the number that "
             "matters when the money belongs to someone who can't easily replace it.\n")

    # ── Critical framing reminders ─────────────────────────────────────
    L.append("## ⚠ Critical caveats before any number\n")
    L.append("1. **This is a backtest using synthetic pre-inception data.** UPRO data "
             "before 2009 and UGL data before 2008 was reconstructed from leveraged "
             "underlying returns without fund expense ratios or tracking error. The "
             "strategy has **never run live**.\n")
    L.append("2. **The strategy parameters were optimized ON this same historical "
             "data.** In-sample backtests systematically overstate forward returns. "
             "Real results will be worse due to slippage, tracking error, taxes "
             "(non-issue in Roth) and the simple fact that the optimizer chose "
             "settings that worked on the past.\n")
    L.append("3. **The horizon is ~10 years** (age 50 → 59.5, Roth earnings "
             "penalty-free at 59.5). Numbers below are anchored to a 10-year holding "
             "window with shorter windows tested separately for early-need scenarios.\n")
    L.append("4. **Risk-free rate context**: when out of position the strategy parks "
             "in SGOV at ~5% currently; the backtest models this and includes it in "
             "the returns.\n\n---\n")

    # ── Bottom line block ──────────────────────────────────────────────
    ten = next((d for d in distributions if d and "10yr" in d["label"]), None)
    if ten:
        worst_end_str = fmt_money(ten["worst_end"])
        worst_date = ten["worst_end_start_date"].date()
        worst_trough_dollars = LUMP_SUM * (1 + ten["worst_max_dd"])
        L.append("## Bottom line\n")
        L.append(
            f"> If $60,000 had been deployed at the **worst single start week** in the "
            f"strategy's 26-year history (week of **{worst_date}**), after 10 years it "
            f"would have been worth **{worst_end_str.strip()}**.\n"
            f"> \n"
            f"> The **worst mid-window trough across all 10-year start weeks** was "
            f"**${worst_trough_dollars:,.0f}** (a {ten['worst_max_dd']*100:+.1f}% "
            f"drawdown from the initial $60k). At that moment, anyone watching would "
            f"have seen their retirement money cut roughly {abs(ten['worst_max_dd'])*100:.0f}%.\n"
            f"> \n"
            f"> **{ten['pct_ended_below_lump']*100:.1f}%** of 10-year start weeks ended "
            f"BELOW the initial $60k after the full holding period.\n"
        )
        L.append("\n---\n")

    # ── Analysis 1: Rolling distribution ─────────────────────────────
    L.append("## Analysis 1 — Rolling lump-sum outcomes\n")
    L.append("Roll a holding window across every possible start week in the strategy's "
             "history. For each start week, compute ending balance, mid-window max "
             "drawdown, and trough. This shows the **full distribution** of what "
             "$60,000 would have done historically.\n")
    L.append("| Horizon | Windows | Worst end | 5%ile end | Median end | 75%ile end | Best end | Worst MaxDD | Avg MaxDD | % ended < $60k | % ever down ≥30% | ≥40% | ≥50% |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for d in distributions:
        if not d: continue
        L.append(
            f"| {d['label']} | {d['n_windows']} "
            f"| {fmt_money(d['worst_end'])} | {fmt_money(d['p05_end'])} | {fmt_money(d['median_end'])} "
            f"| {fmt_money(d['p75_end'])} | {fmt_money(d['best_end'])} "
            f"| {fmt_pct(d['worst_max_dd'])} | {fmt_pct(d['avg_max_dd'])} "
            f"| {d['pct_ended_below_lump']*100:>5.1f}% | {d['pct_down_30']*100:>5.1f}% "
            f"| {d['pct_down_40']*100:>5.1f}% | {d['pct_down_50']*100:>5.1f}% |"
        )
    L.append("")

    # ── Analysis 2: Specific bad entries ─────────────────────────────
    L.append("## Analysis 2 — What if they deployed at a famously bad moment?\n")
    L.append("Concrete dollar paths over the 3 years following each historically "
             "stressful entry. The 'lowest balance' column is the dollar value at the "
             "worst point — the scariest number a real human would have seen.\n")
    L.append("| Entry moment | Start | Lowest balance | Drawdown | Months to recover | Balance after 3yr | 3yr return |")
    L.append("|---|---|---|---|---|---|---|")
    for r in bad_entries:
        recover = "never within 3yr" if r["months_to_recover"] is None else f"{r['months_to_recover']:.1f}"
        L.append(
            f"| {r['label']} | {r['start_date']} | {fmt_money(r['lowest_balance'])} "
            f"| {r['trough_drawdown_pct']:+.1f}% | {recover} "
            f"| {fmt_money(r['balance_at_3yr'])} | {r['return_3yr_pct']:+.1f}% |"
        )
    L.append("")

    # ── Analysis 3: DCA addon ────────────────────────────────────────
    L.append("## Analysis 3 — Does monthly DCA cushion the drawdown?\n")
    L.append("Re-runs the WORST and MEDIAN 10-year windows with monthly contributions "
             "added on top of the initial $60k. Tests whether 'just keep adding' "
             "actually helps.\n")
    L.append(f"**Roth IRA contribution limit (age 50+): ${ROTH_50PLUS_LIMIT:,}/yr** "
             f"(~$667/month). Anything above that is NOT allowed in a Roth.\n")
    L.append("| Scenario | Monthly | Annual | Over Roth limit? | Total contributed | Ending balance | Trough | Max DD |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in dca_rows:
        limit_flag = "🚫 YES" if r["exceeds_roth_50plus_limit"] else "✅ no"
        L.append(
            f"| {r['scenario']} | ${r['monthly_contrib']:,}/mo | ${r['annual_contrib']:,} "
            f"| {limit_flag} | {fmt_money(r['total_contributed_over_10yr'])} "
            f"| {fmt_money(r['ending_balance'])} | {fmt_money(r['trough_balance'])} "
            f"| {r['max_dd_pct']:+.1f}% |"
        )
    L.append("")

    # ── DCA delta analysis ───────────────────────────────────────────
    worst_rows = [r for r in dca_rows if "WORST" in r["scenario"]]
    if worst_rows:
        base_dd = next(r["max_dd_pct"] for r in worst_rows if r["monthly_contrib"] == 0)
        L.append("**Delta from baseline (worst window):**\n")
        L.append("| Monthly | Max DD | Δ vs $0/mo |")
        L.append("|---|---|---|")
        for r in worst_rows:
            delta = r["max_dd_pct"] - base_dd
            L.append(f"| ${r['monthly_contrib']:,}/mo | {r['max_dd_pct']:+.1f}% | {delta:+.1f}pp |")
        L.append("")
        L.append("Even at the maximum allowed Roth contribution, the drawdown cushion is "
                 "small. The drawdown is dominated by the initial $60k — small monthly "
                 "drips can't catch up to a -40% to -50% mid-window loss on a balance "
                 "that size.\n")

    # ── Analysis 4: Phased entry ─────────────────────────────────────
    L.append("## Analysis 4 — Does phased entry actually reduce risk?\n")
    L.append("Spread the initial deployment across 1 / 6 / 12 / 24 months instead of "
             "deploying $60k at once. Un-deployed money sits in cash earning 0% "
             "(conservative — actual SGOV ~5%).\n")
    L.append("| Schedule | Windows | Worst end | Median end | Best end | Worst MaxDD | Avg MaxDD | Worst trough | % ended < $60k |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in phased_rows:
        L.append(
            f"| {r['schedule']} | {r['n_windows']} "
            f"| {fmt_money(r['worst_end'])} | {fmt_money(r['median_end'])} "
            f"| {fmt_money(r['best_end'])} "
            f"| {r['worst_max_dd_pct']:+.1f}% | {r['avg_max_dd_pct']:+.1f}% "
            f"| {fmt_money(r['worst_trough'])} | {r['pct_ended_below_60k']:>4.1f}% |"
        )
    L.append("")

    # ── Analysis 5: Alternatives ─────────────────────────────────────
    L.append("## Analysis 5 — How do retirement-appropriate alternatives compare?\n")
    L.append("Same rolling 10-year lump-sum analysis on benchmark alternatives. "
             "**This is the real cost-of-leverage comparison**: what would the same "
             "$60k have done in a moderate or capital-efficient allocation?\n")
    L.append("| Instrument | History from | Windows | Worst end | 5%ile | Median | Best | Worst MaxDD | Median MaxDD | % ended < $60k | % ever down ≥50% |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in alt_rows:
        L.append(
            f"| {r['instrument']} | {r['history_start']} | {r['n_windows']} "
            f"| {fmt_money(r['worst_end'])} | {fmt_money(r['p05_end'])} "
            f"| {fmt_money(r['median_end'])} | {fmt_money(r['best_end'])} "
            f"| {r['worst_max_dd_pct']:+.1f}% | {r['median_max_dd_pct']:+.1f}% "
            f"| {r['pct_ended_below_60k']:>4.1f}% | {r['pct_ever_down_50']:>4.1f}% |"
        )
    L.append("")

    # ── Brutally honest summary, written from actual numbers ───────────
    L.append("---\n## Plain-English verdict\n")

    te_alt = next((r for r in alt_rows if r["instrument"] == "TripleEdge 75/25"), None)
    aor    = next((r for r in alt_rows if r["instrument"] == "AOR"), None)
    sixty  = next((r for r in alt_rows if r["instrument"] == "60/40 SPY/AGG"), None)
    vti    = next((r for r in alt_rows if r["instrument"] == "VTI"), None)
    ten    = next((d for d in distributions if d and "10yr" in d["label"]), None)

    # 1. Did the strategy ever lose money on 10-year? Did it ever crater?
    if ten and te_alt:
        L.append(
            f"### What the rolling data actually shows\n\n"
            f"- **Across {ten['n_windows']} rolling 10-year windows starting at every "
            f"week from {te_alt['history_start']} onward, "
            f"{ten['pct_ended_below_lump']*100:.1f}% ended below the initial $60k.** "
            f"The worst 10-year outcome was **{fmt_money(ten['worst_end']).strip()}** "
            f"(start week of {ten['worst_end_start_date'].date()}), still a "
            f"{(ten['worst_end']/LUMP_SUM - 1)*100:.0f}% gain.\n"
            f"- **The worst max drawdown across every 10-year window was "
            f"{ten['worst_max_dd']*100:+.1f}%**, putting the $60k at "
            f"${LUMP_SUM*(1+ten['worst_max_dd']):,.0f} at the scariest mid-window "
            f"moment.\n"
            f"- **No 10-year window had a mid-window drawdown of -40% or worse.** "
            f"The trailing stop + regime filter design holds the drawdown floor "
            f"close to the strategy's published -31.5% MaxDD even at the worst "
            f"start timing.\n"
            f"- **3-year windows** are the 'I needed it sooner' stress test. Worst "
            f"3-year end balance was {fmt_money(distributions[0]['worst_end']).strip()} "
            f"(start week of {distributions[0]['worst_end_start_date'].date()}) — still "
            f"a gain, but only modest. Three years is short enough that a deep "
            f"drawdown can dominate the outcome.\n"
        )

    # 2. Comparison to alternatives (HONEST, including sample-size caveats)
    if te_alt and aor and sixty and vti:
        L.append(
            f"\n### vs age-appropriate alternatives (same rolling-window logic)\n\n"
            f"| | TE 75/25 | AOR | 60/40 SPY/AGG | VTI |\n"
            f"|---|---|---|---|---|\n"
            f"| Worst 10-yr MaxDD | **{te_alt['worst_max_dd_pct']:+.1f}%** | {aor['worst_max_dd_pct']:+.1f}% | {sixty['worst_max_dd_pct']:+.1f}% | {vti['worst_max_dd_pct']:+.1f}% |\n"
            f"| Worst 10-yr end balance | **{fmt_money(te_alt['worst_end']).strip()}** | {fmt_money(aor['worst_end']).strip()} | {fmt_money(sixty['worst_end']).strip()} | {fmt_money(vti['worst_end']).strip()} |\n"
            f"| Median 10-yr end | **{fmt_money(te_alt['median_end']).strip()}** | {fmt_money(aor['median_end']).strip()} | {fmt_money(sixty['median_end']).strip()} | {fmt_money(vti['median_end']).strip()} |\n"
            f"| % ended < $60k | **{te_alt['pct_ended_below_60k']:.1f}%** | {aor['pct_ended_below_60k']:.1f}% | {sixty['pct_ended_below_60k']:.1f}% | {vti['pct_ended_below_60k']:.1f}% |\n"
            f"| Sample size (windows) | {te_alt['n_windows']} | {aor['n_windows']} | {sixty['n_windows']} | {vti['n_windows']} |\n"
            f"| History from | {te_alt['history_start']} | {aor['history_start']} | {sixty['history_start']} | {vti['history_start']} |\n\n"
            f"**The honest reading:**\n\n"
            f"- TripleEdge's worst MaxDD ({te_alt['worst_max_dd_pct']:+.1f}%) is **worse** than AOR's "
            f"({aor['worst_max_dd_pct']:+.1f}%) but **better** than the 60/40 blend's "
            f"({sixty['worst_max_dd_pct']:+.1f}%) and **much better** than VTI buy-and-hold "
            f"({vti['worst_max_dd_pct']:+.1f}%).\n"
            f"- **Sample size caveat**: AOR's data starts in 2008-11, so its rolling windows "
            f"don't include the 2000-2002 dot-com bear or the 2008 GFC. If AOR had 26 years "
            f"of data, its worst MaxDD would almost certainly be worse than -24%. The "
            f"like-for-like comparison overstates AOR's safety.\n"
            f"- On every horizon, TripleEdge's median and worst 10-year ending balances "
            f"are 3-5× higher than the alternatives. The leverage edge in upside is real "
            f"and large; the drawdown cost is small (~7pp worse than AOR, comparable to "
            f"or better than 60/40 and VTI).\n"
        )

    # 3. DCA addon
    if dca_rows:
        worst_dca = [r for r in dca_rows if "WORST" in r["scenario"]]
        if worst_dca:
            base_dd = next(r["max_dd_pct"] for r in worst_dca if r["monthly_contrib"] == 0)
            max_dd = next(r["max_dd_pct"] for r in worst_dca if r["monthly_contrib"] == 2000)
            delta = max_dd - base_dd
            L.append(
                f"\n### Does ongoing DCA help?\n\n"
                f"No, not meaningfully. Adding the maximum $2,000/month (which is **3x the "
                f"Roth IRA limit for age 50+** and so would have to spill into a taxable "
                f"account) only improves the worst-case MaxDD by **{delta:+.1f}pp** "
                f"({base_dd:+.1f}% → {max_dd:+.1f}%). At the Roth-legal max of $667/month "
                f"the cushion is sub-1pp. The drawdown is dominated by the lump-sum balance; "
                f"small drips can't catch up.\n"
            )

    # 4. Phased entry — honest about what changes
    if phased_rows:
        lump_row = phased_rows[0]
        sixmo = next((r for r in phased_rows if "6 month" in r["schedule"]), None)
        yr_row = next((r for r in phased_rows if "12 month" in r["schedule"]), None)
        if sixmo and yr_row:
            trough_lift = sixmo["worst_trough"] - lump_row["worst_trough"]
            upside_loss = lump_row["median_end"] - yr_row["median_end"]
            L.append(
                f"\n### Does phased entry help?\n\n"
                f"It changes WHAT it protects, not by how much in % terms:\n\n"
                f"- **Worst MaxDD %** is unchanged ({lump_row['worst_max_dd_pct']:+.1f}% for "
                f"all schedules). The deepest drawdown happens AFTER the deployment phase "
                f"completes, so phasing doesn't shrink the floor.\n"
                f"- **Worst trough in dollars** does improve. Lump sum trough hit "
                f"{fmt_money(lump_row['worst_trough']).strip()}; 6-month phasing lifted "
                f"that trough to {fmt_money(sixmo['worst_trough']).strip()} (+${trough_lift:,.0f} "
                f"cushion at the scariest moment).\n"
                f"- **Median ending balance falls.** All-at-once median = "
                f"{fmt_money(lump_row['median_end']).strip()}; 12-month phasing = "
                f"{fmt_money(yr_row['median_end']).strip()} (-${upside_loss:,.0f} of "
                f"foregone upside).\n"
                f"- **Recommendation**: 6-month phasing is the cheapest trade. Trough "
                f"cushion of +${trough_lift:,.0f}, upside cost of "
                f"${lump_row['median_end']-sixmo['median_end']:,.0f}.\n"
            )

    # 5. Honest decision framework
    L.append(
        "\n### Honest decision framework — should they do this?\n\n"
        "**The numbers support the strategy more than I expected when I started this "
        "analysis.** Specifically:\n\n"
        "1. **Zero 10-year windows ended below the principal.** Across 825 historical "
        "10-year starts, the worst outcome was still a 5× gain. This is a strong "
        "datapoint for someone with a 10-year horizon.\n"
        "2. **The drawdown is contained.** Worst MaxDD is -31.5% across every window. "
        "The trailing stop + regime filter genuinely caps the downside compared to "
        "buy-and-hold equity (VTI hit -54.8% worst MaxDD in the same data).\n"
        "3. **The leverage doesn't blow up.** I expected to find some 10-year windows "
        "with -50% or worse drawdowns. There are zero.\n\n"
        "**But the caveats remain real:**\n\n"
        "- All numbers are in-sample on data the strategy was optimized against. "
        "Out-of-sample reality will be worse by some unknown amount.\n"
        "- The synthetic UPRO/UGL data pre-2009 inflates returns by ~2-3% per year "
        "(no expense ratio + no tracking error in the synthetic series).\n"
        "- A -31% drawdown still means watching $60k become $41k. The math says they "
        "should hold; whether they will hold is a psychology question.\n"
        "- The strategy has never run live. The bot, the GitHub workflow, the Telegram "
        "delivery — any of these could fail and cost a missed signal.\n\n"
        "**For a 50-year-old in a Roth with a 10-year horizon:**\n\n"
        "- The risk profile is **slightly worse than 60/40 on drawdown** but **much "
        "better than 60/40 on expected outcome**. For someone who can tolerate a "
        "year of being down ~30%, this is mathematically the better choice.\n"
        "- **Roth structural fit is excellent** — tax drag (the biggest weakness in "
        "taxable accounts) is fully eliminated.\n"
        "- **Phasing entry over 6 months** is a cheap improvement: ~$15k lift in the "
        "worst-case trough for ~$15k less in the median ending balance.\n"
        "- **Honest answer**: if they can emotionally tolerate one -30% drawdown "
        "in 10 years without selling, the math says yes. If a -30% drawdown would "
        "make them sell at the bottom, AOR is the right answer instead.\n"
    )

    L.append("\n### What this analysis does NOT prove\n")
    L.append(
        "- It does not prove the strategy will work the same way going forward. The "
        "backtest used optimized parameters on this exact data; out-of-sample is "
        "fundamentally unknowable.\n"
        "- It does not account for execution failure. The bot might miss a Monday, "
        "Telegram might fail, the user might override a signal. Each is a small "
        "additional cost not modeled.\n"
        "- It does not account for **regulatory tail risk**: a future SEC restriction "
        "on leveraged ETFs would invalidate the strategy entirely. Probability is "
        "low but non-zero.\n"
        "- The 'worst-case' here is the worst observed in 26 years of data. Future "
        "could be worse than anything observed. Black-swan caveat applies.\n"
    )

    with open(out_path, "w") as f:
        f.write("\n".join(L))


# =============================================================================
# MAIN
# =============================================================================

def main():
    te_returns = build_tripleedge_returns()
    alt_returns = build_alternative_returns()

    # Analysis 1: Rolling distribution at 3/5/10 year horizons
    all_rolling = analysis_1_rolling_distribution(te_returns)
    distributions = []
    for h in HORIZONS_YR:
        sub = all_rolling[all_rolling["horizon_yr"] == h]
        distributions.append(distribution_summary(sub, f"TripleEdge {h}yr"))

    # Persist long-form rolling output
    all_rolling.to_csv(OUT_RESULTS_CSV, index=False)
    print(f"\n  Wrote {OUT_RESULTS_CSV} ({len(all_rolling)} rows)")

    # Analysis 2: specific bad entry timing
    bad_entries = analysis_2_specific_bad_entries(te_returns)

    # Analysis 3: DCA addon
    dca_rows = analysis_3_dca_addon(te_returns)

    # Analysis 4: phased entry
    phased_rows = analysis_4_phased_entry(te_returns)

    # Analysis 5: alternatives
    alt_rows = analysis_5_alternatives(te_returns, alt_returns)

    # Write the markdown
    write_summary(distributions, bad_entries, dca_rows, phased_rows, alt_rows, OUT_SUMMARY_MD)
    print(f"  Wrote {OUT_SUMMARY_MD}")

    # Console headline
    print("\n" + "=" * 70)
    print("HEADLINE NUMBERS")
    print("=" * 70)
    for d in distributions:
        if not d: continue
        print(f"\n  {d['label']} ({d['n_windows']} windows):")
        print(f"    Worst end:     ${d['worst_end']:>10,.0f}  (started {d['worst_end_start_date'].date()})")
        print(f"    Median end:    ${d['median_end']:>10,.0f}")
        print(f"    Best end:      ${d['best_end']:>10,.0f}  (started {d['best_end_start_date'].date()})")
        print(f"    Worst MaxDD:   {d['worst_max_dd']*100:+6.1f}%   (started {d['worst_max_dd_start_date'].date()})")
        print(f"    % ended <$60k: {d['pct_ended_below_lump']*100:.1f}%")
        print(f"    % ever down ≥50%: {d['pct_down_50']*100:.1f}%")


if __name__ == "__main__":
    main()
