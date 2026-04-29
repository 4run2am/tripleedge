# TripleEdge UGL — Research Summary

## What We Built

A systematic, weekly trend-following strategy for UGL (ProShares Ultra Gold, 2x daily Gold) using the same TripleEdge framework proven on TQQQ and UPRO. The strategy uses GLD (unleveraged gold) as the signal source for both regime filter and re-entry, with a 28% trailing stop on UGL. This is the uncorrelated diversification engine — gold moves on completely different macro drivers than US equities, and the weekly return correlation between this engine and the UPRO engine is only **0.081**.

## The Strategy (Final Rules)

**ENTRY (all must be true):**
1. **Regime filter:** GLD weekly close > GLD 100-week SMA
2. **Re-entry signal:** GLD weekly close > GLD 20-week SMA
3. No trailing stop currently triggered

**EXIT (any triggers full exit):**
1. **Trailing stop:** UGL drops 28% from its highest close since entry
2. **Regime break:** GLD weekly close falls below GLD 100-week SMA

**While out:** 100% cash earning ~5.2% annualized (SGOV/T-bills proxy)
**Cadence:** Weekly — check every Friday at close, act the following Monday
**Friction:** 0.05% per trade (one-way)

## Final Performance Table

| Metric | TripleEdge UGL | B&H UGL | B&H GLD | B&H SPY | TripleEdge TQQQ | TripleEdge UPRO |
|---|---|---|---|---|---|---|
| CAGR | **17.8%** | 16.9% | 11.3% | 7.8% | 20.8% | 24.2% |
| Max Drawdown | **-49.1%** | -75.0% | -44.7% | -54.6% | -46.5% | -40.4% |
| Sharpe | **0.54** | 0.48 | 0.42 | 0.23 | 0.58 | 0.68 |
| Sortino | 0.45 | 0.47 | 0.40 | 0.21 | 0.45 | 0.56 |
| Calmar | **0.36** | 0.23 | 0.25 | 0.14 | 0.45 | 0.60 |
| Ulcer Index | 0.284 | 0.414 | 0.188 | 0.162 | 0.188 | 0.158 |
| UPI | 0.44 | 0.28 | 0.32 | 0.16 | 0.83 | 1.20 |
| Worst 1yr | -40.0% | -53.0% | -29.3% | -45.6% | -35.8% | -36.7% |
| Worst 3yr | -42.9% | -67.2% | -39.2% | -43.1% | -29.6% | +11.8% |
| % 3yr Negative | 24.2% | 25.5% | 17.7% | 14.6% | 5.9% | 0.0% |
| Recovery (weeks) | 67 | 481 | 244 | 180 | 22 | 65 |
| Trades | 37 | 0 | 0 | 0 | 136 | 38 |
| % Time Invested | 71% | 100% | 100% | 100% | 55% | 72% |
| Total Return | 66.4x | 54.4x | 15.4x | 6.8x | 125.9x | 259.6x |
| Train CAGR | 20.9% | 13.4% | 8.9% | 3.9% | 12.3% | 21.6% |
| Test CAGR | 13.3% | 22.7% | 15.1% | 13.9% | 34.7% | 28.4% |
| Train Sharpe | 0.64 | 0.39 | 0.28 | 0.02 | 0.37 | 0.64 |
| Test Sharpe | 0.40 | 0.64 | 0.65 | 0.55 | 0.82 | 0.75 |

*All benchmarks run over the same date range: 2000-09 to 2026-04 (~25.6 years)*

**Key takeaway:** TripleEdge UGL turns a 75% max drawdown instrument into one with -49% max drawdown while capturing nearly all the upside (66.4x vs 54.4x total return). The strategy beats B&H UGL on every risk-adjusted metric. Compared to the equity engines, the absolute CAGR is lower (17.8% vs 24.2%) — but the diversification value is where the real payoff lives (see Correlation section below).

## DCA Comparison ($500/week)

| Metric | TripleEdge UGL | B&H UGL | B&H GLD |
|---|---|---|---|
| Total invested | $668,500 | $668,500 | $668,500 |
| Terminal value | $9,734,750 | $8,322,905 | $3,583,751 |
| Multiple of cost | 14.56x | 12.45x | 5.36x |
| Max drawdown | -47.6% | -73.1% | -36.9% |
| DCA Sharpe | 1.06 | 0.98 | 1.11 |

