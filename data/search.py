"""
data/search.py — Ticker search: resolve symbol or company name → candidates.
Uses yfinance Search API. No changes to DataProvider interface.
"""

from dataclasses import dataclass

import yfinance as yf

from stock_engine.exceptions import DataError

PRICE_FIELDS = ["Close", "Open", "High", "Low"]
DEFAULT_PRICE_FIELD = "Close"


@dataclass
class TickerMatch:
    symbol: str
    name: str
    exchange: str
    type_: str

    def label(self) -> str:
        return f"{self.symbol} — {self.name} ({self.exchange})"


def search_tickers(query: str, max_results: int = 5) -> list[TickerMatch]:
    """
    Search by ticker symbol or company name.
    Returns up to max_results TickerMatch objects.
    Raises DataError on API failure.
    """
    if not query or not query.strip():
        return []
    try:
        results = yf.Search(query, max_results=max_results)
        quotes = results.quotes
        if not quotes:
            return []
        matches = []
        for q in quotes[:max_results]:
            symbol = q.get("symbol", "")
            if not symbol:
                continue
            matches.append(TickerMatch(
                symbol=symbol,
                name=q.get("longname") or q.get("shortname") or symbol,
                exchange=q.get("exchange", ""),
                type_=q.get("quoteType", ""),
            ))
        return matches
    except Exception as exc:
        raise DataError(f"Ticker search failed for '{query}': {exc}") from exc
