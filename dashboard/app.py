"""Streamlit dashboard entry point — multi-page layout."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from dashboard.components.market import select_market  # noqa: E402

st.set_page_config(
    page_title="Trading Agents Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 Multi-Agent Trading Dashboard")
st.markdown("Pick a market in the sidebar, then navigate to view portfolio, agent performance, "
            "trades, and risk metrics.")

# Sidebar
st.sidebar.title("🤖 Trading Agents")
MKT = select_market()
st.sidebar.markdown("---")
st.sidebar.info("Start all engines with:\n```\n./start.sh\n```")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Database Controls")
if st.sidebar.button(f"🗑️ Reset {MKT.name} History & Trades", type="secondary"):
    import datetime
    import sqlite3

    cap = MKT.settings.general.initial_capital
    db_path = MKT.db_path

    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM signals")
        conn.execute("DELETE FROM equity_snapshots")
        conn.execute("DELETE FROM agent_state")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO equity_snapshots (timestamp, total_equity, cash, unrealized_pnl, realized_pnl, positions_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now, cap, cap, 0.0, 0.0, "[]")
        )
        conn.commit()
        conn.close()
        st.sidebar.success(f"History reset to {MKT.currency}{cap:,.2f} baseline!")
        st.rerun()

# Market summary: one card per market
st.markdown("---")
st.subheader("🌍 Markets")
from src.core.markets import MARKETS, market_db_path, market_settings  # noqa: E402
import sqlite3  # noqa: E402

cols = st.columns(len(MARKETS))
for col, key in zip(cols, MARKETS):
    s = market_settings(key)
    db = market_db_path(key)
    equity, n_trades = s.general.initial_capital, 0
    if db.exists():
        try:
            conn = sqlite3.connect(str(db))
            row = conn.execute("SELECT total_equity FROM equity_snapshots ORDER BY id DESC LIMIT 1").fetchone()
            n_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            conn.close()
            if row:
                equity = row[0]
        except sqlite3.Error:
            pass
    ret = (equity / s.general.initial_capital - 1) * 100
    col.metric(f"{s.general.market_name}", f"{s.general.currency_symbol}{equity:,.2f}", f"{ret:+.2f}%")
    col.caption(f"{len(s.symbols)} symbols · {s.data_feed.timeframe} bars · {n_trades} fills")
