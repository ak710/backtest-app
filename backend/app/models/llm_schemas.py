from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.indicators import IndicatorMetaSummary


# ── LLM Call #1 ────────────────────────────────────────────────────────────

class LLMIndicatorSelectionRequest(BaseModel):
    stock_symbol: str
    timeframe: Literal["weekly", "monthly"]
    sample_start: str
    sample_end: str
    num_bars: int
    basic_stats: dict
    indicator_catalog: list[IndicatorMetaSummary]
    fundamental_context: dict | None = None
    benchmark: dict | None = None  # buy-and-hold metrics: sharpe, cagr, max_drawdown, total_return
    price_regime: dict | None = None  # autocorr_lag1, trend_slope_annualized, vol_regime
    objective: str = (
        "Select 8-12 promising indicator configurations for backtesting. "
        "Focus on robust, low-drawdown strategies that can beat the buy-and-hold benchmark."
    )


class SelectedIndicatorConfig(BaseModel):
    indicator_name: str
    params: dict
    strategy_template: str
    rationale: str


class IndicatorSelectionResponse(BaseModel):
    indicators_to_test: list[SelectedIndicatorConfig]


# ── LLM Call #2 ────────────────────────────────────────────────────────────

class StrategySummary(BaseModel):
    indicator_name: str
    strategy_template: str
    params: dict
    cagr: float
    sharpe: float
    max_drawdown: float
    volatility: float
    num_trades: int
    win_rate: float
    total_return: float
    beats_benchmark: bool = False  # True if this strategy's Sharpe > buy-and-hold Sharpe


class LLMAnalysisRequest(BaseModel):
    stock_symbol: str
    timeframe: Literal["weekly", "monthly"]
    risk_free_rate_annual: float
    num_bars: int
    strategies: list[StrategySummary]
    benchmark: dict | None = None  # buy-and-hold metrics: sharpe, cagr, max_drawdown, total_return
    notes: str = ""


class TopStrategy(BaseModel):
    indicator_name: str
    strategy_template: str
    params: dict
    reason: str


class SuggestedModification(BaseModel):
    base_indicator_name: str
    base_strategy_template: str
    new_params: dict
    risk_controls: dict = {}
    expected_effect: str
    expected_sharpe_range: list[float] | None = None  # [low, high] e.g. [0.8, 1.2]
    targets: str | None = None  # "drawdown" | "sharpe" | "win_rate" | "frequency"


class LLMAnalysisResponse(BaseModel):
    summary_insights: str
    top_strategies: list[TopStrategy]
    suggested_modifications: list[SuggestedModification]
    warnings: list[str] = []


# ── LLM Call #3: Reversal Prediction ──────────────────────────────────────────

class ReversalPredictionResponse(BaseModel):
    uptrend_probability: float          # 0–100
    confidence: str                     # "low" | "medium" | "high"
    signal_strength: str                # "weak" | "moderate" | "strong"
    timeframe_estimate: str             # e.g. "4–8 weeks"
    bullish_signals: list[str]
    bearish_signals: list[str]
    neutral_signals: list[str]
    analysis: str                       # 3–4 paragraph narrative
    key_support_level: float | None = None
    key_resistance_level: float | None = None
    risk_factors: list[str]
    historical_evidence_summary: str    # 1–2 sentences on what past patterns showed
