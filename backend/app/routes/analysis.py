from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.pipeline import run_full_analysis
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


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

    # Build response
    def _safe_metrics(r):
        return {
            "indicator_name": r.indicator_name,
            "strategy_template": r.strategy_template,
            "params": r.params,
            "skipped": r.skipped,
            "skip_reason": r.skip_reason,
            "metrics": r.metrics,
            "trades": [t.model_dump() for t in r.trades],
        }

    bm = result.benchmark_result
    benchmark_payload = None
    if bm:
        benchmark_payload = {
            "indicator_name": bm.indicator_name,
            "strategy_template": bm.strategy_template,
            "params": bm.params,
            "skipped": bm.skipped,
            "skip_reason": bm.skip_reason,
            "metrics": bm.metrics,
            "trades": [t.model_dump() for t in bm.trades],
        }

    return JSONResponse(
        content={
            "stock_symbol": result.stock_symbol,
            "model_used": model.strip() or settings.openrouter_model,
            "timeframe": result.timeframe,
            "base_strategies": [_safe_metrics(r) for r in result.base_results],
            "modified_strategies": [_safe_metrics(r) for r in result.modified_results],
            "llm_summary": result.llm_analysis.get("summary_insights", ""),
            "llm_top_strategies": result.llm_analysis.get("top_strategies", []),
            "llm_suggested_modifications": result.llm_analysis.get("suggested_modifications", []),
            "llm_warnings": result.llm_analysis.get("warnings", []),
            "charts": result.report.get("charts", []),
            "strategy_charts": result.report.get("strategy_charts", []),
            "modified_strategy_charts": result.report.get("modified_strategy_charts", []),
            "selection_rationales": result.selection_rationales,
            "fundamental_context": result.fundamental_context,
            "benchmark": benchmark_payload,
            "data_quality": result.data_quality,
            "oos_strategies": [_safe_metrics(r) for r in result.oos_results],
            "oos_strategy_charts": result.report.get("oos_strategy_charts", []),
            "walk_forward_enabled": result.walk_forward_enabled,
            "walk_forward_split_date": result.walk_forward_split_date,
        }
    )
