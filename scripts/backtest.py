"""Simple backtester script for evaluating strategies on historical data."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from src.core.config import load_settings
from src.core.execution import ExecutionEngine
from src.core.models import Bar, SignalDirection
from src.strategies import STRATEGY_REGISTRY


async def run_backtest(strategy_name: str, symbol: str, timeframe: str = "1h", limit: int = 500):
    settings = load_settings()
    execution = ExecutionEngine(settings.exchange)
    await execution.connect()

    print(f"Fetching {limit} {timeframe} candles for {symbol}...")
    raw = await execution.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    await execution.close()

    if not raw:
        print("Failed to fetch historical candles.")
        return

    bars = [
        Bar(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc),
            open=c[1], high=c[2], low=c[3], close=c[4], volume=c[5],
            is_closed=True,
        )
        for c in raw
    ]

    agent_cls = STRATEGY_REGISTRY.get(strategy_name)
    if not agent_cls:
        print(f"Strategy {strategy_name} not found.")
        return

    signal_queue = asyncio.Queue()
    params = settings.strategies.get(strategy_name, {})
    params_dict = params.model_dump() if hasattr(params, "model_dump") else {}

    agent = agent_cls(
        agent_id=f"backtest_{strategy_name}",
        symbols=[symbol],
        signal_queue=signal_queue,
        params=params_dict,
    )

    print(f"Running backtest for {strategy_name} across {len(bars)} bars...")
    signals = []
    for bar in bars:
        await agent.on_bar(bar)
        while not signal_queue.empty():
            signals.append(await signal_queue.get())

    print(f"\n--- Backtest Results ---")
    print(f"Total Bars: {len(bars)}")
    print(f"Signals Generated: {len(signals)}")
    for sig in signals:
        print(f"  [{sig.timestamp}] {sig.direction.value.upper()} @ conf={sig.confidence:.2f} stop={sig.stop_loss} tp={sig.take_profit} meta={sig.metadata}")


def main():
    parser = argparse.ArgumentParser(description="Run backtest on strategy")
    parser.add_argument("--strategy", default="ma_crossover", choices=list(STRATEGY_REGISTRY.keys()))
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()

    asyncio.run(run_backtest(args.strategy, args.symbol, args.timeframe, args.limit))


if __name__ == "__main__":
    main()
