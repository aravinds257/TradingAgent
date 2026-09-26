"""Strategy 4: Momentum Breakout using Donchian Channels (Turtle Trading)."""

from __future__ import annotations

import pandas as pd

from src.core.models import Signal, SignalDirection
from src.indicators.technical import add_atr, add_donchian_channels
from src.strategies.base import BaseStrategyAgent


class MomentumBreakoutAgent(BaseStrategyAgent):
    strategy_name = "momentum_breakout"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.entry_period = self.params.get("entry_period", 20)
        self.exit_period = self.params.get("exit_period", 10)
        self.atr_period = self.params.get("atr_period", 20)
        self.risk_per_trade_pct = self.params.get("risk_per_trade_pct", 1.0)

    def _min_bars_required(self) -> int:
        return self.entry_period + 5

    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        df = add_donchian_channels(df, self.entry_period, self.exit_period)
        df = add_atr(df, self.atr_period)

        upper_col = f"dc_upper_{self.entry_period}"
        lower_col = f"dc_lower_{self.exit_period}"
        atr_col = f"atr_{self.atr_period}"

        if any(df[c].isna().iloc[-1] for c in [upper_col, lower_col, atr_col]):
            return None

        curr_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        # Use the previous bar's channel values (current bar contributes to current channel)
        dc_upper = df[upper_col].iloc[-2]
        dc_lower = df[lower_col].iloc[-2]
        curr_atr = df[atr_col].iloc[-1]

        if pd.isna(dc_upper) or pd.isna(dc_lower):
            return None

        # Breakout above upper channel
        if curr_close > dc_upper and prev_close <= dc_upper:
            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.LONG,
                stop_loss=curr_close - 2 * curr_atr,
                confidence=0.6,
                metadata={"trigger": "donchian_breakout_up", "dc_upper": dc_upper},
            )

        # Breakout below lower channel
        if curr_close < dc_lower and prev_close >= dc_lower:
            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.SHORT,
                stop_loss=curr_close + 2 * curr_atr,
                confidence=0.6,
                metadata={"trigger": "donchian_breakout_down", "dc_lower": dc_lower},
            )

        return None
