# TripleEdge

Rules-based, systematic dual-engine strategy delivering weekly BUY / HOLD / WAIT / SELL signals via Telegram. Built for a 21-year-old investor with a 20+ year horizon, monthly DCA contributions, and high risk tolerance.

**Active allocation: 75% UPRO / 25% UGL**

---

## The Strategy

Two uncorrelated engines run in parallel. Capital not deployed in a given engine sits in SGOV (~5.2% yield). Check signals every Friday close, act Monday open.

### UPRO Engine (75% of portfolio)
ProShares UltraPro S&P 500 — 3x leveraged S&P 500

| Rule | Detail |
|---|---|
| Regime filter | SPY weekly close > SPY **65-week SMA** |
| Re-entry signal | UPRO weekly close > UPRO **10-week SMA** |
| Trailing stop | UPRO drops **22%** from peak price since entry (ratchets up only) |
| Cash proxy | SGOV / T-bills when out |

### UGL Engine (25% of portfolio)
ProShares Ultra Gold — 2x leveraged Gold

| Rule | Detail |
|---|---|
| Regime filter | GLD weekly close > GLD **100-week SMA** |
| Re-entry signal | GLD weekly close > GLD **20-week SMA** |
| Trailing stop | UGL drops **28%** from peak price since entry (ratchets up only) |
| Cash proxy | SGOV / T-bills when out |

> Note: Both regime and re-entry for the UGL engine use GLD (unleveraged). UGL is only tracked for the trailing stop. This is intentional — leverage decay on UGL adds noise to trend signals; GLD is cleaner.

### Signal Logic (each engine independently)

```
Stop hit?         → SELL — exit to SGOV immediately
Regime OFF?       → CASH — stay in SGOV
Regime ON, re-entry not confirmed? → WAIT — hold SGOV, watch for re-entry
Regime ON, re-entry confirmed?     → BUY / HOLD
```

### While Sidelined

Park in **SGOV** (iShares 0-3 Month Treasury Bond ETF). Pays weekly dividends, essentially zero price risk, currently ~5.2% annualized. This is not "doing nothing" — it's earning risk-free yield and accumulating dry powder for the next re-entry.

---

## Backtest Results

*Full period using synthetic data pre-inception + real data post-inception.*

### UPRO Engine (1996–present, 29 years)
| Metric | Value |
|---|---|
| CAGR | 24.6% |
| Max Drawdown | -51.8% |
| Sharpe Ratio | 0.67 |
| Calmar Ratio | 0.47 |
| % Time in UPRO | 70% |
| Train CAGR (pre-2017) | 22.6% |
| Test CAGR (2017+) | **28.4%** |

### UGL Engine (2000–present, 25 years)
| Metric | Value |
|---|---|
| CAGR | 17.6% |
| Max Drawdown | -49.1% |
| Sharpe Ratio | 0.54 |
| Calmar Ratio | 0.36 |
| % Time in UGL | 71% |
| Train CAGR (pre-2016) | 20.9% |
| Test CAGR (2016+) | 12.9% |

### Combined Portfolio (75% UPRO / 25% UGL)
| Metric | Value |
|---|---|
| CAGR | ~23.9% |
| Max Drawdown | ~-31.5% |
| Sharpe Ratio | ~0.77 |
| Calmar Ratio | ~0.76 |

*The engines have near-zero correlation (0.08). When one is in a drawdown, the other is often not. UGL provides meaningful drawdown compression with minimal CAGR cost.*

---

## Why 75/25 (Not Equal Weight)

The mathematically optimal Calmar allocation was ~50% UPRO / 50% UGL. The 75/25 choice is deliberate for this investor profile:

- **+0.9% CAGR** compounds to ~$18M more over 30 years on a $30k starting balance
- **DCA smooths drawdowns**: monthly contributions buy cheaper shares during pullbacks, reducing the psychological and financial impact of the -31.5% max drawdown
- **UPRO's real test period CAGR (28.4%)** is more than double UGL's (12.9%) — the current regime favors the heavier UPRO weight
- **At 21 years old**, time horizon is long enough to absorb higher drawdowns and let the extra CAGR compound

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Register for weekly Monday signals |
| `/status` | Get both engine signals right now |
| `/setportfolio <amount>` | Set your total portfolio value (shows 75/25 split) |
| `/help` | List all commands and strategy rules |

