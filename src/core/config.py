"""Load and validate settings.yaml into typed Python objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class ExchangeConfig(BaseModel):
    name: str = "binance"
    sandbox: bool = True
    api_key: str = ""
    api_secret: str = ""
    rate_limit_per_min: int = 1100
    timeout_ms: int = 30000


class DataFeedConfig(BaseModel):
    timeframe: str = "1h"
    warmup_bars: int = 200


class RiskConfig(BaseModel):
    max_daily_drawdown_pct: float = 3.0
    max_total_drawdown_pct: float = 8.0
    max_position_concentration_pct: float = 25.0
    max_risk_per_trade_pct: float = 1.0
    max_open_positions: int = 12


class GeneralConfig(BaseModel):
    mode: str = "paper"
    initial_capital: float = 100000.0
    base_currency: str = "USDT"
    log_level: str = "INFO"
    data_dir: str = "data"
    db_path: str = "data/trading_system.db"


class DashboardConfig(BaseModel):
    refresh_interval_sec: int = 5
    port: int = 8501


class StrategyParams(BaseModel):
    """Generic strategy parameters — each strategy reads its own keys."""
    enabled: bool = True
    capital_pct: float = 0.167
    # All other params stored as extra fields
    model_config = {"extra": "allow"}


class Settings(BaseModel):
    general: GeneralConfig = GeneralConfig()
    symbols: list[str] = ["BTC/USDT", "ETH/USDT"]
    exchange: ExchangeConfig = ExchangeConfig()
    data_feed: DataFeedConfig = DataFeedConfig()
    strategies: dict[str, StrategyParams] = {}
    risk: RiskConfig = RiskConfig()
    dashboard: DashboardConfig = DashboardConfig()


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from YAML file. Falls back to defaults if file not found."""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return Settings(**raw)

    return Settings()
