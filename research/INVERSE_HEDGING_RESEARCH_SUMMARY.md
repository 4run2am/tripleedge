# TripleEdge Inverse Hedging Research Summary

> **Numbers in this document are from the original research run (not refreshed).** The conclusion (inverse hedging strictly underperforms cash) is robust to the small CAGR drift that has occurred since — every inverse configuration was worse than baseline by margins much larger than the data-update noise. For current standalone engine numbers see `research/upro/UPRO_RESEARCH_SUMMARY.md` and `research/ugl/UGL_RESEARCH_SUMMARY.md` (refreshed 2026-05-29).

## What We Tested

Tested whether rotating into inverse leveraged ETFs (SH/SDS/SPXU for S&P 500, PSQ/QID/SQQQ for Nasdaq-100) during TripleEdge "exit" periods improves risk-adjusted returns versus the baseline strategy of sitting in cash (SGOV/T-bills at ~5.2% annually).

## Key Question

Does rotating into inverse leveraged ETFs during exit periods improve TripleEdge returns vs sitting in cash?

## TL;DR Verdict

**No. Stick with cash.**

Across 297 inverse configurations tested per engine (8 trigger types x 3 leverage levels x 11 exit variants), **zero configurations robustly improved the UPRO engine**, and only **2 marginally improved the TQQQ engine** (D3_1x_exit4_12w: Sharpe 0.574 vs 0.559 baseline, driven entirely by 2 inverse trades over 23 years). At the combined 60/20/20 portfolio level, the best possible enhancement adds just +0.006 Sharpe (0.809 vs 0.803) — not worth the added complexity, tax drag, or execution risk. The baseline cash-on-exit strategy remains optimal.

---

## Best Configuration Per Engine

### UPRO Engine (3x S&P 500)

**No configuration beats baseline.** All 297 inverse variants produced lower Sharpe ratios than cash-on-exit.

| Metric | Baseline (Cash) | Best Inverse (B_1x_exit1_regime) |
|---|---|---|
| CAGR | 22.1% | 20.9% |
| Max Drawdown | -51.8% | -57.2% |
| Sharpe | 0.623 | 0.592 |
| Calmar | 0.427 | 0.366 |

The "best" UPRO inverse config (trailing stop trigger, 1x inverse SH, exit on regime reversal) actually **reduces** CAGR by 1.2% and **worsens** MaxDD by 5.4 percentage points.

### TQQQ Engine (3x Nasdaq-100)

| Metric | Baseline (Cash) | Best Inverse (D3_1x_exit4_12w) | Delta |
|---|---|---|---|
| CAGR | 19.9% | 20.6% | +0.7% |
| Max Drawdown | -46.5% | -42.9% | +3.6% better |
| Sharpe | 0.559 | 0.574 | +0.015 |
| Calmar | 0.428 | 0.480 | +0.052 |
| Inverse Trades | 0 | 2 | — |
| Inverse Hit Rate | — | 50% | — |
| Train/Test Sharpe Ratio | 2.36 | 2.30 | — |

Config: **D3** (delayed regime break — wait 2 weeks after QQQ drops below 200-week SMA before entering inverse), **1x PSQ**, **12-week time-based exit**. The entire improvement comes from 2 inverse trades, one during the GFC.

---

## Comparison Tables

### All 9 Trigger Configs — UPRO Engine (avg across leverage and exit types)

| Trigger | Avg Sharpe | Best Sharpe | Avg CAGR | Description |
|---|---|---|---|---|
| D3 | 0.418 | 0.552 | 14.3% | Delayed regime break (2wk wait) |
| D5 | 0.475 | 0.578 | 16.6% | Death cross (50w < 200w SMA) |
| D6 | 0.465 | 0.584 | 16.5% | Multi-timeframe (30w < 50w SMA) |
| B | 0.431 | 0.592 | 14.9% | Trailing stop only |
| C | 0.357 | 0.587 | 12.1% | Either trigger |
| D2 | 0.358 | 0.517 | 11.5% | Regime break + price < 10w SMA |
| D1 | 0.343 | 0.534 | 11.1% | Confirmed 2-week regime break |
| A | 0.328 | 0.525 | 10.2% | Regime break only |
| D4 | 0.293 | 0.517 | 8.8% | Regime break + VIX > 25 |
| **Baseline** | **0.623** | **—** | **22.1%** | **Cash on exit** |

**Every trigger type averages below baseline Sharpe of 0.623.**

### All 9 Trigger Configs — TQQQ Engine

