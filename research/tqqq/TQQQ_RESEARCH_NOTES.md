# TQQQ Research Notes

**Status: Researched and excluded from active strategy.**

TQQQ (ProShares UltraPro QQQ, 3x Nasdaq-100) was the original TripleEdge engine and is fully documented here. It was dropped from the active portfolio after optimization research showed it adds negligible value to a UPRO + UGL portfolio while introducing meaningful tax and wash-sale friction.

---

## TQQQ Engine Parameters (Final Optimized)

The original live signal used:

| Parameter | Value |
|---|---|
| Regime filter | QQQ weekly close > QQQ **200-week SMA** |
| Re-entry signal | TQQQ weekly close > TQQQ **20-week SMA** |
| Trailing stop | **12%** from peak TQQQ price |
| Cash proxy | SGOV / T-bills |

The portfolio optimizer (which ran all three engines in combination) used slightly different params that produced better combined metrics:

| Parameter | Value |
|---|---|
| Regime filter | QQQ weekly close > QQQ **200-week SMA** |
| Re-entry signal | TQQQ weekly close > TQQQ **10-week SMA** |
| Trailing stop | **10%** from peak TQQQ price |

---

## TQQQ Standalone Performance

*Backtest period: 1999–present (~26 years), using synthetic 3x QQQ returns pre-2010 spliced with real TQQQ prices.*

| Metric | TQQQ Engine | B&H TQQQ | B&H QQQ |
|---|---|---|---|
| CAGR | ~20% | 27.6% | 15.0% |
| Max Drawdown | ~-65% | -93.6% | -51.4% |
| Sharpe | ~0.45 | 0.39 | 0.53 |
| Calmar | ~0.31 | 0.29 | 0.29 |

The system meaningfully improves risk-adjusted returns vs buy-and-hold TQQQ (Sharpe 0.45 vs 0.39, Calmar 0.31 vs 0.29). Standalone, it's a valid engine.

---

## Why TQQQ Was Excluded

### 1. Near-perfect correlation with UPRO

TQQQ and UPRO have a **0.91 weekly return correlation** over the common backtest period. Both are leveraged large-cap US equity ETFs — QQQ and SPY move together. Adding TQQQ to a portfolio that already has UPRO provides almost no diversification.

By contrast:
- UPRO vs UGL: **0.08 correlation** (near zero — independent drivers)
- TQQQ vs UGL: **0.03 correlation** (also near zero)

The diversification value comes entirely from UGL, not from TQQQ.

### 2. Tax drag (taxable account)

All three engines are active strategies with regular trades. In a taxable account:

| Engine | Avg hold per trade | % Short-term gains | Effective tax rate |
|---|---|---|---|
| TQQQ | ~4.3 months | ~85% | ~32% |
| UPRO | ~8.5 months | ~40% | ~24% |
| UGL | ~55 months | ~20% | ~21% |

TQQQ generates mostly short-term capital gains (held <1 year). At a 37% ordinary income bracket, the after-tax CAGR on TQQQ is materially worse than the pre-tax number.

### 3. Wash-sale risk

TQQQ has ~5.8 trades per year. With UPRO at ~3.5 trades per year, these signals can closely mirror each other (both respond to large-cap equity regimes). A TQQQ sell followed by an UPRO buy within 30 days — or vice versa — creates a wash-sale situation on the loss. The IRS considers substantially identical securities on a facts-and-circumstances basis.

### 4. Portfolio optimization results

Running the full 3-engine grid search (231 allocations at 5% increments):

**Adding TQQQ at any weight did not materially improve Calmar or Sharpe** vs the best 0% TQQQ allocation. The Calmar difference between the global optimal (with some TQQQ) and the best UPRO-only + UGL allocation was within 0.02 — well within noise.

Best with TQQQ (by Calmar): ~19% TQQQ / 27% UPRO / 54% UGL → Calmar ~1.01
Best without TQQQ (by Calmar): 50% UPRO / 50% UGL → Calmar ~0.91

The 0.10 Calmar improvement requires taking on meaningful TQQQ tax drag and wash-sale risk, plus reducing UPRO allocation (the better standalone performer in real data).

### 5. UPRO's real test period dominance

In the out-of-sample test period (2016+, real data only):
- UPRO CAGR: **28.4%**
- TQQQ CAGR: roughly similar or slightly higher, but with more drawdown and worse tax treatment

Given 0.91 correlation, UPRO is simply the cleaner, more tax-efficient way to get large-cap US equity leverage exposure.

---

## Conclusion

TQQQ is a good engine in isolation. It was the original TripleEdge instrument. But in the context of:
- A taxable account with DCA contributions
- An existing UPRO allocation
- A goal of CAGR + risk-adjusted return optimization

...it adds friction without adding independent return or diversification. The active strategy uses **75% UPRO / 25% UGL**.

---

*If you want to re-examine TQQQ, the original signal.py logic (from the initial commit) used QQQ 200-week SMA + TQQQ 20-week SMA + 12% trailing stop. That code is preserved in git history.*
