"""Reusable Plotly chart components for the dashboard."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def equity_curve_chart(df: pd.DataFrame) -> go.Figure:
    """Line chart of total equity over time."""
    fig = px.line(df, x="timestamp", y="total_equity",
                  title="Portfolio Equity Curve",
                  labels={"total_equity": "Total Equity (USDT)", "timestamp": "Time"})
    fig.update_layout(height=400, template="plotly_dark",
                      hovermode="x unified")
    return fig


def agent_equity_comparison(agent_data: list[dict]) -> go.Figure:
    """Bar chart comparing agent performance."""
    df = pd.DataFrame(agent_data)
    if df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Realized P&L", x=df["agent_id"], y=df["realized_pnl"],
                          marker_color=["green" if v >= 0 else "red" for v in df["realized_pnl"]]))
    fig.add_trace(go.Bar(name="Unrealized P&L", x=df["agent_id"], y=df["unrealized_pnl"],
                          marker_color="orange", opacity=0.7))
    fig.update_layout(title="Agent P&L Comparison", barmode="group",
                      template="plotly_dark", height=400)
    return fig


def trade_distribution_chart(trades: list[dict]) -> go.Figure:
    """Histogram of trade P&L distribution."""
    df = pd.DataFrame(trades)
    if df.empty or "pnl" not in df.columns:
        return go.Figure()

    fig = px.histogram(df, x="pnl", nbins=30, title="Trade P&L Distribution",
                       color_discrete_sequence=["#636EFA"])
    fig.add_vline(x=0, line_dash="dash", line_color="white")
    fig.update_layout(template="plotly_dark", height=350)
    return fig


def drawdown_gauge(current_dd: float, max_dd_limit: float) -> go.Figure:
    """Gauge chart for current drawdown vs limit."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=current_dd,
        title={"text": "Current Drawdown %"},
        delta={"reference": 0, "increasing": {"color": "red"}, "decreasing": {"color": "green"}},
        gauge={
            "axis": {"range": [0, max_dd_limit * 1.5]},
            "bar": {"color": "red" if current_dd > max_dd_limit * 0.7 else "orange"},
            "steps": [
                {"range": [0, max_dd_limit * 0.5], "color": "darkgreen"},
                {"range": [max_dd_limit * 0.5, max_dd_limit * 0.8], "color": "darkorange"},
                {"range": [max_dd_limit * 0.8, max_dd_limit * 1.5], "color": "darkred"},
            ],
            "threshold": {
                "line": {"color": "white", "width": 4},
                "thickness": 0.75,
                "value": max_dd_limit,
            },
        },
    ))
    fig.update_layout(height=300, template="plotly_dark")
    return fig
