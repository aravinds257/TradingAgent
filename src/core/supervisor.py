"""Supervisor: manages agent lifecycle, warmup, and the main trading loop."""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime, timezone

import structlog

from src.core.config import Settings, load_settings
from src.core.event_bus import EventBus
from src.core.execution import ExecutionEngine
from src.core.logging_setup import setup_logging
from src.core.models import AgentStatus, Bar, Fill, Signal
from src.core.portfolio import PortfolioManager
from src.core.risk_engine import RiskEngine
from src.data.feed import BinanceWebSocketFeed, PollingFeed
from src.data.historical import fetch_warmup_bars
from src.db.database import Database
from src.strategies import STRATEGY_REGISTRY
from src.strategies.base import BaseStrategyAgent

logger = structlog.get_logger("supervisor")


class Supervisor:
    """Orchestrates all components: agents, feeds, execution, risk, DB."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.event_bus = EventBus()
        self.db = Database(self.settings.general.db_path)
        self.execution = ExecutionEngine(self.settings.exchange)
        self.portfolio = PortfolioManager(
            self.settings.general.initial_capital,
            self.settings.risk.max_risk_per_trade_pct,
        )
        self.risk_engine = RiskEngine(self.settings.risk, self.portfolio)
        self.agents: dict[str, BaseStrategyAgent] = {}
        self._signal_queue: asyncio.Queue[Signal] = asyncio.Queue()
        self._running = False

    async def start(self) -> None:
        """Initialize everything and run the main loop."""
        setup_logging(self.settings.general.log_level)
        logger.info("supervisor_starting", mode=self.settings.general.mode)

        # Connect DB and exchange
        await self.db.connect()
        await self.execution.connect()

        # Register and create agents
        self._create_agents()

        # Warmup: feed historical bars to agents
        await self._warmup_agents()

        # Start main loops
        self._running = True
        self._setup_signal_handlers()

        tasks = [
            asyncio.create_task(self._run_data_feed(), name="data_feed"),
            asyncio.create_task(self._process_signals(), name="signal_processor"),
            asyncio.create_task(self._process_bars(), name="bar_processor"),
            asyncio.create_task(self._periodic_snapshot(), name="snapshotter"),
        ]

        logger.info("supervisor_running", agents=list(self.agents.keys()))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("supervisor_shutting_down")
        finally:
            await self._shutdown()

    def _create_agents(self) -> None:
        """Instantiate strategy agents based on config."""
        enabled_strategies = [
            (name, model) for name, model in self.settings.strategies.items() if model.enabled
        ]
        total_weight = sum(m.capital_pct for _, m in enabled_strategies) or 1.0

        for name, params_model in enabled_strategies:
            agent_cls = STRATEGY_REGISTRY.get(name)
            if agent_cls is None:
                logger.warning("unknown_strategy", name=name)
                continue

            # Determine which symbols this agent trades
            params = params_model.model_dump()
            if name == "pairs_trading":
                symbols = [params.get("pair_a", "BTC/USDT"),
                           params.get("pair_b", "ETH/USDT")]
            else:
                symbols = list(self.settings.symbols)

            agent_id = f"{name}"
            agent = agent_cls(
                agent_id=agent_id,
                symbols=symbols,
                signal_queue=self._signal_queue,
                params=params,
            )
            agent.status = AgentStatus.RUNNING
            self.agents[agent_id] = agent

            # Register normalized capital allocation (exact fraction of portfolio)
            normalized_pct = params_model.capital_pct / total_weight
            self.portfolio.register_agent(agent_id, normalized_pct)
            logger.info("agent_created", agent_id=agent_id, strategy=name,
                        symbols=symbols, capital_pct=round(normalized_pct, 4))

    async def _warmup_agents(self) -> None:
        """Feed historical bars to agents so indicators are primed."""
        logger.info("warmup_starting", bars=self.settings.data_feed.warmup_bars)

        all_symbols = set()
        for agent in self.agents.values():
            all_symbols.update(agent.symbols)

        for symbol in all_symbols:
            bars = await fetch_warmup_bars(
                self.execution, symbol,
                self.settings.data_feed.timeframe,
                self.settings.data_feed.warmup_bars,
            )
            if not bars:
                continue

            # Feed all but the last bar for history warmup
            for bar in bars[:-1]:
                self.portfolio.update_price(bar.symbol, bar.close)
                for agent in self.agents.values():
                    if bar.symbol in agent.symbols:
                        await agent.on_bar(bar)

            # Drain older historical signals
            while not self._signal_queue.empty():
                self._signal_queue.get_nowait()

            # Now feed the latest closed bar so current setups can trigger
            latest_bar = bars[-1]
            self.portfolio.update_price(latest_bar.symbol, latest_bar.close)
            for agent in self.agents.values():
                if latest_bar.symbol in agent.symbols:
                    await agent.on_bar(latest_bar)

        # Record initial snapshot to DB immediately so dashboard has baseline
        snapshot = self.portfolio.get_snapshot()
        await self.db.record_equity_snapshot(snapshot)
        for agent_id, agent in self.agents.items():
            perf = self.portfolio.get_agent_performance(
                agent_id, agent.strategy_name, agent.status
            )
            await self.db.save_agent_state(
                agent_id=agent_id,
                strategy_name=agent.strategy_name,
                status=agent.status.value,
                allocated_capital=perf.allocated_capital,
                current_equity=perf.current_equity,
                realized_pnl=perf.realized_pnl,
                unrealized_pnl=perf.unrealized_pnl,
                total_trades=perf.total_trades,
                winning_trades=perf.winning_trades,
                losing_trades=perf.losing_trades,
                max_drawdown=perf.max_drawdown,
                peak_equity=self.portfolio.accounts[agent_id].peak_equity,
            )

        logger.info("warmup_complete")

    async def _run_data_feed(self) -> None:
        """Start the live data feed."""
        symbols = list(self.settings.symbols)
        tf = self.settings.data_feed.timeframe

        try:
            feed = BinanceWebSocketFeed(symbols, tf, self.event_bus)
            await feed.start()
        except Exception as e:
            logger.warning("ws_feed_failed, falling back to polling", error=str(e))
            feed = PollingFeed(self.execution, symbols, tf, self.event_bus, poll_interval=60)
            await feed.start()

    async def _process_bars(self) -> None:
        """Consume bar events and dispatch to all agents."""
        bar_queue = self.event_bus.subscribe("bar")

        while self._running:
            try:
                bar: Bar = await asyncio.wait_for(bar_queue.get(), timeout=5.0)
                self.portfolio.update_price(bar.symbol, bar.close)

                for agent in self.agents.values():
                    if agent.status == AgentStatus.RUNNING and bar.symbol in agent.symbols:
                        try:
                            await agent.on_bar(bar)
                        except Exception as e:
                            logger.error("agent_bar_error",
                                          agent_id=agent.agent_id, error=str(e))
                            agent.status = AgentStatus.ERROR

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _process_signals(self) -> None:
        """Consume signals from agents, run risk checks, execute orders."""
        while self._running:
            try:
                signal: Signal = await asyncio.wait_for(
                    self._signal_queue.get(), timeout=5.0
                )

                # Convert signal to order
                order = self.portfolio.signal_to_order(signal)
                if order is None:
                    await self.db.record_signal(signal, approved=False,
                                                 reject_reason="no_order_generated")
                    continue

                # Risk check
                risk_result = self.risk_engine.check_order(order)
                if not risk_result.approved:
                    logger.warning("order_rejected", order_id=order.order_id,
                                    reason=risk_result.reason)
                    await self.db.record_signal(signal, approved=False,
                                                 reject_reason=risk_result.reason)
                    continue

                await self.db.record_signal(signal, approved=True)

                # Execute order
                fill = await self.execution.submit_order(order)
                if fill is None:
                    continue

                # Process fill
                pnl = self.portfolio.process_fill(fill)
                self.risk_engine.update_daily_pnl(pnl)
                await self.db.record_fill(fill, pnl=pnl)

                # Notify agent
                agent = self.agents.get(fill.agent_id)
                if agent:
                    await agent.on_fill(fill)

                logger.info("trade_complete",
                            agent=fill.agent_id, symbol=fill.symbol,
                            side=fill.side.value, price=fill.price,
                            qty=fill.quantity, pnl=pnl)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("signal_processing_error", error=str(e), exc_info=True)

    async def _periodic_snapshot(self) -> None:
        """Periodically save portfolio snapshots to DB."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Every minute
                snapshot = self.portfolio.get_snapshot()
                await self.db.record_equity_snapshot(snapshot)

                # Save agent state
                for agent_id, agent in self.agents.items():
                    perf = self.portfolio.get_agent_performance(
                        agent_id, agent.strategy_name, agent.status
                    )
                    await self.db.save_agent_state(
                        agent_id=agent_id,
                        strategy_name=agent.strategy_name,
                        status=agent.status.value,
                        allocated_capital=perf.allocated_capital,
                        current_equity=perf.current_equity,
                        realized_pnl=perf.realized_pnl,
                        unrealized_pnl=perf.unrealized_pnl,
                        total_trades=perf.total_trades,
                        winning_trades=perf.winning_trades,
                        losing_trades=perf.losing_trades,
                        max_drawdown=perf.max_drawdown,
                        peak_equity=self.portfolio.accounts[agent_id].peak_equity,
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("snapshot_error", error=str(e))

    def _setup_signal_handlers(self) -> None:
        """Handle SIGINT/SIGTERM for graceful shutdown."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                pass

    async def stop(self) -> None:
        self._running = False
        logger.info("stop_requested")

    async def _shutdown(self) -> None:
        """Graceful shutdown: persist state, close connections."""
        logger.info("shutting_down")

        # Final snapshot
        try:
            snapshot = self.portfolio.get_snapshot()
            await self.db.record_equity_snapshot(snapshot)
        except Exception:
            pass

        for agent in self.agents.values():
            agent.status = AgentStatus.STOPPED

        await self.execution.close()
        await self.db.close()
        logger.info("shutdown_complete")
