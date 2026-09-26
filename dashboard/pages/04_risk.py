"""Page 4: Risk Monitor — drawdown, exposure, circuit breakers."""

import sqlite3
import streamlit as st
import pandas as pd
import json
from pathlib import Path
import sys

from src.core.config import load_settings
from dashboard.components.charts import drawdown_gauge

st.set_page_config(page_title="Risk Monitor", page_icon="🛡️", layout="wide")
st.title("🛡️ Risk Monitor")

settings = load_settings()
INITIAL_CAPITAL = settings.general.initial_capital
MAX_DD_LIMIT = settings.risk.max_total_drawdown_pct
DB_PATH = Path(__file__).parent.parent.parent / "data" / "trading_system.db"

def load_risk_data():
    if not DB_PATH.exists():
        return [], []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    equity = [dict(r) for r in conn.execute(
        "SELECT * FROM equity_snapshots ORDER BY timestamp DESC LIMIT 500"
    ).fetchall()]
    agents = [dict(r) for r in conn.execute("SELECT * FROM agent_state").fetchall()]
    conn.close()
    return equity, agents

equity_history, agents = load_risk_data()

if equity_history:
    df = pd.DataFrame(equity_history).sort_values("timestamp")
    current_equity = df["total_equity"].iloc[-1]
    peak = df["total_equity"].cummax()
    current_dd = ((peak.iloc[-1] - current_equity) / peak.iloc[-1]) * 100

    # Drawdown gauge
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(drawdown_gauge(current_dd, MAX_DD_LIMIT), use_container_width=True)
    with col2:
        st.metric("Current Equity", f"${current_equity:,.2f}")
        st.metric("Peak Equity", f"${peak.iloc[-1]:,.2f}")
        st.metric("Current Drawdown", f"{current_dd:.2f}%")
        st.metric("Max Allowed DD", f"{MAX_DD_LIMIT}%")

        if current_dd > MAX_DD_LIMIT * 0.8:
            st.error("⚠️ APPROACHING DRAWDOWN LIMIT — New entries may be blocked")
        elif current_dd > MAX_DD_LIMIT * 0.5:
            st.warning("⚡ Elevated drawdown — monitor closely")
        else:
            st.success("✅ Drawdown within safe limits")

    # Per-agent risk
    st.markdown("---")
    st.subheader("Agent Circuit Breakers")
    if agents:
        for agent in agents:
            agent_dd = agent.get("max_drawdown", 0)
            status = "🟢 Active" if agent["status"] == "running" else "🔴 " + agent["status"]
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.write(f"**{agent['agent_id']}** — {status}")
            col2.write(f"Drawdown: {agent_dd:.2f}%")
            col3.progress(min(agent_dd / (MAX_DD_LIMIT * 2), 1.0))

    # Position Exposure
    st.markdown("---")
    st.subheader("Position Exposure")
    latest = equity_history[0]
    positions_json = latest.get("positions_json", "[]")
    if positions_json:
        positions = json.loads(positions_json)
        if positions:
            df_pos = pd.DataFrame(positions)
            if "current_price" in df_pos.columns and "quantity" in df_pos.columns:
                df_pos["value"] = df_pos["current_price"] * df_pos["quantity"]
                df_pos["pct_of_portfolio"] = (df_pos["value"] / current_equity * 100).round(1)
                st.dataframe(df_pos[["symbol", "agent_id", "side", "quantity",
                                     "entry_price", "current_price", "unrealized_pnl",
                                     "value", "pct_of_portfolio"]], use_container_width=True)
            else:
                st.dataframe(pd.DataFrame(positions), use_container_width=True)
        else:
            st.info("No open positions — portfolio is fully in cash")
else:
    st.info("📭 No data yet. Start the trading engine to begin monitoring risk.")
