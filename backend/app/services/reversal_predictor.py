"""
Reversal Predictor Service.

Orchestrates: data fetch → indicator computation → pattern matching →
peer analysis → LLM prompt → structured prediction response.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import ta
from pydantic import ValidationError

from app.models.llm_schemas import ReversalPredictionResponse
from app.services import pattern_engine as pe
from app.services.roic_client import (
    fetch_fundamental_context,
    fetch_historical_prices,
    fetch_latest_price,
)
from app.services.sector_peers import get_peers_for_sector
from app.utils.json_utils import safe_parse_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

REVERSAL_SYSTEM_PROMPT = """You are a professional technical analyst and quantitative researcher.
Your task is to assess the probability of an uptrend reversal for a stock based on:
1. Current technical indicator readings
2. Historically similar patterns in this stock's own history and sector peers
3. Fundamental context

You must weigh all available evidence holistically — do NOT rely on a single indicator.
Historical pattern evidence is particularly important: if similar indicator setups historically resolved upward
the majority of the time, that is strong evidence in favor of an uptrend reversal.

You MUST respond with valid JSON only — no prose, no markdown, no explanation outside the JSON."""


def _label_rsi(v: float) -> str:
    if v < 30:
        return "oversold"
    if v < 40:
        return "approaching oversold"
    if v > 70:
        return "overbought"
    if v > 60:
        return "approaching overbought"
    return "neutral"


def _label_stoch(v: float) -> str:
    if v < 20:
        return "oversold"
    if v > 80:
        return "overbought"
    return "neutral"


def _label_cci(v: float) -> str:
    if v < -100:
        return "extreme oversold"
    if v < -50:
        return "oversold"
    if v > 100:
        return "extreme overbought"
    if v > 50:
        return "overbought"
    return "neutral"


def _label_willr(v: float) -> str:
    if v < -80:
        return "oversold"
    if v > -20:
        return "overbought"
    return "neutral"


def _label_adx(v: float) -> str:
    if v < 20:
        return "weak trend / ranging"
    if v < 30:
        return "moderate trend"
    return "strong trend"


def _label_pct_b(v: float) -> str:
    if v < 0.1:
        return "near/below lower band"
    if v > 0.9:
        return "near/above upper band"
    return "mid-band"


def _label_cmf(v: float) -> str:
    if v > 0.1:
        return "buying pressure"
    if v < -0.1:
        return "selling pressure"
    return "neutral"


def compute_current_snapshot(weekly_df: pd.DataFrame) -> dict:
    """Extract current (last-bar) indicator readings with qualitative labels."""
    close = weekly_df["close"]
    high = weekly_df["high"]
    low = weekly_df["low"]
    volume = weekly_df["volume"]

    def last(series: pd.Series) -> float | None:
        vals = series.dropna()
        return round(float(vals.iloc[-1]), 4) if len(vals) > 0 else None

    rsi_val = last(ta.momentum.RSIIndicator(close, window=14, fillna=False).rsi())
    stoch_k_val = last(
        ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3, fillna=False).stoch()
    )
    stoch_d_val = last(
        ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3, fillna=False).stoch_signal()
    )

    macd_obj = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9, fillna=False)
    macd_val = last(macd_obj.macd())
    macd_sig_val = last(macd_obj.macd_signal())
    macd_hist_val = last(macd_obj.macd_diff())

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0, fillna=False)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_range = (bb_upper - bb_lower).replace(0, np.nan)
    pct_b_series = (close - bb_lower) / bb_range
    pct_b_val = last(pct_b_series)

    cci_val = last(ta.trend.CCIIndicator(high, low, close, window=20, fillna=False).cci())
    willr_val = last(ta.momentum.WilliamsRIndicator(high, low, close, lbp=14, fillna=False).williams_r())
    roc_val = last(ta.momentum.ROCIndicator(close, window=12, fillna=False).roc())
    adx_val = last(ta.trend.ADXIndicator(high, low, close, window=14, fillna=False).adx())
    cmf_val = last(ta.volume.ChaikinMoneyFlowIndicator(high, low, close, volume, window=20, fillna=False).chaikin_money_flow())
    atr_val = last(ta.volatility.AverageTrueRange(high, low, close, window=14, fillna=False).average_true_range())

    current_price = float(close.iloc[-1])
    high_52w = float(close.tail(52).max())
    low_52w = float(close.tail(52).min())
    pct_from_52w_high = round((current_price - high_52w) / high_52w * 100, 2) if high_52w > 0 else None
    ret_4w = round((current_price - float(close.iloc[-5])) / float(close.iloc[-5]) * 100, 2) if len(close) >= 5 else None

    snapshot = {
        "current_price": round(current_price, 4),
        "high_52w": round(high_52w, 4),
        "low_52w": round(low_52w, 4),
        "pct_from_52w_high": pct_from_52w_high,
        "ret_4w_pct": ret_4w,
        "indicators": {},
    }

    if rsi_val is not None:
        snapshot["indicators"]["RSI(14)"] = {"value": rsi_val, "label": _label_rsi(rsi_val)}
    if stoch_k_val is not None:
        snapshot["indicators"]["Stoch %K(14,3)"] = {"value": round(stoch_k_val, 2), "label": _label_stoch(stoch_k_val)}
    if stoch_d_val is not None:
        snapshot["indicators"]["Stoch %D(14,3)"] = {"value": round(stoch_d_val, 2), "label": "signal"}
    if macd_hist_val is not None:
        direction = "bullish" if macd_hist_val > 0 else "bearish"
        snapshot["indicators"]["MACD histogram(12,26,9)"] = {
            "value": round(macd_hist_val, 4),
            "label": f"{direction}, {'expanding' if abs(macd_hist_val) > 0 else 'flat'}",
        }
    if pct_b_val is not None:
        snapshot["indicators"]["Bollinger %B(20,2)"] = {"value": round(pct_b_val, 3), "label": _label_pct_b(pct_b_val)}
    if cci_val is not None:
        snapshot["indicators"]["CCI(20)"] = {"value": round(cci_val, 2), "label": _label_cci(cci_val)}
    if willr_val is not None:
        snapshot["indicators"]["Williams %R(14)"] = {"value": round(willr_val, 2), "label": _label_willr(willr_val)}
    if roc_val is not None:
        snapshot["indicators"]["ROC(12)"] = {"value": round(roc_val, 2), "label": "momentum"}
    if adx_val is not None:
        snapshot["indicators"]["ADX(14)"] = {"value": round(adx_val, 2), "label": _label_adx(adx_val)}
    if cmf_val is not None:
        snapshot["indicators"]["CMF(20)"] = {"value": round(cmf_val, 4), "label": _label_cmf(cmf_val)}
    if atr_val is not None:
        atr_pct = round(atr_val / current_price * 100, 2) if current_price > 0 else None
        snapshot["indicators"]["ATR(14)"] = {
            "value": round(atr_val, 4),
            "label": f"{atr_pct}% of price" if atr_pct else "volatility measure",
        }

    return snapshot


def _format_snapshot_for_prompt(ticker: str, snapshot: dict, as_of: str) -> str:
    lines = [f"Current snapshot for {ticker} (weekly bars, as of {as_of}):"]
    lines.append(f"  Price: ${snapshot['current_price']}")
    lines.append(f"  52-week high: ${snapshot['high_52w']}, low: ${snapshot['low_52w']}")
    if snapshot.get("pct_from_52w_high") is not None:
        lines.append(f"  % from 52w high: {snapshot['pct_from_52w_high']}%")
    if snapshot.get("ret_4w_pct") is not None:
        lines.append(f"  4-week return: {snapshot['ret_4w_pct']}%")
    lines.append("")
    lines.append("  Indicator readings:")
    for ind_name, info in snapshot.get("indicators", {}).items():
        lines.append(f"    {ind_name} = {info['value']}  [{info['label']}]")
    return "\n".join(lines)


def _format_pattern_summary(summary: dict, label: str) -> str:
    if not summary or summary.get("match_count", 0) == 0:
        return f"{label}: No similar patterns found."
    lines = [f"{label}:"]
    lines.append(f"  Found {summary['match_count']} similar bars (avg cosine similarity: {summary['avg_similarity']})")
    for horizon_key, stats in summary.get("horizons", {}).items():
        if stats.get("uptrend_pct") is not None:
            lines.append(
                f"  {horizon_key} forward: {stats['uptrend_pct']}% uptrend "
                f"({stats['count']} matches), median return {stats['median_return_pct']:+.1f}%"
            )
    if summary.get("matches"):
        top3 = summary["matches"][:3]
        lines.append("  Top 3 most similar past bars:")
        for m in top3:
            parts = [f"    {m['date']} (similarity {m['similarity']})"]
            returns = []
            if m.get("fwd_4w_pct") is not None:
                returns.append(f"4w: {m['fwd_4w_pct']:+.1f}%")
            if m.get("fwd_8w_pct") is not None:
                returns.append(f"8w: {m['fwd_8w_pct']:+.1f}%")
            if m.get("fwd_12w_pct") is not None:
                returns.append(f"12w: {m['fwd_12w_pct']:+.1f}%")
            if returns:
                parts.append(" → " + ", ".join(returns))
            lines.append("".join(parts))
    return "\n".join(lines)


def _format_peer_summaries(peer_results: list[dict]) -> str:
    valid = [p for p in peer_results if p.get("match_count", 0) > 0]
    if not valid:
        return "Peer analysis: No comparable patterns found in peer stocks."

    lines = [f"Peer pattern analysis ({len(valid)} peer stocks with matches):"]
    # Aggregate across peers
    all_8w_rates = [p["horizons"]["8w"]["uptrend_pct"] for p in valid if p.get("horizons", {}).get("8w", {}).get("uptrend_pct") is not None]
    all_8w_returns = [p["horizons"]["8w"]["median_return_pct"] for p in valid if p.get("horizons", {}).get("8w", {}).get("median_return_pct") is not None]
    if all_8w_rates:
        lines.append(f"  Aggregate 8w uptrend rate across peers: {sum(all_8w_rates)/len(all_8w_rates):.1f}%")
    if all_8w_returns:
        lines.append(f"  Aggregate 8w median return across peers: {sum(all_8w_returns)/len(all_8w_returns):+.1f}%")
    lines.append("")
    for p in valid:
        ticker = p.get("ticker", "?")
        h8 = p.get("horizons", {}).get("8w", {})
        if h8.get("uptrend_pct") is not None:
            lines.append(
                f"  {ticker}: {p['match_count']} similar bars, "
                f"8w uptrend {h8['uptrend_pct']}%, median {h8['median_return_pct']:+.1f}%"
            )
    return "\n".join(lines)


def _format_fundamentals(fundamentals: dict) -> str:
    if not fundamentals:
        return ""
    lines = ["Fundamental context (Roic.ai):"]
    if "sector" in fundamentals:
        lines.append(f"  Sector: {fundamentals['sector']} / {fundamentals.get('industry', 'N/A')}")
    if "market_cap_bn" in fundamentals:
        lines.append(f"  Market Cap: ${fundamentals['market_cap_bn']}B")
    if "roic_avg" in fundamentals:
        lines.append(f"  ROIC (3yr avg): {fundamentals['roic_avg']:.1%}")
    if "revenue_cagr_3yr" in fundamentals:
        lines.append(f"  Revenue CAGR (3yr): {fundamentals['revenue_cagr_3yr']:.1%}")
    if "net_margin_avg" in fundamentals:
        lines.append(f"  Net Margin (avg): {fundamentals['net_margin_avg']:.1%}")
    return "\n".join(lines)


def build_llm_prompt(
    ticker: str,
    snapshot: dict,
    own_stock_summary: dict,
    peer_summaries: list[dict],
    fundamentals: dict | None,
    as_of: str,
) -> str:
    sections = [
        _format_snapshot_for_prompt(ticker, snapshot, as_of),
        "",
        _format_pattern_summary(own_stock_summary, f"Historical pattern matching — {ticker}'s own history"),
        "",
        _format_peer_summaries(peer_summaries),
    ]
    if fundamentals:
        sections += ["", _format_fundamentals(fundamentals)]

    sections += [
        "",
        "Instructions:",
        "- Synthesize ALL evidence: current indicator readings + historical pattern outcomes + peer evidence + fundamentals.",
        "- Pay special attention to the historical pattern evidence — if similar setups resolved upward historically, that is important.",
        "- uptrend_probability should reflect your holistic assessment (0=certain downtrend, 100=certain uptrend).",
        "- Be specific in bullish_signals, bearish_signals — name the actual indicator and value.",
        "- In analysis, reference specific historical patterns and dates where relevant.",
        "- Identify key_support_level and key_resistance_level from recent price action if discernible.",
        "",
        "Respond with ONLY this JSON (no markdown, no prose outside JSON):",
        json.dumps({
            "uptrend_probability": 65.0,
            "confidence": "medium",
            "signal_strength": "moderate",
            "timeframe_estimate": "4–8 weeks",
            "bullish_signals": ["RSI at 28.4 — oversold zone signals potential bounce"],
            "bearish_signals": ["ADX at 38.1 — strong trend, reversal requires momentum shift"],
            "neutral_signals": ["MACD histogram narrowing — inconclusive"],
            "analysis": "3–4 paragraph holistic analysis here...",
            "key_support_level": 145.00,
            "key_resistance_level": 162.00,
            "risk_factors": ["Broader market weakness could override oversold readings"],
            "historical_evidence_summary": "7 similar patterns found in AAPL's history; 86% led to gains within 8 weeks.",
        }, indent=2),
    ]
    return "\n".join(sections)


def _call_llm(api_key: str, model: str, prompt: str) -> dict:
    """Make an OpenRouter API call for the reversal prediction."""
    import httpx

    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://backtesting-bot.local",
        "X-Title": "LLM Backtesting Bot",
    }
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": REVERSAL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.Client(timeout=600.0) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=payload)
    data = resp.json()

    if "error" in data:
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise ValueError(f"OpenRouter error ({resp.status_code}): {msg}")

    if resp.status_code != 200:
        raise ValueError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")

    choices = data.get("choices", [])
    if not choices:
        raise ValueError("OpenRouter returned no choices.")

    return safe_parse_json(choices[0]["message"]["content"]) or {}


def predict_reversal(
    ticker: str,
    peer_tickers: list[str] | None,
    model: str,
    openrouter_api_key: str,
    roic_api_key: str,
) -> dict:
    """
    Full orchestration pipeline.
    Returns a dict with keys: ticker, company_name, current_price,
    change_percent, as_of, weekly_bars, own_stock_pattern, peer_patterns,
    prediction (ReversalPredictionResponse fields).
    """
    ticker = ticker.upper().strip()
    logger.info("Starting reversal prediction for %s", ticker)

    # 1. Fetch historical prices
    daily_df = fetch_historical_prices(ticker, roic_api_key)
    if daily_df is None or len(daily_df) < 40:
        raise ValueError(f"Insufficient historical price data for {ticker}. The ticker may be invalid or not covered.")

    # 2. Resample to weekly
    weekly_df = pe.resample_to_weekly(daily_df)
    if len(weekly_df) < 30:
        raise ValueError(f"Not enough weekly bars for {ticker} after resampling (got {len(weekly_df)}).")
    logger.info("%s: %d weekly bars", ticker, len(weekly_df))

    # 3. Fetch live price (for current price display)
    latest = fetch_latest_price(ticker, roic_api_key)
    current_price = latest["close"] if latest and latest.get("close") else float(weekly_df["close"].iloc[-1])
    change_percent = latest.get("change_percent") if latest else None
    as_of = latest.get("date", "") if latest else str(weekly_df["time"].iloc[-1])[:10]

    # 4. Compute current snapshot (indicator readings)
    snapshot = compute_current_snapshot(weekly_df)

    # 5. Own-stock pattern matching
    own_stock_summary = pe.run_own_stock_analysis(weekly_df)
    logger.info("%s own-stock pattern: %s matches", ticker, own_stock_summary.get("match_count", 0))

    # 6. Build current indicator vector (for peer comparison)
    indicator_matrix = pe.build_indicator_matrix(weekly_df)
    current_vector = indicator_matrix.iloc[-1].values if len(indicator_matrix) > 0 else None

    # 7. Fetch fundamentals (for sector peer detection + LLM context)
    fundamentals = fetch_fundamental_context(ticker, roic_api_key)
    company_name = fundamentals.get("company_name", ticker) if fundamentals else ticker

    # 8. Determine peers
    if peer_tickers:
        peers_to_analyze = [p.upper().strip() for p in peer_tickers if p.strip()]
    elif fundamentals and fundamentals.get("sector"):
        peers_to_analyze = get_peers_for_sector(fundamentals["sector"], exclude_ticker=ticker)
        logger.info("Auto-detected peers for sector '%s': %s", fundamentals["sector"], peers_to_analyze)
    else:
        peers_to_analyze = []

    # 9. Peer pattern analysis
    peer_summaries: list[dict] = []
    if current_vector is not None and peers_to_analyze:
        for peer in peers_to_analyze[:6]:  # cap at 6 peers to control latency
            try:
                peer_daily = fetch_historical_prices(peer, roic_api_key, limit=1300)
                if peer_daily is None or len(peer_daily) < 40:
                    logger.warning("Skipping peer %s — insufficient data", peer)
                    continue
                peer_weekly = pe.resample_to_weekly(peer_daily)
                if len(peer_weekly) < 30:
                    continue
                peer_result = pe.run_peer_analysis(current_vector, peer, peer_weekly)
                peer_summaries.append(peer_result)
            except Exception as exc:
                logger.warning("Peer analysis failed for %s: %s", peer, exc)

    logger.info("Completed peer analysis for %d/%d peers", len(peer_summaries), len(peers_to_analyze))

    # 10. Build LLM prompt and call LLM
    prompt = build_llm_prompt(ticker, snapshot, own_stock_summary, peer_summaries, fundamentals, as_of)
    logger.debug("Reversal LLM prompt:\n%s", prompt[:2000])

    raw_llm = _call_llm(openrouter_api_key, model, prompt)

    # 11. Parse and validate response
    prediction: dict = {}
    try:
        validated = ReversalPredictionResponse(**raw_llm)
        prediction = validated.model_dump()
    except (ValidationError, TypeError) as exc:
        logger.warning("Reversal LLM response validation error: %s", exc)
        prediction = {
            "uptrend_probability": raw_llm.get("uptrend_probability", 50.0),
            "confidence": raw_llm.get("confidence", "low"),
            "signal_strength": raw_llm.get("signal_strength", "weak"),
            "timeframe_estimate": raw_llm.get("timeframe_estimate", "unknown"),
            "bullish_signals": raw_llm.get("bullish_signals", []),
            "bearish_signals": raw_llm.get("bearish_signals", []),
            "neutral_signals": raw_llm.get("neutral_signals", []),
            "analysis": raw_llm.get("analysis", "Analysis unavailable due to parsing error."),
            "key_support_level": raw_llm.get("key_support_level"),
            "key_resistance_level": raw_llm.get("key_resistance_level"),
            "risk_factors": raw_llm.get("risk_factors", []),
            "historical_evidence_summary": raw_llm.get("historical_evidence_summary", ""),
        }

    return {
        "ticker": ticker,
        "company_name": company_name,
        "current_price": round(float(current_price), 4),
        "change_percent": change_percent,
        "as_of": as_of,
        "weekly_bars": len(weekly_df),
        "snapshot": snapshot,
        "own_stock_pattern": own_stock_summary,
        "peer_patterns": peer_summaries,
        "peers_analyzed": [p.get("ticker") for p in peer_summaries],
        "prediction": prediction,
    }
