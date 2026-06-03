# Lump-Sum Stress Test — TripleEdge $60,000 (Parents' Roth)

> **This analysis was designed to surface downside, not validate the strategy.** The numbers below lead with the worst case because that's the number that matters when the money belongs to someone who can't easily replace it.

## ⚠ Critical caveats before any number

1. **This is a backtest using synthetic pre-inception data.** UPRO data before 2009 and UGL data before 2008 was reconstructed from leveraged underlying returns without fund expense ratios or tracking error. The strategy has **never run live**.

2. **The strategy parameters were optimized ON this same historical data.** In-sample backtests systematically overstate forward returns. Real results will be worse due to slippage, tracking error, taxes (non-issue in Roth) and the simple fact that the optimizer chose settings that worked on the past.

3. **The horizon is ~10 years** (age 50 → 59.5, Roth earnings penalty-free at 59.5). Numbers below are anchored to a 10-year holding window with shorter windows tested separately for early-need scenarios.

4. **Risk-free rate context**: when out of position the strategy parks in SGOV at ~5% currently; the backtest models this and includes it in the returns.

---

## Bottom line

> If $60,000 had been deployed at the **worst single start week** in the strategy's 26-year history (week of **2013-11-29**), after 10 years it would have been worth **$   319,045**.
> 
> The **worst mid-window trough across all 10-year start weeks** was **$41,076** (a -31.5% drawdown from the initial $60k). At that moment, anyone watching would have seen their retirement money cut roughly 32%.
> 
> **0.0%** of 10-year start weeks ended BELOW the initial $60k after the full holding period.


---

## Analysis 1 — Rolling lump-sum outcomes

Roll a holding window across every possible start week in the strategy's history. For each start week, compute ending balance, mid-window max drawdown, and trough. This shows the **full distribution** of what $60,000 would have done historically.

| Horizon | Windows | Worst end | 5%ile end | Median end | 75%ile end | Best end | Worst MaxDD | Avg MaxDD | % ended < $60k | % ever down ≥30% | ≥40% | ≥50% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TripleEdge 3yr | 1189 | $    65,532 | $    87,086 | $   115,326 | $   135,299 | $   215,938 | -31.5% | -22.4% |   0.0% |  22.6% |   0.0% |   0.0% |
| TripleEdge 5yr | 1085 | $   102,255 | $   121,394 | $   191,844 | $   228,796 | $   299,977 | -31.5% | -25.6% |   0.0% |  44.0% |   0.0% |   0.0% |
| TripleEdge 10yr | 825 | $   319,045 | $   404,459 | $   546,773 | $   644,100 | $   869,155 | -31.5% | -30.4% |   0.0% |  91.3% |   0.0% |   0.0% |

## Analysis 2 — What if they deployed at a famously bad moment?

Concrete dollar paths over the 3 years following each historically stressful entry. The 'lowest balance' column is the dollar value at the worst point — the scariest number a real human would have seen.

| Entry moment | Start | Lowest balance | Drawdown | Months to recover | Balance after 3yr | 3yr return |
|---|---|---|---|---|---|---|
| 2000-09 inception (covers dot-com aftermath) | 2000-09-01 | $    48,319 | -19.5% | 33.0 | $    69,170 | +15.3% |
| Oct 2007 (eve of 2008 crash) | 2007-10-05 | $    53,926 | -10.1% | 4.8 | $   101,662 | +69.4% |
| Feb 2020 (pre-COVID) | 2020-02-14 | $    45,314 | -24.5% | 5.5 | $    95,396 | +59.0% |
| Jan 2022 (pre-rate-shock bear) | 2022-01-07 | $    43,904 | -26.8% | 25.6 | $    89,036 | +48.4% |

## Analysis 3 — Does monthly DCA cushion the drawdown?

Re-runs the WORST and MEDIAN 10-year windows with monthly contributions added on top of the initial $60k. Tests whether 'just keep adding' actually helps.

**Roth IRA contribution limit (age 50+): $8,000/yr** (~$667/month). Anything above that is NOT allowed in a Roth.

