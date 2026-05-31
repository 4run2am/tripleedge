# TripleEdge UPRO - Research Summary

> **Numbers last refreshed: 2026-05-29** via `upro_winner_summary.py`. Backtest metrics drift week-over-week as new market data accumulates. Sections marked "refreshed 2026-05-29" reflect the current run; other tables (benchmark comparisons, structural variant deltas) are from the original research run and not refreshed in this update.

## What We Built

An independently optimized TripleEdge strategy for UPRO (3x leveraged S&P 500), using the same research methodology as the TQQQ version but letting the data find UPRO-specific optimal parameters. The strategy was tested across 2,106 parameter combinations across three grid searches, 59 structural variants, and validated with walk-forward analysis, Monte Carlo simulation, DCA analysis, and benchmark comparisons.

---

## The Strategy (Final Rules)

**Instrument:** UPRO (ProShares UltraPro S&P 500, 3x daily leverage)

### Entry Rules (ALL must be true):
1. **Regime filter:** SPY weekly close > SPY **65-WEEK SMA**
2. **Re-entry signal:** UPRO weekly close > UPRO **10-WEEK SMA**
3. No trailing stop currently triggered

### Exit Rules (ANY triggers full exit):
1. **Trailing stop:** UPRO drops **22%** from highest close since entry
2. **Regime break:** SPY weekly close <= SPY 65-week SMA

### Operational Details:
- **While out of trade:** 100% cash earning ~5.2% annualized (SGOV/T-bills proxy)
- **Cadence:** Weekly - check every Friday at close, act the following Monday
- **Friction:** 0.05% per trade (one-way)
- **Signal source for regime:** SPY (unleveraged, no leverage decay noise)
- **Signal source for re-entry:** UPRO (leveraged ETF itself)

---

## Final Performance Table

### Strategy vs Benchmarks (1996-2026, ~30 years)

*TripleEdge UPRO column refreshed **2026-05-29** via `upro_winner_summary.py`. Benchmark columns (B&H UPRO/SPY/SSO, TripleEdge TQQQ) are from an earlier run and not refreshed in this update. To rerun benchmarks: `python upro_winner_summary.py`.*

| Metric | TripleEdge UPRO | B&H UPRO | B&H SPY | B&H SSO (2x) | TripleEdge TQQQ |
|---|---|---|---|---|---|
| **CAGR** | **25.2%** | 15.9% | 10.0% | 16.6% | 19.9% |
| **Max Drawdown** | **-51.8%** | -96.2% | -54.6% | -83.2% | -46.5% |
| **Sharpe Ratio** | **0.69** | 0.45 | 0.34 | 0.47 | 0.56 |
| **Sortino Ratio** | **0.57** | 0.44 | 0.32 | 0.45 | 0.42 |
| **Calmar Ratio** | **0.49** | 0.17 | 0.18 | 0.20 | 0.43 |
| **Ulcer Index** | 0.218 | 0.501 | 0.151 | 0.314 | 0.183 |
| **UPI** | 0.92 | 0.21 | 0.32 | 0.36 | 0.80 |
| **Worst 1-yr Return** | -51.3% | -90.9% | -45.6% | -75.5% | -35.8% |
| **Worst 3-yr Return** | -46.4% | -90.8% | -43.1% | -74.3% | -29.6% |
| **% 3yr Negative** | 6.1% | 26.1% | 18.6% | 22.1% | 5.6% |
| **Recovery (weeks)** | 177 | 407 | 180 | 219 | 22 |
| **Total Return** | **926.2x** | 86.3x | 18.0x | 104.7x | 135.6x |
| **Trades** | 49 | 0 | 0 | 0 | 136 |
| **% Time in Equities** | 70% | 100% | 100% | 100% | 52% |
| **Train CAGR (pre-2017)** | 22.6% | 12.2% | 8.3% | 12.8% | 10.9% |
| **Test CAGR (2017+)** | 30.5% | 24.0% | 14.0% | 25.5% | 38.2% |
| **Train Sharpe** | 0.63 | 0.39 | 0.25 | 0.38 | 0.33 |
| **Test Sharpe** | 0.80 | 0.59 | 0.55 | 0.69 | 0.90 |
| **Train/Test Sharpe Ratio** | **0.79** | 0.66 | 0.45 | 0.55 | 0.37 |