---

## Project Structure

```
tripleedge/
├── signal.py              # Signal engine — fetches data, computes UPRO + UGL signals
├── bot_actions.py         # GitHub Actions bot (50-sec polling, handles commands)
├── bot.py                 # Local testing bot (infinite polling)
├── users.json             # Registered users and portfolio values
├── bot_offset.json        # Telegram update offset (GitHub Actions state)
├── engine_state.json      # Per-engine position state (in_position, peak, entry)
├── requirements.txt       # Python dependencies
│
├── .github/
│   └── workflows/
│       ├── tripleedge.yml # Weekly Monday signal (8am ET) + manual trigger
│       └── bot.yml        # Bot command handler (every 10 minutes)
│
└── research/
    ├── upro/              # UPRO optimization research (Phase 1–3)
    │   ├── upro_optimizer.py
    │   ├── upro_final_validation.py
    │   ├── upro_winner_summary.py     ← run this for live UPRO status
    │   ├── upro_winner_params.json
    │   ├── upro_results.csv
    │   ├── upro_variant_results.csv
    │   └── UPRO_RESEARCH_SUMMARY.md
    │
    ├── ugl/               # UGL optimization research (Phase 1–3)
    │   ├── ugl_optimizer.py
    │   ├── ugl_structural_variants.py
    │   ├── ugl_final_validation.py
    │   ├── ugl_winner_summary.py      ← run this for live UGL status
    │   ├── ugl_winner_params.json
    │   ├── ugl_results.csv
    │   ├── ugl_variant_results.csv
    │   └── UGL_RESEARCH_SUMMARY.md
    │
    ├── portfolio/         # Portfolio allocation optimization
    │   ├── portfolio_optimizer.py     ← run to re-run all allocation tests
    │   ├── portfolio_results_coarse.csv
    │   ├── portfolio_results_fine.csv
    │   └── portfolio_recommendation.json
    │
    └── tqqq/              # TQQQ research — documented, not active
        └── TQQQ_RESEARCH_NOTES.md
```

**Running live signal checks locally:**
```bash
cd research/upro && python3 upro_winner_summary.py   # UPRO status
cd research/ugl  && python3 ugl_winner_summary.py    # UGL status
```

---

## Setup

### 1. Create a Telegram Bot
- Message [@BotFather](https://t.me/BotFather) on Telegram
- Run `/newbot` and follow the prompts
- Save your bot token

### 2. Get a Tiingo API Key
- Sign up at [tiingo.com](https://www.tiingo.com) (free tier is sufficient)
- Save your API key

### 3. Fork This Repo (keep it private)

### 4. Add GitHub Secrets
Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your token from BotFather |
| `TIINGO_API_KEY` | Your Tiingo API key |

### 5. Enable GitHub Actions
Go to the **Actions** tab → enable workflows → run **TripleEdge Signal** manually to test.

### 6. Register
Message your bot `/start`, then `/setportfolio 30000`

---

## How It Works

```
Every Monday 8am ET
       │
       ▼
GitHub Actions → signal.py
       │
       ▼
Fetches SPY, UPRO, GLD, UGL from Tiingo (weekly bars)
       │
       ▼
UPRO Engine: SPY vs 65w SMA + UPRO vs 10w SMA + 22% trailing stop
UGL Engine:  GLD vs 100w SMA + GLD vs 20w SMA + 28% trailing stop on UGL
       │
       ▼
Sends dual-engine signal to all registered Telegram users

Every 10 minutes
       │
       ▼
GitHub Actions → bot_actions.py
       │
       ▼
Polls Telegram for /status, /setportfolio, /help commands
```

---

## Research Notes

All optimization work lives in `research/`. Each engine went through:

1. **Phase 1** — Grid search over regime periods, re-entry periods, stop percentages
2. **Phase 2** — Structural variants (EMA vs SMA, alternative filters, golden cross)
3. **Phase 3** — Walk-forward validation, Monte Carlo simulation, DCA analysis, benchmark comparison

See `research/upro/UPRO_RESEARCH_SUMMARY.md` and `research/ugl/UGL_RESEARCH_SUMMARY.md` for full findings.

**TQQQ** was fully researched and excluded — see `research/tqqq/TQQQ_RESEARCH_NOTES.md` for reasoning.

---

_TripleEdge · Rules-based · Not financial advice_
