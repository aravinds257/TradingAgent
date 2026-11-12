"""Yahoo Finance market data + local paper broker for stock markets (US, India, ...).

Drop-in replacement for `ExecutionEngine` (same async interface) so the Supervisor,
warmup and PollingFeed work unchanged. There is NO live order routing: every order is
filled locally at the latest price, with a configurable cost per side.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd
import structlog

from src.core.config import ExchangeConfig
from src.core.models import Fill, Order, OrderStatus

logger = structlog.get_logger("yahoo")

# timeframe -> (yfinance interval, bar length, bars per calendar day (approx))
_INTERVALS: dict[str, tuple[str, timedelta, float]] = {
    "1d": ("1d", timedelta(days=1), 252 / 365),
    "1h": ("1h", timedelta(hours=1), 6.5 * 252 / 365),
    "1wk": ("1wk", timedelta(weeks=1), 1 / 7),
}


class YahooMarketData:
    """Market data from Yahoo Finance plus a simulated (paper) broker."""

    def __init__(self, config: ExchangeConfig):
        self.config = config
        self._sem = asyncio.Semaphore(4)  # be gentle with Yahoo

    async def connect(self) -> None:
        import yfinance  # noqa: F401  (fail fast if missing)
        logger.info("exchange_connected", name="yahoo", mode="paper")

    async def close(self) -> None:
        return None

    # ------------------------------------------------------------------ data
    @staticmethod
    def _download(symbol: str, timeframe: str, limit: int) -> list[list]:
        import yfinance as yf

        if timeframe not in _INTERVALS:
            raise ValueError(f"Unsupported timeframe for yahoo: {timeframe} "
                             f"(use one of {list(_INTERVALS)})")
        interval, bar_len, per_day = _INTERVALS[timeframe]
        days = int(limit / per_day * 1.15) + 7
        if interval == "1h":
            days = min(days, 729)  # Yahoo keeps ~730 days of hourly data
        start = (datetime.now(timezone.utc) - timedelta(days=days)).date()

        df = yf.Ticker(symbol).history(start=start, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            return []

        now = pd.Timestamp.now(tz="UTC")
        rows: list[list] = []
        for ts, r in df.iterrows():
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            if ts + bar_len > now:
                continue  # bar still forming -> skip (only completed bars)
            if pd.isna(r["Close"]):
                continue
            rows.append([int(ts.tz_convert("UTC").timestamp() * 1000),
                         float(r["Open"]), float(r["High"]), float(r["Low"]),
                         float(r["Close"]), float(r.get("Volume", 0) or 0)])
        return rows[-limit:]

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1d",
                          limit: int = 200) -> list[list]:
        """Completed OHLCV bars in ccxt format: [ms, open, high, low, close, volume]."""
        async with self._sem:
            try:
                return await asyncio.to_thread(self._download, symbol, timeframe, limit)
            except Exception as e:
                logger.error("ohlcv_fetch_failed", symbol=symbol, error=str(e))
                return []

    async def fetch_ticker_price(self, symbol: str) -> float | None:
        import yfinance as yf

        def _last() -> float | None:
            price = yf.Ticker(symbol).fast_info.get("lastPrice")
            return float(price) if price else None

        async with self._sem:
            try:
                return await asyncio.to_thread(_last)
            except Exception as e:
                logger.warning("ticker_fetch_failed", symbol=symbol, error=str(e))
                return None

    # ---------------------------------------------------------------- orders
    async def submit_order(self, order: Order) -> Fill | None:
        price = order.price or await self.fetch_ticker_price(order.symbol) or 0.0
        if price <= 0:
            logger.warning("simulated_order_failed_no_price", symbol=order.symbol)
            return None
        commission = round(price * order.quantity * self.config.fee_pct / 100.0, 4)
        fill = Fill(
            order_id=order.order_id, agent_id=order.agent_id, symbol=order.symbol,
            side=order.side, quantity=order.quantity, price=price, commission=commission,
            stop_loss=order.stop_loss, take_profit=order.take_profit,
        )
        order.status = OrderStatus.FILLED
        logger.info("paper_order_simulated_fill", fill_id=fill.fill_id, symbol=order.symbol,
                    price=price, qty=order.quantity, fee=commission)
        return fill
