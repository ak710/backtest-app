# LLM Backtesting Bot

A single-stock, LLM-assisted backtesting webapp. Upload weekly or monthly OHLCV data and an LLM will select technical indicator configurations, run backtests, and propose improvements.

## Quick Start

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173 (proxies /api to :8000)
```

## CSV Format

Required columns (case-insensitive): `time`, `open`, `high`, `low`, `close`, `volume`

- `time`: date string (e.g. `2024-01-31`)
- Only **weekly** or **monthly** bars are accepted (no daily/intraday)

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required)* | OpenRouter API key |
| `OPENROUTER_MODEL` | `anthropic/claude-3.5-sonnet` | Model to use |
| `APP_ENV` | `dev` | `dev` or `prod` |

## Architecture

```
backend/
  app/
    main.py                 # FastAPI entry
    config.py               # Settings (env vars)
    models/
      data_models.py        # Pydantic models for OHLCV, backtest results
      llm_schemas.py        # Pydantic models for LLM I/O
      indicators.py         # Indicator metadata + registry (18 indicators)
    services/
      data_loader.py        # CSV parsing, resampling, validation
      indicators_engine.py  # pandas-ta indicator computation
      strategies.py         # 10 strategy templates
      backtester.py         # Bar-by-bar simulation engine
      metrics.py            # Sharpe, CAGR, drawdown, win rate
      llm_client.py         # OpenRouter client (LLM #1 + #2)
      pipeline.py           # Full orchestration
      reporting.py          # Plotly chart generation
    routes/
      analysis.py           # POST /api/analyze, GET /api/health
    utils/
      logging.py
      json_utils.py         # Safe JSON parsing / repair

frontend/
  src/
    pages/
      UploadPage.tsx        # CSV upload form
      ResultsPage.tsx       # Results dashboard
    components/
      StrategyTable.tsx     # Metrics table
      LLMInsights.tsx       # LLM commentary cards
      PlotlyChart.tsx       # Interactive Plotly wrapper
```

## Indicators Supported

**Trend:** SMA, EMA, HMA, MACD, ADX, Aroon  
**Momentum:** RSI, Stochastic, ROC, CCI, Williams %R, PPO  
**Volatility:** Bollinger Bands, ATR Trailing Stop, Donchian Channel  
**Volume:** OBV, MFI, CMF

## Strategy Templates

- `rsi_mean_reversion` — Buy when RSI crosses below oversold, sell when overbought
- `rsi_trend_follow` — Buy when RSI > 50 and price above slow EMA
- `bollinger_mean_reversion` — Buy at lower band, exit at middle band
- `ma_crossover` — Fast MA crosses above slow MA
- `macd_trend` — MACD line crosses above signal line
- `atr_trailing_stop` — EMA breakout entry with ATR trailing stop
- `stoch_mean_reversion` — Stochastic %K oversold/overbought
- `cci_mean_reversion` — CCI extreme reversals
- `adx_breakout` — Strong trend (ADX > threshold) with directional bias
- `obv_momentum` — OBV crosses above its SMA