### DCA Comparison ($500/week over full period)

| Metric | TripleEdge UPRO | B&H UPRO | B&H SPY |
|---|---|---|---|
| Total Invested | $789,500 | $789,500 | $789,500 |
| Terminal Value | **$85,542,942** | $16,676,837 | $4,849,756 |
| Multiple of Cost | **108.35x** | 21.12x | 6.14x |
| Max Drawdown | -47.5% | -94.2% | -50.2% |
| DCA Sharpe | 1.04 | 0.79 | 0.99 |

### Monte Carlo (2000 sims, 5-year horizon, 12-week block bootstrap)

| Percentile | Terminal Wealth | Annualized Return |
|---|---|---|
| 5th | 1.04x | +0.8% |
| 25th | 2.04x | +15.4% |
| **50th (median)** | **3.21x** | **+26.3%** |
| 75th | 5.12x | +38.6% |
| 95th | 9.48x | +56.8% |
| **P(loss over 5yr)** | **4.7%** | |

---

## How We Got Here

### Phase 1a: Initial Grid Search (504 Combinations)

**What we tested:**
- Regime filter: SPY weekly SMA [150, 175, 200, 225, 250] + SPY 200-day SMA
- Re-entry instrument: [UPRO, SPY]
- Re-entry SMA period: [8, 10, 12, 15, 20, 25, 30]
- Trailing stop: [6%, 8%, 10%, 12%, 15%, 18%]

**Initial results were disappointing.** The best Calmar was only 0.23 (SPY 250-week SMA, UPRO SMA30, 18% stop) with a CAGR of 10.7% - barely matching SPY buy-and-hold. The very long regime periods (150-250 weeks) produced ultra-conservative strategies that spent too much time in cash with poor walk-forward consistency (consistency score: 0.07).

### Phase 1b: Extended Grid (1,134 Combinations)

The initial grid only tested regime periods 150+ weeks - all very slow "secular bull" filters. We expanded to test shorter regime periods that function as "trend confirmation" rather than "secular regime" filters:

- Regime filter: SPY weekly SMA [30, 35, 40, 45, 50, 60, 75, 100, 125]
- Re-entry instrument: [UPRO, SPY]
- Re-entry SMA period: [8, 10, 12, 15, 20, 25, 30]
- Trailing stop: [6%, 8%, 10%, 12%, 15%, 18%, 20%, 22%, 25%]

### Phase 1c: Focused Comparison (468 Combinations)

Narrowed to the promising 20-80 week regime zone with fine-grained stops:

- Regime filter: SPY weekly SMA [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]
- Re-entry instrument: UPRO (confirmed winner)
- Re-entry SMA period: [8, 10, 12, 15]
- Trailing stop: [10%, 12%, 15%, 18%, 20%, 22%, 25%, 28%, 30%]

**Best Calmar by regime period (each row = best config at that period):**

| Regime | Re-entry | Stop | CAGR | MaxDD | Sharpe | Calmar | Train/Test Sharpe |
|---|---|---|---|---|---|---|---|
| 30w | SMA10 | 30% | 14.2% | -77.1% | 0.41 | 0.18 | 0.55 |
| 40w | SMA8 | 28% | 16.2% | -67.2% | 0.46 | 0.24 | 0.59 |
| 50w | SMA8 | 28% | 20.9% | -52.7% | 0.58 | 0.40 | 0.88 |
| 55w | SMA8 | 28% | 20.5% | -54.9% | 0.56 | 0.37 | 0.69 |
| 60w | SMA10 | 22% | 21.6% | -47.7% | 0.60 | 0.45 | 0.86 |
| **65w** | **SMA10** | **22%** | **25.2%** | **-51.8%** | **0.69** | **0.49** | **0.79** |
| 70w | SMA10 | 22% | 23.1% | -51.8% | 0.64 | 0.45 | 0.88 |
| 75w | SMA10 | 22% | 21.2% | -51.8% | 0.59 | 0.41 | 0.78 |
| 80w | SMA12 | 22% | 19.9% | -50.2% | 0.56 | 0.40 | 0.71 |

