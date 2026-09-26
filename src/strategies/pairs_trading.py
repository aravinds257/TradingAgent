"""Strategy 6: Pairs Trading (Statistical Arbitrage) — market neutral."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.models import Signal, SignalDirection
from src.indicators.technical import compute_zscore
from src.strategies.base import BaseStrategyAgent


class PairsTradingAgent(BaseStrategyAgent):
    strategy_name = "pairs_trading"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pair_a = self.params.get("pair_a", "BTC/USDT")
        self.pair_b = self.params.get("pair_b", "ETH/USDT")
        self.lookback_period = self.params.get("lookback_period", 90)
        self.entry_z = self.params.get("entry_z", 2.0)
        self.exit_z = self.params.get("exit_z", 0.0)
        self.stop_z = self.params.get("stop_z", 3.5)
        self._in_trade: str | None = None  # "long_spread" or "short_spread"

    def _min_bars_required(self) -> int:
        return self.lookback_period + 10

    def _compute_signal(self, symbol: str, df: pd.DataFrame) -> Signal | None:
        # Pairs trading only triggers on pair_a updates (to avoid double-signals)
        if symbol != self.pair_a:
            return None

        # Need bars for both assets
        bars_a = self._bars.get(self.pair_a, [])
        bars_b = self._bars.get(self.pair_b, [])

        if len(bars_a) < self._min_bars_required() or len(bars_b) < self._min_bars_required():
            return None

        # Align by taking the last N bars from each
        n = min(len(bars_a), len(bars_b))
        prices_a = pd.Series([b["close"] for b in bars_a[-n:]])
        prices_b = pd.Series([b["close"] for b in bars_b[-n:]])

        # Compute hedge ratio via simple rolling OLS
        log_a = np.log(prices_a)
        log_b = np.log(prices_b)

        # Rolling OLS hedge ratio (simplified — using recent window)
        window = min(self.lookback_period, n)
        recent_a = log_a.iloc[-window:]
        recent_b = log_b.iloc[-window:]

        # β = cov(A, B) / var(B)
        cov = np.cov(recent_a, recent_b)
        if cov[1, 1] == 0:
            return None
        beta = cov[0, 1] / cov[1, 1]

        # Compute spread and z-score
        spread = log_a - beta * log_b
        z = compute_zscore(spread, lookback=self.lookback_period)

        if z.isna().iloc[-1]:
            return None

        curr_z = z.iloc[-1]
        curr_close = df["close"].iloc[-1]

        # Exit logic
        if self._in_trade == "long_spread" and curr_z >= self.exit_z:
            self._in_trade = None
            return Signal(
                agent_id=self.agent_id, symbol=self.pair_a,
                direction=SignalDirection.CLOSE, confidence=0.8,
                metadata={"trigger": "pairs_exit", "z_score": curr_z},
            )
        if self._in_trade == "short_spread" and curr_z <= self.exit_z:
            self._in_trade = None
            return Signal(
                agent_id=self.agent_id, symbol=self.pair_a,
                direction=SignalDirection.CLOSE, confidence=0.8,
                metadata={"trigger": "pairs_exit", "z_score": curr_z},
            )

        # Stop loss
        if self._in_trade and abs(curr_z) > self.stop_z:
            self._in_trade = None
            return Signal(
                agent_id=self.agent_id, symbol=self.pair_a,
                direction=SignalDirection.CLOSE, confidence=1.0,
                metadata={"trigger": "pairs_stop", "z_score": curr_z},
            )

        # Entry: long spread (buy A, sell B) when z-score is very negative
        if self._in_trade is None and curr_z < -self.entry_z:
            self._in_trade = "long_spread"
            return Signal(
                agent_id=self.agent_id, symbol=self.pair_a,
                direction=SignalDirection.LONG, confidence=0.7,
                metadata={"trigger": "pairs_long_spread", "z_score": curr_z, "beta": beta},
            )

        # Entry: short spread (sell A, buy B) when z-score is very positive
        if self._in_trade is None and curr_z > self.entry_z:
            self._in_trade = "short_spread"
            return Signal(
                agent_id=self.agent_id, symbol=self.pair_a,
                direction=SignalDirection.SHORT, confidence=0.7,
                metadata={"trigger": "pairs_short_spread", "z_score": curr_z, "beta": beta},
            )

        return None
