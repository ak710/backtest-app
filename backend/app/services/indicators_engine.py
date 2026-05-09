from __future__ import annotations

import math

import numpy as np
import pandas as pd
import ta

from app.models.indicators import IndicatorMeta
from app.utils.logging import get_logger

logger = get_logger(__name__)


def compute_indicator(
    df: pd.DataFrame,
    meta: IndicatorMeta,
    params: dict,
) -> pd.Series | pd.DataFrame | None:
    try:
        return _dispatch(df, meta.name, params)
    except Exception as exc:
        logger.warning("Indicator '%s' computation failed: %s", meta.name, exc)
        return None


def _wma(series: pd.Series, window: int) -> pd.Series:
    weights = np.arange(1, window + 1, dtype=float)
    return series.rolling(window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)


def _dispatch(df: pd.DataFrame, name: str, params: dict) -> pd.Series | pd.DataFrame | None:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    if name == "sma":
        fast = int(params.get("fast_length", 10))
        slow = int(params.get("slow_length", 30))
        return pd.DataFrame({
            "fast": ta.trend.SMAIndicator(close, window=fast, fillna=False).sma_indicator(),
            "slow": ta.trend.SMAIndicator(close, window=slow, fillna=False).sma_indicator(),
        })

    elif name == "ema":
        fast = int(params.get("fast_length", 10))
        slow = int(params.get("slow_length", 30))
        return pd.DataFrame({
            "fast": ta.trend.EMAIndicator(close, window=fast, fillna=False).ema_indicator(),
            "slow": ta.trend.EMAIndicator(close, window=slow, fillna=False).ema_indicator(),
        })

    elif name == "hma":
        n = int(params.get("length", 16))
        half_n = max(2, n // 2)
        sqrt_n = max(2, int(math.floor(math.sqrt(n))))
        diff = 2 * _wma(close, half_n) - _wma(close, n)
        return _wma(diff, sqrt_n)

    elif name == "macd":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        ind = ta.trend.MACD(close, window_fast=fast, window_slow=slow, window_sign=signal, fillna=False)
        return pd.DataFrame({
            "macd": ind.macd(),
            "signal": ind.macd_signal(),
            "hist": ind.macd_diff(),
        })

    elif name == "adx":
        length = int(params.get("length", 14))
        ind = ta.trend.ADXIndicator(high, low, close, window=length, fillna=False)
        return pd.DataFrame({
            "adx": ind.adx(),
            "dmp": ind.adx_pos(),
            "dmn": ind.adx_neg(),
        })

    elif name == "aroon":
        length = int(params.get("length", 25))
        ind = ta.trend.AroonIndicator(high, low, window=length, fillna=False)
        return pd.DataFrame({
            "aroon_up": ind.aroon_up(),
            "aroon_down": ind.aroon_indicator(),
        })

    elif name == "rsi":
        length = int(params.get("length", 14))
        return ta.momentum.RSIIndicator(close, window=length, fillna=False).rsi()

    elif name == "stoch":
        k = int(params.get("k", 14))
        d = int(params.get("d", 3))
        smooth_k = int(params.get("smooth_k", 3))
        ind = ta.momentum.StochasticOscillator(high, low, close, window=k, smooth_window=smooth_k, fillna=False)
        return pd.DataFrame({
            "k": ind.stoch(),
            "d": ind.stoch_signal(),
        })

    elif name == "roc":
        length = int(params.get("length", 12))
        return ta.momentum.ROCIndicator(close, window=length, fillna=False).roc()

    elif name == "cci":
        length = int(params.get("length", 20))
        return ta.trend.CCIIndicator(high, low, close, window=length, fillna=False).cci()

    elif name == "willr":
        length = int(params.get("length", 14))
        return ta.momentum.WilliamsRIndicator(high, low, close, lbp=length, fillna=False).williams_r()

    elif name == "ppo":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        ema_fast = ta.trend.EMAIndicator(close, window=fast, fillna=False).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(close, window=slow, fillna=False).ema_indicator()
        ppo_line = (ema_fast - ema_slow) / ema_slow * 100
        ppo_signal = ta.trend.EMAIndicator(ppo_line, window=signal, fillna=False).ema_indicator()
        return pd.DataFrame({
            "macd": ppo_line,
            "signal": ppo_signal,
            "hist": ppo_line - ppo_signal,
        })

    elif name == "bbands":
        length = int(params.get("length", 20))
        std = float(params.get("std", 2.0))
        ind = ta.volatility.BollingerBands(close, window=length, window_dev=std, fillna=False)
        return pd.DataFrame({
            "lower": ind.bollinger_lband(),
            "mid": ind.bollinger_mavg(),
            "upper": ind.bollinger_hband(),
        })

    elif name == "atr":
        length = int(params.get("length", 14))
        trend_length = int(params.get("trend_length", 20))
        atr_series = ta.volatility.AverageTrueRange(high, low, close, window=length, fillna=False).average_true_range()
        trend_ema = ta.trend.EMAIndicator(close, window=trend_length, fillna=False).ema_indicator()
        return pd.DataFrame({"atr": atr_series, "trend_ema": trend_ema})

    elif name == "donchian":
        lower_length = int(params.get("lower_length", 20))
        upper_length = int(params.get("upper_length", 20))
        window = max(lower_length, upper_length)
        ind = ta.volatility.DonchianChannel(high, low, close, window=window, fillna=False)
        return pd.DataFrame({
            "upper": ind.donchian_channel_hband(),
            "lower": ind.donchian_channel_lband(),
            "mid": ind.donchian_channel_mband(),
            "fast": ind.donchian_channel_hband(),
            "slow": ind.donchian_channel_lband(),
        })

    elif name == "obv":
        sma_length = int(params.get("sma_length", 20))
        obv_series = ta.volume.OnBalanceVolumeIndicator(close, volume, fillna=False).on_balance_volume()
        obv_sma = ta.trend.SMAIndicator(obv_series, window=sma_length, fillna=False).sma_indicator()
        return pd.DataFrame({"obv": obv_series, "obv_sma": obv_sma})

    elif name == "mfi":
        length = int(params.get("length", 14))
        return ta.volume.MFIIndicator(high, low, close, volume, window=length, fillna=False).money_flow_index()

    elif name == "cmf":
        length = int(params.get("length", 20))
        return ta.volume.ChaikinMoneyFlowIndicator(high, low, close, volume, window=length, fillna=False).chaikin_money_flow()

    else:
        raise ValueError(f"Unknown indicator: {name}")