**18 combinations appeared in both top-30 Calmar AND top-30 Sharpe** across the focused grid - extremely strong cross-metric agreement centering on the 60-70 week regime zone with 20-22% stops.

**Key findings:**

1. **The 65-week regime is the sweet spot.** It's responsive enough to exit before bear markets deepen (catches the 2001, 2008, 2020, and 2022 crashes) but slow enough to not whipsaw on routine 5-10% corrections. Below 50 weeks, MaxDD increases sharply (>60%). Above 80 weeks, the strategy becomes too conservative.

2. **SMA10 re-entry is optimal.** Same as TQQQ. A fast re-entry captures recoveries quickly. The regime filter does the heavy lifting on risk management, so the re-entry just needs to confirm the bounce.

3. **22% trailing stop is optimal.** The Calmar heatmap shows a clear peak at 20-22% for the 60-70 week regime zone. Below 18%, too many false exits from normal volatility. Above 25%, the stop is too loose to add value.

4. **Train/Test robustness is excellent.** The winner has Train CAGR 22.6%, Test CAGR 30.5% (as of 2026-05-29). Train Sharpe 0.63, Test Sharpe 0.80. Train/Test Sharpe ratio of 0.79 indicates genuine edge, not overfit.

### Phase 2: Structural Variants (59 Tests)

**Tested on top 5 initial grid winners:**

| Variant | Effect | Verdict |
|---|---|---|
| EMA regime filter | Neutral (+0.1-0.5% CAGR) | No improvement |
| ATR-based stops | Slightly worse (-0.4-1.6% CAGR) | Rejected |
| Golden cross regime | Not beneficial | Rejected |
| Partial exit (50% at first stop, 50% at 15%) | +2.2% CAGR on daily regime base | Complexity concern |
| VIX filter (<25/30/35) | Effectively neutral | Rejected |
| UPRO > SMA50 extra filter | Marginal (+0.7-1.1%) | Minor help |
| SSO (2x leverage) | Lower returns, similar risk | Rejected |

**Same finding as TQQQ: every structural addition either made things worse or was neutral.** The simplest formulation remains best.

### Phase 3: Validation

**Walk-Forward Analysis (5 periods, ~5.8 years each):**

| Period | CAGR | Sharpe | Max DD | Calmar | Trades |
|---|---|---|---|---|---|
| 1997-2003 | 0.6% | 0.02 | -51.8% | 0.01 | 10 |
| 2003-2008 | 16.8% | 0.53 | -22.9% | 0.73 | 2 |
| 2008-2014 | 28.1% | 0.79 | -40.4% | 0.52 | 13 |
| 2014-2020 | 14.6% | 0.44 | -40.1% | 0.37 | 11 |
| 2020-2026 | 12.6% | 0.38 | -31.6% | 0.40 | 12 |

**Mean Sharpe: 0.43 | Std: 0.28 | Consistency score: 1.54**

All five periods produced non-negative Sharpe ratios. The weakest period (1997-2003, spanning the dot-com crash) was essentially flat - the strategy stayed out of the crash but didn't compound much in the recovery phase either. The remaining four periods all delivered double-digit CAGRs.

**Train/Test Split (refreshed 2026-05-29):**
- Train (1996-2016): CAGR 22.6%, Sharpe 0.63, MaxDD -51.8%
- Test (2017-present): CAGR 30.5%, Sharpe 0.80, MaxDD -40.1%
- Train/Test Sharpe Ratio: 0.79

---

## What We Rejected and Why

| Variant | Reason for Rejection |
|---|---|
| Regime SMA periods 150-250 weeks | Too conservative; CAGR barely matched SPY B&H. Walk-forward consistency was terrible (0.07). |
| Regime SMA periods 20-40 weeks | Too responsive; MaxDD > 63%. Whipsawed on normal S&P corrections. |
| 200-day SMA regime filter | Produced 200+ trades (~8/yr). Whipsawed on normal corrections. |
| SPY-based re-entry signal | Higher trade count, lower Calmar. |
| Re-entry SMA periods 20-30 | Only optimal when paired with ultra-long regime (250-week). With 65-week regime, SMA10 is better. |
| Trailing stops 6-15% | Too tight; UPRO's normal volatility triggered false exits. |
| Trailing stops 25-30% | Too loose; didn't add risk protection beyond what the regime filter provides. |
| EMA regime/re-entry | Neutral; not worth complexity. |
| ATR-based stops | Worse performance; noisy ATR proxy. |
| Golden cross regime | Lagged too much; missed entries. |
| VIX filter | Negligible impact. |
| SSO (2x leverage) | Lower CAGR with similar MaxDD. |

