"""Strategy 2: RSI Divergence — swing reversal on momentum exhaustion."""

from __future__ import annotations

import pandas as pd

from src.core.models import Signal, SignalDirection
from src.indicators.technical import add_rsi, detect_divergence
from src.strategies.base import BaseStrategyAgent


class RSIDivergenceAgent(BaseStrategyAgent):
    strategy_name = "rsi_divergence"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rsi_period = self.params.get("rsi_period", 14)
        self.rsi_oversold = self.params.get("rsi_oversold", 35)
        self.rsi_overbought = self.params.get("rsi_overbought", 65)
        self.pivot_lookback = self.params.get("pivot_lookback", 5)
        self.reward_risk_ratio = self.params.get("reward_risk_ratio", 2.0)

    def _min_bars_required(self) -> int:
        return self.rsi_period + self.pivot_lookback * 3

    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        df = add_rsi(df, self.rsi_period)
        rsi_col = f"rsi_{self.rsi_period}"

        if df[rsi_col].isna().iloc[-1]:
            return None

        curr_rsi = df[rsi_col].iloc[-1]
        curr_close = df["close"].iloc[-1]

        # Detect divergence
        divergence = detect_divergence(
            df["close"], df[rsi_col], lookback=self.pivot_lookback
        )
        latest_div = divergence.iloc[-1]

        # Bullish divergence in oversold zone
        if latest_div == 1 and curr_rsi < self.rsi_oversold:
            swing_low = df["low"].iloc[-self.pivot_lookback:].min()
            stop_loss = swing_low * 0.998  # Just below swing low
            risk = curr_close - stop_loss
            take_profit = curr_close + risk * self.reward_risk_ratio

            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.LONG,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=0.7,
                metadata={"trigger": "bullish_divergence", "rsi": curr_rsi},
            )

        # Bearish divergence in overbought zone
        if latest_div == -1 and curr_rsi > self.rsi_overbought:
            swing_high = df["high"].iloc[-self.pivot_lookback:].max()
            stop_loss = swing_high * 1.002
            risk = stop_loss - curr_close
            take_profit = curr_close - risk * self.reward_risk_ratio

            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.SHORT,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=0.7,
                metadata={"trigger": "bearish_divergence", "rsi": curr_rsi},
            )

        return None
