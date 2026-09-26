"""Page 1: Portfolio Overview — equity curve, KPIs, positions."""

import sqlite3
import streamlit as st
import pandas as pd
from pathlib import Path

# Add project root to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.components.charts import equity_curve_chart
from dashboard.components.metrics import compute_portfolio_kpis, compute_win_rate

st.set_page_config(page_title="Portfolio Overview", page_icon="📈", layout="wide")
st.title("📈 Portfolio Overview")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "trading_system.db"

def load_data():
    if not DB_PATH.exists():
        return [], [], 100000.0
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    equity = [dict(r) for r in conn.execute(
        "SELECT * FROM equity_snapshots ORDER BY timestamp DESC LIMIT 1000"
    ).fetchall()]

    trades = [dict(r) for r in conn.execute(
        "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 500"
    ).fetchall()]

    conn.close()
    return equity, trades, 100000.0

equity_history, all_trades, initial_capital = load_data()

# KPI Cards
kpis = compute_portfolio_kpis(equity_history, initial_capital)
win_rate = compute_win_rate(all_trades)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("💰 Total Equity", f"${kpis['current_equity']:,.2f}",
            f"{kpis['total_return_pct']:+.2f}%")
col2.metric("📈 Total P&L", f"${kpis['total_return_usd']:,.2f}")
col3.metric("📉 Max Drawdown", f"{kpis['max_drawdown_pct']:.2f}%")
col4.metric("📊 Sharpe Ratio", f"{kpis['sharpe_ratio']:.2f}")
col5.metric("🎯 Win Rate", f"{win_rate:.1f}%")

# Equity Curve
st.markdown("---")
if equity_history:
    df_equity = pd.DataFrame(equity_history).sort_values("timestamp")
    st.plotly_chart(equity_curve_chart(df_equity), use_container_width=True)
else:
    st.info("📭 No equity data yet. Start the trading engine to begin tracking.")

# Current Positions
st.subheader("📋 Open Positions")
if equity_history:
    import json
    latest = equity_history[0]
    positions_json = latest.get("positions_json", "[]")
    if positions_json:
        positions = json.loads(positions_json)
        if positions:
            st.dataframe(pd.DataFrame(positions), use_container_width=True)
        else:
            st.info("No open positions")
else:
    st.info("No data available")

# Auto-refresh
st.markdown("---")
refresh = st.checkbox("🔄 Auto-refresh (every 10 seconds)", value=False)
if refresh:
    import time
    time.sleep(10)
    st.rerun()
