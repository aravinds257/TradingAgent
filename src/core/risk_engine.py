"""Central risk engine — every order must pass these checks before execution."""

from __future__ import annotations

import structlog

from src.core.config import RiskConfig
from src.core.models import Order, Side
from src.core.portfolio import PortfolioManager

logger = structlog.get_logger("risk_engine")


class RiskCheckResult:
    def __init__(self, approved: bool, reason: str = ""):
        self.approved = approved
        self.reason = reason


class RiskEngine:
    """Pre-trade risk gatekeeper."""

    def __init__(self, config: RiskConfig, portfolio: PortfolioManager):
        self.config = config
        self.portfolio = portfolio
        self._daily_pnl: float = 0.0
        self._kill_switch: bool = False

    def reset_daily(self) -> None:
        """Call at start of each trading day to reset daily limits."""
        self._daily_pnl = 0.0
        self._kill_switch = False
        logger.info("daily_risk_reset")

    def update_daily_pnl(self, pnl: float) -> None:
        """Track cumulative daily P&L."""
        self._daily_pnl += pnl

    def check_order(self, order: Order) -> RiskCheckResult:
        """Run all pre-trade risk checks. Returns approval or rejection with reason."""

        # 1. Kill switch
        if self._kill_switch:
            return RiskCheckResult(False, "kill_switch_active")

        # 2. Daily drawdown limit
        snapshot = self.portfolio.get_snapshot()
        daily_dd_pct = abs(self._daily_pnl / self.portfolio.initial_capital * 100)
        if self._daily_pnl < 0 and daily_dd_pct >= self.config.max_daily_drawdown_pct:
            self._kill_switch = True
            logger.error("daily_drawdown_breached", pct=daily_dd_pct)
            return RiskCheckResult(False, f"daily_drawdown_{daily_dd_pct:.1f}%")

        # 3. Total drawdown limit
        total_dd_pct = (self.portfolio.initial_capital - snapshot.total_equity) / \
                        self.portfolio.initial_capital * 100
        if total_dd_pct >= self.config.max_total_drawdown_pct:
            self._kill_switch = True
            logger.error("total_drawdown_breached", pct=total_dd_pct)
            return RiskCheckResult(False, f"total_drawdown_{total_dd_pct:.1f}%")

        # 4. Max open positions
        total_positions = sum(
            len(acc.positions) for acc in self.portfolio.accounts.values()
        )
        if total_positions >= self.config.max_open_positions:
            return RiskCheckResult(False, f"max_positions_{total_positions}")

        # 5. Position concentration check
        if order.price and order.price > 0:
            order_value = order.quantity * order.price
        elif order.symbol in self.portfolio._latest_prices:
            order_value = order.quantity * self.portfolio._latest_prices[order.symbol]
        else:
            order_value = 0

        if snapshot.total_equity > 0 and order_value > 0:
            concentration = order_value / snapshot.total_equity * 100
            if concentration > self.config.max_position_concentration_pct:
                return RiskCheckResult(
                    False, f"concentration_{concentration:.1f}%_exceeds_{self.config.max_position_concentration_pct}%"
                )

        # 6. Per-agent circuit breaker
        account = self.portfolio.accounts.get(order.agent_id)
        if account:
            agent_dd = (account.allocated_capital - account.equity) / \
                        account.allocated_capital * 100
            if agent_dd > self.config.max_daily_drawdown_pct * 2:
                logger.warning("agent_circuit_breaker", agent_id=order.agent_id, dd=agent_dd)
                return RiskCheckResult(False, f"agent_drawdown_{agent_dd:.1f}%")

        # 7. Quantity sanity
        if order.quantity <= 0:
            return RiskCheckResult(False, "invalid_quantity")

        logger.info("order_approved", order_id=order.order_id,
                     agent_id=order.agent_id, symbol=order.symbol)
        return RiskCheckResult(True)
