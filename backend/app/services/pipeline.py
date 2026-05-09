from __future__ import annotations

from typing import BinaryIO, Literal

from app.config import settings
from app.models.data_models import BacktestResult, FullAnalysisResult, PreparedData, RiskSettings
from app.models.indicators import IndicatorRegistry
from app.models.llm_schemas import LLMAnalysisRequest, LLMIndicatorSelectionRequest
from app.services.backtester import run_strategy
from app.services.data_loader import load_and_prepare_timeseries
from app.services.indicators_engine import compute_indicator
from app.services.llm_client import LLMClient
from app.services.metrics import compute_metrics, to_strategy_summary
from app.services.reporting import generate_report
from app.services.roic_client import fetch_fundamental_context
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_RISK_SETTINGS = RiskSettings()


def _run_backtest_for_config(
    prepared: PreparedData,
    registry: IndicatorRegistry,
    indicator_name: str,
    strategy_template: str,
    params: dict,
    risk_settings: RiskSettings,
) -> BacktestResult | None:
    meta = registry.get(indicator_name)
    if meta is None:
        logger.warning("Unknown indicator in registry: %s", indicator_name)
        return None

    indicator_data = compute_indicator(prepared.df, meta, params)
    if indicator_data is None:
        return BacktestResult(
            indicator_name=indicator_name,
            strategy_template=strategy_template,
            params=params,
            trades=[],
            equity_curve=[],
            period_returns=[],
            skipped=True,
            skip_reason="Indicator computation failed (insufficient data or unsupported params).",
        )

    result = run_strategy(
        data=prepared,
        meta=meta,
        indicator_data=indicator_data,
        params=params,
        strategy_template=strategy_template,
        risk_settings=risk_settings,
    )
    return result


def run_full_analysis(
    file_bytes: bytes,
    stock_symbol: str,
    timeframe: Literal["weekly", "monthly"],
    risk_free_rate_annual: float,
    model: str | None = None,
) -> FullAnalysisResult:
    # ── Step 1: Data preparation ──────────────────────────────────────────
    logger.info("Loading data for %s (%s)", stock_symbol, timeframe)
    prepared = load_and_prepare_timeseries(file_bytes, timeframe, symbol=stock_symbol)
    logger.info("Loaded %d bars from %s to %s", prepared.num_bars, prepared.start_date, prepared.end_date)

    registry = IndicatorRegistry()

    # ── Step 2: LLM #1 – select indicators ───────────────────────────────
    resolved_model = model or settings.openrouter_model
    logger.info("Using model: %s", resolved_model)
    llm_client = LLMClient(api_key=settings.openrouter_api_key, model=resolved_model)

    logger.info("Fetching fundamental context from Roic.ai for %s...", stock_symbol)
    fundamental_context = fetch_fundamental_context(stock_symbol, settings.roic_api_key)
    if fundamental_context:
        logger.info("Fundamental context fetched successfully")
    else:
        logger.info("No fundamental context (ROIC_API_KEY not set or request failed) — proceeding without it")

    selection_request = LLMIndicatorSelectionRequest(
        stock_symbol=stock_symbol,
        timeframe=timeframe,
        sample_start=prepared.start_date,
        sample_end=prepared.end_date,
        num_bars=prepared.num_bars,
        basic_stats=prepared.basic_stats,
        indicator_catalog=registry.to_summaries(),
        fundamental_context=fundamental_context,
    )

    logger.info("Calling LLM #1 to select indicators...")
    selection_response = llm_client.select_indicators(selection_request)
    configs = selection_response.indicators_to_test
    logger.info("LLM selected %d indicator configs", len(configs))

    # ── Step 3: Run backtests ─────────────────────────────────────────────
    base_results: list[BacktestResult] = []
    for cfg in configs:
        logger.info("Backtesting: %s / %s", cfg.indicator_name, cfg.strategy_template)
        result = _run_backtest_for_config(
            prepared=prepared,
            registry=registry,
            indicator_name=cfg.indicator_name,
            strategy_template=cfg.strategy_template,
            params=cfg.params,
            risk_settings=DEFAULT_RISK_SETTINGS,
        )
        if result is None:
            continue
        result.metrics = compute_metrics(result, timeframe, risk_free_rate_annual)
        base_results.append(result)

    logger.info("Completed %d backtests (%d skipped)", len(base_results), sum(1 for r in base_results if r.skipped))

    # ── Step 4: LLM #2 – analyze results ─────────────────────────────────
    valid_results = [r for r in base_results if not r.skipped]
    summaries = [to_strategy_summary(r) for r in valid_results]

    short_data_warning = ""
    min_bars = 36 if timeframe == "monthly" else 156
    if prepared.num_bars < min_bars:
        short_data_warning = (
            f"Dataset is short ({prepared.num_bars} {timeframe} bars). "
            "Backtest results may overfit and Sharpe ratios are statistically unreliable."
        )

    analysis_request = LLMAnalysisRequest(
        stock_symbol=stock_symbol,
        timeframe=timeframe,
        risk_free_rate_annual=risk_free_rate_annual,
        num_bars=prepared.num_bars,
        strategies=summaries,
        notes=short_data_warning,
    )

    logger.info("Calling LLM #2 to analyze results...")
    llm_analysis = llm_client.analyze_results(analysis_request)

    # ── Step 5: Backtest suggested modifications ──────────────────────────
    modified_results: list[BacktestResult] = []
    for mod in llm_analysis.suggested_modifications:
        logger.info("Backtesting modification: %s / %s", mod.base_indicator_name, mod.base_strategy_template)
        # Merge risk controls into params
        merged_params = {**mod.new_params, **mod.risk_controls}
        result = _run_backtest_for_config(
            prepared=prepared,
            registry=registry,
            indicator_name=mod.base_indicator_name,
            strategy_template=mod.base_strategy_template,
            params=merged_params,
            risk_settings=DEFAULT_RISK_SETTINGS,
        )
        if result is None:
            continue
        result.metrics = compute_metrics(result, timeframe, risk_free_rate_annual)
        # Tag as modified
        result.params["_modified"] = True
        result.params["_expected_effect"] = mod.expected_effect
        modified_results.append(result)

    # ── Step 6: Generate report ───────────────────────────────────────────
    logger.info("Generating report...")
    report = generate_report(
        prepared=prepared,
        base_results=base_results,
        modified_results=modified_results,
        llm_analysis=llm_analysis,
        initial_capital=DEFAULT_RISK_SETTINGS.initial_capital,
    )

    return FullAnalysisResult(
        stock_symbol=stock_symbol,
        timeframe=timeframe,
        base_results=base_results,
        modified_results=modified_results,
        llm_analysis=llm_analysis.model_dump(),
        report=report,
    )