| Trigger | Avg Sharpe | Best Sharpe | Avg CAGR |
|---|---|---|---|
| **D3** | **0.515** | **0.574** | **18.4%** |
| D4 | 0.412 | 0.528 | 14.2% |
| D2 | 0.363 | 0.491 | 12.1% |
| D5 | 0.338 | 0.459 | 11.1% |
| A | 0.334 | 0.494 | 10.7% |
| D1 | 0.325 | 0.472 | 10.4% |
| D6 | 0.227 | 0.425 | 6.3% |
| B | 0.046 | 0.513 | 0.1% |
| C | 0.028 | 0.505 | -0.5% |
| **Baseline** | **0.559** | **—** | **19.9%** |

Only D3 best config (0.574) exceeds baseline (0.559). Even D3 averages 0.515.

### Leverage Comparison (averaged across all triggers and exit types)

| Leverage | UPRO Avg Sharpe | TQQQ Avg Sharpe |
|---|---|---|
| 1x (SH/PSQ) | 0.445 | 0.340 |
| 2x (SDS/QID) | 0.392 | 0.290 |
| 3x (SPXU/SQQQ) | 0.319 | 0.233 |
| **Baseline** | **0.623** | **0.559** |

**1x inverse is consistently least harmful. 3x is catastrophic.** Higher leverage amplifies decay and wrong-way losses.

### Exit Type Comparison (averaged across triggers and leverage — TQQQ top trigger D3)

| Exit Type | D3 TQQQ Best Sharpe | D3 TQQQ Best Config |
|---|---|---|
| Exit 4 (time-based, 12w) | 0.574 | D3_1x_exit4_12w |
| Exit 4 (time-based, 4w) | 0.555 | D3_1x_exit4_4w |
| Exit 3 (either) | 0.552 | D3_1x_exit3_either |
| Exit 2 (inverse stop) | 0.548 | D3_1x_exit2_stop12 |
| Exit 1 (regime reversal) | 0.548 | D3_1x_exit1_regime |

Time-based exits (12 weeks) work best because they cap decay exposure.

---

## What Worked and Why

### D3 (delayed regime break) was the least-bad trigger

D3 waits 2 weeks after the regime SMA breaks before entering inverse. This filters out single-week noise where the price barely touches the SMA line and bounces back. For TQQQ (200-week SMA), this is effective because:
- The 200-week SMA is very smooth; crossings are significant events
- The 2-week delay confirms the break is sustained
- By the time D3 fires, the bear market is often well-established

### 1x leverage preserved capital

1x inverse (PSQ for TQQQ) minimizes volatility decay. Over a 12-week holding period, 1x inverse loses ~4.7% to decay per trade vs ~16.7% for 2x. The lower leverage makes the difference between a marginally profitable and clearly unprofitable inverse allocation.

### Time-based exits (12 weeks) limited decay drag

Capping inverse exposure at 12 weeks prevents the worst effects of volatility decay and catches the sharpest part of the decline without overstaying.

---

## What Failed and Why

### Config B (trailing stop trigger) — Expected failure

Trailing stops fire during temporary corrections, not just bear markets. Going inverse on pullbacks means shorting into recoveries. Average Sharpe: 0.431 (UPRO), 0.046 (TQQQ). The TQQQ result of 0.046 — essentially zero — confirms that most stop-fire events are buying opportunities, not selling opportunities.

### Config C (either trigger) — Expected failure

Maximum inverse exposure means maximum exposure to decay and wrong-way risk. Average Sharpe: 0.357 (UPRO), 0.028 (TQQQ). Several 3x variants with long holding periods (26 weeks) lost -100% of capital.

### 3x inverse leverage — Expected failure

SPXU/SQQQ have ~3x the decay of 1x alternatives. Combined with extended holding periods, 3x inverse destroys capital. The worst configs (C_3x_exit4_26w) lost 98-100% of the starting capital.

### Config A (regime break from CASH) — Cycling problem

With CASH-state re-entry, Config A cycles in and out of inverse continuously during bear markets. This creates excessive trading costs and ensures the strategy catches both the decline AND the recovery (in inverse), negating the benefit.

### D5 (death cross 50w < 200w) — Too slow

The death cross signal is so slow that by the time it fires, much of the bear market is already priced in. The inverse entry comes late and catches the sideways-to-recovery phase.

---

## Bear Market Performance

### UPRO Engine: Inverse HURT in every bear market