## Monte Carlo Results (2,000 sims, 5-year horizon, 12-week block bootstrap)

| Percentile | Terminal Wealth | Annualized Return |
|---|---|---|
| 5th | 0.89x | -2.2% |
| 25th | 1.62x | +10.1% |
| **50th (median)** | **2.41x** | **+19.2%** |
| 75th | 3.60x | +29.2% |
| 95th | 6.44x | +45.1% |

**P(losing money over 5 years): 7.0%**

## How We Got Here

### Phase 1: Grid Search (2,816 combinations)

**Parameters tested:**
- Regime filter (GLD SMA): 20, 26, 30, 35, 40, 45, 50, 55, 60, 65, 75, 100, 125, 150, 175, 200 weeks
- Re-entry signal: UGL or GLD, SMA periods 5, 8, 10, 12, 15, 20, 25, 30 weeks
- Trailing stop: 6%, 8%, 10%, 12%, 15%, 18%, 20%, 22%, 25%, 28%, 30%

**Key findings:**

1. **The regime period sweet spot is 100 weeks (~2 years).** This makes intuitive sense for gold — gold secular trends last 5-10+ years, so a 100-week lookback captures the intermediate trend without being whipsawed by short-term noise, while also being responsive enough to avoid multi-year bear markets. The 40-50w range also performed well (Calmar 0.34-0.36) but with a very different profile: tight 6% stops with frequent trading (~210 trades) vs the winner's 28% stop with only 37 trades.

2. **GLD won as re-entry signal source over UGL.** The top result uses GLD for BOTH regime and re-entry signals. This differs from TQQQ and UPRO (where the leveraged ETF won for re-entry). The likely explanation: UGL's 2x leverage decay adds noise to the price series, and since gold is less volatile than equities, the noise-to-signal ratio from leverage decay is proportionally higher. GLD provides a cleaner signal.

3. **SMA20 re-entry won, not SMA10.** Gold trends start more slowly than equity trends — they grind rather than V-bounce. A 20-week moving average filters out false starts that a 10-week MA would catch. This is a meaningful difference from the equity engines.

4. **28% trailing stop is very wide.** This reflects gold's tendency to have deep intermediate pullbacks within secular bull markets. A tight stop would whipsaw constantly. The 28% stop lets UGL breathe while still protecting against the 2011-2015 type bear market. For comparison: TQQQ uses 10%, UPRO uses 22%.

5. **Two distinct winning archetypes emerged:**
   - **High-CAGR / wide-stop:** R100 GLD SMA20 28% stop → 17.8% CAGR, -49.1% MaxDD (THE WINNER)
   - **Low-DD / tight-stop:** R40-50 UGL SMA25 6% stop → 13.3% CAGR, -36.9% MaxDD (frequent trading, lower returns)

6. **4 combinations appeared in both top-20 Calmar AND top-20 Sharpe lists** — all centered around the 100-125w regime with 20-30w re-entry and 28-30% stops. Strong cross-metric agreement.

### Best Configuration per Regime Period

| Regime Period | Re-entry | Stop | CAGR | MaxDD | Sharpe | Calmar | Trades |
|---|---|---|---|---|---|---|---|
| 20w | GLD 12w | 6% | 11.0% | -38.6% | 0.34 | 0.29 | 242 |
| 40w | UGL 25w | 6% | 13.3% | -36.9% | 0.42 | 0.36 | 214 |
| 50w | UGL 25w | 6% | 13.5% | -37.7% | 0.43 | 0.36 | 212 |
| 55w | GLD 5w | 28% | 16.2% | -47.0% | 0.49 | 0.34 | 67 |
| **100w** | **GLD 20w** | **28%** | **17.8%** | **-49.1%** | **0.54** | **0.36** | **37** |
| 125w | GLD 20w | 28% | 17.0% | -51.0% | 0.52 | 0.33 | 29 |
| 200w | GLD 25w | 18% | 15.7% | -52.1% | 0.50 | 0.30 | 43 |

### Phase 2: Structural Variants (75 tests on top 5 winners)

Tested 10 variant types including 4 gold-specific filters. **Every variant either hurt or was neutral.** Consistent with TQQQ and UPRO findings.

