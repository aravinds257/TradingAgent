"""Page 3: Trade History with filters."""

import sqlite3
import streamlit as st
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from dashboard.components.charts import trade_distribution_chart

st.set_page_config(page_title="Trade History", page_icon="📝", layout="wide")
st.title("📝 Trade History")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "trading_system.db"

def load_trades(agent_filter=None, symbol_filter=None, limit=500):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM trades WHERE 1=1"
    params = []
    if agent_filter and agent_filter != "All":
        query += " AND agent_id = ?"
        params.append(agent_filter)
    if symbol_filter and symbol_filter != "All":
        query += " AND symbol = ?"
        params.append(symbol_filter)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    trades = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return trades

def get_filter_options():
    if not DB_PATH.exists():
        return ["All"], ["All"]
    conn = sqlite3.connect(str(DB_PATH))
    agents = ["All"] + [r[0] for r in conn.execute("SELECT DISTINCT agent_id FROM trades").fetchall()]
    symbols = ["All"] + [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM trades").fetchall()]
    conn.close()
    return agents, symbols

# Filters
agents, symbols = get_filter_options()
col1, col2, col3 = st.columns(3)
with col1:
    agent_filter = st.selectbox("Filter by Agent", agents)
with col2:
    symbol_filter = st.selectbox("Filter by Symbol", symbols)
with col3:
    limit = st.number_input("Max trades", value=500, min_value=10, max_value=5000)

trades = load_trades(agent_filter, symbol_filter, limit)

if trades:
    df = pd.DataFrame(trades)

    # Summary stats
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trades", len(df))
    col2.metric("Total P&L", f"${df['pnl'].sum():,.2f}")
    col3.metric("Avg P&L", f"${df['pnl'].mean():,.2f}")
    col4.metric("Win Rate",
                f"{(df['pnl'] > 0).sum() / len(df) * 100:.1f}%" if len(df) > 0 else "N/A")

    # P&L Distribution
    st.plotly_chart(trade_distribution_chart(trades), use_container_width=True)

    # Trade Table
    st.subheader("Trade Log")
    st.dataframe(df, use_container_width=True, height=400)
else:
    st.info("📭 No trades recorded yet.")
