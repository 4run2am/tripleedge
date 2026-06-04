"""
Alpaca broker adapter — paper trading by default.

Uses the official alpaca-py SDK (verified against docs.alpaca.markets):
  - TradingClient(api_key, secret_key, paper=True)
  - StockHistoricalDataClient(api_key, secret_key)
  - MarketOrderRequest, OrderSide, TimeInForce

Fetches up to HISTORY_WEEKS of weekly bars for SPY, UPRO, GLD, UGL,
returns them as a pandas Series each. Falls back to Tiingo via the
existing engine.fetch_tiingo if Alpaca data is unavailable (e.g.
weekend, no entitlement) — Alpaca's free IEX feed has limited
historical depth, so the fallback matters for the 100-week SMAs.
"""

import os
import sys
from typing import Optional

import pandas as pd

from .config import (  # type: ignore
    BotConfig, HISTORY_WEEKS,
    PAPER_ENDPOINT, LIVE_ENDPOINT,
    UPRO_SYMBOL, UGL_SYMBOL,
)


# ────────────────────────────────────────────────────────────────────────────
# Lazy import so tests / alert-only paths don't need alpaca-py installed
# ────────────────────────────────────────────────────────────────────────────

def _import_alpaca():
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    except ImportError as e:
        print(
            f"ERROR: alpaca-py not installed. Run: pip install alpaca-py\n  ({e})",
            file=sys.stderr,
        )
        sys.exit(2)
    return {
        "TradingClient":             TradingClient,
        "MarketOrderRequest":        MarketOrderRequest,
        "OrderSide":                 OrderSide,
        "TimeInForce":               TimeInForce,
        "StockHistoricalDataClient": StockHistoricalDataClient,
        "StockBarsRequest":          StockBarsRequest,
        "TimeFrame":                 TimeFrame,
        "TimeFrameUnit":             TimeFrameUnit,
    }


# ────────────────────────────────────────────────────────────────────────────
# Trading client
# ────────────────────────────────────────────────────────────────────────────

class AlpacaBroker:
    """Wraps alpaca-py TradingClient + StockHistoricalDataClient with the
    minimum surface area the bot needs. Hardcodes paper=True unless the
    config explicitly enables live AND confirms it."""

    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self._alpaca = _import_alpaca()
        TradingClient = self._alpaca["TradingClient"]
        StockHistoricalDataClient = self._alpaca["StockHistoricalDataClient"]

        # paper=True is the SDK default. We pass it explicitly for clarity.
        # The cfg.live_trading flag has already been confirmed in config.py.
        self.trading = TradingClient(
            api_key=cfg.alpaca_api_key,
            secret_key=cfg.alpaca_secret_key,
            paper=(not cfg.live_trading),
        )
        self.data = StockHistoricalDataClient(
            api_key=cfg.alpaca_api_key,
            secret_key=cfg.alpaca_secret_key,
        )

    # ── ACCOUNT / POSITIONS ────────────────────────────────────────────────

    def get_equity(self) -> float:
        acct = self.trading.get_account()
        return float(acct.equity)

    def get_positions(self) -> dict:
        """Return {symbol: {qty, market_value, avg_entry_price}} for all open positions."""
        positions = self.trading.get_all_positions()
        out = {}
        for p in positions:
            out[p.symbol] = {
                "qty":              float(p.qty),
                "market_value":     float(p.market_value),
                "avg_entry_price":  float(p.avg_entry_price),
                "unrealized_pl":    float(p.unrealized_pl),
            }
        return out

    # ── HISTORICAL DATA ────────────────────────────────────────────────────

    def fetch_weekly_bars(self, symbols, weeks=HISTORY_WEEKS) -> dict:
        """Fetch ~`weeks` worth of weekly Friday-close bars for each symbol.

        Returns {symbol: pandas.Series of closes indexed by date}.

        Alpaca's free IEX feed only goes back ~16-month-ish; for long history
        we resample daily bars to weekly. If the symbol still has insufficient
        history (need 100 weeks for UGL regime SMA), we fall back to Tiingo
        via the existing engine.fetch_tiingo function.
        """
        TimeFrame    = self._alpaca["TimeFrame"]
        TimeFrameUnit = self._alpaca["TimeFrameUnit"]
        StockBarsRequest = self._alpaca["StockBarsRequest"]

        # Fetch daily bars over the full lookback window
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc) - timedelta(weeks=weeks + 10)

        out = {}
        for sym in symbols:
            try:
                req = StockBarsRequest(
                    symbol_or_symbols=sym,
                    timeframe=TimeFrame(1, TimeFrameUnit.Day),
                    start=start,
                )
                bars = self.data.get_stock_bars(req)
                df = bars.df
                if df.empty:
                    raise ValueError("no bars")
                # df has multi-index (symbol, timestamp); drop symbol level
                if isinstance(df.index, pd.MultiIndex):
                    df = df.droplevel(0)
                df.index = pd.to_datetime(df.index).tz_localize(None) \
                    if df.index.tz is not None else pd.to_datetime(df.index)
                weekly = df["close"].resample("W-FRI").last().dropna()
                if len(weekly) < weeks * 0.8:  # accept some shortfall
                    raise ValueError(f"only {len(weekly)} weekly bars")
                out[sym] = weekly
            except Exception as e:
                print(f"  Alpaca data insufficient for {sym} ({e}); "
                      f"falling back to Tiingo.")
                out[sym] = self._fetch_tiingo_fallback(sym, weeks)
        return out

    def _fetch_tiingo_fallback(self, symbol, weeks):
        """Use the validated engine.fetch_tiingo for long-history data."""
        from datetime import datetime, timedelta
        tiingo_key = os.environ.get("TIINGO_API_KEY")
        if not tiingo_key:
            raise RuntimeError(
                f"Alpaca data short for {symbol} and no TIINGO_API_KEY set. "
                f"Either upgrade Alpaca data feed or set TIINGO_API_KEY in .env."
            )
        from engine import fetch_tiingo  # validated long-history fetcher
        start = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        return fetch_tiingo(symbol, tiingo_key, start)

    # ── ORDERS ─────────────────────────────────────────────────────────────

    def latest_price(self, symbol: str) -> float:
        """Best-effort latest trade price for sizing market orders."""
        from alpaca.data.requests import StockLatestTradeRequest
        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        result = self.data.get_stock_latest_trade(req)
        return float(result[symbol].price)

    def submit_market_order(self, symbol: str, qty: float, side: str,
                             dry_run: bool = False) -> dict:
        """Place a notional or qty-based market order.

        side: 'buy' or 'sell' (lowercase). qty is shares (float allowed for
        fractional). Returns a dict describing what was submitted or — in
        dry_run — what WOULD be submitted.
        """
        OrderSide          = self._alpaca["OrderSide"]
        TimeInForce        = self._alpaca["TimeInForce"]
        MarketOrderRequest = self._alpaca["MarketOrderRequest"]

        side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side_enum,
            time_in_force=TimeInForce.DAY,
        )
        payload = {"symbol": symbol, "qty": qty, "side": side, "type": "market"}
        if dry_run:
            payload["status"] = "DRY_RUN — not submitted"
            return payload

        order = self.trading.submit_order(order_data=req)
        payload["status"] = "submitted"
        payload["id"] = str(order.id)
        return payload


def make_broker(cfg: BotConfig) -> Optional[AlpacaBroker]:
    """Factory. In alert_only mode the broker is still constructed (we need
    account equity for sizing) but no orders will be submitted."""
    return AlpacaBroker(cfg)
