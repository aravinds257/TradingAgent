"""Strategy 1: Dual Moving Average Crossover — trend following."""

from __future__ import annotations

import pandas as pd

from src.core.models import Signal, SignalDirection
from src.indicators.technical import add_atr, add_ema
from src.strategies.base import BaseStrategyAgent


class MACrossoverAgent(BaseStrategyAgent):
    strategy_name = "ma_crossover"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fast_period = self.params.get("fast_period", 9)
        self.slow_period = self.params.get("slow_period", 21)
        self.atr_period = self.params.get("atr_period", 14)
        self.atr_stop_multiplier = self.params.get("atr_stop_multiplier", 2.0)

    def _min_bars_required(self) -> int:
        return self.slow_period + 5

    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        df = add_ema(df, self.fast_period)
        df = add_ema(df, self.slow_period)
        df = add_atr(df, self.atr_period)

        fast_col = f"ema_{self.fast_period}"
        slow_col = f"ema_{self.slow_period}"
        atr_col = f"atr_{self.atr_period}"

        # Need at least 2 rows to detect crossover
        if df[fast_col].isna().iloc[-2:].any() or df[slow_col].isna().iloc[-2:].any():
            return None

        prev_fast = df[fast_col].iloc[-2]
        prev_slow = df[slow_col].iloc[-2]
        curr_fast = df[fast_col].iloc[-1]
        curr_slow = df[slow_col].iloc[-1]
        curr_close = df["close"].iloc[-1]
        curr_atr = df[atr_col].iloc[-1]

        if pd.isna(curr_atr) or curr_atr <= 0:
            return None

        # Golden Cross: fast crosses above slow
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.LONG,
                stop_loss=curr_close - self.atr_stop_multiplier * curr_atr,
                confidence=min(abs(curr_fast - curr_slow) / curr_close * 100, 1.0),
                metadata={"trigger": "golden_cross", "fast": curr_fast, "slow": curr_slow},
            )

        # Death Cross: fast crosses below slow
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.SHORT,
                stop_loss=curr_close + self.atr_stop_multiplier * curr_atr,
                confidence=min(abs(curr_fast - curr_slow) / curr_close * 100, 1.0),
                metadata={"trigger": "death_cross", "fast": curr_fast, "slow": curr_slow},
            )

        return None