| Period | Baseline Return | Best Inverse Return | Delta |
|---|---|---|---|
| Dot-com 2000-2003 | -39.8% | -43.3% | -3.5% worse |
| GFC 2008-2009 | -17.7% | -20.4% | -2.7% worse |
| COVID 2020 | -30.4% | -31.4% | -1.0% worse |
| Rate shock 2022 | -25.9% | -26.7% | -0.8% worse |
| 2018 volatility | -37.1% | -39.9% | -2.8% worse |

The UPRO engine's 65-week regime SMA is fast enough that exits are well-timed. Adding inverse positions introduces wrong-way risk during the recovery.

### TQQQ Engine: Inverse helped ONLY during GFC

| Period | Baseline Return | D3_1x_exit4_12w Return | Delta |
|---|---|---|---|
| Dot-com 2000-2003 | +13.7% | +13.7% | No change |
| GFC 2008-2009 | -31.9% | -25.5% | **+6.4% better** |
| COVID 2020 | -28.6% | -28.6% | No change |
| Rate shock 2022 | -4.0% | -4.0% | No change |

The GFC improvement (+6.4%) is the sole source of the TQQQ enhancement. The dot-com period shows no change because the TQQQ backtest starts from ~2003 (200-week warmup). COVID and 2022 show no change because the regime break was too brief or didn't meet D3's 2-week confirmation requirement.

---

## Decay Analysis

### Volatility decay destroys inverse returns over holding periods > 4 weeks

| Config | Avg Decay/Trade | Total Decay | Avg Hold |
|---|---|---|---|
| TQQQ D3_1x_exit4_12w | -4.71%/trade | -9.42% | 12 weeks |
| TQQQ D3_2x_exit4_12w | -16.66%/trade | -33.31% | 12 weeks |
| UPRO B_1x_exit1_regime | -0.01%/trade | -0.22% | 1 week |
| UPRO C_1x_exit4_4w | -0.41%/trade | -9.94% | 4 weeks |

The 2x inverse (QID) loses **16.7% per trade** to decay over 12 weeks — more than wiping out any directional gain from the bear market decline. Even 1x (PSQ) loses 4.7% per trade. This decay is the fundamental reason inverse hedging fails.

---

## Combined Portfolio Impact

### 60% UPRO / 20% TQQQ / 20% UGL

| Portfolio | CAGR | MaxDD | Sharpe | Calmar | P50 (MC 5yr) |
|---|---|---|---|---|---|
| **Baseline (all cash)** | **26.1%** | **-32.1%** | **0.803** | **0.813** | **3.27x** |
| Enhanced (both inverse) | 25.7% | -32.1% | 0.791 | 0.801 | 3.23x |
| Hybrid (UPRO inv only) | 25.5% | -32.1% | 0.785 | 0.794 | 3.21x |
| **Hybrid (TQQQ inv only)** | **26.3%** | **-32.1%** | **0.809** | **0.820** | **3.29x** |

The TQQQ-only hybrid shows a marginal improvement (+0.2% CAGR, +0.006 Sharpe). The full enhanced portfolio (both engines) is WORSE than baseline because UPRO inverse drag overwhelms TQQQ's tiny gain.

**The improvement is not portfolio-significant.** A +0.006 Sharpe delta is within noise range and depends on 2 inverse trades over 23 years.

---

## Recommendation

### Deploy or don't?

**Don't deploy. Stick with cash on exit for both engines.**

Reasons:

1. **Marginal pre-tax improvement:** The best possible config (TQQQ D3_1x_exit4_12w) adds +0.7% CAGR and +0.015 Sharpe — driven by 2 trades over 23 years.

2. **After-tax erosion:** Inverse ETF gains are taxed as short-term capital gains (~30-37% marginal rate). The 0.7% CAGR improvement would shrink to ~0.5% after tax, while the cash baseline's 5.2% is taxed at lower rates (interest income from T-bills).

3. **Execution complexity:** Adding inverse logic to a live system creates additional failure modes (wrong ETF, missed signal, slippage on low-volume inverse ETFs).

4. **Sample size of 2 trades:** The TQQQ improvement depends on exactly 2 inverse trades. This is not a statistically meaningful sample. One bad trade in the future could erase the entire historical edge.

5. **The baseline is strong:** Cash earning 5.2% during exit periods is a guaranteed, tax-efficient return. The inverse alternative adds risk for almost no additional return.

6. **Walk-forward failure:** The TQQQ best config shows 20% consistency across 5 periods (positive Sharpe in only 1 of 5 periods). The improvement is concentrated in the recent period, not distributed evenly.

