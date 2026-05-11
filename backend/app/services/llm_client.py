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
Focus on robust, low-drawdown strategies that can beat the buy-and-hold benchmark. Prefer indicators with a strong theoretical basis.
Prioritize configurations likely to achieve Sharpe ratio > 1.0 and max drawdown < 25%.
You MUST respond with valid JSON only — no prose, no markdown, no explanation outside the JSON."""

ANALYSIS_SYSTEM_PROMPT = """You are a quantitative portfolio analyst specializing in strategy optimization.
Your goal is to analyze backtest results and provide actionable parameter modifications to beat the buy-and-hold benchmark.
A strategy that beats buy-and-hold by 0.3 Sharpe is valuable even if its absolute Sharpe is modest.
Your modifications must be mechanistically grounded — explain WHY the parameter change produces the improvement, not just what changes.
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
        data = resp.json()

        # Surface API-level errors before touching response fields
        if "error" in data:
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise ValueError(f"OpenRouter error ({resp.status_code}): {msg}")

        if resp.status_code != 200:
            raise ValueError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")

        if "choices" not in data or not data["choices"]:
            logger.error("Unexpected OpenRouter response: %s", data)
            raise ValueError(f"OpenRouter returned no choices. Full response: {json.dumps(data)[:500]}")

        return data["choices"][0]["message"]["content"]

    def select_indicators(
        self, req: LLMIndicatorSelectionRequest
    ) -> IndicatorSelectionResponse:
        catalog_json = json.dumps(
            [s.model_dump() for s in req.indicator_catalog], indent=2
        )
        fundamental_block = ""
        if req.fundamental_context:
            fc = req.fundamental_context
            lines = []
            if "sector" in fc:
                lines.append(f"  Sector / Industry: {fc.get('sector')} / {fc.get('industry', 'N/A')}")
            if "market_cap_bn" in fc:
                lines.append(f"  Market Cap: ${fc['market_cap_bn']}B")
            if "roic_avg" in fc:
                lines.append(f"  ROIC (3yr avg): {fc['roic_avg']:.1%}")
            if "revenue_cagr_3yr" in fc:
                lines.append(f"  Revenue CAGR (3yr): {fc['revenue_cagr_3yr']:.1%}")
            if "gross_margin_avg" in fc:
                lines.append(f"  Gross Margin (avg): {fc['gross_margin_avg']:.1%}")
            if "net_margin_avg" in fc:
                lines.append(f"  Net Margin (avg): {fc['net_margin_avg']:.1%}")
            if "ebitda_margin_avg" in fc:
                lines.append(f"  EBITDA Margin (avg): {fc['ebitda_margin_avg']:.1%}")
            if "roa_avg" in fc:
                lines.append(f"  ROA (avg): {fc['roa_avg']:.1%}")
            if lines:
                fundamental_block = "\nFundamental context (Roic.ai):\n" + "\n".join(lines) + "\n"

        benchmark_block = ""
        if req.benchmark:
            bm = req.benchmark
            benchmark_block = f"""
Buy-and-hold benchmark (what you must beat):
  Sharpe ratio: {bm.get('sharpe', 0):.3f}
  CAGR: {bm.get('cagr', 0):.1%}
  Max drawdown: {bm.get('max_drawdown', 0):.1%}
  Total return: {bm.get('total_return', 0):.1%}
  Period: {bm.get('years', 0):.1f} years

TARGET: Only suggest configurations you believe can achieve Sharpe > {bm.get('sharpe', 0):.2f} (the buy-and-hold Sharpe). Configurations that cannot plausibly beat this should not be included.
"""

        regime_block = ""
        if req.price_regime:
            pr = req.price_regime
            regime_block = f"""
Price regime signals:
  Return autocorrelation (lag-1): {pr.get('autocorr_lag1', 0):.3f}  (positive = momentum tendency, negative = mean-reversion tendency)
  Trend slope (annualized): {pr.get('trend_slope_annualized', 0):.2%}  (positive = uptrend, negative = downtrend)
  Volatility regime: {pr.get('vol_regime', 'normal')}  (recent vol vs historical)
  Recent annualized vol: {pr.get('recent_vol_annualized', 0):.1%}
  Full-period annualized vol: {pr.get('full_period_vol_annualized', 0):.1%}
  Regime hint: {pr.get('regime_hint', 'mixed')}

IMPORTANT: Let the regime hint guide your indicator class selection:
  - If regime_hint = "momentum" → heavily favor trend-following and momentum indicators (MA crossovers, MACD, ADX, ROC). Mean-reversion indicators are unlikely to work here.
  - If regime_hint = "mean-reversion" → heavily favor oscillator-based indicators (RSI, Stochastic, Bollinger Bands, CCI). Trend-following will generate whipsaws.
  - If regime_hint = "mixed" → balance both but lean toward indicators with adaptive behavior.
  - In a high-volatility regime → prefer wider bands/longer lookbacks to reduce noise; avoid tight stop-losses.
  - In a low-volatility regime → shorter lookbacks and tighter entry thresholds can be more responsive.
"""

        user_prompt = f"""Stock: {req.stock_symbol}
Timeframe: {req.timeframe} bars
Period: {req.sample_start} to {req.sample_end} ({req.num_bars} bars)

Basic price statistics:
{json.dumps(req.basic_stats, indent=2)}
{benchmark_block}{regime_block}{fundamental_block}
Objective: {req.objective}

Available indicators:
{catalog_json}

Instructions:
- Select 8-12 indicator configurations. Fewer high-quality picks beat 15 mediocre ones.
- Each pick must be grounded in the regime signals above — your rationale must reference the autocorrelation or trend slope when relevant.
- For each, pick parameters within the specified param_ranges.
- Assign a strategy_template from the indicator's compatible_strategies list.
- Use the fundamental context to bias your choices: high ROIC + strong revenue growth → favour trend/momentum; low margins + cyclical profile → favour mean-reversion and volatility indicators.
- For indicators with fast/slow lengths, ensure fast < slow.
- Do NOT include an indicator class that directly contradicts the regime hint (e.g. do not include pure trend-following in a mean-reversion regime unless you have a strong fundamental reason).

Respond with ONLY this JSON:
{{
  "indicators_to_test": [
    {{
      "indicator_name": "<name>",
      "params": {{}},
      "strategy_template": "<template>",
      "rationale": "<why this configuration can beat the buy-and-hold Sharpe, referencing regime signals>"
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
        analysis_benchmark_block = ""
        if req.benchmark:
            bm = req.benchmark
            analysis_benchmark_block = f"""Buy-and-hold benchmark:
  Sharpe: {bm.get('sharpe', 0):.3f}
  CAGR: {bm.get('cagr', 0):.1%}
  Max drawdown: {bm.get('max_drawdown', 0):.1%}
  Total return: {bm.get('total_return', 0):.1%}

