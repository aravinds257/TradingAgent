"""Sidebar market selector shared by all dashboard pages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from src.core.config import Settings
from src.core.markets import MARKETS, market_db_path, market_settings


@dataclass
class MarketContext:
    key: str
    settings: Settings
    db_path: Path
    currency: str
    name: str


def select_market() -> MarketContext:
    """Render the market picker in the sidebar (persists across pages) and return its context."""
    labels = {k: market_settings(k).general.market_name for k in MARKETS}
    if "market" not in st.session_state:
        st.session_state["market"] = next(iter(MARKETS))
    key = st.sidebar.selectbox("🌍 Market", list(MARKETS), format_func=labels.get, key="market")
    settings = market_settings(key)
    return MarketContext(
        key=key,
        settings=settings,
        db_path=market_db_path(key),
        currency=settings.general.currency_symbol,
        name=settings.general.market_name,
    )
