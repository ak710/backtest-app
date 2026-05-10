"""Simple JSON file store for persisting analysis runs."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent.parent.parent / "data" / "runs.json"
RUNS_FILE = Path(os.environ.get("RUNS_FILE_PATH", str(_DEFAULT_PATH)))
MAX_RUNS = 200


def _load() -> list[dict]:
    if not RUNS_FILE.exists():
        return []
    try:
        with open(RUNS_FILE) as f:
            return json.load(f).get("runs", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save(runs: list[dict]) -> None:
    RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNS_FILE, "w") as f:
        json.dump({"runs": runs}, f)


def save_run(run_data: dict) -> str:
    runs = _load()
    run_id = str(uuid.uuid4())
    run_data["id"] = run_id
    run_data["created_at"] = datetime.now(timezone.utc).isoformat()
    runs.insert(0, run_data)
    if len(runs) > MAX_RUNS:
        runs = runs[:MAX_RUNS]
    _save(runs)
    return run_id


def list_runs() -> list[dict]:
    runs = _load()
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "stock_symbol": r["stock_symbol"],
            "timeframe": r["timeframe"],
            "model_used": r.get("model_used", ""),
            "walk_forward_enabled": r.get("walk_forward_enabled", False),
            "best_sharpe": r.get("best_sharpe"),
            "best_cagr": r.get("best_cagr"),
            "benchmark_cagr": r.get("benchmark_cagr"),
            "num_strategies": r.get("num_strategies", 0),
            "data_quality": r.get("data_quality", []),
        }
        for r in runs
    ]


def get_run(run_id: str) -> dict | None:
    for r in _load():
        if r.get("id") == run_id:
            return r
    return None


def delete_run(run_id: str) -> bool:
    runs = _load()
    filtered = [r for r in runs if r.get("id") != run_id]
    if len(filtered) == len(runs):
        return False
    _save(filtered)
    return True
