from __future__ import annotations

import pandas as pd
import numpy as np

from app.models.data_models import BacktestResult, EquityPoint, PreparedData, RiskSettings, Trade
from app.models.indicators import IndicatorMeta
from app.services.indicators_engine import compute_indicator
from app.services.strategies import compute_signals
from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_strategy(
    data: PreparedData,
    meta: IndicatorMeta,
    indicator_data: pd.Series | pd.DataFrame,
    params: dict,
    strategy_template: str,
    risk_settings: RiskSettings,
) -> BacktestResult:
    """Run a single strategy backtest on prepared data."""
    df = data.df
    close = df["close"]

    # Compute entry/exit signals
    try:
        signals = compute_signals(
            meta.name, strategy_template, df, indicator_data, params
        )
    except Exception as exc:
        logger.warning("Signal computation failed for %s/%s: %s", meta.name, strategy_template, exc)
        return BacktestResult(
            indicator_name=meta.name,
            strategy_template=strategy_template,
            params=params,
            trades=[],
            equity_curve=[],
            period_returns=[],
            skipped=True,
            skip_reason=str(exc),
        )

    # ── Bar-by-bar simulation ───────────────────────────────────────────────
    initial_capital = risk_settings.initial_capital
    commission_rate = risk_settings.commission
    slippage_rate = risk_settings.slippage
    position_size = risk_settings.position_size

    cash = initial_capital
    shares = 0.0
    in_position = False
    entry_price = 0.0
    entry_date = None
    entry_bar = 0

    equity_curve: list[EquityPoint] = []
    trades: list[Trade] = []
    period_returns: list[float] = []
    prev_equity = initial_capital

    for i in range(len(df)):
        date_str = str(df.index[i].date() if hasattr(df.index[i], "date") else df.index[i])
        price = float(close.iloc[i])
        sig = int(signals.iloc[i]) if i < len(signals) else 0

        # Enter long
        if not in_position and sig == 1 and not np.isnan(price):
            invest = cash * position_size
            buy_price = price * (1 + slippage_rate)
            commission = invest * commission_rate
            shares = (invest - commission) / buy_price
            cash -= invest
            in_position = True
            entry_price = buy_price
            entry_date = date_str
            entry_bar = i

        # Exit long
        elif in_position and sig == -1 and not np.isnan(price):
            sell_price = price * (1 - slippage_rate)
            proceeds = shares * sell_price
            commission = proceeds * commission_rate
            net = proceeds - commission
            cash += net
            pnl_pct = (sell_price - entry_price) / entry_price
            trades.append(
                Trade(
                    entry_date=entry_date,
                    exit_date=date_str,
                    entry_price=entry_price,
                    exit_price=sell_price,
                    pnl_pct=pnl_pct,
                    num_bars=i - entry_bar,
                )
            )
            in_position = False
            shares = 0.0

        # Mark-to-market equity
        current_equity = cash + shares * price if not np.isnan(price) else prev_equity
        equity_curve.append(EquityPoint(date=date_str, equity=round(current_equity, 4)))

        if i > 0 and prev_equity > 0:
            period_returns.append((current_equity - prev_equity) / prev_equity)
        prev_equity = current_equity

    # Close any open position at last bar price
    if in_position and len(df) > 0:
        last_price = float(close.iloc[-1])
        sell_price = last_price * (1 - slippage_rate)
        proceeds = shares * sell_price
        commission = proceeds * commission_rate
        net = proceeds - commission
        pnl_pct = (sell_price - entry_price) / entry_price
        trades.append(
            Trade(
                entry_date=entry_date,
                exit_date=str(df.index[-1].date() if hasattr(df.index[-1], "date") else df.index[-1]),
                entry_price=entry_price,
                exit_price=sell_price,
                pnl_pct=pnl_pct,
                num_bars=len(df) - 1 - entry_bar,
            )
        )

    return BacktestResult(
        indicator_name=meta.name,
        strategy_template=strategy_template,
        params=params,
        trades=trades,
        equity_curve=equity_curve,
        period_returns=period_returns,
    )
