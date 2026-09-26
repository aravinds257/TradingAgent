"""SQLite database manager with WAL mode for concurrent read/write."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from src.core.models import Fill, PortfolioSnapshot, Signal


class Database:
    """Async SQLite database for trade storage and portfolio tracking."""

    def __init__(self, db_path: str = "data/trading_system.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open connection and create tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        # Performance pragmas
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA synchronous = NORMAL;")
        await self._conn.execute("PRAGMA busy_timeout = 5000;")
        await self._conn.execute("PRAGMA cache_size = -64000;")
        await self._create_tables()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _create_tables(self) -> None:
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                fill_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                commission REAL NOT NULL DEFAULT 0.0,
                pnl REAL DEFAULT 0.0,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                confidence REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                approved INTEGER NOT NULL DEFAULT 0,
                reject_reason TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_equity REAL NOT NULL,
                cash REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                positions_json TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_state (
                agent_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                status TEXT NOT NULL,
                allocated_capital REAL NOT NULL,
                current_equity REAL NOT NULL,
                realized_pnl REAL NOT NULL DEFAULT 0.0,
                unrealized_pnl REAL NOT NULL DEFAULT 0.0,
                total_trades INTEGER NOT NULL DEFAULT 0,
                winning_trades INTEGER NOT NULL DEFAULT 0,
                losing_trades INTEGER NOT NULL DEFAULT 0,
                max_drawdown REAL NOT NULL DEFAULT 0.0,
                peak_equity REAL NOT NULL DEFAULT 0.0,
                state_json TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trades_agent ON trades(agent_id);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
            CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(agent_id);
            CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON equity_snapshots(timestamp);
        """)
        await self._conn.commit()

    # ─── Trade Recording ─────────────────────────────────

    async def record_fill(self, fill: Fill, pnl: float = 0.0) -> None:
        await self._conn.execute(
            """INSERT OR REPLACE INTO trades
               (fill_id, order_id, agent_id, symbol, side, quantity, price, commission, pnl, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fill.fill_id, fill.order_id, fill.agent_id, fill.symbol,
             fill.side.value, fill.quantity, fill.price, fill.commission,
             pnl, fill.timestamp.isoformat())
        )
        await self._conn.commit()

    async def record_signal(self, signal: Signal, approved: bool, reject_reason: str = "") -> None:
        await self._conn.execute(
            """INSERT OR REPLACE INTO signals
               (signal_id, agent_id, symbol, direction, confidence, stop_loss, take_profit,
                approved, reject_reason, timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal.signal_id, signal.agent_id, signal.symbol,
             signal.direction.value, signal.confidence,
             signal.stop_loss, signal.take_profit,
             1 if approved else 0, reject_reason,
             signal.timestamp.isoformat(), json.dumps(signal.metadata))
        )
        await self._conn.commit()

    # ─── Equity Snapshots ────────────────────────────────

    async def record_equity_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        positions_json = json.dumps([p.model_dump(mode="json") for p in snapshot.positions])
        await self._conn.execute(
            """INSERT INTO equity_snapshots
               (timestamp, total_equity, cash, unrealized_pnl, realized_pnl, positions_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (snapshot.timestamp.isoformat(), snapshot.total_equity,
             snapshot.cash, snapshot.unrealized_pnl, snapshot.realized_pnl,
             positions_json)
        )
        await self._conn.commit()

    # ─── Agent State ─────────────────────────────────────

    async def save_agent_state(self, agent_id: str, strategy_name: str, status: str,
                                allocated_capital: float, current_equity: float,
                                realized_pnl: float, unrealized_pnl: float,
                                total_trades: int, winning_trades: int, losing_trades: int,
                                max_drawdown: float, peak_equity: float,
                                state_json: str = "{}") -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """INSERT OR REPLACE INTO agent_state
               (agent_id, strategy_name, status, allocated_capital, current_equity,
                realized_pnl, unrealized_pnl, total_trades, winning_trades, losing_trades,
                max_drawdown, peak_equity, state_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, strategy_name, status, allocated_capital, current_equity,
             realized_pnl, unrealized_pnl, total_trades, winning_trades, losing_trades,
             max_drawdown, peak_equity, state_json, now)
        )
        await self._conn.commit()

    # ─── Query Helpers (for dashboard) ───────────────────

    async def get_all_trades(self, agent_id: str | None = None,
                              symbol: str | None = None,
                              limit: int = 500) -> list[dict]:
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._conn.execute(query, params) as cursor:
            columns = [desc[0] for desc in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    async def get_equity_history(self, limit: int = 1000) -> list[dict]:
        async with self._conn.execute(
            "SELECT timestamp, total_equity, cash, unrealized_pnl, realized_pnl "
            "FROM equity_snapshots ORDER BY timestamp DESC LIMIT ?", (limit,)
        ) as cursor:
            columns = [desc[0] for desc in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    async def get_agent_states(self) -> list[dict]:
        async with self._conn.execute("SELECT * FROM agent_state ORDER BY agent_id") as cursor:
            columns = [desc[0] for desc in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    async def get_agent_trades_summary(self) -> list[dict]:
        """Aggregate trade stats per agent for the dashboard."""
        async with self._conn.execute("""
            SELECT
                agent_id,
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                ROUND(SUM(pnl), 2) as total_pnl,
                ROUND(AVG(pnl), 2) as avg_pnl,
                ROUND(MAX(pnl), 2) as best_trade,
                ROUND(MIN(pnl), 2) as worst_trade
            FROM trades
            GROUP BY agent_id
        """) as cursor:
            columns = [desc[0] for desc in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
