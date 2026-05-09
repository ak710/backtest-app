from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.models.indicators import INDICATOR_STRATEGIES
from app.models.llm_schemas import (
    IndicatorSelectionResponse,
    LLMAnalysisRequest,
    LLMAnalysisResponse,
    LLMIndicatorSelectionRequest,
    SelectedIndicatorConfig,
    SuggestedModification,
    TopStrategy,
)
from app.utils.json_utils import safe_parse_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SELECTION_SYSTEM_PROMPT = """You are a quantitative trading research assistant specializing in technical analysis for weekly and monthly bar data.
Your goal is to select promising indicator configurations for backtesting on a single stock.
Focus on robust, low-drawdown strategies. Prefer indicators with a strong theoretical basis.
You MUST respond with valid JSON only — no prose, no markdown, no explanation outside the JSON."""

ANALYSIS_SYSTEM_PROMPT = """You are a quantitative portfolio analyst specializing in strategy optimization.
Your goal is to analyze backtest results and provide actionable insights to improve Sharpe ratio and reduce volatility.
You MUST respond with valid JSON only — no prose, no markdown, no explanation outside the JSON."""


class LLMClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.client = httpx.Client(timeout=120.0)

    def _chat(self, system: str, user: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://backtesting-bot.local",
            "X-Title": "LLM Backtesting Bot",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = self.client.post(OPENROUTER_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def select_indicators(
        self, req: LLMIndicatorSelectionRequest
    ) -> IndicatorSelectionResponse:
        catalog_json = json.dumps(
            [s.model_dump() for s in req.indicator_catalog], indent=2
        )
        user_prompt = f"""Stock: {req.stock_symbol}
Timeframe: {req.timeframe} bars
Period: {req.sample_start} to {req.sample_end} ({req.num_bars} bars)

Basic statistics:
{json.dumps(req.basic_stats, indent=2)}

Objective: {req.objective}

Available indicators:
{catalog_json}

Instructions:
- Select exactly 10-15 indicator configurations.
- For each, pick parameters within the specified param_ranges.
- Assign a strategy_template from the indicator's compatible_strategies list.
- Provide a brief rationale.
- Ensure diversity: include trend, momentum, volatility, and volume indicators.
- For indicators with fast/slow lengths, ensure fast < slow.

Respond with ONLY this JSON:
{{
  "indicators_to_test": [
    {{
      "indicator_name": "<name>",
      "params": {{}},
      "strategy_template": "<template>",
      "rationale": "<why>"
    }}
  ]
}}"""

        raw = self._chat(SELECTION_SYSTEM_PROMPT, user_prompt)
        logger.debug("LLM selection response: %s", raw[:1000])
        parsed = safe_parse_json(raw)
        if not parsed:
            raise ValueError("LLM returned unparseable JSON for indicator selection.")

        # Validate and filter
        raw_list = parsed.get("indicators_to_test", [])
        valid_configs: list[SelectedIndicatorConfig] = []
        for item in raw_list:
            try:
                cfg = SelectedIndicatorConfig(**item)
                # Check indicator exists in registry
                from app.models.indicators import INDICATOR_CATALOG, INDICATOR_STRATEGIES
                if cfg.indicator_name not in INDICATOR_CATALOG:
                    logger.warning("LLM picked unknown indicator: %s", cfg.indicator_name)
                    continue
                # Check strategy is compatible
                allowed = INDICATOR_STRATEGIES.get(cfg.indicator_name, [])
                if cfg.strategy_template not in allowed:
                    # Use first compatible strategy
                    if allowed:
                        cfg.strategy_template = allowed[0]
                    else:
                        continue
                # Clip params to ranges
                meta = INDICATOR_CATALOG[cfg.indicator_name]
                clipped_params = {}
                for k, v in cfg.params.items():
                    if k in meta.param_ranges:
                        r = meta.param_ranges[k]
                        if isinstance(r, dict) and "min" in r:
                            clipped_params[k] = max(r["min"], min(r["max"], v))
                        else:
                            clipped_params[k] = v
                    else:
                        clipped_params[k] = v
                cfg.params = clipped_params
                valid_configs.append(cfg)
            except (ValidationError, TypeError) as exc:
                logger.warning("Invalid indicator config from LLM: %s – %s", item, exc)

        if not valid_configs:
            raise ValueError("LLM returned no valid indicator configurations.")

        return IndicatorSelectionResponse(indicators_to_test=valid_configs)

    def analyze_results(self, req: LLMAnalysisRequest) -> LLMAnalysisResponse:
        summaries_json = json.dumps(
            [s.model_dump() for s in req.strategies], indent=2
        )
        short_data_note = (
            f"NOTE: Only {req.num_bars} {req.timeframe} bars are available. "
            "Statistical significance is limited — please caveat conclusions accordingly."
            if req.num_bars < (36 if req.timeframe == "monthly" else 156)
            else ""
        )
        user_prompt = f"""Stock: {req.stock_symbol}
Timeframe: {req.timeframe} bars
Risk-free rate (annual): {req.risk_free_rate_annual:.2%}
{short_data_note}

Backtest results:
{summaries_json}

Additional notes: {req.notes or "None"}

Instructions:
1. Rank strategies by ROBUSTNESS (not just Sharpe). Consider drawdown, num_trades, win_rate.
2. Explain which indicators worked best and the likely reason.
3. Suggest specific parameter changes to improve Sharpe and reduce max_drawdown.
4. Include warnings about data limitations.

Respond with ONLY this JSON:
{{
  "summary_insights": "<2-3 paragraph analysis>",
  "top_strategies": [
    {{
      "indicator_name": "<name>",
      "strategy_template": "<template>",
      "params": {{}},
      "reason": "<why this is top>"
    }}
  ],
  "suggested_modifications": [
    {{
      "base_indicator_name": "<name>",
      "base_strategy_template": "<template>",
      "new_params": {{}},
      "risk_controls": {{}},
      "expected_effect": "<what this should improve>"
    }}
  ],
  "warnings": ["<warning1>"]
}}"""

        raw = self._chat(ANALYSIS_SYSTEM_PROMPT, user_prompt)
        logger.debug("LLM analysis response: %s", raw[:1000])
        parsed = safe_parse_json(raw)
        if not parsed:
            raise ValueError("LLM returned unparseable JSON for result analysis.")

        try:
            return LLMAnalysisResponse(**parsed)
        except (ValidationError, TypeError) as exc:
            logger.warning("LLM analysis response validation error: %s", exc)
            # Return partial response
            return LLMAnalysisResponse(
                summary_insights=parsed.get("summary_insights", "Analysis unavailable."),
                top_strategies=[
                    TopStrategy(**s)
                    for s in parsed.get("top_strategies", [])
                    if all(k in s for k in ("indicator_name", "strategy_template", "params", "reason"))
                ],
                suggested_modifications=[
                    SuggestedModification(**m)
                    for m in parsed.get("suggested_modifications", [])
                    if all(k in m for k in ("base_indicator_name", "base_strategy_template", "new_params"))
                ],
                warnings=parsed.get("warnings", []),
            )
