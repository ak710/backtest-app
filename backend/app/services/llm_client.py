from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.models.indicators import INDICATOR_STRATEGIES
from app.models.llm_schemas import (
    ComboIndicatorConfig,
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
            "max_tokens": 16384,
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

INDICATOR REGIME-FIT REFERENCE — match your picks to the regime above:

TRENDING / MOMENTUM regime (autocorr > 0.1 OR strong positive trend slope):
  ma_crossover strategy:      sma, ema, hma, aroon, donchian, psar, vortex, kama
  macd_trend strategy:        macd, ppo, trix, kst, tsi
  adx_breakout strategy:      adx  (confirms trend strength before entry)
  atr_trailing_stop strategy: atr  (adaptive trend exit)
  zero_cross strategy:        roc, roc2  (roc = momentum filter when positive; roc2 = acceleration signal)
  rsi_trend_follow strategy:  rsi  (RSI above 50 + price above MA)
  obv_momentum strategy:      obv, cmf, fi, eom, vpt, ao  (volume-confirmed trend)
  AVOID: bollinger_mean_reversion, stoch_mean_reversion, cci_mean_reversion, rsi_mean_reversion

MEAN-REVERSION / SIDEWAYS regime (autocorr < -0.1 OR flat/negative trend slope):
  rsi_mean_reversion strategy:    rsi, mfi, uo  (oscillator extremes)
  stoch_mean_reversion strategy:  stoch, willr, stochrsi
  cci_mean_reversion strategy:    cci, dpo
  bollinger_mean_reversion:       bbands, kc
  AVOID: ma_crossover, macd_trend, adx_breakout, atr_trailing_stop, zero_cross (all whipsaw)

MIXED / UNCERTAIN regime (autocorr near zero):
  Prefer adaptive/multi-timeframe: kama (ma_crossover), uo (rsi_mean_reversion), tsi (macd_trend)
  Acceptable both ways: rsi (either template), bbands, adx (as entry filter only)

ROC / ROC2 NOTES:
  roc (zero_cross): ideal momentum regime filter — buy when price % change crosses above zero.
    Unreliable standalone in mean-reversion regime; best used as a combo component.
  roc2 (zero_cross): momentum *acceleration* — buy when rate-of-change itself turns positive.
    Useful even in mixed regimes as a combo confirmation (pair with a slower trend indicator).

VOLATILITY ADJUSTMENTS:
  High vol → wider bands (bbands std ≥ 2.5), longer ATR multiplier (≥ 2.5), longer lookbacks
  Low vol  → tighter thresholds, shorter lookbacks
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
- Select 8-12 single-indicator configurations. Fewer high-quality picks beat 15 mediocre ones.
- Each pick MUST be from the correct regime category above. Do NOT select indicators from the AVOID list for the current regime.
- Each pick must be grounded in the regime signals — your rationale must reference autocorrelation and/or trend slope.
- Rate each pick with confidence 1–5. Only include picks with confidence ≥ 3. Confidence reflects: fit to regime, likelihood of beating the benchmark, expected trade frequency.
- Trade frequency: each configuration must be expected to generate at least 8 trades over {req.num_bars} bars. Shorter lookbacks generate more signals; longer lookbacks generate fewer. Avoid configs likely to produce < 8 trades.
- {"Overfitting guard: with only " + str(req.num_bars) + " bars, avoid indicators with more than 2 tunable parameters." if req.num_bars < 80 else ""}
- For each, pick parameters within the specified param_ranges.
- Assign a strategy_template from the indicator's compatible_strategies list.
- Use fundamental context to bias: high ROIC + strong revenue growth → favour trend/momentum; low margins + cyclical → favour mean-reversion and volatility.
- For indicators with fast/slow lengths, ensure fast < slow.
- Also suggest 2–3 combined strategies in combo_configs_to_test. Each combo must:
  • Pair indicators from DIFFERENT categories (e.g., a momentum oscillator + a trend filter)
  • Each component must individually fit the regime
  • AND logic = higher conviction, fewer trades; MAJORITY logic = more trades, less filtering
  • Include a rationale explaining why the pairing reduces false signals compared to either indicator alone
  • roc2 is excellent as a combo confirmation component (momentum acceleration) even in mixed regimes

Respond with ONLY this JSON:
{{
  "indicators_to_test": [
    {{
      "indicator_name": "<name>",
      "params": {{}},
      "strategy_template": "<template>",
      "rationale": "<why this beats buy-and-hold Sharpe, referencing regime signals>",
      "confidence": <1-5>
    }}
  ],
  "combo_configs_to_test": [
    {{
      "indicators": [
        {{"indicator_name": "<name>", "params": {{}}, "strategy_template": "<template>", "rationale": ""}},
        {{"indicator_name": "<name>", "params": {{}}, "strategy_template": "<template>", "rationale": ""}}
      ],
      "combo_logic": "<AND|MAJORITY>",
      "rationale": "<why this pairing reduces false signals>"
    }}
  ]
}}"""

        raw = self._chat(SELECTION_SYSTEM_PROMPT, user_prompt)
        logger.debug("LLM selection response: %s", raw[:1000])
        parsed = safe_parse_json(raw)
        if not parsed:
            raise ValueError("LLM returned unparseable JSON for indicator selection.")

        from app.models.indicators import INDICATOR_CATALOG, INDICATOR_STRATEGIES

        def _validate_single_config(item: dict) -> SelectedIndicatorConfig | None:
            """Validate, fix, and clip a single indicator config dict. Returns None if invalid."""
            try:
                cfg = SelectedIndicatorConfig(**item)
            except (ValidationError, TypeError) as exc:
                logger.warning("Invalid indicator config from LLM: %s – %s", item, exc)
                return None
            if cfg.indicator_name not in INDICATOR_CATALOG:
                logger.warning("LLM picked unknown indicator: %s", cfg.indicator_name)
                return None
            allowed = INDICATOR_STRATEGIES.get(cfg.indicator_name, [])
            if cfg.strategy_template not in allowed:
                if allowed:
                    cfg.strategy_template = allowed[0]
                else:
                    return None
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
            return cfg

        # Parse and filter single-indicator configs
        raw_list = parsed.get("indicators_to_test", [])
        valid_configs: list[SelectedIndicatorConfig] = []
        for item in raw_list:
            cfg = _validate_single_config(item)
            if cfg is None:
                continue
            if cfg.confidence < 3:
                logger.info("Dropping low-confidence config: %s (confidence=%d)", cfg.indicator_name, cfg.confidence)
                continue
            valid_configs.append(cfg)

        if not valid_configs:
            raise ValueError("LLM returned no valid indicator configurations.")

        # Parse and validate combo configs
        raw_combos = parsed.get("combo_configs_to_test", [])
        valid_combos: list[ComboIndicatorConfig] = []
        for combo_item in raw_combos:
            try:
                raw_components = combo_item.get("indicators", [])
                validated_components = []
                for comp in raw_components:
                    comp_cfg = _validate_single_config(comp)
                    if comp_cfg is not None:
                        validated_components.append(comp_cfg)
                if len(validated_components) < 2:
                    logger.warning("Combo has fewer than 2 valid components — skipping")
                    continue
                combo = ComboIndicatorConfig(
                    indicators=validated_components,
                    combo_logic=combo_item.get("combo_logic", "AND"),
                    rationale=combo_item.get("rationale", ""),
                )
                valid_combos.append(combo)
            except (ValidationError, TypeError) as exc:
                logger.warning("Invalid combo config from LLM: %s – %s", combo_item, exc)

        logger.info("Parsed %d single configs, %d combo configs", len(valid_configs), len(valid_combos))
        return IndicatorSelectionResponse(indicators_to_test=valid_configs, combo_configs_to_test=valid_combos)

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
2. Explain which indicators worked best and WHY — reference the specific market condition or price pattern the indicator exploits.
3. Suggest AT LEAST 4 parameter modifications. Rules:
   a. ONLY modify strategies that beat the benchmark or are within 0.2 Sharpe of it. Do not try to salvage badly underperforming strategies.
   b. Each modification must be MEANINGFUL — not trivial ±1 tweaks. State the mechanism (e.g. "widening BB from 2.0 to 2.5 std filters false breakouts in high-vol regimes").
   c. Provide expected_sharpe_range as [low_estimate, high_estimate] — be realistic.
   d. Label each with targets: "drawdown", "sharpe", "win_rate", or "frequency".
   e. At least 2 modifications targeting sharpe, at least 1 targeting drawdown.
   f. COMBINED strategies (indicator_name containing '+') CAN and SHOULD be modified. To modify a combo:
      - Set new_combo_components to the full updated component list (change params, swap indicators, or both)
      - Optionally set new_combo_logic to change AND ↔ MAJORITY
      - Set new_params to {{}} when using new_combo_components
      - Good examples: tighten RSI oversold in RSI+MACD; change AND→MAJORITY to get more trades; swap slow MA for EMA
4. Include warnings about data limitations.

Respond with ONLY this JSON:
{{
  "summary_insights": "<2-3 paragraph analysis>",
  "top_strategies": [
    {{
      "indicator_name": "<name>",
      "strategy_template": "<template>",
      "params": {{}},
      "reason": "<why this is top, referencing beats_benchmark and specific metrics>"
    }}
  ],
  "suggested_modifications": [
    {{
      "base_indicator_name": "<name or 'rsi+macd' for combo>",
      "base_strategy_template": "<template>",
      "new_params": {{}},
      "risk_controls": {{}},
      "expected_effect": "<mechanism: WHY this change improves performance>",
      "expected_sharpe_range": [<low_float>, <high_float>],
      "targets": "<drawdown|sharpe|win_rate|frequency>",
      "new_combo_components": null,
      "new_combo_logic": null
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
