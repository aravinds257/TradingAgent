"""Strategy 7: Regime-Filtered Supertrend — slow trend following (designed for 4h bars).

Entry (long):  Supertrend bullish AND ADX > adx_min (trending regime) AND close > SMA(sma_period).
Exit:          Supertrend flips bearish (acts as a trailing stop) -> CLOSE signal.
Protective stop: the Supertrend line at entry time.

Backtested (scripts/compare_strategies.py, 2y, BTC/ETH/SOL/BNB, fees+slippage) this was the only
candidate that was net positive after costs, and only on the 4h timeframe. Shorts are disabled by
default because they were net negative in the backtest.
"""

from __future__ import annotations

import pandas as pd

from src.core.models import Fill, Side, Signal, SignalDirection
from src.indicators.technical import add_adx, add_sma, add_supertrend
from src.strategies.base import BaseStrategyAgent


class SupertrendRegimeAgent(BaseStrategyAgent):
    strategy_name = "supertrend_regime"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.st_period = int(self.params.get("st_period", 10))
        self.st_multiplier = float(self.params.get("st_multiplier", 3.0))
        self.adx_period = int(self.params.get("adx_period", 14))
        self.adx_min = float(self.params.get("adx_min", 22))
        self.sma_period = int(self.params.get("sma_period", 200))
        self.allow_short = bool(self.params.get("allow_short", False))
        # symbol -> "long" | "short" ; tracked from fills (including SL exits)
        self._positions: dict[str, str] = {}

    def _min_bars_required(self) -> int:
        return self.sma_period + 5

    async def on_fill(self, fill: Fill) -> None:
        await super().on_fill(fill)
        current = self._positions.get(fill.symbol)
        if current is None:
            self._positions[fill.symbol] = "long" if fill.side == Side.BUY else "short"
        elif (current == "long" and fill.side == Side.SELL) or \
             (current == "short" and fill.side == Side.BUY):
            self._positions.pop(fill.symbol, None)

    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        df = add_supertrend(df, self.st_period, self.st_multiplier)
        df = add_adx(df, self.adx_period)
        df = add_sma(df, self.sma_period)

        sma_col = f"sma_{self.sma_period}"
        adx_col = f"adx_{self.adx_period}"
        last = df.iloc[-1]
        if pd.isna(last[sma_col]) or pd.isna(last[adx_col]) or pd.isna(last["st_line"]):
            return None

        close, st_dir, st_line = last["close"], last["st_dir"], last["st_line"]
        adx, sma = last[adx_col], last[sma_col]
        position = self._positions.get(symbol)
        meta = {"adx": round(float(adx), 2), "sma": float(sma), "st_line": float(st_line)}

        # Exit on Supertrend flip against the open position
        if (position == "long" and st_dir == -1) or (position == "short" and st_dir == 1):
            return Signal(agent_id=self.agent_id, symbol=symbol,
                          direction=SignalDirection.CLOSE, confidence=1.0,
                          metadata={**meta, "trigger": "supertrend_flip"})

        if position is not None or adx <= self.adx_min:
            return None  # already positioned, or ranging market -> stay out

        if st_dir == 1 and close > sma:
            return Signal(agent_id=self.agent_id, symbol=symbol,
                          direction=SignalDirection.LONG, stop_loss=float(st_line),
                          confidence=min(adx / 50, 1.0),
                          metadata={**meta, "trigger": "trend_long"})

        if self.allow_short and st_dir == -1 and close < sma:
            return Signal(agent_id=self.agent_id, symbol=symbol,
                          direction=SignalDirection.SHORT, stop_loss=float(st_line),
                          confidence=min(adx / 50, 1.0),
                          metadata={**meta, "trigger": "trend_short"})

        return None