Strategies with beats_benchmark=true already outperform passive investing. Focus modifications on these winners — do NOT try to rescue strategies that badly underperform the benchmark.

"""
        user_prompt = f"""Stock: {req.stock_symbol}
Timeframe: {req.timeframe} bars
Risk-free rate (annual): {req.risk_free_rate_annual:.2%}
{short_data_note}

{analysis_benchmark_block}Backtest results (beats_benchmark=true means Sharpe > buy-and-hold Sharpe of {f"{req.benchmark.get('sharpe', 0):.3f}" if req.benchmark else "?"}):
{summaries_json}

Additional notes: {req.notes or "None"}

Instructions:
1. Rank strategies by ROBUSTNESS (not just Sharpe). Prioritize strategies where beats_benchmark=true. Consider drawdown, num_trades, win_rate.
2. Explain which indicators worked best and WHY — reference the specific market condition or price pattern that the indicator exploits.
3. Suggest AT LEAST 4 specific parameter modifications. Rules for modifications:
   a. ONLY modify strategies that already beat the benchmark or are very close (Sharpe within 0.2 of benchmark). Do not try to salvage badly underperforming strategies.
   b. Each modification must change the strategy's behavior MEANINGFULLY — not trivial ±1 tweaks. The change must have a clear mechanism (e.g. "widening the Bollinger Band from 2.0 to 2.5 std reduces false breakout signals in high-vol regimes").
   c. Provide an expected_sharpe_range as [low_estimate, high_estimate] — be realistic, not optimistic.
   d. Label each modification with a targets field: one of "drawdown", "sharpe", "win_rate", or "frequency".
   e. Include at least 2 modifications targeting Sharpe improvement and at least 1 targeting drawdown reduction.
4. Include warnings about data limitations.

Respond with ONLY this JSON:
{{
  "summary_insights": "<2-3 paragraph analysis>",
  "top_strategies": [
    {{
      "indicator_name": "<name>",
      "strategy_template": "<template>",
      "params": {{}},
      "reason": "<why this is top, referencing beats_benchmark status and specific metrics>"
    }}
  ],
  "suggested_modifications": [
    {{
      "base_indicator_name": "<name>",
      "base_strategy_template": "<template>",
      "new_params": {{}},
      "risk_controls": {{}},
      "expected_effect": "<mechanism: WHY this parameter change improves performance>",
      "expected_sharpe_range": [<low_float>, <high_float>],
      "targets": "<drawdown|sharpe|win_rate|frequency>"
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
