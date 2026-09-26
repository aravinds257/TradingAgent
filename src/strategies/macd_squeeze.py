"""Strategy 5: MACD + Bollinger Band Squeeze — volatility breakout."""

from __future__ import annotations

import pandas as pd

from src.core.models import Signal, SignalDirection
from src.indicators.technical import (
    add_bollinger_bands,
    add_keltner_channels,
    add_macd,
)
from src.strategies.base import BaseStrategyAgent


class MACDSqueezeAgent(BaseStrategyAgent):
    strategy_name = "macd_squeeze"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bb_period = self.params.get("bb_period", 20)
        self.bb_std = self.params.get("bb_std", 2.0)
        self.kc_period = self.params.get("kc_period", 20)
        self.kc_atr_multiplier = self.params.get("kc_atr_multiplier", 1.5)
        self.macd_fast = self.params.get("macd_fast", 12)
        self.macd_slow = self.params.get("macd_slow", 26)
        self.macd_signal = self.params.get("macd_signal", 9)

    def _min_bars_required(self) -> int:
        return max(self.bb_period, self.macd_slow) + 10

    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        df = add_bollinger_bands(df, self.bb_period, self.bb_std)
        df = add_keltner_channels(df, self.kc_period, self.kc_atr_multiplier)
        df = add_macd(df, self.macd_fast, self.macd_slow, self.macd_signal)

        required = ["bb_lower", "bb_upper", "kc_lower", "kc_upper", "macd_histogram"]
        if any(df[c].isna().iloc[-1] for c in required):
            return None

        curr_close = df["close"].iloc[-1]

        # Check squeeze state (BB inside KC)
        prev_squeeze = (df["bb_lower"].iloc[-2] > df["kc_lower"].iloc[-2] and
                         df["bb_upper"].iloc[-2] < df["kc_upper"].iloc[-2])
        curr_squeeze = (df["bb_lower"].iloc[-1] > df["kc_lower"].iloc[-1] and
                         df["bb_upper"].iloc[-1] < df["kc_upper"].iloc[-1])

        # Squeeze just fired (was in squeeze, now released)
        if prev_squeeze and not curr_squeeze:
            hist_curr = df["macd_histogram"].iloc[-1]
            hist_prev = df["macd_histogram"].iloc[-2]

            # Bullish: histogram positive and rising
            if hist_curr > 0 and hist_curr > hist_prev:
                return Signal(
                    agent_id=self.agent_id,
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    stop_loss=df["bb_lower"].iloc[-1],
                    confidence=0.65,
                    metadata={"trigger": "squeeze_fire_long", "macd_hist": hist_curr},
                )

            # Bearish: histogram negative and falling
            if hist_curr < 0 and hist_curr < hist_prev:
                return Signal(
                    agent_id=self.agent_id,
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    stop_loss=df["bb_upper"].iloc[-1],
                    confidence=0.65,
                    metadata={"trigger": "squeeze_fire_short", "macd_hist": hist_curr},
                )

        return None