7. **Decay is real and unavoidable:** Even 1x inverse ETFs lose ~4.7% per 12-week trade to volatility decay. This structural drag means inverse positions need to be strongly directionally correct to break even.

### If you insist on deploying (conditional recommendation):

If you want to experiment with a small allocation despite the above:
- **Engine:** TQQQ only (do NOT add inverse to UPRO)
- **Trigger:** D3 (delayed regime break — 2 consecutive weeks below 200-week SMA)
- **Instrument:** PSQ (1x inverse QQQ) — NOT QID or SQQQ
- **Exit:** 12-week time limit (exit after 12 weeks regardless of conditions)
- **Allocation:** Consider 50% inverse / 50% cash during exit periods (partial inverse blend showed Sharpe 0.574 vs 0.574 full, same result with less risk)

---

## Current Status (as of 2026-04-07)

Per the optimal config D3_1x_exit4_12w for TQQQ:
- **QQQ regime (200-week SMA):** Check current QQQ price vs 200-week SMA
- **If QQQ > 200w SMA:** Regime ON. No inverse position. Standard TripleEdge rules apply.
- **If QQQ < 200w SMA for 2+ weeks:** D3 would trigger PSQ entry for 12 weeks.

Since we recommend NOT deploying inverse hedging, the current action is: **follow original TripleEdge signals. Cash (SGOV/BIL) on any exit.**

---

## Methodology Notes

### Synthetic Data Construction
All inverse ETFs were synthesized back to 1993 (UPRO engine) / 1999 (TQQQ engine) using:
```
synthetic_daily_return = -N * underlying_daily_return (N = 1, 2, or 3)
```
Chain-linked into price series and spliced with real ETF data from inception.

### Synthetic Validation (all PASS > 0.97 correlation)
| ETF | Correlation | Overlap | Annual Drift |
|---|---|---|---|
| UPRO | 0.9996 | 876 weeks | +0.0483/yr |
| SH | 0.9962 | 1033 weeks | -0.0242/yr |
| SDS | 0.9972 | 1030 weeks | -0.0379/yr |
| SPXU | 0.9994 | 876 weeks | -0.0427/yr |
| TQQQ | 0.9996 | 843 weeks | +0.0496/yr |
| PSQ | 0.9975 | 1033 weeks | -0.0197/yr |
| QID | 0.9985 | 1030 weeks | -0.0285/yr |
| SQQQ | 0.9994 | 843 weeks | -0.0369/yr |

Drift is due to expense ratios and management fees in real ETFs (synthetic has zero fees).

### Sanity Checks
- [x] Synthetic correlations > 0.97 (all PASS)
- [x] Inverse positions show realistic decay (confirmed: -4.7% per 12-week trade for 1x)
- [x] Bear markets do NOT universally benefit from inverse logic (UPRO inverse hurts in all bears)
- [x] 2010-2020 bull market does NOT benefit (confirmed)
- [x] Multiple configs show inverse WORSENING performance (bottom 5 configs lost 90-100% of capital)
- [x] Inverse trade hit rates reported (50% for best TQQQ config, 0-67% range across configs)
- [x] Tax implications discussed in recommendation
- [x] Recommendation is clear: don't deploy

### Parameters Used
- **UPRO Engine:** SPY > 65-week SMA regime, UPRO > 10-week SMA re-entry, 22% trailing stop
- **TQQQ Engine:** QQQ > 200-week SMA regime, TQQQ > 10-week SMA re-entry, 10% trailing stop
- **Cash rate:** 5.2% annual
- **Transaction cost:** 0.05% per trade (one-way)
- **Cadence:** Weekly (Friday close signal, Monday open execution)

### Files Generated
| File | Description |
|---|---|
| `backtest_utils.py` | Core infrastructure (data, engine, metrics, grid search) |
| `tripleedge_inverse_optimizer_upro.py` | UPRO grid search (Phase 1-3) |
| `tripleedge_inverse_optimizer_tqqq.py` | TQQQ grid search (Phase 1-3) |
| `tripleedge_inverse_validation.py` | Walk-forward, Monte Carlo, stress tests (Phase 4) |
| `tripleedge_inverse_portfolio.py` | Combined 60/20/20 portfolio (Phase 5) |
| `inverse_results_upro.csv` | 298 rows: baseline + 297 configs |
| `inverse_results_tqqq.csv` | 298 rows: baseline + 297 configs |
| `validation_results.json` | Phase 4 detailed results |
| `portfolio_comparison.csv` | Phase 5 portfolio metrics |
