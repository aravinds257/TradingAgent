"""Strategy 3: Bollinger Bands + RSI Mean Reversion — counter-trend."""

from __future__ import annotations

import pandas as pd

from src.core.models import Signal, SignalDirection
from src.indicators.technical import add_atr, add_bollinger_bands, add_rsi
from src.strategies.base import BaseStrategyAgent


class BollingerMeanReversionAgent(BaseStrategyAgent):
    strategy_name = "bollinger_mean_reversion"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bb_period = self.params.get("bb_period", 20)
        self.bb_std = self.params.get("bb_std", 2.0)
        self.rsi_period = self.params.get("rsi_period", 14)
        self.rsi_oversold = self.params.get("rsi_oversold", 30)
        self.rsi_overbought = self.params.get("rsi_overbought", 70)
        self.atr_period = self.params.get("atr_period", 14)
        self.atr_stop_multiplier = self.params.get("atr_stop_multiplier", 1.5)

    def _min_bars_required(self) -> int:
        return max(self.bb_period, self.rsi_period) + 5

    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        df = add_bollinger_bands(df, self.bb_period, self.bb_std)
        df = add_rsi(df, self.rsi_period)
        df = add_atr(df, self.atr_period)

        rsi_col = f"rsi_{self.rsi_period}"
        atr_col = f"atr_{self.atr_period}"

        if any(df[c].isna().iloc[-1] for c in ["bb_lower", "bb_upper", "bb_mid", rsi_col, atr_col]):
            return None

        curr_close = df["close"].iloc[-1]
        curr_rsi = df[rsi_col].iloc[-1]
        bb_lower = df["bb_lower"].iloc[-1]
        bb_upper = df["bb_upper"].iloc[-1]
        bb_mid = df["bb_mid"].iloc[-1]
        curr_atr = df[atr_col].iloc[-1]

        # Long: price at/below lower BB AND RSI oversold
        if curr_close <= bb_lower and curr_rsi <= self.rsi_oversold:
            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.LONG,
                stop_loss=curr_close - self.atr_stop_multiplier * curr_atr,
                take_profit=bb_mid,
                confidence=0.75,
                metadata={"trigger": "bb_rsi_oversold", "rsi": curr_rsi,
                           "bb_lower": bb_lower},
            )

        # Short: price at/above upper BB AND RSI overbought
        if curr_close >= bb_upper and curr_rsi >= self.rsi_overbought:
            return Signal(
                agent_id=self.agent_id,
                symbol=symbol,
                direction=SignalDirection.SHORT,
                stop_loss=curr_close + self.atr_stop_multiplier * curr_atr,
                take_profit=bb_mid,
                confidence=0.75,
                metadata={"trigger": "bb_rsi_overbought", "rsi": curr_rsi,
                           "bb_upper": bb_upper},
            )

        return None
