from typing import Literal
from pydantic import BaseModel


class IndicatorMeta(BaseModel):
    name: str
    human_name: str
    category: Literal["trend", "momentum", "volatility", "volume", "other"]
    required_inputs: list[str]
    default_params: dict
    param_ranges: dict
    description: str


class IndicatorMetaSummary(BaseModel):
    name: str
    human_name: str
    category: str
    default_params: dict
    param_ranges: dict
    description: str
    compatible_strategies: list[str]


INDICATOR_CATALOG: dict[str, IndicatorMeta] = {
    # ── TREND ──────────────────────────────────────────────────────────────
    "sma": IndicatorMeta(
        name="sma",
        human_name="Simple Moving Average Crossover",
        category="trend",
        required_inputs=["close"],
        default_params={"fast_length": 10, "slow_length": 30},
        param_ranges={
            "fast_length": {"min": 5, "max": 50, "step": 1},
            "slow_length": {"min": 20, "max": 200, "step": 5},
        },
        description="Dual SMA crossover. Buy when fast SMA crosses above slow SMA.",
    ),
    "ema": IndicatorMeta(
        name="ema",
        human_name="Exponential Moving Average Crossover",
        category="trend",
        required_inputs=["close"],
        default_params={"fast_length": 10, "slow_length": 30},
        param_ranges={
            "fast_length": {"min": 5, "max": 50, "step": 1},
            "slow_length": {"min": 20, "max": 200, "step": 5},
        },
        description="Dual EMA crossover. More reactive than SMA due to exponential weighting.",
    ),
    "hma": IndicatorMeta(
        name="hma",
        human_name="Hull Moving Average",
        category="trend",
        required_inputs=["close"],
        default_params={"length": 16},
        param_ranges={"length": {"min": 5, "max": 60, "step": 1}},
        description="Reduces lag while preserving smoothness. Used for trend direction.",
    ),
    "macd": IndicatorMeta(
        name="macd",
        human_name="MACD",
        category="trend",
        required_inputs=["close"],
        default_params={"fast": 12, "slow": 26, "signal": 9},
        param_ranges={
            "fast": {"min": 5, "max": 50, "step": 1},
            "slow": {"min": 13, "max": 100, "step": 1},
            "signal": {"min": 3, "max": 20, "step": 1},
        },
        description="Moving Average Convergence Divergence. Trend and momentum indicator.",
    ),
    "adx": IndicatorMeta(
        name="adx",
        human_name="Average Directional Index",
        category="trend",
        required_inputs=["high", "low", "close"],
        default_params={"length": 14, "strength_threshold": 25},
        param_ranges={
            "length": {"min": 5, "max": 50, "step": 1},
            "strength_threshold": {"min": 15, "max": 40, "step": 1},
        },
        description="Measures trend strength. Trade only when ADX > threshold and +DI > -DI.",
    ),
    "aroon": IndicatorMeta(
        name="aroon",
        human_name="Aroon",
        category="trend",
        required_inputs=["high", "low"],
        default_params={"length": 25},
        param_ranges={"length": {"min": 5, "max": 50, "step": 1}},
        description="Identifies trend changes using recent highs/lows. Aroon Up > 70 = uptrend.",
    ),
    # ── MOMENTUM ───────────────────────────────────────────────────────────
    "rsi": IndicatorMeta(
        name="rsi",
        human_name="Relative Strength Index",
        category="momentum",
        required_inputs=["close"],
        default_params={"length": 14, "overbought": 70, "oversold": 30},
        param_ranges={
            "length": {"min": 5, "max": 50, "step": 1},
            "overbought": {"min": 60, "max": 80, "step": 1},
            "oversold": {"min": 20, "max": 40, "step": 1},
        },
        description="Momentum oscillator 0-100. Below oversold = buy, above overbought = sell.",
    ),
    "stoch": IndicatorMeta(
        name="stoch",
        human_name="Stochastic Oscillator",
        category="momentum",
        required_inputs=["high", "low", "close"],
        default_params={"k": 14, "d": 3, "smooth_k": 3, "overbought": 80, "oversold": 20},
        param_ranges={
            "k": {"min": 5, "max": 50, "step": 1},
            "d": {"min": 3, "max": 10, "step": 1},
            "smooth_k": {"min": 1, "max": 10, "step": 1},
            "overbought": {"min": 70, "max": 90, "step": 5},
            "oversold": {"min": 10, "max": 30, "step": 5},
        },
        description="Compares close to its high-low range. Classic mean-reversion oscillator.",
    ),
    "roc": IndicatorMeta(
        name="roc",
        human_name="Rate of Change",
        category="momentum",
        required_inputs=["close"],
        default_params={"length": 12},
        param_ranges={"length": {"min": 2, "max": 30, "step": 1}},
        description="Percentage price change over N periods. Positive = upward momentum.",
    ),
    "cci": IndicatorMeta(
        name="cci",
        human_name="Commodity Channel Index",
        category="momentum",
        required_inputs=["high", "low", "close"],
        default_params={"length": 20, "oversold": -100, "overbought": 100},
        param_ranges={
            "length": {"min": 5, "max": 50, "step": 1},
            "oversold": {"min": -200, "max": -50, "step": 10},
            "overbought": {"min": 50, "max": 200, "step": 10},
        },
        description="Measures deviation from statistical mean. Extremes signal reversals.",
    ),
    "willr": IndicatorMeta(
        name="willr",
        human_name="Williams %R",
        category="momentum",
        required_inputs=["high", "low", "close"],
        default_params={"length": 14, "overbought": -20, "oversold": -80},
        param_ranges={
            "length": {"min": 5, "max": 50, "step": 1},
            "overbought": {"min": -30, "max": -10, "step": 5},
            "oversold": {"min": -90, "max": -60, "step": 5},
        },
        description="Range -100 to 0. Near 0 = overbought, near -100 = oversold.",
    ),
    "ppo": IndicatorMeta(
        name="ppo",
        human_name="Percentage Price Oscillator",
        category="momentum",
        required_inputs=["close"],
        default_params={"fast": 12, "slow": 26, "signal": 9},
        param_ranges={
            "fast": {"min": 5, "max": 50, "step": 1},
            "slow": {"min": 13, "max": 100, "step": 1},
            "signal": {"min": 3, "max": 20, "step": 1},
        },
        description="Percentage version of MACD. Normalizes across different price levels.",
    ),
    # ── VOLATILITY ─────────────────────────────────────────────────────────
    "bbands": IndicatorMeta(
        name="bbands",
        human_name="Bollinger Bands",
        category="volatility",
        required_inputs=["close"],
        default_params={"length": 20, "std": 2.0},
        param_ranges={
            "length": {"min": 5, "max": 50, "step": 1},
            "std": {"min": 1.0, "max": 3.0, "step": 0.5},
        },
        description="Volatility bands around SMA. Price at lower band = oversold, upper = overbought.",
    ),
    "atr": IndicatorMeta(
        name="atr",
        human_name="ATR Trailing Stop",
        category="volatility",
        required_inputs=["high", "low", "close"],
        default_params={"length": 14, "atr_mult": 2.0, "trend_length": 20},
        param_ranges={
            "length": {"min": 5, "max": 50, "step": 1},
            "atr_mult": {"min": 1.0, "max": 4.0, "step": 0.5},
            "trend_length": {"min": 10, "max": 100, "step": 5},
        },
        description="ATR-based trailing stop. Enter on EMA breakout, exit when price falls below trail.",
    ),
    "donchian": IndicatorMeta(
        name="donchian",
        human_name="Donchian Channel Breakout",
        category="volatility",
        required_inputs=["high", "low", "close"],
        default_params={"lower_length": 20, "upper_length": 20},
        param_ranges={
            "lower_length": {"min": 5, "max": 50, "step": 1},
            "upper_length": {"min": 5, "max": 50, "step": 1},
        },
        description="Breakout above N-period high = buy signal. Classic trend-following channel.",
    ),
    # ── VOLUME ─────────────────────────────────────────────────────────────
    "obv": IndicatorMeta(
        name="obv",
        human_name="On-Balance Volume",
        category="volume",
        required_inputs=["close", "volume"],
        default_params={"sma_length": 20},
        param_ranges={"sma_length": {"min": 5, "max": 50, "step": 1}},
        description="Cumulative volume indicator. Buy when OBV crosses above its own SMA.",
    ),
    "mfi": IndicatorMeta(
        name="mfi",
        human_name="Money Flow Index",
        category="volume",
        required_inputs=["high", "low", "close", "volume"],
        default_params={"length": 14, "overbought": 80, "oversold": 20},
        param_ranges={
            "length": {"min": 5, "max": 50, "step": 1},
            "overbought": {"min": 70, "max": 90, "step": 5},
            "oversold": {"min": 10, "max": 30, "step": 5},
        },
        description="Volume-weighted RSI. Combines price and volume for mean-reversion signals.",
    ),
    "cmf": IndicatorMeta(
        name="cmf",
        human_name="Chaikin Money Flow",
        category="volume",
        required_inputs=["high", "low", "close", "volume"],
        default_params={"length": 20},
        param_ranges={"length": {"min": 5, "max": 50, "step": 1}},
        description="Buying/selling pressure indicator. Above 0 = accumulation (buy signal).",
    ),
}

