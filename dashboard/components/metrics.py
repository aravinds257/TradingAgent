"""Helper functions to compute dashboard metrics from DB data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_portfolio_kpis(equity_history: list[dict],
                            initial_capital: float) -> dict:
    """Compute key portfolio metrics from equity snapshots."""
    if not equity_history:
        return {
            "total_return_pct": 0.0,
            "total_return_usd": 0.0,
            "current_equity": initial_capital,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_pnl": 0.0,
        }

    df = pd.DataFrame(equity_history)
    df = df.sort_values("timestamp")

    current_equity = df["total_equity"].iloc[-1]
    total_return_usd = current_equity - initial_capital
    total_return_pct = (total_return_usd / initial_capital) * 100

    # Max drawdown
    peak = df["total_equity"].cummax()
    drawdown = (peak - df["total_equity"]) / peak * 100
    max_drawdown = drawdown.max()

    # Sharpe ratio (annualized, assuming hourly snapshots)
    if len(df) > 1:
        returns = df["total_equity"].pct_change().dropna()
        if returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(8760)  # hourly -> annual
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    total_pnl = df["realized_pnl"].iloc[-1] if "realized_pnl" in df.columns else 0.0

    return {
        "total_return_pct": round(total_return_pct, 2),
        "total_return_usd": round(total_return_usd, 2),
        "current_equity": round(current_equity, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe, 2),
        "total_pnl": round(total_pnl, 2),
    }


def compute_win_rate(trades: list[dict]) -> float:
    """Compute win rate from trade list."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    return round(wins / len(trades) * 100, 1)
