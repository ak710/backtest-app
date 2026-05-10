"""Strategy templates: compute buy/sell signal Series from indicator data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.utils.logging import get_logger

logger = get_logger(__name__)

STRATEGY_REGISTRY: dict[str, callable] = {}


def register(name: str):
    def decorator(fn):
        STRATEGY_REGISTRY[name] = fn
        return fn
    return decorator


def compute_signals(
    indicator_name: str,
    strategy_template: str,
    df: pd.DataFrame,
    indicator_data: pd.Series | pd.DataFrame,
    params: dict,
) -> pd.Series:
    """
    Returns a Series indexed like df with values:
      1  = enter long
     -1  = exit long
      0  = hold
    """
    fn = STRATEGY_REGISTRY.get(strategy_template)
    if fn is None:
        raise ValueError(f"Unknown strategy template: {strategy_template}")
    signals = fn(df, indicator_data, params)
    return signals.reindex(df.index, fill_value=0)


def _crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """1 where a crosses above b, -1 where a crosses below b."""
    above = (a > b).astype(int)
    cross = above.diff()
    result = pd.Series(0, index=a.index)
    result[cross == 1] = 1
    result[cross == -1] = -1
    return result


@register("rsi_mean_reversion")
def rsi_mean_reversion(df: pd.DataFrame, ind: pd.Series, params: dict) -> pd.Series:
    overbought = float(params.get("overbought", 70))
    oversold = float(params.get("oversold", 30))

    signals = pd.Series(0, index=df.index)
    below_os = ind < oversold
    above_ob = ind > overbought

    for i in range(1, len(df)):
        if below_os.iloc[i] and not below_os.iloc[i - 1]:
            signals.iloc[i] = 1
        elif above_ob.iloc[i] and not above_ob.iloc[i - 1]:
            signals.iloc[i] = -1
    return signals


@register("rsi_trend_follow")
def rsi_trend_follow(df: pd.DataFrame, ind: pd.Series, params: dict) -> pd.Series:
    slow_length = int(params.get("slow_length", 50))
    import ta as ta_lib
    slow_ma = ta_lib.trend.EMAIndicator(df["close"], window=slow_length, fillna=False).ema_indicator()

    signals = pd.Series(0, index=df.index)
    above_mid = ind > 50
    above_ma = df["close"] > slow_ma

    for i in range(1, len(df)):
        was_in = above_mid.iloc[i - 1] and above_ma.iloc[i - 1]
        is_in = above_mid.iloc[i] and above_ma.iloc[i]
        if is_in and not was_in:
            signals.iloc[i] = 1
        elif not is_in and was_in:
            signals.iloc[i] = -1
    return signals


@register("bollinger_mean_reversion")
def bollinger_mean_reversion(df: pd.DataFrame, ind: pd.DataFrame, params: dict) -> pd.Series:
    if "lower" not in ind.columns or "mid" not in ind.columns:
        return pd.Series(0, index=df.index)

    lower = ind["lower"]
    mid = ind["mid"]
    close = df["close"]

    signals = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if close.iloc[i] <= lower.iloc[i] and close.iloc[i - 1] > lower.iloc[i - 1]:
            signals.iloc[i] = 1
        elif close.iloc[i] >= mid.iloc[i] and close.iloc[i - 1] < mid.iloc[i - 1]:
            signals.iloc[i] = -1
    return signals


@register("ma_crossover")
def ma_crossover(df: pd.DataFrame, ind: pd.DataFrame | pd.Series, params: dict) -> pd.Series:
    if isinstance(ind, pd.Series):
        return pd.Series(0, index=df.index)

    if "fast" in ind.columns and "slow" in ind.columns:
        fast_col, slow_col = "fast", "slow"
    else:
        cols = [c for c in ind.columns if not c.startswith("DC")]
        if len(cols) < 2:
            return pd.Series(0, index=df.index)
        fast_col, slow_col = cols[0], cols[1]

    return _crossover(ind[fast_col], ind[slow_col])


@register("macd_trend")
def macd_trend(df: pd.DataFrame, ind: pd.DataFrame, params: dict) -> pd.Series:
    if "macd" not in ind.columns or "signal" not in ind.columns:
        return pd.Series(0, index=df.index)
    return _crossover(ind["macd"], ind["signal"])


@register("atr_trailing_stop")
def atr_trailing_stop(df: pd.DataFrame, ind: pd.DataFrame, params: dict) -> pd.Series:
    atr_mult = float(params.get("atr_mult", 2.0))
    atr = ind["atr"] if "atr" in ind.columns else ind.iloc[:, 0]
    trend_ema = ind["trend_ema"] if "trend_ema" in ind.columns else ind.iloc[:, 1]
    close = df["close"]

    signals = pd.Series(0, index=df.index)
    in_trade = False
    trail_stop = 0.0

    for i in range(1, len(df)):
        if pd.isna(atr.iloc[i]) or pd.isna(trend_ema.iloc[i]):
            continue
        price = float(close.iloc[i])
        atr_val = float(atr.iloc[i])

        if not in_trade:
            # Enter when price crosses above trend EMA
            if price > float(trend_ema.iloc[i]) and float(close.iloc[i - 1]) <= float(trend_ema.iloc[i - 1]):
                signals.iloc[i] = 1
                trail_stop = price - atr_mult * atr_val
                in_trade = True
        else:
            # Update trailing stop upward only
            new_stop = price - atr_mult * atr_val
            trail_stop = max(trail_stop, new_stop)
            if price < trail_stop:
                signals.iloc[i] = -1
                in_trade = False

    return signals


@register("stoch_mean_reversion")
def stoch_mean_reversion(df: pd.DataFrame, ind: pd.DataFrame, params: dict) -> pd.Series:
    overbought = float(params.get("overbought", 80))
    oversold = float(params.get("oversold", 20))

    k = ind["k"] if "k" in ind.columns else ind.iloc[:, 0]

    signals = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if k.iloc[i] < oversold and k.iloc[i - 1] >= oversold:
            signals.iloc[i] = 1
        elif k.iloc[i] > overbought and k.iloc[i - 1] <= overbought:
            signals.iloc[i] = -1
    return signals


@register("cci_mean_reversion")
def cci_mean_reversion(df: pd.DataFrame, ind: pd.Series, params: dict) -> pd.Series:
    oversold = float(params.get("oversold", -100))
    overbought = float(params.get("overbought", 100))

    signals = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if ind.iloc[i] < oversold and ind.iloc[i - 1] >= oversold:
            signals.iloc[i] = 1
        elif ind.iloc[i] > overbought and ind.iloc[i - 1] <= overbought:
            signals.iloc[i] = -1
    return signals


@register("adx_breakout")
def adx_breakout(df: pd.DataFrame, ind: pd.DataFrame, params: dict) -> pd.Series:
    strength_threshold = float(params.get("strength_threshold", 25))

    if "adx" not in ind.columns:
        return pd.Series(0, index=df.index)

    adx = ind["adx"]
    dmp = ind["dmp"] if "dmp" in ind.columns else None
    dmn = ind["dmn"] if "dmn" in ind.columns else None

    signals = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if pd.isna(adx.iloc[i]):
            continue
        strong = adx.iloc[i] > strength_threshold
        uptrend = (dmp is not None and dmn is not None and dmp.iloc[i] > dmn.iloc[i])

        was_strong = adx.iloc[i - 1] > strength_threshold
        was_uptrend = (dmp is not None and dmn is not None and dmp.iloc[i - 1] > dmn.iloc[i - 1])

        if strong and uptrend and not (was_strong and was_uptrend):
            signals.iloc[i] = 1
        elif not (strong and uptrend) and (was_strong and was_uptrend):
            signals.iloc[i] = -1
    return signals


@register("zero_cross")
def zero_cross(df: pd.DataFrame, ind: pd.Series, params: dict) -> pd.Series:
    """Buy when series crosses above zero; sell when it crosses below zero."""
    if isinstance(ind, pd.DataFrame):
        ind = ind.iloc[:, 0]
    return _crossover(ind, pd.Series(0.0, index=ind.index))


@register("obv_momentum")
def obv_momentum(df: pd.DataFrame, ind: pd.DataFrame, params: dict) -> pd.Series:
    if isinstance(ind, pd.Series):
        return pd.Series(0, index=df.index)

    obv_col = "obv" if "obv" in ind.columns else ind.columns[0]
    sma_col = "obv_sma" if "obv_sma" in ind.columns else (ind.columns[1] if len(ind.columns) > 1 else None)

    if sma_col is None:
        return pd.Series(0, index=df.index)

    return _crossover(ind[obv_col], ind[sma_col])
