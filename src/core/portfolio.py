"""Portfolio manager: tracks positions, capital allocation, and P&L per agent."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from src.core.models import (
    AgentPerformance, AgentStatus, Fill, Order, Position,
    PortfolioSnapshot, Side, Signal, SignalDirection,
)

logger = structlog.get_logger("portfolio")


class VirtualAccount:
    """Tracks capital and positions for a single strategy agent."""

    def __init__(self, agent_id: str, allocated_capital: float):
        self.agent_id = agent_id
        self.allocated_capital = allocated_capital
        self.cash = allocated_capital
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.realized_pnl: float = 0.0
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.peak_equity: float = allocated_capital
        self.max_drawdown: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def equity(self) -> float:
        return self.cash + self.unrealized_pnl

    def update_price(self, symbol: str, price: float) -> None:
        """Update current price for unrealized P&L calculation."""
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.current_price = price
            if pos.side == Side.BUY:
                pos.unrealized_pnl = (price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - price) * pos.quantity

        # Track peak equity and max drawdown
        current_equity = self.equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        drawdown = (self.peak_equity - current_equity) / self.peak_equity * 100
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

    def open_position(self, fill: Fill) -> None:
        """Open a new position from a fill."""
        self.positions[fill.symbol] = Position(
            symbol=fill.symbol,
            agent_id=fill.agent_id,
            side=fill.side,
            quantity=fill.quantity,
            entry_price=fill.price,
            current_price=fill.price,
        )
        cost = fill.price * fill.quantity + fill.commission
        self.cash -= cost
        self.total_trades += 1

    def close_position(self, fill: Fill) -> float:
        """Close an existing position. Returns realized P&L."""
        if fill.symbol not in self.positions:
            return 0.0

        pos = self.positions[fill.symbol]
        if pos.side == Side.BUY:
            pnl = (fill.price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - fill.price) * pos.quantity

        pnl -= fill.commission
        self.realized_pnl += pnl
        self.cash += fill.price * fill.quantity - fill.commission

        if pnl > 0:
            self.winning_trades += 1
        elif pnl < 0:
            self.losing_trades += 1

        del self.positions[fill.symbol]
        return pnl


class PortfolioManager:
    """Manages all virtual accounts and creates orders from signals."""

    def __init__(self, initial_capital: float, risk_per_trade_pct: float = 1.0):
        self.initial_capital = initial_capital
        self.total_cash = initial_capital
        self.risk_per_trade_pct = risk_per_trade_pct
        self.accounts: dict[str, VirtualAccount] = {}
        self._latest_prices: dict[str, float] = {}

    def register_agent(self, agent_id: str, capital_pct: float) -> None:
        """Allocate capital to an agent's virtual account."""
        allocated = self.initial_capital * capital_pct
        self.accounts[agent_id] = VirtualAccount(agent_id, allocated)
        logger.info("agent_registered", agent_id=agent_id, capital=allocated)

    def update_price(self, symbol: str, price: float) -> None:
        """Update price across all accounts."""
        self._latest_prices[symbol] = price
        for account in self.accounts.values():
            account.update_price(symbol, price)

    def signal_to_order(self, signal: Signal) -> Order | None:
        """Convert a strategy signal into a concrete order with position sizing."""
        account = self.accounts.get(signal.agent_id)
        if account is None:
            logger.warning("unknown_agent", agent_id=signal.agent_id)
            return None

        symbol = signal.symbol
        price = self._latest_prices.get(symbol)
        if price is None or price <= 0:
            logger.warning("no_price_for_symbol", symbol=symbol)
            return None

        # Handle CLOSE signals
        if signal.direction == SignalDirection.CLOSE:
            pos = account.positions.get(symbol)
            if pos is None:
                return None
            side = Side.SELL if pos.side == Side.BUY else Side.BUY
            return Order(
                agent_id=signal.agent_id, symbol=symbol,
                side=side, quantity=pos.quantity, signal_id=signal.signal_id,
            )

        # Check if already in a position for this symbol
        if symbol in account.positions:
            logger.info("already_in_position", agent_id=signal.agent_id, symbol=symbol)
            return None

        # Position sizing: risk 1% of account equity
        side = Side.BUY if signal.direction == SignalDirection.LONG else Side.SELL
        risk_amount = account.equity * (self.risk_per_trade_pct / 100.0)

        if signal.stop_loss and signal.stop_loss > 0:
            risk_per_unit = abs(price - signal.stop_loss)
            if risk_per_unit <= 0:
                risk_per_unit = price * 0.02  # Fallback: 2% of price
            quantity = risk_amount / risk_per_unit
        else:
            # Fallback: risk 2% of price as stop distance
            quantity = risk_amount / (price * 0.02)

        # Cap quantity so total cost doesn't exceed available cash
        max_quantity = (account.cash * 0.95) / price  # Keep 5% cash buffer
        quantity = min(quantity, max_quantity)

        if quantity <= 0:
            logger.warning("insufficient_capital", agent_id=signal.agent_id)
            return None

        # Round quantity to reasonable precision
        quantity = round(quantity, 6)

        return Order(
            agent_id=signal.agent_id, symbol=symbol, side=side,
            quantity=quantity, stop_loss=signal.stop_loss,
            take_profit=signal.take_profit, signal_id=signal.signal_id,
        )

    def process_fill(self, fill: Fill) -> float:
        """Process a fill event. Returns realized P&L (0 if opening)."""
        account = self.accounts.get(fill.agent_id)
        if account is None:
            return 0.0

        # Determine if this closes an existing position or opens a new one
        existing = account.positions.get(fill.symbol)
        if existing is not None:
            # Close if sides are opposite
            if existing.side != fill.side:
                return account.close_position(fill)

        # Open new position
        account.open_position(fill)
        return 0.0

    def get_snapshot(self) -> PortfolioSnapshot:
        """Get current portfolio state."""
        all_positions = []
        total_unrealized = 0.0
        total_realized = 0.0
        total_cash = 0.0

        for account in self.accounts.values():
            all_positions.extend(account.positions.values())
            total_unrealized += account.unrealized_pnl
            total_realized += account.realized_pnl
            total_cash += account.cash

        return PortfolioSnapshot(
            total_equity=total_cash + total_unrealized,
            cash=total_cash,
            unrealized_pnl=total_unrealized,
            realized_pnl=total_realized,
            positions=all_positions,
        )

    def get_agent_performance(self, agent_id: str, strategy_name: str,
                               status: AgentStatus) -> AgentPerformance:
        account = self.accounts.get(agent_id)
        if account is None:
            return AgentPerformance(
                agent_id=agent_id, strategy_name=strategy_name, status=status,
                allocated_capital=0, current_equity=0, realized_pnl=0,
                unrealized_pnl=0, total_trades=0, winning_trades=0,
                losing_trades=0,
            )

        total = account.total_trades
        win_rate = (account.winning_trades / total * 100) if total > 0 else 0.0

        return AgentPerformance(
            agent_id=agent_id, strategy_name=strategy_name, status=status,
            allocated_capital=account.allocated_capital,
            current_equity=account.equity,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
            total_trades=total, winning_trades=account.winning_trades,
            losing_trades=account.losing_trades,
            win_rate=win_rate, max_drawdown=account.max_drawdown,
        )
