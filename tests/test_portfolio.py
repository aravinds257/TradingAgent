"""Tests for portfolio management."""

import pytest

from src.core.models import Fill, Side, Signal, SignalDirection
from src.core.portfolio import PortfolioManager


@pytest.fixture
def portfolio():
    pm = PortfolioManager(100000)
    pm.register_agent("trend", 0.5)
    pm.register_agent("revert", 0.5)
    pm.update_price("BTC/USDT", 65000.0)
    return pm


def test_register_agent(portfolio):
    assert "trend" in portfolio.accounts
    assert portfolio.accounts["trend"].allocated_capital == 50000.0


def test_signal_to_order(portfolio):
    signal = Signal(agent_id="trend", symbol="BTC/USDT",
                    direction=SignalDirection.LONG, stop_loss=63000.0)
    order = portfolio.signal_to_order(signal)
    assert order is not None
    assert order.side == Side.BUY
    assert order.quantity > 0


def test_duplicate_position_blocked(portfolio):
    # First signal creates an order
    signal1 = Signal(agent_id="trend", symbol="BTC/USDT",
                     direction=SignalDirection.LONG, stop_loss=63000.0)
    order1 = portfolio.signal_to_order(signal1)
    assert order1 is not None

    # Simulate fill
    fill = Fill(order_id=order1.order_id, agent_id="trend",
                symbol="BTC/USDT", side=Side.BUY, quantity=order1.quantity,
                price=65000.0)
    portfolio.process_fill(fill)

    # Second signal for same symbol should be blocked
    signal2 = Signal(agent_id="trend", symbol="BTC/USDT",
                     direction=SignalDirection.LONG, stop_loss=63000.0)
    order2 = portfolio.signal_to_order(signal2)
    assert order2 is None


def test_pnl_calculation(portfolio):
    # Open position
    fill_open = Fill(order_id="o1", agent_id="trend", symbol="BTC/USDT",
                     side=Side.BUY, quantity=0.1, price=65000.0)
    portfolio.process_fill(fill_open)

    # Close with profit
    fill_close = Fill(order_id="o2", agent_id="trend", symbol="BTC/USDT",
                      side=Side.SELL, quantity=0.1, price=66000.0)
    pnl = portfolio.process_fill(fill_close)
    assert pnl == pytest.approx(100.0, abs=1.0)  # (66000-65000) * 0.1


def test_snapshot(portfolio):
    snapshot = portfolio.get_snapshot()
    assert snapshot.total_equity == pytest.approx(100000.0)
    assert snapshot.cash == pytest.approx(100000.0)


def test_reversal_signal_closes_position(portfolio):
    # Open LONG position
    sig_long = Signal(agent_id="trend", symbol="BTC/USDT", direction=SignalDirection.LONG)
    order_buy = portfolio.signal_to_order(sig_long)
    fill_buy = Fill(order_id=order_buy.order_id, agent_id="trend", symbol="BTC/USDT",
                    side=Side.BUY, quantity=order_buy.quantity, price=65000.0)
    portfolio.process_fill(fill_buy)
    assert "BTC/USDT" in portfolio.accounts["trend"].positions

    # Reversal signal (SHORT) should generate an order to close the LONG position
    sig_short = Signal(agent_id="trend", symbol="BTC/USDT", direction=SignalDirection.SHORT)
    order_close = portfolio.signal_to_order(sig_short)
    assert order_close is not None
    assert order_close.side == Side.SELL
    assert order_close.quantity == order_buy.quantity


def test_stop_loss_and_take_profit_triggers(portfolio):
    # Open position with SL=64000 and TP=67000
    fill = Fill(order_id="o1", agent_id="trend", symbol="BTC/USDT",
                side=Side.BUY, quantity=0.1, price=65000.0,
                stop_loss=64000.0, take_profit=67000.0)
    portfolio.process_fill(fill)

    # Price at 64500 (between SL and TP) -> no exit order
    assert len(portfolio.check_stop_loss_take_profit_orders("BTC/USDT", 64500.0)) == 0

    # Price drops to 63900 (below SL) -> triggers exit order
    sl_orders = portfolio.check_stop_loss_take_profit_orders("BTC/USDT", 63900.0)
    assert len(sl_orders) == 1
    assert sl_orders[0].side == Side.SELL
    assert sl_orders[0].quantity == 0.1

    # Price rises to 67500 (above TP) -> triggers exit order
    tp_orders = portfolio.check_stop_loss_take_profit_orders("BTC/USDT", 67500.0)
    assert len(tp_orders) == 1
    assert tp_orders[0].side == Side.SELL

