from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from app.models.data_models import BacktestResult
from app.models.llm_schemas import StrategySummary
from app.utils.logging import get_logger

logger = get_logger(__name__)


def compute_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate_annual: float,
    frequency: Literal["weekly", "monthly"],
) -> float:
    if returns.empty or returns.std() == 0:
        return 0.0
    periods_per_year = 52 if frequency == "weekly" else 12
    rf_per_period = (1 + risk_free_rate_annual) ** (1 / periods_per_year) - 1
    excess = returns - rf_per_period
    mean_excess = excess.mean()
    std_excess = excess.std()
    if std_excess == 0:
        return 0.0
    return float(mean_excess / std_excess * (periods_per_year ** 0.5))


def compute_max_drawdown(equity_curve: list[float]) -> tuple[float, int]:
    """Returns (max_drawdown_pct, duration_in_bars)."""
    if not equity_curve:
        return 0.0, 0
    eq = np.array(equity_curve)
    running_max = np.maximum.accumulate(eq)
    drawdown = (eq - running_max) / running_max
    max_dd = float(drawdown.min())
    # Duration of the worst drawdown
    trough_idx = int(drawdown.argmin())
    peak_idx = int(np.argmax(eq[:trough_idx + 1])) if trough_idx > 0 else 0
    duration = trough_idx - peak_idx
    return max_dd, duration


def compute_cagr(
    initial: float,
    final: float,
    num_periods: int,
    frequency: Literal["weekly", "monthly"],
) -> float:
    if initial <= 0 or num_periods == 0:
        return 0.0
    periods_per_year = 52 if frequency == "weekly" else 12
    years = num_periods / periods_per_year
    if years == 0:
        return 0.0
    return float((final / initial) ** (1 / years) - 1)


def compute_metrics(
    result: BacktestResult,
    frequency: Literal["weekly", "monthly"],
    risk_free_rate_annual: float,
    initial_capital: float = 100_000.0,
) -> dict:
    if result.skipped or not result.equity_curve:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "volatility": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_duration": 0,
            "num_trades": 0,
            "win_rate": 0.0,
            "avg_trade_pnl": 0.0,
            "profit_factor": 0.0,
        }

    returns = pd.Series(result.period_returns)
    equity_values = [ep.equity for ep in result.equity_curve]
    final_equity = equity_values[-1] if equity_values else initial_capital

    total_return = (final_equity - initial_capital) / initial_capital
    cagr = compute_cagr(initial_capital, final_equity, len(result.equity_curve), frequency)
    sharpe = compute_sharpe_ratio(returns, risk_free_rate_annual, frequency)
    volatility = float(returns.std() * ((52 if frequency == "weekly" else 12) ** 0.5))
    max_dd, dd_duration = compute_max_drawdown(equity_values)

    trades = result.trades
    num_trades = len(trades)
    if num_trades > 0:
        pnls = [t.pnl_pct for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / num_trades
        avg_trade_pnl = float(np.mean(pnls))
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    else:
        win_rate = 0.0
        avg_trade_pnl = 0.0
        profit_factor = 0.0

    return {
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 4),
        "volatility": round(volatility, 4),
        "max_drawdown": round(max_dd, 4),
        "max_drawdown_duration": dd_duration,
        "num_trades": num_trades,
        "win_rate": round(win_rate, 4),
        "avg_trade_pnl": round(avg_trade_pnl, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
    }


def to_strategy_summary(result: BacktestResult) -> StrategySummary:
    m = result.metrics
    return StrategySummary(
        indicator_name=result.indicator_name,
        strategy_template=result.strategy_template,
        params=result.params,
        cagr=m.get("cagr", 0.0),
        sharpe=m.get("sharpe", 0.0),
        max_drawdown=m.get("max_drawdown", 0.0),
        volatility=m.get("volatility", 0.0),
        num_trades=m.get("num_trades", 0),
        win_rate=m.get("win_rate", 0.0),
        total_return=m.get("total_return", 0.0),
    )
