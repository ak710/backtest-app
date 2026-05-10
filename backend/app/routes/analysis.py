from __future__ import annotations

from typing import Annotated

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from pydantic import BaseModel

from app.config import settings
from app.models.data_models import BacktestResult, EquityPoint, PreparedData, Trade
from app.models.llm_schemas import LLMAnalysisResponse
from app.services.pipeline import run_full_analysis
from app.services.reporting import generate_report
from app.services.reversal_predictor import predict_reversal
from app.services.storage import delete_run, get_run, list_runs, save_run
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _safe_metrics(r: BacktestResult) -> dict:
    return {
        "indicator_name": r.indicator_name,
        "strategy_template": r.strategy_template,
        "params": r.params,
        "skipped": r.skipped,
        "skip_reason": r.skip_reason,
        "metrics": r.metrics,
        "trades": [t.model_dump() for t in r.trades],
    }


def _strip_for_storage(r: BacktestResult) -> dict:
    """Strip period_returns (not needed once metrics are computed)."""
    return {
        "indicator_name": r.indicator_name,
        "strategy_template": r.strategy_template,
        "params": r.params,
        "skipped": r.skipped,
        "skip_reason": r.skip_reason,
        "metrics": r.metrics,
        "trades": [t.model_dump() for t in r.trades],
        "equity_curve": [ep.model_dump() for ep in r.equity_curve],
    }


def _reconstruct(d: dict) -> BacktestResult:
    return BacktestResult(
        indicator_name=d["indicator_name"],
        strategy_template=d["strategy_template"],
        params=d.get("params", {}),
        skipped=d.get("skipped", False),
        skip_reason=d.get("skip_reason", ""),
        metrics=d.get("metrics", {}),
        trades=[Trade(**t) for t in d.get("trades", [])],
        equity_curve=[EquityPoint(**ep) for ep in d.get("equity_curve", [])],
        period_returns=[],
    )


