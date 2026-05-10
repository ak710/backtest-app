"""Fetch fundamental context and price data for a stock from the Roic.ai API."""
from __future__ import annotations

import httpx
import pandas as pd

from app.utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.roic.ai/v2"


def _get(client: httpx.Client, path: str, api_key: str, params: dict | None = None) -> dict | list | None:
    url = f"{BASE_URL}/{path}"
    p = {"apikey": api_key, **(params or {})}
    try:
        resp = client.get(url, params=p, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Roic.ai request failed (%s): %s", path, exc)
        return None


def _avg(records: list[dict], field: str) -> float | None:
    vals = [r[field] for r in records if isinstance(r.get(field), (int, float))]
    return round(sum(vals) / len(vals), 4) if vals else None


def _revenue_growth(records: list[dict]) -> float | None:
    """CAGR of revenue over available annual records (oldest → newest)."""
    rev_field = "is_sales_revenue_turnover"
    vals = [r[rev_field] for r in reversed(records) if isinstance(r.get(rev_field), (int, float)) and r[rev_field] > 0]
    if len(vals) < 2:
        return None
    years = len(vals) - 1
    return round((vals[-1] / vals[0]) ** (1 / years) - 1, 4)


def fetch_historical_prices(ticker: str, api_key: str, years: int = 5) -> pd.DataFrame | None:
    """
    Fetch daily OHLCV history from roic.ai going back `years` years.
    Returns a DataFrame sorted ascending by date with columns:
    time, open, high, low, close, volume.
    Returns None if the request fails or returns no data.
    """
    if not api_key:
        return None
    from datetime import date, timedelta
    date_start = (date.today() - timedelta(days=years * 365)).isoformat()
    # ~252 trading days/year; set limit generously above that
    limit = years * 300
    with httpx.Client() as client:
        data = _get(client, f"stock-prices/{ticker.upper()}", api_key, {
            "date_start": date_start,
            "order": "ASC",
            "limit": limit,
        })
    if not data or not isinstance(data, list):
        logger.warning("No historical price data returned for %s", ticker)
        return None
    try:
        df = pd.DataFrame(data)
        df = df.rename(columns={"date": "time"})
        df["time"] = pd.to_datetime(df["time"])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[["time", "open", "high", "low", "close", "volume"]].dropna()
        df = df.sort_values("time").reset_index(drop=True)
        logger.info("Fetched %d daily bars for %s", len(df), ticker)
        return df
    except Exception as exc:
        logger.warning("Failed to parse historical prices for %s: %s", ticker, exc)
        return None


def fetch_latest_price(ticker: str, api_key: str) -> dict | None:
    """
    Fetch the most recent trading day's price for a ticker.
    Returns a dict with keys: close, open, high, low, volume, change_percent, date.
    """
    if not api_key:
        return None
    with httpx.Client() as client:
        data = _get(client, f"stock-prices/{ticker.upper()}", api_key, {"limit": 1, "order": "DESC"})
    if not data:
        return None
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return None
    return {
        "date": data.get("date", ""),
        "close": data.get("close"),
        "open": data.get("open"),
        "high": data.get("high"),
        "low": data.get("low"),
        "volume": data.get("volume"),
        "change_percent": data.get("change_percent"),
        "vwap": data.get("vwap"),
    }


def fetch_fundamental_context(ticker: str, api_key: str) -> dict | None:
    """
    Returns a dict of fundamental metrics for the given ticker, or None if
    the API key is missing or all requests fail.
    """
    if not api_key:
        return None

    with httpx.Client() as client:
        fin_params = {"period": "annual", "limit": 4}
        profile_data = _get(client, f"company/profile/{ticker}", api_key)
        profitability = _get(client, f"fundamental/ratios/profitability/{ticker}", api_key, fin_params)
        income = _get(client, f"fundamental/income-statement/{ticker}", api_key, fin_params)
        search_data = _get(client, "tickers/search", api_key, {"query": ticker})

    if not any([profile_data, profitability, income]):
        logger.warning("All Roic.ai requests failed for %s", ticker)
        return None

    context: dict = {"ticker": ticker}

    # Company name from ticker search
    if isinstance(search_data, list):
        match = next((t for t in search_data if t.get("symbol") == ticker.upper()), None)
        if match:
            context["company_name"] = match.get("name", "")

    # Company profile
    if profile_data and isinstance(profile_data, dict):
        context["sector"] = profile_data.get("sector", "Unknown")
        context["industry"] = profile_data.get("industry", "Unknown")
        mktcap = profile_data.get("market_cap")
        if isinstance(mktcap, (int, float)) and mktcap > 0:
            context["market_cap_bn"] = round(mktcap / 1e9, 1)

    # Profitability ratios (last 3 annual periods)
    # Roic.ai returns these as whole-number percentages (e.g. 18.68 = 18.68%),
    # so divide by 100 to normalise to decimal form for consistent frontend display.
    if isinstance(profitability, list) and profitability:
        records = profitability[:3]
        for field, label in [
            ("return_on_inv_capital", "roic_avg"),
            ("gross_margin", "gross_margin_avg"),
            ("profit_margin", "net_margin_avg"),
            ("ebitda_margin", "ebitda_margin_avg"),
            ("return_on_asset", "roa_avg"),
        ]:
            val = _avg(records, field)
            if val is not None:
                context[label] = round(val / 100, 4)

    # Income statement — revenue growth
    if isinstance(income, list) and income:
        growth = _revenue_growth(income[:4])
        if growth is not None:
            context["revenue_cagr_3yr"] = growth

    logger.info("Roic.ai fundamental context for %s: %s", ticker, context)
    return context
