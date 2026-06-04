"""
Bot configuration — reads env vars, enforces safety defaults.

DESIGN PRINCIPLE: every dangerous setting defaults to its SAFE value.
The only way to turn safety off is to explicitly set an env var.
"""

import os
import sys
from dataclasses import dataclass


# ── Allowed bot modes — must be one of these ────────────────────────────────
MODE_ALERT_ONLY = "alert_only"  # default: compute + log, place NO orders
MODE_DRY_RUN    = "dry_run"     # show what would be submitted, no orders
MODE_EXECUTE    = "execute"     # actually place paper (or live) orders

VALID_MODES = (MODE_ALERT_ONLY, MODE_DRY_RUN, MODE_EXECUTE)

# ── Endpoints — paper is the ONLY default ───────────────────────────────────
PAPER_ENDPOINT = "https://paper-api.alpaca.markets"
LIVE_ENDPOINT  = "https://api.alpaca.markets"

# ── Strategy weights (must match engine.py) ─────────────────────────────────
W_UPRO = 0.75
W_UGL  = 0.25
UPRO_SYMBOL = "UPRO"
UGL_SYMBOL  = "UGL"

# ── How much history to fetch for SMAs ──────────────────────────────────────
# UGL needs 100-week SMA; pad to 220 weeks (≈4.2 yrs) for a clean warm-up.
HISTORY_WEEKS = 220


@dataclass(frozen=True)
class BotConfig:
    """Runtime config snapshot — built once at startup, then immutable."""
    alpaca_api_key:        str
    alpaca_secret_key:     str
    mode:                  str            # alert_only / dry_run / execute
    live_trading:          bool           # False = paper (the safe default)
    live_confirmed:        bool           # Required when live_trading=True
    endpoint:              str            # paper or live URL
    telegram_bot_token:    str | None     # optional
    telegram_chat_id:      str | None     # optional


def _env(name: str, default: str | None = None) -> str | None:
    """Read env var, treat empty string as None."""
    v = os.environ.get(name)
    return v if v else default


def load_config() -> BotConfig:
    """Read environment, build config, ERROR LOUDLY on bad input.

    Loads .env automatically if present (for local dev convenience).
    Never falls back to hardcoded keys — missing keys is a fatal error.
    """
    # Try loading .env if python-dotenv is available; otherwise rely on
    # whatever the shell exported. Either way, no hardcoded fallback.
    try:
        from dotenv import load_dotenv  # type: ignore
        # Look for .env at repo root (one dir above this file)
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(repo_root, ".env"))
    except ImportError:
        pass  # dotenv is optional; env vars from shell still work

    api_key    = _env("ALPACA_API_KEY")
    secret_key = _env("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        print(
            "ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.\n"
            "  1. Copy .env.example to .env in the repo root.\n"
            "  2. Add your PAPER trading keys from https://app.alpaca.markets\n"
            "  3. Verify .env is gitignored:  git check-ignore .env\n"
            "  4. Re-run.\n",
            file=sys.stderr,
        )
        sys.exit(2)

    mode = (_env("BOT_MODE") or MODE_ALERT_ONLY).strip().lower()
    if mode not in VALID_MODES:
        print(
            f"ERROR: BOT_MODE='{mode}' is invalid. "
            f"Must be one of: {', '.join(VALID_MODES)}",
            file=sys.stderr,
        )
        sys.exit(2)

    live_trading   = (_env("LIVE_TRADING") or "").strip().lower() == "true"
    live_confirmed = (_env("LIVE_TRADING_CONFIRMED") or "").strip().lower() == "true"

    endpoint = LIVE_ENDPOINT if live_trading else PAPER_ENDPOINT

    return BotConfig(
        alpaca_api_key     = api_key,
        alpaca_secret_key  = secret_key,
        mode               = mode,
        live_trading       = live_trading,
        live_confirmed     = live_confirmed,
        endpoint           = endpoint,
        telegram_bot_token = _env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id   = _env("BOT_NOTIFY_CHAT_ID"),
    )


def print_startup_banner(cfg: BotConfig) -> None:
    """Print clear mode banner so the operator always knows the safety state."""
    bar = "=" * 72
    print(bar)
    print("  TripleEdge — Alpaca Paper-Trading Bot")
    print(bar)
    print(f"  Endpoint:      {cfg.endpoint}")
    print(f"  Mode:          {cfg.mode}")
    print(f"  Live trading:  {'⚠ LIVE ⚠' if cfg.live_trading else 'PAPER (safe)'}")
    if cfg.live_trading:
        if not cfg.live_confirmed:
            print()
            print("  ✗ LIVE_TRADING=true but LIVE_TRADING_CONFIRMED is NOT set.")
            print("    Refusing to start. Set both env vars to enable live execution.")
            print(bar)
            sys.exit(3)
        print()
        print("  ⚠  YOU ARE ABOUT TO TRADE REAL MONEY  ⚠")
        print("     Press Ctrl-C in the next 5 seconds to abort.")
        import time; time.sleep(5)
    print(bar)
