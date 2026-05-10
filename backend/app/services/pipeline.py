from __future__ import annotations

from typing import BinaryIO, Literal

import pandas as pd

from app.config import settings
from app.models.data_models import BacktestResult, FullAnalysisResult, PreparedData, RiskSettings
from app.models.indicators import IndicatorRegistry
from app.models.llm_schemas import LLMAnalysisRequest, LLMIndicatorSelectionRequest
from app.services.backtester import run_benchmark, run_strategy
from app.services.data_loader import load_and_prepare_timeseries
from app.services.indicators_engine import compute_indicator
from app.services.llm_client import LLMClient
from app.services.metrics import compute_metrics, to_strategy_summary
from app.services.reporting import generate_report
from app.services.roic_client import fetch_fundamental_context
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Minimum bars required for IS and OOS slices
_MIN_IS_BARS = {"monthly": 24, "weekly": 96}
_MIN_OOS_BARS = {"monthly": 12, "weekly": 48}


def _slice_prepared_data(prepared: PreparedData, df_slice: pd.DataFrame) -> PreparedData:
    """Return a new PreparedData covering only df_slice rows."""
    returns = df_slice["close"].pct_change().dropna()
    basic_stats = {
        "mean_return": float(returns.mean()),
        "std_return": float(returns.std()),
        "min_price": float(df_slice["close"].min()),
        "max_price": float(df_slice["close"].max()),
        "mean_volume": float(df_slice["volume"].mean()),
        "total_bars": len(df_slice),
        "years_covered": round((df_slice.index[-1] - df_slice.index[0]).days / 365.25, 2),
    }
    return PreparedData(
        symbol=prepared.symbol,
        frequency=prepared.frequency,
        df=df_slice,
        returns=returns,
        num_bars=len(df_slice),
        start_date=str(df_slice.index[0].date()),
        end_date=str(df_slice.index[-1].date()),
        basic_stats=basic_stats,
        data_quality=[],
    )


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
    commission: float = 0.001,
    slippage: float = 0.0005,
    walk_forward: bool = False,
) -> FullAnalysisResult:
    # ── Step 1: Data preparation ──────────────────────────────────────────
    logger.info("Loading data for %s (%s)", stock_symbol, timeframe)
    full_prepared = load_and_prepare_timeseries(file_bytes, timeframe, symbol=stock_symbol)
    logger.info("Loaded %d bars from %s to %s", full_prepared.num_bars, full_prepared.start_date, full_prepared.end_date)
    if full_prepared.data_quality:
        logger.warning("Data quality issues: %s", full_prepared.data_quality)

    risk_settings = RiskSettings(commission=commission, slippage=slippage)
    registry = IndicatorRegistry()

    # ── Walk-forward split ────────────────────────────────────────────────
    oos_prepared: PreparedData | None = None
    walk_forward_split_date = ""

    if walk_forward:
        split_idx = int(len(full_prepared.df) * 0.7)
        min_is = _MIN_IS_BARS[timeframe]
        min_oos = _MIN_OOS_BARS[timeframe]
        if split_idx >= min_is and (len(full_prepared.df) - split_idx) >= min_oos:
            is_df = full_prepared.df.iloc[:split_idx]
            oos_df = full_prepared.df.iloc[split_idx:]
            walk_forward_split_date = str(oos_df.index[0].date())
            oos_prepared = _slice_prepared_data(full_prepared, oos_df)
            prepared = _slice_prepared_data(full_prepared, is_df)
            logger.info(
                "Walk-forward enabled: IS %d bars (%s → %s), OOS %d bars (%s → %s)",
                len(is_df), prepared.start_date, prepared.end_date,
                len(oos_df), oos_prepared.start_date, oos_prepared.end_date,
            )
        else:
            logger.warning(
                "Insufficient data for walk-forward (need IS≥%d + OOS≥%d, got %d total). "
                "Proceeding without split.",
                min_is, min_oos, full_prepared.num_bars,
            )
            walk_forward = False
            prepared = full_prepared
    else:
        prepared = full_prepared

    # ── Step 2: LLM #1 – select indicators (uses IS stats when WF on) ────
    resolved_model = model or settings.openrouter_model
    logger.info("Using model: %s", resolved_model)
    llm_client = LLMClient(api_key=settings.openrouter_api_key, model=resolved_model)

    logger.info("Fetching fundamental context from Roic.ai for %s...", stock_symbol)
    fundamental_context = fetch_fundamental_context(stock_symbol, settings.roic_api_key)
    if fundamental_context:
        logger.info("Fundamental context fetched successfully")
    else:
        logger.info("No fundamental context — proceeding without it")

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

    # ── Step 3: Run backtests on IS (or full) data ────────────────────────
    base_results: list[BacktestResult] = []
    for cfg in configs:
        logger.info("Backtesting: %s / %s", cfg.indicator_name, cfg.strategy_template)
        result = _run_backtest_for_config(
            prepared=prepared,
            registry=registry,
            indicator_name=cfg.indicator_name,
            strategy_template=cfg.strategy_template,
            params=cfg.params,
            risk_settings=risk_settings,
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

    # ── Step 5: Backtest suggested modifications (on IS/full data) ────────
    modified_results: list[BacktestResult] = []
    for mod in llm_analysis.suggested_modifications:
        logger.info("Backtesting modification: %s / %s", mod.base_indicator_name, mod.base_strategy_template)
        merged_params = {**mod.new_params, **mod.risk_controls}
        result = _run_backtest_for_config(
            prepared=prepared,
            registry=registry,
            indicator_name=mod.base_indicator_name,
            strategy_template=mod.base_strategy_template,
            params=merged_params,
            risk_settings=risk_settings,
        )
        if result is None:
            continue
        result.metrics = compute_metrics(result, timeframe, risk_free_rate_annual)
        result.params["_modified"] = True
        result.params["_expected_effect"] = mod.expected_effect
        modified_results.append(result)

    # ── Step 6: OOS validation (top strategies on held-out data) ─────────
    oos_results: list[BacktestResult] = []
    if walk_forward and oos_prepared is not None and llm_analysis.top_strategies:
        logger.info("Running OOS validation on %d top strategies...", len(llm_analysis.top_strategies))
        for top in llm_analysis.top_strategies:
            result = _run_backtest_for_config(
                prepared=oos_prepared,
                registry=registry,
                indicator_name=top.indicator_name,
                strategy_template=top.strategy_template,
                params=dict(top.params),
                risk_settings=risk_settings,
            )
            if result is None:
                continue
            result.metrics = compute_metrics(result, timeframe, risk_free_rate_annual, risk_settings.initial_capital)
            oos_results.append(result)
        logger.info("OOS validation complete: %d results", len(oos_results))

    # ── Step 7: Compute buy-and-hold benchmark (on IS/full data) ─────────
    logger.info("Computing buy-and-hold benchmark...")
    benchmark = run_benchmark(prepared, risk_settings)
    benchmark.metrics = compute_metrics(benchmark, timeframe, risk_free_rate_annual, risk_settings.initial_capital)

    # ── Step 8: Generate report ───────────────────────────────────────────
    logger.info("Generating report...")
    report = generate_report(
        prepared=prepared,
        base_results=base_results,
        modified_results=modified_results,
        llm_analysis=llm_analysis,
        initial_capital=risk_settings.initial_capital,
        benchmark_result=benchmark,
        oos_results=oos_results,
        walk_forward_split_date=walk_forward_split_date,
    )

    return FullAnalysisResult(
        stock_symbol=stock_symbol,
        timeframe=timeframe,
        base_results=base_results,
        modified_results=modified_results,
        llm_analysis=llm_analysis.model_dump(),
        report=report,
        selection_rationales=[
            {
                "indicator_name": cfg.indicator_name,
                "strategy_template": cfg.strategy_template,
                "params": cfg.params,
                "rationale": cfg.rationale,
            }
            for cfg in configs
        ],
        fundamental_context=fundamental_context,
        benchmark_result=benchmark,
        data_quality=full_prepared.data_quality,
        oos_results=oos_results,
        walk_forward_enabled=walk_forward,
        walk_forward_split_date=walk_forward_split_date,
    )
