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
