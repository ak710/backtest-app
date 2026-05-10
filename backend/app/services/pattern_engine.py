"""
Pattern matching engine for reversal prediction.

Workflow:
1. Resample daily OHLCV → weekly bars
2. Compute 9 normalized indicator values at every weekly bar → indicator matrix
3. Cosine-similarity search: find top-K historical bars most similar to current bar
4. Extract forward returns (4w, 8w, 12w) at each match
5. Summarize uptrend rates and median returns per horizon
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import ta

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Horizons (in weekly bars) to measure forward returns
HORIZONS = [4, 8, 12]
TOP_K = 8
# Exclude the most recent N bars from similarity search to avoid lookahead
RECENT_EXCLUDE = 4


def resample_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Resample a daily OHLCV DataFrame (with 'time' column) to weekly OHLCV."""
    df = daily_df.copy()
    df = df.set_index(pd.DatetimeIndex(df["time"]))
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    weekly = df.resample("W-FRI").agg(agg).dropna(subset=["close"])
    weekly = weekly[weekly["close"] > 0]
    weekly.index.name = "time"
    return weekly.reset_index()


def _safe_series(series: pd.Series, fill: float = 0.0) -> pd.Series:
    return series.fillna(fill)


def build_indicator_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 9 normalized indicator values for every weekly bar.
    Returns a DataFrame where each row is a bar and each column is a
    normalized indicator value in approximately [0, 1] or [-1, 1].
    Rows with any NaN are dropped.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # RSI(14): natural range 0–100, normalize to [0, 1]
    rsi = _safe_series(
        ta.momentum.RSIIndicator(close, window=14, fillna=False).rsi()
    ) / 100.0

    # Stochastic %K(14,3): natural range 0–100, normalize to [0, 1]
    stoch_k = _safe_series(
        ta.momentum.StochasticOscillator(
            high, low, close, window=14, smooth_window=3, fillna=False
        ).stoch()
    ) / 100.0

    # MACD histogram (12,26,9): normalize by price to make cross-stock comparable
    macd_obj = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9, fillna=False)
    macd_hist = macd_obj.macd_diff()
    # Normalize by rolling 52-bar std of close, clip to [-1, 1]
    price_std = close.rolling(52, min_periods=12).std()
    macd_hist_norm = (macd_hist / price_std.replace(0, np.nan)).clip(-1, 1).fillna(0)

    # Bollinger %B (20,2): natural range ~[0,1], can exceed — clip to [-0.5, 1.5] then scale
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0, fillna=False)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_range = (bb_upper - bb_lower).replace(0, np.nan)
    pct_b = ((close - bb_lower) / bb_range).clip(-0.5, 1.5).fillna(0.5)
    # Rescale [-0.5, 1.5] → [0, 1]
    pct_b_norm = (pct_b + 0.5) / 2.0

    # CCI(20): normalize via tanh to squash to (-1, 1) then shift to [0, 1]
    cci = ta.trend.CCIIndicator(high, low, close, window=20, fillna=False).cci()
    cci_norm = (np.tanh(cci.fillna(0) / 100.0) + 1.0) / 2.0

    # Williams %R(14): natural range -100–0, normalize to [0, 1] (inverted: -100 → 1)
    willr = ta.momentum.WilliamsRIndicator(high, low, close, lbp=14, fillna=False).williams_r()
    willr_norm = (willr.fillna(-50) + 100.0) / 100.0

    # ROC(12): normalize via tanh to [-1, 1] then shift to [0, 1]
    roc = ta.momentum.ROCIndicator(close, window=12, fillna=False).roc()
    roc_norm = (np.tanh(roc.fillna(0) / 10.0) + 1.0) / 2.0

    # ADX(14): natural range 0–100, normalize to [0, 1]
    adx = ta.trend.ADXIndicator(high, low, close, window=14, fillna=False).adx()
    adx_norm = _safe_series(adx) / 100.0

    # CMF(20): natural range -1–1, normalize to [0, 1]
    cmf = ta.volume.ChaikinMoneyFlowIndicator(
        high, low, close, volume, window=20, fillna=False
    ).chaikin_money_flow()
    cmf_norm = (cmf.fillna(0) + 1.0) / 2.0

    matrix = pd.DataFrame({
        "rsi": rsi,
        "stoch_k": stoch_k,
        "macd_hist": macd_hist_norm,
        "pct_b": pct_b_norm,
        "cci": cci_norm,
        "willr": willr_norm,
        "roc": roc_norm,
        "adx": adx_norm,
        "cmf": cmf_norm,
    }, index=df.index)

    return matrix.dropna()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def find_similar_patterns(
    indicator_matrix: pd.DataFrame,
    weekly_df: pd.DataFrame,
    top_k: int = TOP_K,
) -> list[dict]:
    """
    Find the top-K rows in indicator_matrix most similar (cosine) to the last row.
    Both indicator_matrix and weekly_df must share the same integer RangeIndex
    (call reset_index on both before passing).
    Excludes bars that lack at least max(HORIZONS) bars of forward data.
    Returns list of dicts with keys: idx, date, similarity.
    """
    if len(indicator_matrix) < 2:
        return []

    max_horizon = max(HORIZONS)
    n = len(indicator_matrix)
    current_vec = indicator_matrix.iloc[-1].values

    # Exclude bars without enough forward data
    last_valid = n - max_horizon - 1
    if last_valid < 0:
        return []

    similarities = []
    for i in range(last_valid):
        sim = _cosine_similarity(current_vec, indicator_matrix.iloc[i].values)
        similarities.append((i, sim))

    similarities.sort(key=lambda x: x[1], reverse=True)

    results = []
    for idx, sim in similarities[:top_k]:
        row = weekly_df.iloc[idx]
        date_val = row["time"] if "time" in weekly_df.columns else str(weekly_df.index[idx])
        results.append({
            "idx": idx,
            "date": str(date_val)[:10],
            "similarity": round(sim, 4),
        })

    return results


