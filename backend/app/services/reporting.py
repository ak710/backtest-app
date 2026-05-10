"""Generate Plotly chart configs returned as JSON-serializable dicts."""
from __future__ import annotations

import json

import numpy as np
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

_LOG_SCALE_MENU = dict(
    type="buttons",
    direction="left",
    buttons=[
        dict(args=[{"yaxis.type": "linear"}], label="Linear", method="relayout"),
        dict(args=[{"yaxis.type": "log"}], label="Log", method="relayout"),
    ],
    pad={"r": 10, "t": 10},
    showactive=True,
    x=0.01,
    xanchor="left",
    y=1.12,
    yanchor="top",
)


def _fig_to_dict(fig: go.Figure) -> dict:
    return json.loads(fig.to_json())


def _compute_drawdown_pct(equity_values: list[float]) -> list[float]:
    if not equity_values:
        return []
    eq = np.array(equity_values, dtype=float)
    running_max = np.maximum.accumulate(eq)
    with np.errstate(invalid="ignore", divide="ignore"):
        dd = np.where(running_max > 0, (eq - running_max) / running_max * 100, 0.0)
    return [float(v) for v in dd]


def generate_equity_comparison_chart(
    results: list[BacktestResult],
    initial_capital: float = 100_000.0,
    benchmark_result: BacktestResult | None = None,
) -> dict:
    """All strategy equity curves overlaid with buy-and-hold benchmark."""
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

    # Buy-and-hold benchmark line
    if benchmark_result and benchmark_result.equity_curve:
        bh_dates = [ep.date for ep in benchmark_result.equity_curve]
        bh_equity = [ep.equity for ep in benchmark_result.equity_curve]
        fig.add_trace(
            go.Scatter(
                x=bh_dates,
                y=bh_equity,
                mode="lines",
                name="Buy & Hold",
                line=dict(color="gold", width=2, dash="dash"),
            )
        )
    elif visible_results and visible_results[0].equity_curve:
        # Fallback: flat initial capital line
        dates = [ep.date for ep in visible_results[0].equity_curve]
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[initial_capital] * len(dates),
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
        updatemenus=[_LOG_SCALE_MENU],
    )
    return _fig_to_dict(fig)


def generate_price_indicator_chart(
    prepared: PreparedData,
    result: BacktestResult,
) -> dict:
    """Price chart with trade markers, equity curve, and drawdown subplot."""
    if result.skipped or not result.equity_curve:
        return {}

    df = prepared.df
    close = df["close"]
    dates = [str(d.date() if hasattr(d, "date") else d) for d in df.index]

    eq_dates = [ep.date for ep in result.equity_curve]
    eq_values = [ep.equity for ep in result.equity_curve]
    drawdown_pct = _compute_drawdown_pct(eq_values)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.50, 0.30, 0.20],
        subplot_titles=[
            f"{prepared.symbol} Price – {result.indicator_name.upper()} ({result.strategy_template})",
            "Equity Curve",
            "Drawdown (%)",
        ],
        vertical_spacing=0.06,
    )

    # Row 1: Price line
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

    # Row 2: Equity curve
    fig.add_trace(
        go.Scatter(x=eq_dates, y=eq_values, mode="lines", name="Equity", line=dict(color="#00CC96", width=1.5)),
        row=2, col=1,
    )

    # Row 3: Drawdown %
    fig.add_trace(
        go.Scatter(
            x=eq_dates,
            y=drawdown_pct,
            mode="lines",
            fill="tozeroy",
            name="Drawdown %",
            line=dict(color="#EF553B", width=1),
            fillcolor="rgba(239, 85, 59, 0.2)",
        ),
        row=3, col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=700,
        showlegend=True,
        legend=dict(orientation="h", y=-0.08),
    )
    fig.update_yaxes(ticksuffix="%", row=3, col=1)
    return _fig_to_dict(fig)


def generate_metrics_summary_chart(
    results: list[BacktestResult],
    benchmark_result: BacktestResult | None = None,
) -> dict:
    """Scatter plot: Sharpe vs Max Drawdown, bubble size = trade count, color = CAGR."""
    valid = [r for r in results if not r.skipped and r.metrics]
    if not valid:
        return {}

    labels = [f"{r.indicator_name.upper()}<br>{r.strategy_template}" for r in valid]
    sharpes = [r.metrics.get("sharpe", 0) for r in valid]
    drawdowns = [abs(r.metrics.get("max_drawdown", 0)) * 100 for r in valid]
    cagrs = [r.metrics.get("cagr", 0) * 100 for r in valid]
    trade_counts = [max(r.metrics.get("num_trades", 1), 1) for r in valid]
    max_trades = max(trade_counts) if trade_counts else 1
    bubble_sizes = [10 + (t / max_trades) * 28 for t in trade_counts]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=drawdowns,
        y=sharpes,
        mode="markers+text",
        text=labels,
        textposition="top center",
        textfont=dict(size=9),
        marker=dict(
            size=bubble_sizes,
            color=cagrs,
            colorscale="RdYlGn",
            showscale=True,
            colorbar=dict(title="CAGR %", thickness=12),
            line=dict(width=1, color="rgba(255,255,255,0.4)"),
        ),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Max Drawdown: %{x:.1f}%<br>"
            "Sharpe: %{y:.2f}<br>"
            "<extra></extra>"
        ),
        name="Strategies",
    ))

    if benchmark_result and benchmark_result.metrics:
        bm = benchmark_result.metrics
        fig.add_trace(go.Scatter(
            x=[abs(bm.get("max_drawdown", 0)) * 100],
            y=[bm.get("sharpe", 0)],
            mode="markers+text",
            text=["Buy & Hold"],
            textposition="top center",
            textfont=dict(size=10, color="gold"),
            marker=dict(size=18, color="gold", symbol="star", line=dict(width=1, color="white")),
            name="Buy & Hold",
        ))

    fig.update_layout(
        title="Risk vs Return (bubble size = trade count, color = CAGR %)",
        xaxis_title="Max Drawdown (%)",
        yaxis_title="Sharpe Ratio",
        template="plotly_dark",
        height=520,
        showlegend=True,
    )
    return _fig_to_dict(fig)


