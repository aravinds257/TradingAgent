"""Streamlit dashboard entry point — multi-page layout."""

import streamlit as st

st.set_page_config(
    page_title="Trading Agents Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 Multi-Agent Trading Dashboard")
st.markdown("Navigate using the sidebar to view portfolio, agent performance, trades, and risk metrics.")

# Sidebar
st.sidebar.title("🤖 Trading Agents")
st.sidebar.markdown("---")
st.sidebar.info("Start the trading engine with:\n```\npython -m src.main\n```")

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Database Controls")
if st.sidebar.button("🗑️ Reset All History & Trades", type="secondary"):
    import sqlite3
    from pathlib import Path
    from src.core.config import load_settings
    import datetime

    settings = load_settings()
    cap = settings.general.initial_capital
    db_path = Path(__file__).parent.parent / "data" / "trading_system.db"

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
        st.sidebar.success(f"History reset to ${cap:,.2f} baseline!")
        st.rerun()
