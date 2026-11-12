"""Backtest the regime-filtered Supertrend (and benchmarks) on top-20 US and India stocks.

Usage:
    python scripts/compare_stocks.py            # uses cached CSVs in data/bars
    python scripts/compare_stocks.py --refresh

Data: Yahoo Finance (daily 10y, hourly 730d). Costs per side: US 0.05%, India 0.15%
(India includes STT/exchange charges for delivery trades).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compare_strategies as cs  # noqa: E402
from src.core.config import load_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARKETS = {
    "US": (ROOT / "config/markets/us_stocks.yaml", 0.0005),
    "India": (ROOT / "config/markets/india_stocks.yaml", 0.0015),
}
cs.PERIODS_PER_YEAR.update({"1d": 252, "1h": 1638})


def fetch_yahoo(ticker: str, interval: str, period: str, refresh: bool) -> pd.DataFrame | None:
    import yfinance as yf

    cs.BARS_DIR.mkdir(parents=True, exist_ok=True)
    path = cs.BARS_DIR / f"yf_{ticker}_{interval}_{period}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        return None
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
    df.to_csv(path)
    return df


STRATS = {
    "buy_hold": cs.s_buy_hold,
    "supertrend+ADX+SMA200 long": lambda d: cs.s_supertrend_regime(d, long_only=True),
    "supertrend+ADX+SMA200 long/short": cs.s_supertrend_regime,
    "ema 50/200 trend long": lambda d: cs.s_ema_trend(d, long_only=True),
    "turtle 55/20 long": lambda d: cs.s_turtle(d, long_only=True),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:8.2f}")

    for market, (cfg_path, cost) in MARKETS.items():
        cs.COST = cost
        symbols = load_settings(cfg_path).symbols
        for interval, period in [("1d", "10y"), ("1h", "730d")]:
            data = {}
            for t in symbols:
                df = fetch_yahoo(t, interval, period, args.refresh)
                if df is not None and len(df) > 300:
                    data[t] = df
            rows = []
            for name, fn in STRATS.items():
                per = []
                for t, df in data.items():
                    pos = fn(df)
                    per.append(cs.stats(cs.run(df, pos), pos, interval))
                row = pd.DataFrame(per).mean()
                row["trades"] = sum(p["trades"] for p in per)
                row["sym+"] = sum(p["ret%"] > 0 for p in per)
                row["beat_bh"] = np.nan
                row.name = name
                rows.append(row)
            span = next(iter(data.values())).index
            print(f"=== {market} {interval} ({span[0].date()} -> {span[-1].date()}, "
                  f"{len(data)} stocks, cost {cost*100:.2f}%/side) ===")
            print(pd.DataFrame(rows).drop(columns="beat_bh").sort_values("sharpe", ascending=False).to_string())
            print()


if __name__ == "__main__":
    main()