def generate_walk_forward_chart(
    is_results: list[BacktestResult],
    oos_results: list[BacktestResult],
) -> dict:
    """Grouped bar chart: IS vs OOS Sharpe and CAGR for strategies validated OOS."""
    oos_map = {
        (r.indicator_name, r.strategy_template): r
        for r in oos_results if not r.skipped and r.metrics
    }
    matched_is = [
        r for r in is_results
        if not r.skipped and r.metrics and (r.indicator_name, r.strategy_template) in oos_map
    ]
    if not matched_is:
        return {}

    keys = [(r.indicator_name, r.strategy_template) for r in matched_is]
    labels = [f"{k[0].upper()}<br>{k[1]}" for k in keys]
    is_sharpes = [r.metrics.get("sharpe", 0) for r in matched_is]
    oos_sharpes = [oos_map[k].metrics.get("sharpe", 0) for k in keys]
    is_cagrs = [r.metrics.get("cagr", 0) * 100 for r in matched_is]
    oos_cagrs = [oos_map[k].metrics.get("cagr", 0) * 100 for k in keys]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Sharpe Ratio: In-Sample vs Out-of-Sample", "CAGR %: In-Sample vs Out-of-Sample"],
    )
    fig.add_trace(go.Bar(x=labels, y=is_sharpes, name="In-Sample", marker_color="#636EFA"), row=1, col=1)
    fig.add_trace(go.Bar(x=labels, y=oos_sharpes, name="Out-of-Sample", marker_color="#EF553B"), row=1, col=1)
    fig.add_trace(go.Bar(x=labels, y=is_cagrs, name="IS CAGR", marker_color="#636EFA", showlegend=False), row=1, col=2)
    fig.add_trace(go.Bar(x=labels, y=oos_cagrs, name="OOS CAGR", marker_color="#EF553B", showlegend=False), row=1, col=2)

    fig.update_layout(
        title="Walk-Forward Validation: In-Sample vs Out-of-Sample Performance",
        template="plotly_dark",
        height=480,
        barmode="group",
        legend=dict(orientation="h", y=1.14),
    )
    fig.update_xaxes(tickangle=30)
    return _fig_to_dict(fig)


def generate_report(
    prepared: PreparedData,
    base_results: list[BacktestResult],
    modified_results: list[BacktestResult],
    llm_analysis: LLMAnalysisResponse,
    initial_capital: float = 100_000.0,
    benchmark_result: BacktestResult | None = None,
    oos_results: list[BacktestResult] | None = None,
    walk_forward_split_date: str = "",
) -> dict:
    """Assemble the full report dict returned to the frontend."""
    all_results = base_results + modified_results

    # ── Summary charts ──────────────────────────────────────────────────────
    summary_charts = []
    eq_chart = generate_equity_comparison_chart(all_results, initial_capital, benchmark_result)
    if eq_chart:
        title = "Equity Curves – In-Sample" if walk_forward_split_date else "Equity Curves – All Strategies"
        summary_charts.append({"id": "equity_comparison", "title": title, "figure": eq_chart})

    metrics_chart = generate_metrics_summary_chart(all_results, benchmark_result)
    if metrics_chart:
        summary_charts.append({"id": "metrics_comparison", "title": "Risk vs Return", "figure": metrics_chart})

    # Walk-forward charts (appended after IS summary charts)
    oos_strategy_charts: list[dict] = []
    if oos_results:
        wf_chart = generate_walk_forward_chart(base_results, oos_results)
        if wf_chart:
            summary_charts.append({
                "id": "walk_forward_comparison",
                "title": "Walk-Forward: In-Sample vs Out-of-Sample",
                "figure": wf_chart,
            })

        oos_eq_chart = generate_equity_comparison_chart(oos_results, initial_capital)
        if oos_eq_chart:
            summary_charts.append({
                "id": "oos_equity",
                "title": "Out-of-Sample Equity Curves",
                "figure": oos_eq_chart,
            })

        for i, result in enumerate(oos_results):
            if result.skipped or not result.equity_curve:
                oos_strategy_charts.append({})
                continue
            chart = generate_price_indicator_chart(prepared, result)
            oos_strategy_charts.append({
                "id": f"oos_{i}_{result.indicator_name}_{result.strategy_template}",
                "title": f"OOS – {result.indicator_name.upper()} / {result.strategy_template}",
                "figure": chart,
            } if chart else {})

    # ── Per-strategy charts ─────────────────────────────────────────────────
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
        "oos_strategy_charts": oos_strategy_charts,
    }
