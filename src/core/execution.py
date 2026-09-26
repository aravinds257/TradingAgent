"""Rate-limited order execution engine using ccxt."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import ccxt.async_support as ccxt_async
import structlog
from aiolimiter import AsyncLimiter
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import ExchangeConfig
from src.core.models import Fill, Order, OrderStatus, Side

logger = structlog.get_logger("execution")


class ExecutionEngine:
    """Handles order submission to the exchange with rate limiting."""

    def __init__(self, config: ExchangeConfig):
        self.config = config
        self._exchange: Optional[ccxt_async.Exchange] = None
        self._limiter = AsyncLimiter(
            max_rate=config.rate_limit_per_min,
            time_period=60.0,
        )

    async def connect(self) -> None:
        """Initialize exchange connection."""
        exchange_class = getattr(ccxt_async, self.config.name)
        self._exchange = exchange_class({
            "apiKey": self.config.api_key or None,
            "secret": self.config.api_secret or None,
            "timeout": self.config.timeout_ms,
            "enableRateLimit": True,
        })

        if self.config.sandbox:
            self._exchange.set_sandbox_mode(True)
            logger.info("exchange_connected", name=self.config.name, mode="sandbox/paper")
        else:
            logger.info("exchange_connected", name=self.config.name, mode="LIVE")

    async def close(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def submit_order(self, order: Order) -> Fill | None:
        """Submit an order to the exchange. Returns a Fill on success."""
        if self._exchange is None:
            logger.error("exchange_not_connected")
            return None

        # Local simulated paper broker mode when no API keys are provided
        if not self.config.api_key:
            price = order.price or await self.fetch_ticker_price(order.symbol) or 0.0
            if price <= 0:
                logger.warning("simulated_order_failed_no_price", symbol=order.symbol)
                return None
            fee_cost = round(price * order.quantity * 0.00075, 4)  # 0.075% standard taker fee
            fill = Fill(
                order_id=order.order_id,
                agent_id=order.agent_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=price,
                commission=fee_cost,
            )
            order.status = OrderStatus.FILLED
            logger.info("paper_order_simulated_fill", fill_id=fill.fill_id,
                        price=price, qty=order.quantity, fee=fee_cost)
            return fill

        async with self._limiter:
            try:
                order_type = "limit" if order.price else "market"
                side_str = order.side.value

                logger.info("submitting_order",
                            order_id=order.order_id, symbol=order.symbol,
                            side=side_str, qty=order.quantity, type=order_type)

                result = await self._exchange.create_order(
                    symbol=order.symbol,
                    type=order_type,
                    side=side_str,
                    amount=order.quantity,
                    price=order.price,
                )

                fill_price = result.get("average") or result.get("price") or order.price or 0
                filled_qty = result.get("filled") or order.quantity
                fee_cost = 0.0
                if result.get("fee"):
                    fee_cost = result["fee"].get("cost", 0.0) or 0.0

                fill = Fill(
                    order_id=order.order_id,
                    agent_id=order.agent_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=filled_qty,
                    price=fill_price,
                    commission=fee_cost,
                )

                order.status = OrderStatus.FILLED
                logger.info("order_filled", fill_id=fill.fill_id,
                            price=fill_price, qty=filled_qty)
                return fill

            except ccxt_async.InsufficientFunds as e:
                order.status = OrderStatus.REJECTED
                logger.warning("insufficient_funds", order_id=order.order_id, error=str(e))
                return None
            except ccxt_async.InvalidOrder as e:
                order.status = OrderStatus.REJECTED
                logger.warning("invalid_order", order_id=order.order_id, error=str(e))
                return None
            except ccxt_async.RateLimitExceeded:
                logger.warning("rate_limit_hit, backing off")
                raise  # Let tenacity retry
            except Exception as e:
                order.status = OrderStatus.REJECTED
                logger.error("order_error", order_id=order.order_id, error=str(e))
                return None

    async def fetch_ticker_price(self, symbol: str) -> float | None:
        """Get latest price for a symbol."""
        if self._exchange is None:
            return None
        async with self._limiter:
            try:
                ticker = await self._exchange.fetch_ticker(symbol)
                return ticker.get("last")
            except Exception as e:
                logger.warning("ticker_fetch_failed", symbol=symbol, error=str(e))
                return None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1h",
                          limit: int = 200) -> list[list]:
        """Fetch historical OHLCV candles."""
        if self._exchange is None:
            return []
        async with self._limiter:
            try:
                return await self._exchange.fetch_ohlcv(
                    symbol, timeframe=timeframe, limit=limit
                )
            except Exception as e:
                logger.error("ohlcv_fetch_failed", symbol=symbol, error=str(e))
                return []