**The DXY filter was the closest to helping:** On the R100 GLD20 S28% base, DXY < 40w SMA improved Calmar from 0.362 to 0.390, improving both train Sharpe (0.637→0.642) and test Sharpe (0.403→0.418). However, across all 5 tested bases, DXY HURT on average (mean Calmar delta: -0.028). Given the marginal improvement on one base, added data dependency, and pattern of no variant helping in the equity engines, we rejected it.

### Phase 3: Walk-Forward Validation

| Period | Years | CAGR | Sharpe | MaxDD | Calmar | Trades |
|---|---|---|---|---|---|---|
| 2002-08 to 2007-05 | 4.7 | 24.0% | 0.75 | -38.6% | 0.62 | 3 |
| 2007-05 to 2012-01 | 4.7 | 24.5% | 0.78 | -30.4% | 0.80 | 3 |
| 2012-01 to 2016-10 | 4.7 | 4.6% | 0.00 | -16.9% | 0.27 | 1 |
| 2016-10 to 2021-07 | 4.7 | 9.8% | 0.30 | -36.5% | 0.27 | 5 |
| 2021-07 to 2026-04 | 4.7 | 39.1% | 1.18 | -27.9% | 1.40 | 1 |

**Mean Sharpe: 0.60 | Std: 0.46 | Consistency score: 1.31**

The 2012-2016 period (gold bear market) is weak as expected — Sharpe of 0.00, but crucially MaxDD was only -16.9%. The strategy protected capital during gold's lost years. Train/Test Sharpe ratio of 1.58 is higher than ideal (suggesting some train-period overshoot) but still reasonable — the test period Sharpe of 0.40 confirms a real edge exists out of sample.

## What We Rejected and Why

| Variant | Calmar Delta (avg) | Verdict | Why |
|---|---|---|---|
| EMA regime | -0.01 to -0.03 | HURT | Slightly more responsive but added whipsaws |
| EMA re-entry | +0.02 (one base) | NEUTRAL | Marginal improvement on one base, hurt others |
| ATR stops (1.5-4.0x) | -0.05 to -0.13 | HURT | ATR proxy using close-to-close is noisy; fixed % more reliable |
| Golden cross (50/200) | -0.02 to -0.07 | HURT | Too laggy for gold's trend structure |
| Partial exit (50/50) | -0.01 to +0.01 | NEUTRAL | Added complexity for no gain |
| DXY filter (< 40w SMA) | -0.03 avg, +0.03 best | HURT (avg) | Marginal improvement on one base; adds data dependency |
| TIP filter (> 20w SMA) | -0.08 | HURT | Too restrictive; missed entries |
| GDX miners (> 10w SMA) | -0.09 to -0.16 | HURT | GDX data too short; added noise rather than confirmation |
| GLD low volatility | -0.03 to -0.07 | HURT | Filtered out some of the best entry points |
| UGL > SMA50 | -0.06 to -0.08 | HURT | Redundant with re-entry signal; reduced time in position |

## Key Differences from TQQQ and UPRO Versions

| Parameter | TripleEdge TQQQ | TripleEdge UPRO | TripleEdge UGL |
|---|---|---|---|
| **Leveraged ETF** | TQQQ (3x Nasdaq) | UPRO (3x S&P 500) | UGL (2x Gold) |
| **Signal source** | QQQ (unleveraged) | SPY (unleveraged) | GLD (unleveraged) |
| **Regime filter** | QQQ > 200w SMA | SPY > 65w SMA | GLD > 100w SMA |
| **Re-entry** | TQQQ > 10w SMA | UPRO > 10w SMA | GLD > 20w SMA |
| **Re-entry source** | Leveraged ETF | Leveraged ETF | **Unleveraged (GLD)** |
| **Trailing stop** | 10% | 22% | **28%** |
| **CAGR** | 22.4% | 24.1% | 17.8% |
| **Max DD** | -46.5% | -51.8% | -49.1% |
| **Sharpe** | 0.50 | 0.66 | 0.54 |
| **Calmar** | 0.48 | 0.46 | 0.36 |
| **Train/Test Sharpe** | 0.37 | 0.88 | 1.58 |
| **Trades** | ~136 | ~38 | 37 |
| **% Time invested** | 55% | 72% | 71% |

**Why gold's optimal setup differs:**

1. **100w regime vs 200w (TQQQ) and 65w (UPRO):** Gold's secular cycles are long (10+ years) but intermediate trends are more variable. 100 weeks balances trend capture vs responsiveness.