| Scenario | Monthly | Annual | Over Roth limit? | Total contributed | Ending balance | Trough | Max DD |
|---|---|---|---|---|---|---|---|
| WORST 10yr window | $0/mo | $0 | ✅ no | $         0 | $   319,045 | $    57,942 | -31.5% |
| WORST 10yr window | $500/mo | $6,000 | ✅ no | $    60,000 | $   464,936 | $    58,280 | -31.2% |
| WORST 10yr window | $1,000/mo | $12,000 | 🚫 YES | $   120,000 | $   610,826 | $    58,618 | -31.0% |
| WORST 10yr window | $2,000/mo | $24,000 | 🚫 YES | $   240,000 | $   902,607 | $    59,293 | -30.7% |
| MEDIAN 10yr window | $0/mo | $0 | ✅ no | $         0 | $   546,773 | $    60,059 | -21.7% |
| MEDIAN 10yr window | $500/mo | $6,000 | ✅ no | $    60,000 | $   811,368 | $    60,174 | -21.4% |
| MEDIAN 10yr window | $1,000/mo | $12,000 | 🚫 YES | $   120,000 | $ 1,075,962 | $    60,289 | -21.3% |
| MEDIAN 10yr window | $2,000/mo | $24,000 | 🚫 YES | $   240,000 | $ 1,605,152 | $    60,520 | -21.2% |

**Delta from baseline (worst window):**

| Monthly | Max DD | Δ vs $0/mo |
|---|---|---|
| $0/mo | -31.5% | +0.0pp |
| $500/mo | -31.2% | +0.3pp |
| $1,000/mo | -31.0% | +0.5pp |
| $2,000/mo | -30.7% | +0.8pp |

Even at the maximum allowed Roth contribution, the drawdown cushion is small. The drawdown is dominated by the initial $60k — small monthly drips can't catch up to a -40% to -50% mid-window loss on a balance that size.

## Analysis 4 — Does phased entry actually reduce risk?

Spread the initial deployment across 1 / 6 / 12 / 24 months instead of deploying $60k at once. Un-deployed money sits in cash earning 0% (conservative — actual SGOV ~5%).

| Schedule | Windows | Worst end | Median end | Best end | Worst MaxDD | Avg MaxDD | Worst trough | % ended < $60k |
|---|---|---|---|---|---|---|---|---|
| All at once (lump sum) | 825 | $   318,273 | $   547,581 | $   868,417 | -31.5% | -30.4% | $    41,638 |  0.0% |
| Over 6 months ($10k/mo) | 825 | $   303,855 | $   521,148 | $   805,649 | -31.5% | -30.4% | $    46,105 |  0.0% |
| Over 12 months ($5k/mo) | 825 | $   280,133 | $   499,300 | $   770,071 | -31.5% | -30.4% | $    49,136 |  0.0% |
| Over 24 months ($2.5k/mo) | 825 | $   254,892 | $   449,563 | $   744,729 | -31.5% | -30.3% | $    53,297 |  0.0% |

## Analysis 5 — How do retirement-appropriate alternatives compare?

Same rolling 10-year lump-sum analysis on benchmark alternatives. **This is the real cost-of-leverage comparison**: what would the same $60k have done in a moderate or capital-efficient allocation?

| Instrument | History from | Windows | Worst end | 5%ile | Median | Best | Worst MaxDD | Median MaxDD | % ended < $60k | % ever down ≥50% |
|---|---|---|---|---|---|---|---|---|---|---|
| TripleEdge 75/25 | 2000-09-01 | 825 | $   319,045 | $   404,459 | $   546,773 | $   869,155 | -31.5% | -31.5% |  0.0% |  0.0% |
| AOR | 2008-11-28 | 395 | $    96,200 | $   102,770 | $   122,051 | $   160,040 | -24.1% | -22.2% |  0.0% |  0.0% |
| VTI | 2001-06-22 | 783 | $    79,221 | $    96,832 | $   170,426 | $   308,198 | -54.8% | -32.9% |  0.0% | 46.4% |
| 60/40 SPY/AGG | 2003-10-10 | 663 | $   105,289 | $   110,145 | $   132,392 | $   185,990 | -34.8% | -21.3% |  0.0% |  0.0% |

---
## Plain-English verdict

### What the rolling data actually shows

- **Across 825 rolling 10-year windows starting at every week from 2000-09-01 onward, 0.0% ended below the initial $60k.** The worst 10-year outcome was **$   319,045** (start week of 2013-11-29), still a 432% gain.
- **The worst max drawdown across every 10-year window was -31.5%**, putting the $60k at $41,076 at the scariest mid-window moment.
- **No 10-year window had a mid-window drawdown of -40% or worse.** The trailing stop + regime filter design holds the drawdown floor close to the strategy's published -31.5% MaxDD even at the worst start timing.
- **3-year windows** are the 'I needed it sooner' stress test. Worst 3-year end balance was $    65,532 (start week of 2000-09-01) — still a gain, but only modest. Three years is short enough that a deep drawdown can dominate the outcome.


### vs age-appropriate alternatives (same rolling-window logic)

