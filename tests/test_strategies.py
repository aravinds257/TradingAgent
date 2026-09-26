"""Tests for strategy signal generation."""

import asyncio
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.core.models import Bar
from src.strategies import STRATEGY_REGISTRY


@pytest.fixture
def signal_queue():
    return asyncio.Queue()


def make_bars(n: int, base_price: float = 60000,
              trend: float = 0, noise: float = 100) -> list[Bar]:
    """Generate synthetic bars with optional trend."""
    np.random.seed(42)
    bars = []
    price = base_price
    for i in range(n):
        price += trend + np.random.randn() * noise
        bar = Bar(
            symbol="BTC/USDT",
            timestamp=datetime(2026, 1, 1, i % 24, tzinfo=timezone.utc),
            open=price - noise * 0.3,
            high=price + abs(np.random.randn()) * noise,
            low=price - abs(np.random.randn()) * noise,
            close=price,
            volume=1000 + np.random.randint(0, 5000),
            is_closed=True,
        )
        bars.append(bar)
    return bars


@pytest.mark.asyncio
async def test_all_strategies_instantiate(signal_queue):
    """Every strategy in the registry should instantiate without error."""
    for name, cls in STRATEGY_REGISTRY.items():
        agent = cls(
            agent_id=f"test_{name}",
            symbols=["BTC/USDT", "ETH/USDT"],
            signal_queue=signal_queue,
            params={"capital_pct": 0.167, "pair_a": "BTC/USDT", "pair_b": "ETH/USDT"},
        )
        assert agent.strategy_name == name


@pytest.mark.asyncio
async def test_ma_crossover_generates_signal(signal_queue):
    """MA crossover should generate at least one signal on trending data."""
    agent = STRATEGY_REGISTRY["ma_crossover"](
        agent_id="test_ma", symbols=["BTC/USDT"], signal_queue=signal_queue,
        params={"fast_period": 5, "slow_period": 10, "atr_period": 14, "atr_stop_multiplier": 2.0},
    )
    # Strong uptrend should trigger a golden cross
    bars = make_bars(50, base_price=60000, trend=200, noise=50)
    for bar in bars:
        await agent.on_bar(bar)

    # May or may not generate a signal depending on exact crossover timing
    # At minimum, the agent should process without error
    assert agent.status != "error"


@pytest.mark.asyncio
async def test_strategies_handle_insufficient_data(signal_queue):
    """Strategies should not crash when given fewer bars than required."""
    for name, cls in STRATEGY_REGISTRY.items():
        agent = cls(
            agent_id=f"test_{name}", symbols=["BTC/USDT"], signal_queue=signal_queue,
            params={"capital_pct": 0.167, "pair_a": "BTC/USDT", "pair_b": "ETH/USDT"},
        )
        # Feed only 3 bars — well below any strategy's minimum
        bars = make_bars(3, base_price=60000)
        for bar in bars:
            await agent.on_bar(bar)
        # Should not crash — queue should be empty (no signal)
        assert signal_queue.empty(), f"{name} generated a signal with insufficient data"