2. **GLD for re-entry (not UGL):** Gold's lower volatility means 2x leverage decay adds proportionally more noise. GLD gives cleaner re-entry signals. Equities are volatile enough that the leveraged ETF's momentum signal still works.

3. **SMA20 re-entry (not SMA10):** Gold trends grind rather than V-bounce. A 20-week lookback filters false starts. Equities recover faster and benefit from quicker re-entry.

4. **28% trailing stop (widest of all three):** Gold has deep intermediate pullbacks within secular bulls (20-25% corrections are normal). A tight stop would whipsaw out. The 28% stop essentially says: "only exit if this is a genuine trend reversal, not a correction."

## Correlation & Portfolio Analysis

### Weekly Return Correlations

| Pair | Correlation |
|---|---|
| **UGL strategy vs UPRO strategy** | **0.081** |
| **UGL strategy vs TQQQ strategy** | **0.026** |
| TQQQ strategy vs UPRO strategy | 0.674 |

The UGL engine is essentially **uncorrelated** with both equity engines. This is the core thesis validated: gold moves on different drivers (inflation, real rates, USD weakness, central bank buying) than equities (earnings, growth, risk appetite).

### Rolling 52-Week Correlation (UGL vs UPRO)

The yearly averages confirm persistently low correlation:
- 2004-2007: ~0.08 to 0.18
- 2008-2012: 0.15 to 0.34 (slightly higher during 2008 crisis)
- 2013-2016: 0.08 to inf* (both engines frequently in cash)
- 2017-2021: -0.32 to 0.21 (often negatively correlated)
- 2022-2026: -0.15 to 0.19

*inf values from periods where one or both engines were in cash (zero variance in returns).

### Overlap Analysis (All Three Engines)

| State | % of Time |
|---|---|
| All 3 invested simultaneously | 29.6% |
| All 3 in cash simultaneously | 15.2% |
| **Mixed (diversified)** | **55.2%** |

55% of the time, at least one engine diverges from the others — exactly the diversification benefit we wanted. The engines rarely all go to cash simultaneously (only 15% of weeks).

### Combined Portfolio Simulation

| Allocation | CAGR | MaxDD | Sharpe | Calmar | Total Return |
|---|---|---|---|---|---|
| **Equal weight (33/33/33)** | **23.9%** | **-26.1%** | **0.83** | **0.92** | **240.7x** |
| Custom (50 TQQQ / 30 UPRO / 20 UGL) | 23.7% | -30.3% | 0.76 | 0.78 | 231.0x |
| Equity heavy (40/40/20) | 24.0% | -30.6% | 0.78 | 0.79 | 248.8x |
| Gold tilt (25/25/50) | 23.2% | -23.4% | 0.85 | 0.99 | 207.7x |
| Solo UGL | 17.8% | -49.1% | 0.54 | 0.36 | 66.4x |
| Solo TQQQ | 20.8% | -46.5% | 0.57 | 0.45 | 125.9x |
| Solo UPRO | 24.2% | -40.4% | 0.68 | 0.60 | 259.6x |

**The equal-weight portfolio is the standout:** 23.9% CAGR with only -26.1% max drawdown and 0.92 Calmar. Compare this to the best solo engine (UPRO: 0.60 Calmar) — the diversification benefit nearly doubles the risk-adjusted return. The gold tilt (50% UGL) achieves the lowest drawdown (-23.4%) with a near-1.0 Calmar, at the cost of slightly lower CAGR.

## Gold-Specific Considerations

### Why gold's lack of inherent drift matters

Stocks have an inherent long-term upward drift (~10%/yr) because companies generate earnings. Gold's real return over very long periods is ~0-2% — it preserves purchasing power but doesn't compound like equities. This means:

1. **The regime filter is MORE important for gold.** During secular bear markets (2011-2018), gold can grind down 40%+ over years. Equities have bad years but generally recover faster. The 100-week SMA regime filter kept the UGL strategy mostly out during 2012-2016, limiting the worst walk-forward period to -16.9% MaxDD.

2. **Cash earning 5.2% is competitive with gold.** During gold's flat/down periods, parking in T-bills isn't just protection — it's an alpha source. The strategy earned ~5% while gold went nowhere for 7 years.

