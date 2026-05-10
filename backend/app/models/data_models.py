from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd
from pydantic import BaseModel, field_validator


class PreparedData(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    symbol: str
    frequency: Literal["weekly", "monthly"]
    df: pd.DataFrame
    returns: pd.Series
    num_bars: int
    start_date: str
    end_date: str
    basic_stats: dict
    data_quality: list[str] = []

    @field_validator("df", "returns", mode="before")
    @classmethod
    def allow_dataframe(cls, v):
        return v


class RiskSettings(BaseModel):
    initial_capital: float = 100_000.0
    position_size: float = 1.0
    commission: float = 0.001
    slippage: float = 0.0005
    max_position_size: float = 1.0


class Trade(BaseModel):
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    num_bars: int


class EquityPoint(BaseModel):
    date: str
    equity: float


class BacktestResult(BaseModel):
    indicator_name: str
    strategy_template: str
    params: dict
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    period_returns: list[float]
    metrics: dict = {}
    skipped: bool = False
    skip_reason: str = ""


class FullAnalysisResult(BaseModel):
    stock_symbol: str
    timeframe: Literal["weekly", "monthly"]
    base_results: list[BacktestResult]
    modified_results: list[BacktestResult]
    llm_analysis: dict
    report: dict
    selection_rationales: list[dict] = []
    fundamental_context: dict | None = None
    benchmark_result: BacktestResult | None = None
    data_quality: list[str] = []
    oos_results: list[BacktestResult] = []
    walk_forward_enabled: bool = False
    walk_forward_split_date: str = ""
