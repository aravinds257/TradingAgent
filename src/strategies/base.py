"""Abstract base class for all strategy agents."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd
import structlog

from src.core.models import AgentStatus, Bar, Fill, Signal


class BaseStrategyAgent(ABC):
    """Base class for strategy agents.

    Subclasses must implement:
      - strategy_name (class attribute)
      - _compute_signal(symbol, df) -> Signal | None
    """

    strategy_name: str = "base"

    def __init__(self, agent_id: str, symbols: list[str],
                 signal_queue: asyncio.Queue, params: dict):
        self.agent_id = agent_id
        self.symbols = symbols
        self.signal_queue = signal_queue
        self.params = params
        self.status = AgentStatus.CREATED
        self.logger = structlog.get_logger(f"agent.{agent_id}")

        # Each agent maintains its own bar history per symbol
        self._bars: dict[str, list[dict]] = {s: [] for s in symbols}
        self._max_bars = params.get("max_bars", 500)

    async def on_bar(self, bar: Bar) -> None:
        """Called when a new candle arrives. Stores it and checks for signals."""
        if bar.symbol not in self.symbols:
            return
        if not bar.is_closed:
            return  # Only process closed candles

        # Store bar data
        bar_dict = {
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        self._bars[bar.symbol].append(bar_dict)

        # Keep only recent bars
        if len(self._bars[bar.symbol]) > self._max_bars:
            self._bars[bar.symbol] = self._bars[bar.symbol][-self._max_bars:]

        # Build DataFrame and compute signal
        df = pd.DataFrame(self._bars[bar.symbol])
        if len(df) < self._min_bars_required():
            return

        try:
            signal = self._compute_signal(bar.symbol, df)
            if signal is not None:
                self.logger.info("signal_generated",
                                  symbol=signal.symbol,
                                  direction=signal.direction.value,
                                  confidence=signal.confidence)
                await self.signal_queue.put(signal)
        except Exception as e:
            self.logger.error("signal_computation_error", error=str(e), exc_info=True)

    async def on_fill(self, fill: Fill) -> None:
        """Called when one of this agent's orders is filled."""
        self.logger.info("fill_received", symbol=fill.symbol,
                          side=fill.side.value, price=fill.price, qty=fill.quantity)

    @abstractmethod
    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        """Analyze the DataFrame and return a Signal or None.

        The DataFrame has columns: timestamp, open, high, low, close, volume.
        Add any indicators you need in this method.
        """
        ...

    @abstractmethod
    def _min_bars_required(self) -> int:
        """Minimum number of bars needed before signal generation."""
        ...

    def get_state(self) -> dict:
        """Return internal state for dashboard inspection."""
        return {
            "agent_id": self.agent_id,
            "strategy": self.strategy_name,
            "status": self.status.value,
            "bars_stored": {s: len(bars) for s, bars in self._bars.items()},
        }
