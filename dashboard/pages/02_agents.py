"""Page 2: Per-Agent Performance breakdown."""

import sqlite3
import streamlit as st
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from dashboard.components.charts import agent_equity_comparison

st.set_page_config(page_title="Agent Performance", page_icon="🤖", layout="wide")
st.title("🤖 Agent Performance")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "trading_system.db"

def load_agent_data():
    if not DB_PATH.exists():
        return [], []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    agents = [dict(r) for r in conn.execute("SELECT * FROM agent_state ORDER BY agent_id").fetchall()]
    trade_summary = [dict(r) for r in conn.execute("""
        SELECT agent_id,
               COUNT(*) as total_trades,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
               ROUND(SUM(pnl), 2) as total_pnl,
               ROUND(AVG(pnl), 2) as avg_pnl,
               ROUND(MAX(pnl), 2) as best_trade,
               ROUND(MIN(pnl), 2) as worst_trade
        FROM trades GROUP BY agent_id
    """).fetchall()]
    conn.close()
    return agents, trade_summary

agents, trade_summary = load_agent_data()

if agents:
    # Status indicators
    st.subheader("Agent Status")
    cols = st.columns(len(agents))
    status_colors = {"running": "🟢", "paused": "🟡", "stopped": "🔴", "error": "🔴"}
    for i, agent in enumerate(agents):
        with cols[i]:
            icon = status_colors.get(agent["status"], "⚪")
            st.markdown(f"### {icon} {agent['agent_id']}")
            st.caption(f"Strategy: {agent['strategy_name']}")
            st.metric("Equity", f"${agent['current_equity']:,.2f}",
                       f"${agent['realized_pnl']:+,.2f}")

    # Comparison chart
    st.markdown("---")
    st.plotly_chart(agent_equity_comparison(agents), use_container_width=True)

    # Detailed table
    st.subheader("📊 Detailed Metrics")
    df_agents = pd.DataFrame(agents)
    display_cols = ["agent_id", "strategy_name", "status", "allocated_capital",
                    "current_equity", "realized_pnl", "unrealized_pnl",
                    "total_trades", "winning_trades", "losing_trades", "max_drawdown"]
    available_cols = [c for c in display_cols if c in df_agents.columns]
    st.dataframe(df_agents[available_cols], use_container_width=True)

    # Trade summary per agent
    if trade_summary:
        st.subheader("📋 Trade Summary by Agent")
        st.dataframe(pd.DataFrame(trade_summary), use_container_width=True)
else:
    st.info("📭 No agent data yet. Start the trading engine to begin.")
