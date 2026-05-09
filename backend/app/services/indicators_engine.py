from __future__ import annotations

import warnings

import pandas as pd
import pandas_ta as ta

from app.models.indicators import IndicatorMeta
from app.utils.logging import get_logger

logger = get_logger(__name__)


def compute_indicator(
    df: pd.DataFrame,
    meta: IndicatorMeta,
    params: dict,
) -> pd.Series | pd.DataFrame | None:
    """Compute a technical indicator on a DataFrame. Returns None if computation fails."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _dispatch(df, meta.name, params)
    except Exception as exc:
        logger.warning("Indicator '%s' computation failed: %s", meta.name, exc)
        return None


def _dispatch(df: pd.DataFrame, name: str, params: dict) -> pd.Series | pd.DataFrame | None:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    if name == "sma":
        fast = int(params.get("fast_length", 10))
        slow = int(params.get("slow_length", 30))
        result = pd.DataFrame({
            "fast": ta.sma(close, length=fast),
            "slow": ta.sma(close, length=slow),
        })
        return result

    elif name == "ema":
        fast = int(params.get("fast_length", 10))
        slow = int(params.get("slow_length", 30))
        result = pd.DataFrame({
            "fast": ta.ema(close, length=fast),
            "slow": ta.ema(close, length=slow),
        })
        return result

    elif name == "hma":
        length = int(params.get("length", 16))
        return ta.hma(close, length=length)

    elif name == "macd":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        result = ta.macd(close, fast=fast, slow=slow, signal=signal)
        return result

    elif name == "adx":
        length = int(params.get("length", 14))
        result = ta.adx(high, low, close, length=length)
        return result

    elif name == "aroon":
        length = int(params.get("length", 25))
        result = ta.aroon(high, low, length=length)
        return result

    elif name == "rsi":
        length = int(params.get("length", 14))
        return ta.rsi(close, length=length)

    elif name == "stoch":
        k = int(params.get("k", 14))
        d = int(params.get("d", 3))
        smooth_k = int(params.get("smooth_k", 3))
        result = ta.stoch(high, low, close, k=k, d=d, smooth_k=smooth_k)
        return result

    elif name == "roc":
        length = int(params.get("length", 12))
        return ta.roc(close, length=length)

    elif name == "cci":
        length = int(params.get("length", 20))
        return ta.cci(high, low, close, length=length)

    elif name == "willr":
        length = int(params.get("length", 14))
        return ta.willr(high, low, close, length=length)

    elif name == "ppo":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal = int(params.get("signal", 9))
        result = ta.ppo(close, fast=fast, slow=slow, signal=signal)
        return result

    elif name == "bbands":
        length = int(params.get("length", 20))
        std = float(params.get("std", 2.0))
        result = ta.bbands(close, length=length, std=std)
        return result

    elif name == "atr":
        length = int(params.get("length", 14))
        trend_length = int(params.get("trend_length", 20))
        atr_series = ta.atr(high, low, close, length=length)
        trend_ema = ta.ema(close, length=trend_length)
        result = pd.DataFrame({"atr": atr_series, "trend_ema": trend_ema})
        return result

    elif name == "donchian":
        lower_length = int(params.get("lower_length", 20))
        upper_length = int(params.get("upper_length", 20))
        result = ta.donchian(high, low, lower_length=lower_length, upper_length=upper_length)
        return result

    elif name == "obv":
        sma_length = int(params.get("sma_length", 20))
        obv_series = ta.obv(close, volume)
        obv_sma = ta.sma(obv_series, length=sma_length)
        result = pd.DataFrame({"obv": obv_series, "obv_sma": obv_sma})
        return result

    elif name == "mfi":
        length = int(params.get("length", 14))
        return ta.mfi(high, low, close, volume, length=length)

    elif name == "cmf":
        length = int(params.get("length", 20))
        return ta.cmf(high, low, close, volume, length=length)

    else:
        raise ValueError(f"Unknown indicator: {name}")
