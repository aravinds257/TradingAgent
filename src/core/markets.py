"""Registry of tradable markets — one engine process + one SQLite DB per market."""

from __future__ import annotations

from pathlib import Path

from src.core.config import Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

MARKETS: dict[str, Path] = {
    "crypto": PROJECT_ROOT / "config" / "settings.yaml",
    "us": PROJECT_ROOT / "config" / "markets" / "us_stocks.yaml",
    "india": PROJECT_ROOT / "config" / "markets" / "india_stocks.yaml",
}


def market_settings(market: str) -> Settings:
    return load_settings(MARKETS[market])


def market_db_path(market: str) -> Path:
    db = Path(market_settings(market).general.db_path)
    return db if db.is_absolute() else PROJECT_ROOT / db