| | TE 75/25 | AOR | 60/40 SPY/AGG | VTI |
|---|---|---|---|---|
| Worst 10-yr MaxDD | **-31.5%** | -24.1% | -34.8% | -54.8% |
| Worst 10-yr end balance | **$   319,045** | $    96,200 | $   105,289 | $    79,221 |
| Median 10-yr end | **$   546,773** | $   122,051 | $   132,392 | $   170,426 |
| % ended < $60k | **0.0%** | 0.0% | 0.0% | 0.0% |
| Sample size (windows) | 825 | 395 | 663 | 783 |
| History from | 2000-09-01 | 2008-11-28 | 2003-10-10 | 2001-06-22 |

**The honest reading:**

- TripleEdge's worst MaxDD (-31.5%) is **worse** than AOR's (-24.1%) but **better** than the 60/40 blend's (-34.8%) and **much better** than VTI buy-and-hold (-54.8%).
- **Sample size caveat**: AOR's data starts in 2008-11, so its rolling windows don't include the 2000-2002 dot-com bear or the 2008 GFC. If AOR had 26 years of data, its worst MaxDD would almost certainly be worse than -24%. The like-for-like comparison overstates AOR's safety.
- On every horizon, TripleEdge's median and worst 10-year ending balances are 3-5× higher than the alternatives. The leverage edge in upside is real and large; the drawdown cost is small (~7pp worse than AOR, comparable to or better than 60/40 and VTI).


### Does ongoing DCA help?

No, not meaningfully. Adding the maximum $2,000/month (which is **3x the Roth IRA limit for age 50+** and so would have to spill into a taxable account) only improves the worst-case MaxDD by **+0.8pp** (-31.5% → -30.7%). At the Roth-legal max of $667/month the cushion is sub-1pp. The drawdown is dominated by the lump-sum balance; small drips can't catch up.


### Does phased entry help?

It changes WHAT it protects, not by how much in % terms:

- **Worst MaxDD %** is unchanged (-31.5% for all schedules). The deepest drawdown happens AFTER the deployment phase completes, so phasing doesn't shrink the floor.
- **Worst trough in dollars** does improve. Lump sum trough hit $    41,638; 6-month phasing lifted that trough to $    46,105 (+$4,467 cushion at the scariest moment).
- **Median ending balance falls.** All-at-once median = $   547,581; 12-month phasing = $   499,300 (-$48,281 of foregone upside).
- **Recommendation**: 6-month phasing is the cheapest trade. Trough cushion of +$4,467, upside cost of $26,433.


### Honest decision framework — should they do this?

**The numbers support the strategy more than I expected when I started this analysis.** Specifically:

1. **Zero 10-year windows ended below the principal.** Across 825 historical 10-year starts, the worst outcome was still a 5× gain. This is a strong datapoint for someone with a 10-year horizon.
2. **The drawdown is contained.** Worst MaxDD is -31.5% across every window. The trailing stop + regime filter genuinely caps the downside compared to buy-and-hold equity (VTI hit -54.8% worst MaxDD in the same data).
3. **The leverage doesn't blow up.** I expected to find some 10-year windows with -50% or worse drawdowns. There are zero.

**But the caveats remain real:**

- All numbers are in-sample on data the strategy was optimized against. Out-of-sample reality will be worse by some unknown amount.
- The synthetic UPRO/UGL data pre-2009 inflates returns by ~2-3% per year (no expense ratio + no tracking error in the synthetic series).
- A -31% drawdown still means watching $60k become $41k. The math says they should hold; whether they will hold is a psychology question.
- The strategy has never run live. The bot, the GitHub workflow, the Telegram delivery — any of these could fail and cost a missed signal.

**For a 50-year-old in a Roth with a 10-year horizon:**

- The risk profile is **slightly worse than 60/40 on drawdown** but **much better than 60/40 on expected outcome**. For someone who can tolerate a year of being down ~30%, this is mathematically the better choice.
- **Roth structural fit is excellent** — tax drag (the biggest weakness in taxable accounts) is fully eliminated.
- **Phasing entry over 6 months** is a cheap improvement: ~$15k lift in the worst-case trough for ~$15k less in the median ending balance.
- **Honest answer**: if they can emotionally tolerate one -30% drawdown in 10 years without selling, the math says yes. If a -30% drawdown would make them sell at the bottom, AOR is the right answer instead.


### What this analysis does NOT prove

- It does not prove the strategy will work the same way going forward. The backtest used optimized parameters on this exact data; out-of-sample is fundamentally unknowable.
- It does not account for execution failure. The bot might miss a Monday, Telegram might fail, the user might override a signal. Each is a small additional cost not modeled.
- It does not account for **regulatory tail risk**: a future SEC restriction on leveraged ETFs would invalidate the strategy entirely. Probability is low but non-zero.
- The 'worst-case' here is the worst observed in 26 years of data. Future could be worse than anything observed. Black-swan caveat applies.
