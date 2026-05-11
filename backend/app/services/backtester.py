from __future__ import annotations

import pandas as pd
import numpy as np

from app.models.data_models import BacktestResult, EquityPoint, PreparedData, RiskSettings, Trade
from app.models.indicators import IndicatorMeta
from app.services.indicators_engine import compute_indicator
from app.services.strategies import compute_signals  # also used directly in pipeline via import
from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_strategy_from_signals(
    data: PreparedData,
    signals: pd.Series,
    indicator_name: str,
    strategy_template: str,
    params: dict,
    risk_settings: RiskSettings,
) -> BacktestResult:
    """Run a backtest from a pre-computed signal series."""
    df = data.df
    close = df["close"]

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
    in_market_returns: list[float] = []
    prev_equity = initial_capital

    for i in range(len(df)):
        date_str = str(df.index[i].date() if hasattr(df.index[i], "date") else df.index[i])
        price = float(close.iloc[i])
        sig = int(signals.iloc[i]) if i < len(signals) else 0

        was_in_position = in_position

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
            r = (current_equity - prev_equity) / prev_equity
            period_returns.append(r)
            if was_in_position or in_position:
                in_market_returns.append(r)
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
        indicator_name=indicator_name,
        strategy_template=strategy_template,
        params=params,
        trades=trades,
        equity_curve=equity_curve,
        period_returns=period_returns,
        in_market_returns=in_market_returns,
    )


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
    return run_strategy_from_signals(data, signals, meta.name, strategy_template, params, risk_settings)


def run_benchmark(data: PreparedData, risk_settings: RiskSettings) -> BacktestResult:
    """Buy-and-hold: enter at first bar close, exit at last bar close."""
    df = data.df
    close = df["close"]
    initial_capital = risk_settings.initial_capital
    commission_rate = risk_settings.commission
    slippage_rate = risk_settings.slippage

    first_price = float(close.iloc[0])
    buy_price = first_price * (1 + slippage_rate)
    shares = initial_capital * (1 - commission_rate) / buy_price

    equity_curve: list[EquityPoint] = []
    period_returns: list[float] = []
    prev_equity = initial_capital

    for i in range(len(df)):
        date_str = str(df.index[i].date() if hasattr(df.index[i], "date") else df.index[i])
        price = float(close.iloc[i])
        current_equity = shares * price if not np.isnan(price) else prev_equity
        equity_curve.append(EquityPoint(date=date_str, equity=round(current_equity, 4)))
        if i > 0 and prev_equity > 0:
            period_returns.append((current_equity - prev_equity) / prev_equity)
        prev_equity = current_equity
    # B&H is always fully invested, so in_market_returns == period_returns
    in_market_returns = list(period_returns)

    last_price = float(close.iloc[-1])
    sell_price = last_price * (1 - slippage_rate)
    pnl_pct = (sell_price - buy_price) / buy_price
    entry_date = str(df.index[0].date() if hasattr(df.index[0], "date") else df.index[0])
    exit_date = str(df.index[-1].date() if hasattr(df.index[-1], "date") else df.index[-1])

    return BacktestResult(
        indicator_name="buy_and_hold",
        strategy_template="buy_and_hold",
        params={},
        trades=[Trade(
            entry_date=entry_date,
            exit_date=exit_date,
            entry_price=buy_price,
            exit_price=sell_price,
            pnl_pct=pnl_pct,
            num_bars=len(df) - 1,
        )],
        equity_curve=equity_curve,
        period_returns=period_returns,
        in_market_returns=in_market_returns,
    )
