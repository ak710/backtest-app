# LLM-Assisted Indicator Backtesting Webapp – Technical Specification

## 1. Goals and constraints

The application is a single-stock, LLM-assisted backtesting webapp that:

- Accepts weekly or monthly OHLCV data (no daily or intraday) for a single stock at a time.
- Uses a large catalog of technical indicators (not artificially limited) via a Python library such as `pandas-ta` and/or `TA-Lib`.
- Calls an LLM (via OpenRouter API) twice:
  - First: to select 10–15 promising indicator configurations from the full indicator list.
  - Second: to analyze backtest results, highlight which indicators worked best historically, and propose modifications to improve Sharpe ratio and reduce volatility.
- Runs backtests on each selected indicator (using fixed strategy templates per indicator family).
- Computes performance metrics including Sharpe ratio annualized from weekly/monthly returns.
- Produces a human-readable report with:
  - Charts (price + indicator + trades, equity curves),
  - Tables of metrics,
  - LLM-generated insights.
- Is implemented in Python with a small web frontend, easy to host on generic PaaS.

At any point, the app processes one stock and one uploaded dataset.

---

## 2. High-level architecture

### Components

1. **Frontend (SPA or simple web UI)**
   - Built with React + Vite (or similar) consuming a JSON API.
   - Provides:
     - File upload for CSV data,
     - Input for analysis options (weekly vs monthly, risk-free rate, etc.),
     - Progress/status,
     - Results view with charts, metrics tables, and LLM commentary.