def compute_forward_returns(
    weekly_df: pd.DataFrame,
    matches: list[dict],
    horizons: list[int] = HORIZONS,
) -> list[dict]:
    """
    For each matched bar, compute forward returns at each horizon.
    Returns the matches list enriched with forward return fields.
    """
    close = weekly_df["close"].values
    n = len(close)
    enriched = []
    for m in matches:
        idx = m["idx"]
        entry_price = close[idx]
        record = {**m}
        for h in horizons:
            future_idx = idx + h
            if future_idx < n and entry_price > 0:
                fwd_ret = (close[future_idx] - entry_price) / entry_price
                record[f"fwd_{h}w"] = round(float(fwd_ret), 4)
                record[f"up_{h}w"] = fwd_ret > 0
            else:
                record[f"fwd_{h}w"] = None
                record[f"up_{h}w"] = None
        enriched.append(record)
    return enriched


def summarize_pattern_outcomes(
    matches_with_returns: list[dict],
    horizons: list[int] = HORIZONS,
) -> dict:
    """
    Aggregate forward return statistics across all matched bars.
    Returns a dict with per-horizon uptrend_pct, median_return, count,
    avg_similarity, and the individual match records.
    """
    if not matches_with_returns:
        return {"horizons": {}, "avg_similarity": 0.0, "match_count": 0, "matches": []}

    avg_sim = round(
        sum(m["similarity"] for m in matches_with_returns) / len(matches_with_returns), 4
    )

    horizon_stats: dict[str, dict] = {}
    for h in horizons:
        returns = [m[f"fwd_{h}w"] for m in matches_with_returns if m.get(f"fwd_{h}w") is not None]
        ups = [m[f"up_{h}w"] for m in matches_with_returns if m.get(f"up_{h}w") is not None]
        if returns:
            horizon_stats[f"{h}w"] = {
                "count": len(returns),
                "uptrend_pct": round(sum(ups) / len(ups) * 100, 1),
                "median_return_pct": round(float(np.median(returns)) * 100, 2),
                "avg_return_pct": round(float(np.mean(returns)) * 100, 2),
            }
        else:
            horizon_stats[f"{h}w"] = {"count": 0, "uptrend_pct": None, "median_return_pct": None, "avg_return_pct": None}

    # Clean matches for serialization (remove internal idx fields)
    clean_matches = [
        {
            "date": m["date"],
            "similarity": m["similarity"],
            "fwd_4w_pct": round(m["fwd_4w"] * 100, 2) if m.get("fwd_4w") is not None else None,
            "fwd_8w_pct": round(m["fwd_8w"] * 100, 2) if m.get("fwd_8w") is not None else None,
            "fwd_12w_pct": round(m["fwd_12w"] * 100, 2) if m.get("fwd_12w") is not None else None,
        }
        for m in matches_with_returns
    ]

    return {
        "horizons": horizon_stats,
        "avg_similarity": avg_sim,
        "match_count": len(matches_with_returns),
        "matches": clean_matches,
    }


