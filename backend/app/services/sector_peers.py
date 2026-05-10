"""Hardcoded sector → representative large-cap peer tickers (GICS sectors)."""
from __future__ import annotations

SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": ["MSFT", "GOOGL", "META", "NVDA", "AVGO", "ADBE", "CRM", "AMD"],
    "Information Technology": ["MSFT", "GOOGL", "META", "NVDA", "AVGO", "ADBE", "CRM", "AMD"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW"],
    "Consumer Staples": ["PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "CL"],
    "Health Care": ["JNJ", "LLY", "UNH", "ABBV", "MRK", "TMO", "ABT", "DHR"],
    "Healthcare": ["JNJ", "LLY", "UNH", "ABBV", "MRK", "TMO", "ABT", "DHR"],
    "Financials": ["BRK-B", "JPM", "BAC", "WFC", "GS", "MS", "BLK", "AXP"],
    "Energy": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO"],
    "Industrials": ["UNP", "HON", "CAT", "GE", "RTX", "DE", "MMM", "LMT"],
    "Materials": ["LIN", "APD", "SHW", "FCX", "NEM", "NUE", "ALB", "DD"],
    "Real Estate": ["PLD", "AMT", "EQIX", "CCI", "SPG", "PSA", "DLR", "O"],
    "Utilities": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL"],
}

_SECTOR_ALIASES: dict[str, str] = {
    "info tech": "Information Technology",
    "tech": "Technology",
    "software": "Technology",
    "hardware": "Technology",
    "semiconductors": "Technology",
    "comm services": "Communication Services",
    "telecom": "Communication Services",
    "media": "Communication Services",
    "consumer disc": "Consumer Discretionary",
    "retail": "Consumer Discretionary",
    "consumer staples": "Consumer Staples",
    "staples": "Consumer Staples",
    "health care": "Health Care",
    "pharma": "Health Care",
    "biotech": "Health Care",
    "financials": "Financials",
    "banks": "Financials",
    "insurance": "Financials",
    "energy": "Energy",
    "oil": "Energy",
    "industrials": "Industrials",
    "materials": "Materials",
    "real estate": "Real Estate",
    "reits": "Real Estate",
    "utilities": "Utilities",
}


def get_peers_for_sector(sector: str, exclude_ticker: str = "") -> list[str]:
    """Return up to 8 representative peer tickers for the given sector string."""
    normalized = sector.strip()
    peers = SECTOR_PEERS.get(normalized)
    if peers is None:
        # Try case-insensitive match
        lower = normalized.lower()
        for key, tickers in SECTOR_PEERS.items():
            if key.lower() == lower:
                peers = tickers
                break
        if peers is None:
            # Try alias lookup
            canonical = _SECTOR_ALIASES.get(lower)
            if canonical:
                peers = SECTOR_PEERS.get(canonical, [])
    if not peers:
        return []
    exclude = exclude_ticker.upper()
    return [t for t in peers if t.upper() != exclude][:8]
