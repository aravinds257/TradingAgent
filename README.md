# 🤖 Multi-Agent Algorithmic Trading System

A fully local, multi-agent trading system featuring 6 proven strategies, centralized risk management, and a real-time Streamlit dashboard.

## Strategies

| # | Strategy | Type | Win Rate |
|---|----------|------|----------|
| 1 | Dual MA Crossover | Trend Following | 30-40% |
| 2 | RSI Divergence | Swing Reversal | 55-65% |
| 3 | Bollinger Mean Reversion | Counter-Trend | 65-75% |
| 4 | Momentum Breakout (Donchian) | Trend Breakout | 35-45% |
| 5 | MACD + BB Squeeze | Volatility Breakout | 50-60% |
| 6 | Pairs Trading (Stat Arb) | Market Neutral | 65-75% |

## Quick Start

```bash
# Setup virtualenv and install dependencies
cd /Users/aravinds257/Work/trading-agents
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 🚀 Start both Trading Engine + Dashboard in one command:
./start.sh

# 🔄 Start both AND reset all previous history / trades:
./start.sh --reset

# (Alternative using Python directly)
python start.py
python start.py --reset

# Run tests
pytest tests/ -v
```

## Configuration

Edit `config/settings.yaml` to:
- Change trading pairs
- Adjust strategy parameters
- Set risk limits
- Switch between paper and live mode

## Architecture

- **6 Independent Strategy Agents** analyze markets in parallel
- **Central Risk Engine** validates every order before execution
- **Portfolio Manager** handles position sizing, netting, and P&L tracking
- **Binance WebSocket** streams real-time candle data (free, no API key needed for data)
- **SQLite** stores trades, equity snapshots, and agent state
- **Streamlit Dashboard** shows real-time performance across 4 pages

## ⚠️ Disclaimer

This is for educational and research purposes. Not financial advice. Always start with paper trading.