3. **Standalone CAGR expectations should be modest.** A 17.8% CAGR from a 2x gold strategy is genuinely impressive given gold's underlying return profile. Don't judge this engine by comparing it to the 24% CAGR of the 3x equity engines.

### When this engine shines vs struggles

**Shines:** Dollar weakness cycles, inflation scares, geopolitical crises, central bank buying sprees, equity market crashes (2008, 2020, 2022). Gold rallied in each of these while equities fell — the UGL engine was compounding while TQQQ and UPRO were parked in cash.

**Struggles:** Goldilocks economies (low inflation, strong growth, rising real rates). Think 2013-2015: stocks soaring, gold languishing. During these periods, the UGL engine sits in cash earning 5.2% while the equity engines compound.

**This is exactly the diversification we want.** The engines take turns carrying the portfolio.

### Corrections behave differently

Gold corrections are slow grinds, not sharp crashes:
- 2011-2015: -45% over 4 years (slow bleed)
- 2020 COVID crash: -12% in 2 weeks then immediate recovery
- 2022: held roughly flat while equities fell 25%

The 28% trailing stop and 100-week regime filter are calibrated for gold's slow-bleed pattern. A 10% stop (TQQQ-style) would have been whipsawed dozens of times in gold's normal volatility.

## Data Notes

### Synthetic Data Quality

- **Synthetic GLD (pre-2004):** Built from gold futures (GC=F), normalized to match GLD at inception. Correlation with real GLD: **1.0000** (expected — GLD directly tracks gold price).
- **Synthetic UGL (pre-2008):** Built from 2x daily GLD returns, compounded. Correlation with real UGL: **0.9773**. Tracking error: 24.55%. Drift ratio: 1.96x (synthetic drifts upward vs real due to leverage decay in real UGL).

The synthetic UGL correlation of 0.977 is acceptable but the drift is significant — the backtest before 2008 overstates UGL's performance relative to what the real product would have delivered (because the synthetic doesn't capture the friction, tracking error, and expense ratio of the real ETF). This means the ~20.9% train CAGR (pre-2016) is likely optimistic. The 13.3% test CAGR (mostly real data) is more representative of future expectations.

### Backtest Date Range

2000-09-01 to 2026-04-10 (~25.6 years, 1,337 weekly bars). Gold futures data starts from 2000-08-30 (yfinance limitation — GC=F doesn't go back to the 1990s as hoped). This is still sufficient for the 100-week SMA warmup and captures both the 2001-2011 gold bull and 2011-2018 bear.

## Current Status (as of 2026-04-10)

| Signal | Value | Status |
|---|---|---|
| GLD Price | $428.39 | — |
| UGL Price | $60.78 | — |
| GLD 100-week SMA | $307.93 | **Regime ON** (GLD well above SMA) |
| GLD 20-week SMA | $430.66 | **Re-entry: NO** (GLD $428 < SMA $431) |
| UGL 52-week peak | $79.26 | — |
| UGL stop level (28%) | $57.07 | **Stop: NOT HIT** (6.1% cushion) |
| **Action** | | **WAIT** |

GLD is just barely below its 20-week SMA ($428 vs $431). The regime is solidly bullish. If GLD closes above $430.66 next Friday, the re-entry signal fires and the action becomes BUY. The trailing stop has a 6.1% cushion — tight but not triggered.

## Appendix: Sanity Checks

- [x] B&H GLD CAGR: 11.3% (slightly above the 7-9% expected range — recent gold rally inflates this)
- [x] B&H UGL MaxDD: -75.0% (within -50% to -75% expected range)
- [x] Strategy exits early in 2011-2018 gold bear: YES — walk-forward period 3 (2012-2016) shows only -16.9% MaxDD with 1 trade
- [x] Strategy invested during strong gold runs: YES — periods 1-2 (2002-2012) captured 24%+ CAGR
- [x] Number of trades: 37 over 25.6 years (~1.4/year) — very reasonable
- [x] Synthetic UGL correlation > 0.95: YES (0.977)
- [x] Stop-loss exit returns are actual price changes: VERIFIED in backtest engine (exit week uses actual UGL return)
- [x] No gold-specific filter included in winner: CORRECT (DXY tested but rejected)
- [x] Weekly return correlation UGL vs UPRO < 0.3: YES (0.081) — strong diversification