2. **Backend API (Python / FastAPI)**
   - Endpoints to:
     - Upload and validate data,
     - Trigger full analysis pipeline (data prep → LLM #1 → backtests → LLM #2),
     - Retrieve results (if needed separately).
   - Encapsulates:
     - Indicator catalog and computation,
     - Backtest engine,
     - Metrics calculation (including Sharpe),
     - OpenRouter LLM client,
     - Report generator.

3. **LLM Layer (OpenRouter client)**
   - Generic client to call OpenRouter with:
     - System prompts and structured user messages,
     - Strong JSON schema for responses,
     - Robust parsing / retry on invalid JSON.

4. **Report & Visualization**
   - Uses Plotly or Matplotlib to generate:
     - Price + indicator + trade plots,
     - Equity curve plots.
   - Returns:
     - Either pre-rendered images (base64 or URLs) or configuration for frontend charts.

5. **Storage (optional)**
   - For a minimal version, everything can be in memory per request.
   - For multi-run persistence, use SQLite or PostgreSQL, but this is not strictly required.

---

## 3. Tech stack

### Backend

- Language: Python 3.11+
- Web framework: FastAPI (for async, auto-generated docs, and easy JSON handling).
- Data: pandas, numpy.
- Technical indicators:
  - `pandas-ta` (comprehensive indicator set, 150+ indicators).
  - Optionally `TA-Lib` (150+ indicators; can be used via Python wrapper).
- Charts: Plotly for interactive charts; optionally export static PNGs.
- HTTP client for LLM: `httpx` or `requests`.
- Config: `pydantic` models for configuration, API payloads.

### Frontend

- React + Vite SPA.
- Styling via Chakra UI or Tailwind (developer preference).
- Uses fetch/axios to call FastAPI.

### Deployment

- Package as:
  - Single container image (FastAPI + static React build served via ASGI/WSGI or nginx), or
  - Separate frontend and backend services.
- Environment variable configuration:
  - `OPENROUTER_API_KEY`,
  - `OPENROUTER_MODEL` (e.g., `anthropic/claude-3.5-sonnet`),
  - `APP_ENV` (dev/prod).

---

## 4. Directory structure

Suggested backend structure:

```text
backend/
  app/
    main.py                 # FastAPI app entry
    config.py               # settings (env, OpenRouter keys, etc.)
    models/
      data_models.py        # Pydantic models for API payloads
      llm_schemas.py        # Pydantic models for LLM I/O
      indicators.py         # Indicator metadata definitions
    services/
      data_loader.py        # CSV parsing, resampling, validation
      indicators_engine.py  # Indicator catalog + computation
      strategies.py         # Strategy templates using indicators
      backtester.py         # Simulation engine
      metrics.py            # Performance metrics including Sharpe
      llm_client.py         # OpenRouter client + prompts
      pipeline.py           # Orchestration of full analysis
      reporting.py          # Plot generation + report assembly
    routes/
      analysis.py           # REST endpoints for analysis
    utils/
      logging.py            # Logging setup
      json_utils.py         # JSON validation, safe parsing
  tests/
    ...
frontend/
  ...
```

---

## 5. Data model and ingestion

### Input CSV format

Expected columns:

- `time` (date or datetime, monthly or weekly resolution),
- `open`, `high`, `low`, `close`,
- `volume`,
- Optional: `roc`, `acceleration` (second derivative), `plot` (custom).

Constraints:

- Data must be weekly or monthly bars (no daily/intraday).
- Time series strictly increasing, no duplicates.

### Backend data ingestion steps

1. Parse CSV into pandas DataFrame (`data_loader.py`):
   - Infer or validate frequency (weekly vs monthly).
   - Ensure required columns present (case-insensitive mapping).
   - Drop or interpolate small gaps as needed.

2. Resampling (if necessary):
   - If user indicates "monthly" but data is weekly, aggregate (OHLC resample).
   - Keep returns at the final chosen frequency (weekly OR monthly, not mixed).

3. Compute basic derived features (if not provided):
   - Simple returns: `r_t = close_t / close_{t-1} - 1`.
   - Log returns for Sharpe computations.
   - ROC if needed (but user may already provide).

Expose as:

```python
def load_and_prepare_timeseries(
    file: BinaryIO,
    target_frequency: Literal["weekly", "monthly"]
) -> PreparedData:
    ...
```

`PreparedData` includes cleaned OHLCV DataFrame, returns series, and basic stats.

---

## 6. Indicator catalog and management

The indicator catalog should expose all indicators provided by `pandas-ta` (and optionally TA-Lib), but in a controlled way the LLM can reason about.

### Indicator catalog design

1. Introspect library:
   - Use `pandas_ta` / `TA-Lib` to discover available indicators.

2. Metadata schema per indicator:

```python
class IndicatorMeta(BaseModel):
    name: str
    human_name: str
    category: Literal["trend", "momentum", "volatility", "volume", "other"]
    required_inputs: list[str]
    default_params: dict
    param_ranges: dict
    description: str
```

3. Categories:

- Trend: Moving Averages, MACD, ADX, etc.
- Momentum: RSI, Stochastic, ROC, etc.
- Volatility: Bollinger Bands, ATR, etc.
- Volume: OBV, MFI, Chaikin Money Flow, etc.
- Other: specialized indicators.

4. Registry:

```python
class IndicatorRegistry:
    def __init__(self):
        self.indicators: dict[str, IndicatorMeta] = self._load_indicators()

    def _load_indicators(self) -> dict[str, IndicatorMeta]:
        ...

    def list_all(self) -> list[IndicatorMeta]:
        return list(self.indicators.values())
```

5. Computation interface (`indicators_engine.py`):

```python
def compute_indicator(
    df: pd.DataFrame,
    meta: IndicatorMeta,
    params: dict
) -> pd.Series | pd.DataFrame:
    ...
```

The LLM never provides formulas; it only selects indicators and sets parameters within ranges.

---

## 7. LLM call #1 – selecting indicators and configs

### Request model

```python
class LLMIndicatorSelectionRequest(BaseModel):
    stock_symbol: str
    timeframe: Literal["weekly", "monthly"]
    sample_start: date
    sample_end: date
    basic_stats: dict
    indicator_catalog: list[IndicatorMetaSummary]
    objective: str
```

`IndicatorMetaSummary` is a lighter version of `IndicatorMeta`.

### Prompt content

- System prompt: quantitative trading research assistant focusing on robust, low-drawdown strategies.
- User content:
  - Summary of stock stats.
  - Clarification of data frequency (weekly or monthly only).
  - JSON description of indicators and parameter ranges.
  - Objective: choose 10–15 indicator configurations for backtesting.

### Expected LLM response

```json
{
  "indicators_to_test": [
    {
      "indicator_name": "rsi",
      "params": {"length": 14, "overbought": 70, "oversold": 30},
      "strategy_template": "rsi_mean_reversion",
      "rationale": "..."
    }
  ]
}
```

Backend steps:

- Validate JSON against Pydantic.
- Ensure each `indicator_name` exists in registry.
- Clip/reject params outside ranges.
- Map `strategy_template` to a strategy function.

---

## 8. Strategy templates and backtest engine

### Strategy templates

Implement reusable strategy templates keyed by indicator type, e.g.:

- `rsi_mean_reversion`: long when RSI < oversold, exit when RSI crosses above neutral.
- `rsi_trend_follow`: long when RSI > X and price above moving average.
- `bollinger_mean_reversion`: long at lower band touches, exit at middle band.
- `ma_crossover`: long when fast MA crosses above slow MA; exit when reverse.
- `macd_trend`: long when MACD line crosses above signal line and is above zero.
- `atr_trailing_stop`: trend-follow with ATR-based trailing stop.

Signature:

```python
def run_strategy(
    data: PreparedData,
    indicator_series: pd.DataFrame | pd.Series,
    params: dict,
    risk_settings: RiskSettings
) -> BacktestResult:
    ...
```

`RiskSettings` includes size, slippage, commission, and max position size.

### Backtest engine structure

`backtester.py`:

1. Iterate over bars in chronological order.
2. For each bar:
   - Compute signals from strategy template.
   - Decide orders (enter/exit/hold) and update position and cash.
   - Record P&L and equity.
3. Output `BacktestResult`:

```python
class BacktestResult(BaseModel):
    indicator_name: str
    strategy_template: str
    params: dict
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    period_returns: list[float]
    metrics: dict
```

---

## 9. Metrics and Sharpe ratio

`metrics.py` computes for each `BacktestResult`:

- Total return and CAGR.
- Volatility (standard deviation of period returns).
- Max drawdown and duration.
- Number of trades, win rate, average trade P&L, profit factor.
- Sharpe ratio, annualized from weekly or monthly returns.

Example implementation:

```python
def compute_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate_annual: float,
    frequency: Literal["weekly", "monthly"]
) -> float:
    if returns.std() == 0:
        return 0.0

    periods_per_year = 52 if frequency == "weekly" else 12
    rf_per_period = (1 + risk_free_rate_annual) ** (1 / periods_per_year) - 1
    excess = returns - rf_per_period
    mean_excess = excess.mean()
    std_excess = excess.std()

    sharpe_period = mean_excess / std_excess
    return sharpe_period * (periods_per_year ** 0.5)
```

---

## 10. LLM call #2 – analyzing results and proposing improvements

### Data sent to LLM

```python
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
```

```python
class LLMAnalysisRequest(BaseModel):
    stock_symbol: str
    timeframe: Literal["weekly", "monthly"]
    risk_free_rate_annual: float
    strategies: list[StrategySummary]
    notes: str
```

### Prompt content

- System: quantitative portfolio analyst optimizing for robust, low-volatility strategies with good Sharpe.
- User:
  - Clarifies frequency and sample length.
  - Provides strategy summaries.
  - Requests:
    - Ranking by robustness, not just Sharpe.
    - Explanation of which indicators worked best and why.
    - Explicit parameter and risk-control modifications.
    - Caveats about limited data.

### Expected LLM output

```json
{
  "summary_insights": "...",
  "top_strategies": [
    {
      "indicator_name": "rsi",
      "strategy_template": "rsi_mean_reversion",
      "params": {"length": 21, "overbought": 65, "oversold": 35},
      "reason": "..."
    }
  ],
  "suggested_modifications": [
    {
      "base_indicator_name": "rsi",
      "base_strategy_template": "rsi_mean_reversion",
      "new_params": {"length": 21, "overbought": 65, "oversold": 35},
      "risk_controls": {"stop_loss_atr": 2.0, "take_profit_atr": 4.0},
      "expected_effect": "..."
    }
  ],
  "warnings": [
    "Sample includes only X trades – Sharpe may be unreliable."
  ]
}
```

Backend can optionally backtest suggested modifications and include them in the final report.

---

## 11. Orchestration pipeline

`pipeline.py`:

```python
def run_full_analysis(
    data_file: BinaryIO,
    stock_symbol: str,
    timeframe: Literal["weekly", "monthly"],
    risk_free_rate_annual: float,
) -> FullAnalysisResult:
    prepared = load_and_prepare_timeseries(data_file, timeframe)

    registry = IndicatorRegistry()
    catalog = registry.list_all()

    selection_request = LLMIndicatorSelectionRequest(...)
    indicator_configs = llm_client.select_indicators(selection_request)

    results = []
    for config in indicator_configs:
        meta = registry.indicators[config.indicator_name]
        series = compute_indicator(prepared.df, meta, config.params)
        strategy_result = run_strategy(
            prepared, series, config.params, default_risk_settings
        )
        metrics = compute_metrics(strategy_result, timeframe, risk_free_rate_annual)
        strategy_result.metrics = metrics
        results.append(strategy_result)

    summaries = [to_strategy_summary(r) for r in results]
    analysis_request = LLMAnalysisRequest(...)
    llm_analysis = llm_client.analyze_results(analysis_request)

    modified_results = run_modification_backtests(
        prepared, registry, llm_analysis.suggested_modifications
    )

    report = generate_report(
        prepared,
        results,
        modified_results,
        llm_analysis,
    )

    return FullAnalysisResult(
        base_results=results,
        modified_results=modified_results,
        llm_analysis=llm_analysis,
        report=report,
    )
```

`FullAnalysisResult` is JSON-serializable.

---

## 12. API design (FastAPI)

### `POST /api/analyze`

- Multipart form:
  - `file`: CSV file,
  - JSON fields: `stock_symbol`, `timeframe` ("weekly"/"monthly"), `risk_free_rate_annual` (float).

- Behavior: runs `run_full_analysis`.

- Response JSON:

```json
{
  "stock_symbol": "AAPL",
  "timeframe": "monthly",
  "base_strategies": [...],
  "modified_strategies": [...],
  "llm_summary": "...",
  "llm_detailed_insights": "...",
  "charts": [
    {
      "id": "equity_curve_rsi",
      "type": "equity_curve",
      "title": "Equity Curve – RSI Strategy",
      "image_base64": "..."
    }
  ]
}
```

### `GET /api/health`

- Simple health check endpoint.

---

## 13. Frontend behavior

### Upload page

- Form:
  - File input for CSV,
  - Text input for stock symbol,
  - Select for timeframe (weekly/monthly),
  - Input for risk-free rate (default, e.g., 0.03).
- On submit:
  - POST to `/api/analyze`.
  - Show loading state.

### Results page

- Display:
  - Summary text (stock, timeframe, key metrics).
  - Table of strategies (indicator, params, Sharpe, drawdown, etc.).
  - LLM commentary (summary insights, recommended strategies, suggested modifications).
  - Charts (price + indicator + trades, equity curves).

Charts can be static PNGs from backend or interactive Plotly.

---

## 14. OpenRouter client implementation

`llm_client.py`:

```python
class LLMClient:
    def __init__(self, api_key: str, model: str):
        ...

    def select_indicators(self, req: LLMIndicatorSelectionRequest) -> IndicatorSelectionResponse:
        ...

    def analyze_results(self, req: LLMAnalysisRequest) -> LLMAnalysisResponse:
        ...
```

Implementation details:

- Use `/chat/completions` endpoint with given model.
- Messages include system and user prompts.
- Instruct model to respond with valid JSON only.
- On invalid JSON:
  - Try a repair pass.
  - If still invalid, return error to frontend.

---

## 15. Volatility reduction and Sharpe improvement levers

Document the levers the LLM is allowed to modify:

- Indicator smoothing: longer lookback periods, adjusted thresholds.
- Risk controls: ATR-based stops and targets, position sizing scaled to volatility.
- Trade filters: volume filters, trend filters based on slow moving averages.

Backtester must express these via parameters so suggested modifications map directly onto code.

---

## 16. Edge cases and validation

- If the dataset is very short (e.g., < 3 years of monthly data), warn the user and include this in LLM prompts so the model caveats its conclusions.
- If returns variance is zero or near zero, set Sharpe to 0 and mark this in metrics.
- If an indicator cannot be computed due to insufficient history, skip it and log why.