def _build_response(
    stock_symbol: str,
    model_used: str,
    timeframe: str,
    base_results: list[BacktestResult],
    modified_results: list[BacktestResult],
    oos_results: list[BacktestResult],
    benchmark: BacktestResult | None,
    llm_raw: dict,
    report: dict,
    selection_rationales: list,
    fundamental_context: dict | None,
    data_quality: list,
    walk_forward_enabled: bool,
    walk_forward_split_date: str,
) -> dict:
    return {
        "stock_symbol": stock_symbol,
        "model_used": model_used,
        "timeframe": timeframe,
        "base_strategies": [_safe_metrics(r) for r in base_results],
        "modified_strategies": [_safe_metrics(r) for r in modified_results],
        "llm_summary": llm_raw.get("summary_insights", ""),
        "llm_top_strategies": llm_raw.get("top_strategies", []),
        "llm_suggested_modifications": llm_raw.get("suggested_modifications", []),
        "llm_warnings": llm_raw.get("warnings", []),
        "charts": report.get("charts", []),
        "strategy_charts": report.get("strategy_charts", []),
        "modified_strategy_charts": report.get("modified_strategy_charts", []),
        "selection_rationales": selection_rationales,
        "fundamental_context": fundamental_context,
        "benchmark": _safe_metrics(benchmark) if benchmark else None,
        "data_quality": data_quality,
        "oos_strategies": [_safe_metrics(r) for r in oos_results],
        "oos_strategy_charts": report.get("oos_strategy_charts", []),
        "walk_forward_enabled": walk_forward_enabled,
        "walk_forward_split_date": walk_forward_split_date,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/analyze")
async def analyze(
    file: Annotated[UploadFile, File(description="CSV file with OHLCV data")],
    stock_symbol: Annotated[str, Form()],
    timeframe: Annotated[str, Form()],
    risk_free_rate_annual: Annotated[float, Form()] = 0.03,
    model: Annotated[str, Form()] = "",
    commission: Annotated[float, Form()] = 0.001,
    slippage: Annotated[float, Form()] = 0.0005,
    walk_forward: Annotated[bool, Form()] = False,
):
    if timeframe not in ("weekly", "monthly"):
        raise HTTPException(status_code=422, detail="timeframe must be 'weekly' or 'monthly'")

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=422, detail="Only CSV files are accepted.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    try:
        result = run_full_analysis(
            file_bytes=file_bytes,
            stock_symbol=stock_symbol.upper().strip(),
            timeframe=timeframe,
            risk_free_rate_annual=risk_free_rate_annual,
            model=model.strip() or None,
            commission=max(0.0, min(commission, 0.05)),
            slippage=max(0.0, min(slippage, 0.05)),
            walk_forward=walk_forward,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during analysis")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    model_used = model.strip() or settings.openrouter_model
    bm = result.benchmark_result
    valid = [r for r in result.base_results if not r.skipped]
    best = max(valid, key=lambda r: r.metrics.get("sharpe", 0)) if valid else None

    # Persist run (no charts — regenerated on load)
    try:
        save_run({
            "stock_symbol": result.stock_symbol,
            "timeframe": result.timeframe,
            "model_used": model_used,
            "walk_forward_enabled": result.walk_forward_enabled,
            "walk_forward_split_date": result.walk_forward_split_date,
            "data_quality": result.data_quality,
            "fundamental_context": result.fundamental_context,
            "selection_rationales": result.selection_rationales,
            "price_series": result.price_series,
            "llm_analysis": result.llm_analysis,
            "base_strategies": [_strip_for_storage(r) for r in result.base_results],
            "modified_strategies": [_strip_for_storage(r) for r in result.modified_results],
            "oos_strategies": [_strip_for_storage(r) for r in result.oos_results],
            "benchmark": _strip_for_storage(bm) if bm else None,
            # summary fields for list view
            "best_sharpe": best.metrics.get("sharpe") if best else None,
            "best_cagr": best.metrics.get("cagr") if best else None,
            "benchmark_cagr": bm.metrics.get("cagr") if bm else None,
            "num_strategies": len(valid),
        })
    except Exception:
        logger.exception("Failed to save run to storage (non-fatal)")

    return JSONResponse(content=_build_response(
        stock_symbol=result.stock_symbol,
        model_used=model_used,
        timeframe=result.timeframe,
        base_results=result.base_results,
        modified_results=result.modified_results,
        oos_results=result.oos_results,
        benchmark=bm,
        llm_raw=result.llm_analysis,
        report=result.report,
        selection_rationales=result.selection_rationales,
        fundamental_context=result.fundamental_context,
        data_quality=result.data_quality,
        walk_forward_enabled=result.walk_forward_enabled,
        walk_forward_split_date=result.walk_forward_split_date,
    ))


class PredictRequest(BaseModel):
    ticker: str
    peer_tickers: list[str] | None = None
    model: str | None = None


@router.post("/predict")
async def predict(req: PredictRequest):
    ticker = req.ticker.upper().strip()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker is required.")

    model = (req.model or "").strip() or settings.openrouter_model

    if not settings.roic_api_key:
        raise HTTPException(status_code=503, detail="ROIC_API_KEY is not configured on the server.")

    try:
        result = predict_reversal(
            ticker=ticker,
            peer_tickers=req.peer_tickers,
            model=model,
            openrouter_api_key=settings.openrouter_api_key,
            roic_api_key=settings.roic_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during reversal prediction for %s", ticker)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}")

    return JSONResponse(content=result)


@router.get("/runs")
async def list_runs_endpoint():
    return JSONResponse(content={"runs": list_runs()})


@router.get("/runs/{run_id}")
async def get_run_endpoint(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Reconstruct results
    base_results = [_reconstruct(s) for s in run.get("base_strategies", [])]
    modified_results = [_reconstruct(s) for s in run.get("modified_strategies", [])]
    oos_results = [_reconstruct(s) for s in run.get("oos_strategies", [])]
    bm_data = run.get("benchmark")
    benchmark = _reconstruct(bm_data) if bm_data else None

    # Rebuild PreparedData from stored close prices
    price_series = run.get("price_series", {})
    report: dict = {"charts": [], "strategy_charts": [], "modified_strategy_charts": [], "oos_strategy_charts": []}

    if price_series:
        prices = list(price_series.values())
        dates = pd.to_datetime(list(price_series.keys()))
        df = pd.DataFrame({
            "close": prices, "open": prices, "high": prices,
            "low": prices, "volume": [0.0] * len(prices),
        }, index=dates).sort_index()

        prepared = PreparedData(
            symbol=run["stock_symbol"],
            frequency=run["timeframe"],
            df=df,
            returns=df["close"].pct_change().dropna(),
            num_bars=len(df),
            start_date=str(df.index[0].date()),
            end_date=str(df.index[-1].date()),
            basic_stats={},
            data_quality=[],
        )

        llm_analysis = LLMAnalysisResponse.model_validate(run.get("llm_analysis", {}))

        try:
            report = generate_report(
                prepared=prepared,
                base_results=base_results,
                modified_results=modified_results,
                llm_analysis=llm_analysis,
                benchmark_result=benchmark,
                oos_results=oos_results,
                walk_forward_split_date=run.get("walk_forward_split_date", ""),
            )
        except Exception:
            logger.exception("Chart regeneration failed for run %s (non-fatal)", run_id)

    return JSONResponse(content=_build_response(
        stock_symbol=run["stock_symbol"],
        model_used=run.get("model_used", ""),
        timeframe=run["timeframe"],
        base_results=base_results,
        modified_results=modified_results,
        oos_results=oos_results,
        benchmark=benchmark,
        llm_raw=run.get("llm_analysis", {}),
        report=report,
        selection_rationales=run.get("selection_rationales", []),
        fundamental_context=run.get("fundamental_context"),
        data_quality=run.get("data_quality", []),
        walk_forward_enabled=run.get("walk_forward_enabled", False),
        walk_forward_split_date=run.get("walk_forward_split_date", ""),
    ))


@router.delete("/runs/{run_id}")
async def delete_run_endpoint(run_id: str):
    if not delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "deleted"}