def run_own_stock_analysis(weekly_df: pd.DataFrame) -> dict:
    """
    Run the full pattern matching pipeline on one stock's own history.
    Returns a summary dict.
    """
    if len(weekly_df) < 30:
        return {"error": "Insufficient history (< 30 weekly bars)", "match_count": 0}

    indicator_matrix = build_indicator_matrix(weekly_df)
    if len(indicator_matrix) < 20:
        return {"error": "Too many NaN indicators — insufficient data", "match_count": 0}

    # Reindex weekly_df to match indicator_matrix for forward-return lookups
    weekly_aligned = weekly_df.loc[indicator_matrix.index].reset_index(drop=True)
    indicator_matrix_reset = indicator_matrix.reset_index(drop=True)

    matches = find_similar_patterns(indicator_matrix_reset, weekly_aligned)
    if not matches:
        return {"error": "No similar patterns found", "match_count": 0}

    enriched = compute_forward_returns(weekly_aligned, matches)
    return summarize_pattern_outcomes(enriched)


def run_peer_analysis(
    current_vector: np.ndarray,
    peer_ticker: str,
    peer_weekly_df: pd.DataFrame,
) -> dict:
    """
    Search a peer stock's history for bars similar to `current_vector`.
    Returns summary dict with the peer's pattern outcomes.
    """
    if len(peer_weekly_df) < 30:
        return {"ticker": peer_ticker, "error": "Insufficient history", "match_count": 0}

    indicator_matrix = build_indicator_matrix(peer_weekly_df)
    if len(indicator_matrix) < 20:
        return {"ticker": peer_ticker, "error": "Insufficient indicator data", "match_count": 0}

    max_horizon = max(HORIZONS)
    n = len(indicator_matrix)
    last_valid = n - max_horizon - 1
    if last_valid < 0:
        return {"ticker": peer_ticker, "error": "Insufficient forward data", "match_count": 0}

    candidates = indicator_matrix.iloc[:last_valid]
    similarities = []
    for i, row in enumerate(candidates.values):
        sim = _cosine_similarity(current_vector, row)
        similarities.append((i, sim))

    similarities.sort(key=lambda x: x[1], reverse=True)
    top = similarities[:TOP_K]

    peer_weekly_reset = peer_weekly_df.loc[indicator_matrix.index].reset_index(drop=True)
    close_vals = peer_weekly_reset["close"].values

    matches = []
    for original_idx, sim in top:
        entry_price = close_vals[original_idx]
        record: dict = {
            "date": str(peer_weekly_reset.iloc[original_idx].get("time", ""))[:10],
            "similarity": round(sim, 4),
        }
        for h in HORIZONS:
            future_idx = original_idx + h
            if future_idx < len(close_vals) and entry_price > 0:
                fwd = (close_vals[future_idx] - entry_price) / entry_price
                record[f"fwd_{h}w"] = round(float(fwd), 4)
                record[f"up_{h}w"] = fwd > 0
            else:
                record[f"fwd_{h}w"] = None
                record[f"up_{h}w"] = None
        matches.append(record)

    summary = summarize_pattern_outcomes(matches)
    summary["ticker"] = peer_ticker
    return summary
