"""Live market data feed using ccxt WebSocket or polling."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import structlog
import websockets

from src.core.event_bus import EventBus
from src.core.models import Bar

logger = structlog.get_logger("data_feed")


class BinanceWebSocketFeed:
    """Streams real-time kline data from Binance public WebSocket."""

    def __init__(self, symbols: list[str], timeframe: str, event_bus: EventBus):
        self.symbols = symbols
        self.timeframe = timeframe
        self.event_bus = event_bus
        self._running = False
        self._ws = None

    def _build_ws_url(self) -> str:
        """Build the Binance combined WebSocket URL for multiple symbols."""
        # Convert symbols: BTC/USDT -> btcusdt
        streams = []
        for sym in self.symbols:
            clean = sym.replace("/", "").lower()
            streams.append(f"{clean}@kline_{self.timeframe}")
        stream_str = "/".join(streams)
        return f"wss://stream.binance.com:9443/stream?streams={stream_str}"

    async def start(self) -> None:
        """Start streaming. Runs forever until stop() is called."""
        self._running = True
        url = self._build_ws_url()
        logger.info("ws_connecting", url=url, symbols=self.symbols)

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws = ws
                    logger.info("ws_connected")
                    async for raw_msg in ws:
                        if not self._running:
                            break
                        await self._handle_message(raw_msg)
            except websockets.ConnectionClosed:
                logger.warning("ws_disconnected, reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error("ws_error", error=str(e))
                await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _handle_message(self, raw: str) -> None:
        """Parse Binance kline WebSocket message and publish Bar event."""
        try:
            msg = json.loads(raw)
            data = msg.get("data", msg)
            if "k" not in data:
                return

            kline = data["k"]
            # Convert Binance symbol (BTCUSDT) back to ccxt format (BTC/USDT)
            raw_symbol = kline["s"]
            symbol = self._normalize_symbol(raw_symbol)

            bar = Bar(
                symbol=symbol,
                timestamp=datetime.fromtimestamp(kline["t"] / 1000, tz=timezone.utc),
                open=float(kline["o"]),
                high=float(kline["h"]),
                low=float(kline["l"]),
                close=float(kline["c"]),
                volume=float(kline["v"]),
                is_closed=kline["x"],  # True when candle is complete
            )

            await self.event_bus.publish("bar", bar)

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("ws_parse_error", error=str(e))

    def _normalize_symbol(self, raw: str) -> str:
        """Convert BTCUSDT -> BTC/USDT."""
        # Try common quote currencies
        for quote in ["USDT", "BUSD", "BTC", "ETH", "BNB"]:
            if raw.endswith(quote):
                base = raw[:-len(quote)]
                return f"{base}/{quote}"
        return raw


class PollingFeed:
    """Fallback data feed that polls ccxt for candles (no WebSocket needed)."""

    def __init__(self, execution_engine, symbols: list[str],
                 timeframe: str, event_bus: EventBus, poll_interval: int = 60):
        self.execution_engine = execution_engine
        self.symbols = symbols
        self.timeframe = timeframe
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self._running = False
        self._last_timestamps: dict[str, int] = {}

    async def start(self) -> None:
        self._running = True
        logger.info("polling_feed_started", symbols=self.symbols, interval=self.poll_interval)
        while self._running:
            for symbol in self.symbols:
                try:
                    candles = await self.execution_engine.fetch_ohlcv(
                        symbol, self.timeframe, limit=5
                    )
                    for c in candles:
                        ts = c[0]
                        last_ts = self._last_timestamps.get(symbol, 0)
                        if ts > last_ts:
                            bar = Bar(
                                symbol=symbol,
                                timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                                open=c[1], high=c[2], low=c[3],
                                close=c[4], volume=c[5], is_closed=True,
                            )
                            await self.event_bus.publish("bar", bar)
                            self._last_timestamps[symbol] = ts
                except Exception as e:
                    logger.error("polling_error", symbol=symbol, error=str(e))
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        self._running = False
