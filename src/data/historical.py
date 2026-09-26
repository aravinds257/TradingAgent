"""Historical data fetcher — downloads candle data for backtesting and warmup."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import structlog

from src.core.execution import ExecutionEngine
from src.core.models import Bar

logger = structlog.get_logger("historical")


async def fetch_warmup_bars(execution: ExecutionEngine, symbol: str,
                             timeframe: str, limit: int = 200) -> list[Bar]:
    """Fetch recent historical bars for strategy warmup."""
    raw = await execution.fetch_ohlcv(symbol, timeframe, limit=limit)
    bars = []
    for candle in raw:
        bars.append(Bar(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
            open=candle[1], high=candle[2], low=candle[3],
            close=candle[4], volume=candle[5], is_closed=True,
        ))
    logger.info("warmup_loaded", symbol=symbol, bars=len(bars))
    return bars


async def save_bars_to_parquet(bars: list[Bar], data_dir: str = "data/bars") -> None:
    """Save bars to partitioned Parquet files."""
    if not bars:
        return

    records = [b.model_dump() for b in bars]
    df = pd.DataFrame(records)
    symbol_clean = bars[0].symbol.replace("/", "-")
    path = Path(data_dir) / f"{symbol_clean}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine="pyarrow")
    logger.info("bars_saved", path=str(path), count=len(bars))