# Strategy templates compatible with each indicator
INDICATOR_STRATEGIES: dict[str, list[str]] = {
    "sma": ["ma_crossover"],
    "ema": ["ma_crossover"],
    "hma": ["ma_crossover"],
    "macd": ["macd_trend"],
    "adx": ["adx_breakout"],
    "aroon": ["ma_crossover"],
    "rsi": ["rsi_mean_reversion", "rsi_trend_follow"],
    "stoch": ["stoch_mean_reversion"],
    "roc": ["rsi_trend_follow"],
    "cci": ["cci_mean_reversion"],
    "willr": ["stoch_mean_reversion"],
    "ppo": ["macd_trend"],
    "bbands": ["bollinger_mean_reversion"],
    "atr": ["atr_trailing_stop"],
    "donchian": ["ma_crossover"],
    "obv": ["obv_momentum"],
    "mfi": ["rsi_mean_reversion"],
    "cmf": ["obv_momentum"],
}


class IndicatorRegistry:
    def __init__(self) -> None:
        self.indicators: dict[str, IndicatorMeta] = INDICATOR_CATALOG

    def list_all(self) -> list[IndicatorMeta]:
        return list(self.indicators.values())

    def get(self, name: str) -> IndicatorMeta | None:
        return self.indicators.get(name)

    def to_summaries(self) -> list[IndicatorMetaSummary]:
        summaries = []
        for meta in self.indicators.values():
            summaries.append(
                IndicatorMetaSummary(
                    name=meta.name,
                    human_name=meta.human_name,
                    category=meta.category,
                    default_params=meta.default_params,
                    param_ranges=meta.param_ranges,
                    description=meta.description,
                    compatible_strategies=INDICATOR_STRATEGIES.get(meta.name, []),
                )
            )
        return summaries