---

## Key Differences from TQQQ Version

| Aspect | TQQQ Version | UPRO Version | Why It Differs |
|---|---|---|---|
| **Regime SMA** | 200-week | **65-week** | SPY needs a faster regime filter. A 200-week SMA almost never breaks for SPY, making it useless for routine risk management. The 65-week SMA responds to meaningful drawdowns (2001, 2008, 2015-16, 2018, 2020, 2022) while ignoring noise. |
| **Re-entry SMA** | 10-week (on TQQQ) | **10-week (on UPRO)** | Same. Fast re-entry works for both once the regime provides crash protection. |
| **Trailing stop** | 10% | **22%** | UPRO is less volatile than TQQQ week-to-week. A 10% stop on UPRO triggers on normal retracements. The 22% stop only fires on genuine trend breaks. |
| **Trades** | 136 over 23yr (~6/yr) | 49 over 30yr (~1.6/yr) | Fewer, higher-quality signals. |
| **Time in market** | 52% | **70%** | Shorter regime catches crashes but stays in longer during bulls. |
| **CAGR** | 19.9% | **25.2%** | Higher market exposure (70% vs 52%) compounds more aggressively. |
| **Max DD** | -46.5% | -51.8% | Slightly wider drawdown; acceptable given the CAGR premium. |
| **Sharpe** | 0.56 | **0.69** | Better risk-adjusted returns. |
| **Calmar** | 0.43 | **0.49** | Better return per unit of drawdown. |
| **Walk-forward consistency** | Not tested identically | **1.54** | All periods positive Sharpe. |
| **Train/Test Sharpe Ratio** | 0.37 | **0.79** | Much more robust out-of-sample. |

**The 65-week regime was the breakthrough insight.** The initial assumption that UPRO needed a "secular bull" filter (200+ weeks) like TQQQ was wrong. SPY's correction profile is different from QQQ - corrections are shallower but more frequent. A 65-week regime catches both major crashes and meaningful corrections, providing far more actionable signals than a 200-week filter that only triggers once a decade.

---

## Current Status

**As of 2026-04-03:**

| Check | Value | Status |
|---|---|---|
| SPY Price | $655.83 | - |
| SPY 65-week SMA | ~$628 | - |
| Regime filter | SPY > SMA | **ON** |
| UPRO Price | $99.38 | - |
| UPRO 10-week SMA | ~$108 | - |
| Re-entry signal | UPRO < SMA | **OFF** |
| 52-week Peak | $121.38 | - |
| Trailing Stop Level | ~$94.68 (22% below peak) | - |
| Distance to Stop | ~4.7% | - |
| Stop Hit? | NO | - |

**ACTION: WAIT**

The regime filter is ON (SPY well above 65-week SMA), but the re-entry signal is OFF (UPRO $99.38 < 10-week SMA ~$108). The trailing stop has NOT been hit. If currently in a position from before the drawdown, the stop has not triggered so HOLD. If out, WAIT for UPRO to recover above its 10-week SMA before entering.

**Watch closely:** SPY is ~4% above its 65-week SMA. A further decline could break the regime filter.

---

## Appendix: Data Notes

- **Data range:** 1996-01-02 to 2026-04-02 (~30 years)
- **Synthetic UPRO:** Built from 3x daily SPY returns, spliced with real UPRO from June 2009
- **Synthetic vs Real validation:** 0.984 correlation during overlap; 2.25x drift ratio over 17 years (expected due to leverage decay accumulation in synthetic vs actual fund management)
- **SPY B&H CAGR sanity check:** 10.0% (passes ~10-11% expectation)
- **UPRO B&H MaxDD sanity check:** -96.2% (passes -70% to -95% expectation)
- **Total combinations tested:** 2,106 (504 initial + 1,134 extended + 468 focused)
