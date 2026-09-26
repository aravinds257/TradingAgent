"""Shared data models for the trading system. All modules import from here."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── Enums ───────────────────────────────────────────────

class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE = "close"  # close existing position


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AgentStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ─── Market Data ─────────────────────────────────────────

class Bar(BaseModel):
    """A single OHLCV candle."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool = True  # False if candle is still forming


# ─── Strategy Signal ─────────────────────────────────────

class Signal(BaseModel):
    """Output from a strategy agent — a proposed trade intention."""
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_id: str
    symbol: str
    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    stop_loss: Optional[float] = None     # absolute price
    take_profit: Optional[float] = None   # absolute price
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)  # strategy-specific info


# ─── Orders & Fills ──────────────────────────────────────

class Order(BaseModel):
    """An order to be submitted to the exchange."""
    order_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_id: str
    symbol: str
    side: Side
    quantity: float
    price: Optional[float] = None  # None = market order
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    signal_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Fill(BaseModel):
    """Confirmation that an order was executed."""
    fill_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    order_id: str
    agent_id: str
    symbol: str
    side: Side
    quantity: float
    price: float
    commission: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Portfolio State ─────────────────────────────────────

class Position(BaseModel):
    """A position held by a specific agent."""
    symbol: str
    agent_id: str
    side: Side
    quantity: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PortfolioSnapshot(BaseModel):
    """Point-in-time snapshot of the entire portfolio."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_equity: float
    cash: float
    unrealized_pnl: float
    realized_pnl: float
    positions: list[Position] = Field(default_factory=list)


class AgentPerformance(BaseModel):
    """Performance metrics for a single agent."""
    agent_id: str
    strategy_name: str
    status: AgentStatus
    allocated_capital: float
    current_equity: float
    realized_pnl: float
    unrealized_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
