from __future__ import annotations

import io
from typing import BinaryIO, Literal

import numpy as np
import pandas as pd

from app.models.data_models import PreparedData
from app.utils.logging import get_logger

logger = get_logger(__name__)

REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}
COLUMN_ALIASES = {
    "time": "time",
    "date": "time",
    "datetime": "time",
    "timestamp": "time",
    "open": "open",
    "o": "open",
    "high": "high",
    "h": "high",
    "low": "low",
    "l": "low",
    "close": "close",
    "c": "close",
    "adj close": "close",
    "adj_close": "close",
    "volume": "volume",
    "vol": "volume",
    "v": "volume",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {col: COLUMN_ALIASES.get(col.lower().strip(), col.lower().strip()) for col in df.columns}
    return df.rename(columns=renamed)


def _infer_frequency(df: pd.DataFrame) -> Literal["weekly", "monthly"]:
    if len(df) < 2:
        raise ValueError("Dataset too short to infer frequency (need >= 2 rows).")
    diffs = df.index.to_series().diff().dropna()
    median_days = diffs.dt.days.median()
    if median_days <= 10:
        return "weekly"
    return "monthly"


def _resample_to_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate weekly OHLCV to monthly."""
    monthly = df.resample("ME").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return monthly.dropna(subset=["close"])


def load_and_prepare_timeseries(
    file: BinaryIO | bytes | str,
    target_frequency: Literal["weekly", "monthly"],
    symbol: str = "UNKNOWN",
) -> PreparedData:
    if isinstance(file, (bytes, str)):
        raw = io.BytesIO(file) if isinstance(file, bytes) else io.StringIO(file)
    else:
        raw = file

    df = pd.read_csv(raw)
    df = _normalize_columns(df)

    # Validate required columns
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    # Parse time column
    if "time" not in df.columns:
        raise ValueError("No time/date column found in CSV.")
    df["time"] = pd.to_datetime(df["time"], infer_datetime_format=True)
    df = df.set_index("time").sort_index()

    # Drop duplicates
    df = df[~df.index.duplicated(keep="last")]

    # Keep only OHLCV
    df = df[["open", "high", "low", "close", "volume"]].astype(float)

    # Infer source frequency
    source_freq = _infer_frequency(df)
    logger.info("Inferred source frequency: %s, target: %s", source_freq, target_frequency)

    # Resample if needed
    if source_freq == "weekly" and target_frequency == "monthly":
        df = _resample_to_monthly(df)
        logger.info("Resampled weekly -> monthly, bars: %d", len(df))

    # Warn if data is daily/intraday (median gap < 5 days)
    diffs = df.index.to_series().diff().dropna()
    median_days = diffs.dt.days.median()
    if median_days < 5:
        raise ValueError(
            "Data appears to be daily or intraday. Only weekly or monthly bars are supported."
        )

    # Compute simple returns
    returns = df["close"].pct_change().dropna()

    # Basic stats
    basic_stats = {
        "mean_return": float(returns.mean()),
        "std_return": float(returns.std()),
        "min_price": float(df["close"].min()),
        "max_price": float(df["close"].max()),
        "mean_volume": float(df["volume"].mean()),
        "total_bars": len(df),
        "years_covered": round((df.index[-1] - df.index[0]).days / 365.25, 2),
    }

    # Warn on short datasets
    min_bars = 36 if target_frequency == "monthly" else 156
    if len(df) < min_bars:
        logger.warning(
            "Short dataset: %d bars. Results may be unreliable (recommended >= %d).",
            len(df),
            min_bars,
        )

    return PreparedData(
        symbol=symbol,
        frequency=target_frequency,
        df=df,
        returns=returns,
        num_bars=len(df),
        start_date=str(df.index[0].date()),
        end_date=str(df.index[-1].date()),
        basic_stats=basic_stats,
    )
