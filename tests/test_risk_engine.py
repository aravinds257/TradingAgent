"""Tests for the central risk engine."""

import pytest

from src.core.config import RiskConfig
from src.core.models import Order, Side
from src.core.portfolio import PortfolioManager
from src.core.risk_engine import RiskEngine


@pytest.fixture
def setup():
    pm = PortfolioManager(100000)
    pm.register_agent("agent_1", 0.5)
    pm.register_agent("agent_2", 0.5)
    pm.update_price("BTC/USDT", 65000.0)
    config = RiskConfig(
        max_daily_drawdown_pct=3.0,
        max_total_drawdown_pct=8.0,
        max_position_concentration_pct=25.0,
        max_risk_per_trade_pct=1.0,
        max_open_positions=4,
    )
    risk = RiskEngine(config, pm)
    return pm, risk


def test_normal_order_approved(setup):
    pm, risk = setup
    order = Order(agent_id="agent_1", symbol="BTC/USDT", side=Side.BUY,
                  quantity=0.1, price=65000.0)
    result = risk.check_order(order)
    assert result.approved


def test_invalid_quantity_rejected(setup):
    pm, risk = setup
    order = Order(agent_id="agent_1", symbol="BTC/USDT", side=Side.BUY,
                  quantity=0.0, price=65000.0)
    result = risk.check_order(order)
    assert not result.approved
    assert "invalid_quantity" in result.reason


def test_kill_switch_after_drawdown(setup):
    pm, risk = setup
    # Simulate large daily loss
    risk.update_daily_pnl(-3500)  # 3.5% of 100k

    order = Order(agent_id="agent_1", symbol="BTC/USDT", side=Side.BUY,
                  quantity=0.1, price=65000.0)
    result = risk.check_order(order)
    assert not result.approved


def test_concentration_limit(setup):
    pm, risk = setup
    # Order worth more than 25% of portfolio
    order = Order(agent_id="agent_1", symbol="BTC/USDT", side=Side.BUY,
                  quantity=1.0, price=65000.0)  # $65k = 65% of 100k
    result = risk.check_order(order)
    assert not result.approved
    assert "concentration" in result.reason
