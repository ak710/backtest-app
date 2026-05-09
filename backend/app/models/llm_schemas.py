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
    objective: str = (
        "Select 10-15 promising indicator configurations for backtesting. "
        "Focus on robust, low-drawdown strategies with good Sharpe ratio potential."
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


class LLMAnalysisRequest(BaseModel):
    stock_symbol: str
    timeframe: Literal["weekly", "monthly"]
    risk_free_rate_annual: float
    num_bars: int
    strategies: list[StrategySummary]
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


class LLMAnalysisResponse(BaseModel):
    summary_insights: str
    top_strategies: list[TopStrategy]
    suggested_modifications: list[SuggestedModification]
    warnings: list[str] = []
