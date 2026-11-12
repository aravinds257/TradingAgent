"""Tests for multi-market (stocks) support."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.core.markets import MARKETS, market_settings
from src.core.models import Bar, Fill, Side, Signal, SignalDirection
from src.core.portfolio import PortfolioManager


@pytest.mark.parametrize("market", list(MARKETS))
def test_market_configs_load(market):
    s = market_settings(market)
    assert s.symbols
    assert s.strategies["supertrend_regime"].enabled
    if market != "crypto":
        assert s.exchange.name == "yahoo"
        assert s.data_feed.timeframe == "1d"
        assert len(s.symbols) == 20


def test_india_uses_whole_shares():
    s = market_settings("india")
    assert s.general.allow_fractional is False
    assert s.general.currency_symbol == "₹"


def test_whole_share_rounding():
    pm = PortfolioManager(100000, 1.0, allow_fractional=False)
    pm.register_agent("st", 1.0)
    pm.update_price("MARUTI.NS", 12345.0)
    order = pm.signal_to_order(Signal(agent_id="st", symbol="MARUTI.NS",
                                      direction=SignalDirection.LONG, stop_loss=11500.0))
    assert order is not None
    assert order.quantity == int(order.quantity) and order.quantity >= 1


def test_whole_share_too_expensive_is_skipped():
    pm = PortfolioManager(1000, 1.0, allow_fractional=False)
    pm.register_agent("st", 1.0)
    pm.update_price("MARUTI.NS", 12345.0)
    order = pm.signal_to_order(Signal(agent_id="st", symbol="MARUTI.NS",
                                      direction=SignalDirection.LONG, stop_loss=11500.0))
    assert order is None


def test_no_leverage_cap():
    """Total open notional may never exceed agent equity."""
    pm = PortfolioManager(10000, 1.0)
    pm.register_agent("st", 1.0)
    for i in range(10):
        sym = f"S{i}"
        pm.update_price(sym, 100.0)
        order = pm.signal_to_order(Signal(agent_id="st", symbol=sym,
                                          direction=SignalDirection.LONG, stop_loss=95.0))
        if order is None:
            continue
        pm.process_fill(Fill(order_id=order.order_id, agent_id="st", symbol=sym,
                             side=Side.BUY, quantity=order.quantity, price=100.0))
    acct = pm.accounts["st"]
    notional = sum(p.quantity * p.current_price for p in acct.positions.values())
    assert notional <= acct.equity + 1e-6


def test_yahoo_drops_incomplete_bars(monkeypatch):
    """Only completed bars may be returned (today's forming daily bar is excluded)."""
    import yfinance as yf

    from src.data.yahoo import YahooMarketData

    now = pd.Timestamp.now(tz="America/New_York").normalize()
    idx = pd.DatetimeIndex([now - pd.Timedelta(days=2), now - pd.Timedelta(days=1), now])
    df = pd.DataFrame({"Open": [1, 2, 3], "High": [1, 2, 3], "Low": [1, 2, 3],
                       "Close": [1, 2, 3], "Volume": [10, 20, 30]}, index=idx)

    class FakeTicker:
        def __init__(self, sym):
            pass

        def history(self, **kwargs):
            return df

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    rows = YahooMarketData._download("AAPL", "1d", 10)
    assert [r[4] for r in rows] == [1.0, 2.0]


@pytest.mark.asyncio
async def test_agent_ignores_duplicate_bars():
    import asyncio

    from src.strategies import STRATEGY_REGISTRY

    agent = STRATEGY_REGISTRY["supertrend_regime"](
        agent_id="st", symbols=["AAPL"], signal_queue=asyncio.Queue(), params={})
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mk = lambda t, c: Bar(symbol="AAPL", timestamp=t, open=c, high=c, low=c, close=c,
                          volume=1, is_closed=True)
    await agent.on_bar(mk(t0, 100))
    await agent.on_bar(mk(t0 + timedelta(days=1), 101))
    await agent.on_bar(mk(t0 + timedelta(days=1), 102))  # same candle, final value
    await agent.on_bar(mk(t0, 99))                        # stale
    closes = [b["close"] for b in agent._bars["AAPL"]]
    assert closes == [100, 102]
