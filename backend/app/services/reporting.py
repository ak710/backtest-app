"""Generate Plotly chart configs returned as JSON-serializable dicts."""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.models.data_models import BacktestResult, PreparedData
from app.models.llm_schemas import LLMAnalysisResponse
from app.utils.logging import get_logger

logger = get_logger(__name__)

_COLORS = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
]


def _fig_to_dict(fig: go.Figure) -> dict:
    return json.loads(fig.to_json())


def generate_equity_comparison_chart(
    results: list[BacktestResult],
    initial_capital: float = 100_000.0,
) -> dict:
    """Single chart with all equity curves overlaid."""
    fig = go.Figure()
    visible_results = [r for r in results if not r.skipped and r.equity_curve]

    for idx, result in enumerate(visible_results):
        dates = [ep.date for ep in result.equity_curve]
        equity = [ep.equity for ep in result.equity_curve]
        label = f"{result.indicator_name.upper()} / {result.strategy_template}"
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=equity,
                mode="lines",
                name=label,
                line=dict(color=_COLORS[idx % len(_COLORS)], width=1.5),
            )
        )

    # Buy-and-hold baseline
    if visible_results and visible_results[0].equity_curve:
        first = visible_results[0]
        dates = [ep.date for ep in first.equity_curve]
        n = len(dates)
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[initial_capital] * n,
                mode="lines",
                name="Initial Capital",
                line=dict(color="grey", width=1, dash="dot"),
            )
        )

    fig.update_layout(
        title="Equity Curves Comparison",
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        template="plotly_dark",
        legend=dict(orientation="v", x=1.02),
        height=500,
    )
    return _fig_to_dict(fig)


def generate_price_indicator_chart(
    prepared: PreparedData,
    result: BacktestResult,
) -> dict:
    """Price chart with trade markers for a single strategy."""
    if result.skipped or not result.equity_curve:
        return {}

    df = prepared.df
    close = df["close"]
    dates = [str(d.date() if hasattr(d, "date") else d) for d in df.index]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        subplot_titles=[
            f"{prepared.symbol} Price – {result.indicator_name.upper()} ({result.strategy_template})",
            "Equity Curve",
        ],
        vertical_spacing=0.08,
    )

    # Price candlestick
    fig.add_trace(
        go.Scatter(x=dates, y=list(close), mode="lines", name="Close", line=dict(color="#636EFA", width=1.5)),
        row=1, col=1,
    )

    # Trade markers
    for trade in result.trades:
        fig.add_trace(
            go.Scatter(
                x=[trade.entry_date],
                y=[trade.entry_price],
                mode="markers",
                name="Buy",
                marker=dict(color="lime", size=10, symbol="triangle-up"),
                showlegend=False,
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=[trade.exit_date],
                y=[trade.exit_price],
                mode="markers",
                name="Sell",
                marker=dict(color="red", size=10, symbol="triangle-down"),
                showlegend=False,
            ),
            row=1, col=1,
        )

    # Equity sub-chart
    eq_dates = [ep.date for ep in result.equity_curve]
    eq_values = [ep.equity for ep in result.equity_curve]
    fig.add_trace(
        go.Scatter(x=eq_dates, y=eq_values, mode="lines", name="Equity", line=dict(color="#00CC96", width=1.5)),
        row=2, col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=600,
        showlegend=True,
        legend=dict(orientation="h", y=-0.1),
    )
    return _fig_to_dict(fig)


def generate_metrics_summary_chart(results: list[BacktestResult]) -> dict:
    """Bar chart comparing Sharpe and max drawdown across strategies."""
    valid = [r for r in results if not r.skipped and r.metrics]
    if not valid:
        return {}

    labels = [f"{r.indicator_name}\n{r.strategy_template}" for r in valid]
    sharpes = [r.metrics.get("sharpe", 0) for r in valid]
    drawdowns = [abs(r.metrics.get("max_drawdown", 0)) * 100 for r in valid]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Sharpe Ratio", "Max Drawdown (%)"],
    )

    sharpe_colors = ["#00CC96" if s > 0 else "#EF553B" for s in sharpes]
    fig.add_trace(
        go.Bar(x=labels, y=sharpes, marker_color=sharpe_colors, name="Sharpe"),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=labels, y=drawdowns, marker_color="#FFA15A", name="Max Drawdown %"),
        row=1, col=2,
    )

    fig.update_layout(
        title="Strategy Performance Comparison",
        template="plotly_dark",
        height=450,
        showlegend=False,
    )
    fig.update_xaxes(tickangle=45)
    return _fig_to_dict(fig)


def generate_report(
    prepared: PreparedData,
    base_results: list[BacktestResult],
    modified_results: list[BacktestResult],
    llm_analysis: LLMAnalysisResponse,
    initial_capital: float = 100_000.0,
) -> dict:
    """Assemble the full report dict returned to the frontend."""
    all_results = base_results + modified_results

    # ── Summary charts (always shown) ──────────────────────────────────────
    summary_charts = []
    eq_chart = generate_equity_comparison_chart(all_results, initial_capital)
    if eq_chart:
        summary_charts.append({"id": "equity_comparison", "title": "Equity Curves – All Strategies", "figure": eq_chart})

    metrics_chart = generate_metrics_summary_chart(all_results)
    if metrics_chart:
        summary_charts.append({"id": "metrics_comparison", "title": "Performance Comparison", "figure": metrics_chart})

    # ── Per-strategy charts (one per row, in same order as results) ─────────
    def _make_strategy_charts(results: list[BacktestResult], prefix: str) -> list[dict]:
        out = []
        for i, result in enumerate(results):
            if result.skipped or not result.equity_curve:
                out.append({})
                continue
            chart = generate_price_indicator_chart(prepared, result)
            out.append({
                "id": f"{prefix}_{i}_{result.indicator_name}_{result.strategy_template}",
                "title": f"{result.indicator_name.upper()} – {result.strategy_template}",
                "figure": chart,
            } if chart else {})
        return out

    strategy_charts = _make_strategy_charts(base_results, "price")
    modified_strategy_charts = _make_strategy_charts(modified_results, "modified")

    return {
        "charts": summary_charts,
        "strategy_charts": strategy_charts,
        "modified_strategy_charts": modified_strategy_charts,
    }
