"""
data/event_provider.py — Corporate event fetcher (earnings, dividends, splits).
Cached per ticker per session in st.session_state.
ETF/non-equity tickers silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

ICONS = {
    "earnings":  "📊",
    "dividend":  "💰",
    "split":     "✂️",
}


@dataclass
class CorporateEvent:
    ticker: str
    date: str                                      # YYYY-MM-DD
    event_type: Literal["earnings", "dividend", "split"]
    label: str
    detail: Optional[str] = None

    def icon(self) -> str:
        return ICONS.get(self.event_type, "•")

    def display(self) -> str:
        return f"{self.label}{' ' + self.detail if self.detail else ''}"


class EventProvider:
    """Stateless — instantiate fresh per fetch call."""

    def fetch_events(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> list[CorporateEvent]:
        """
        Returns CorporateEvents within [start, end] sorted chronologically.
        Silently returns [] on any failure or non-equity ticker.
        """
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)

            # ETF / non-equity filter
            try:
                quote_type = t.fast_info.quote_type or ""
                if quote_type.upper() not in ("EQUITY", ""):
                    return []
            except Exception:
                pass

            start_ts = pd.Timestamp(start)
            end_ts   = pd.Timestamp(end)
            events: list[CorporateEvent] = []

            # ── Earnings ──────────────────────────────────────────────────────
            try:
                ed = t.earnings_dates
                if ed is not None and not ed.empty:
                    idx = pd.to_datetime(ed.index, utc=True).normalize().tz_localize(None)
                    for dt in idx:
                        if start_ts <= dt <= end_ts:
                            events.append(CorporateEvent(
                                ticker=ticker,
                                date=dt.strftime("%Y-%m-%d"),
                                event_type="earnings",
                                label="Earnings Date",
                            ))
            except Exception:
                pass

            # ── Dividends ─────────────────────────────────────────────────────
            try:
                divs = t.dividends
                if divs is not None and not divs.empty:
                    idx = pd.to_datetime(divs.index, utc=True).normalize().tz_localize(None)
                    for dt, amount in zip(idx, divs.values):
                        if start_ts <= dt <= end_ts:
                            events.append(CorporateEvent(
                                ticker=ticker,
                                date=dt.strftime("%Y-%m-%d"),
                                event_type="dividend",
                                label="Ex-Dividend",
                                detail=f"${float(amount):.2f}/share",
                            ))
            except Exception:
                pass

            # ── Splits ────────────────────────────────────────────────────────
            try:
                splits = t.splits
                if splits is not None and not splits.empty:
                    idx = pd.to_datetime(splits.index, utc=True).normalize().tz_localize(None)
                    for dt, ratio in zip(idx, splits.values):
                        if start_ts <= dt <= end_ts:
                            events.append(CorporateEvent(
                                ticker=ticker,
                                date=dt.strftime("%Y-%m-%d"),
                                event_type="split",
                                label="Stock Split",
                                detail=f"{ratio}:1",
                            ))
            except Exception:
                pass

            return sorted(events, key=lambda e: e.date)

        except Exception:
            return []


def get_events_cached(
    ticker: str,
    start: str,
    end: str,
) -> list[CorporateEvent]:
    """
    Session-cached wrapper around EventProvider.fetch_events().
    Cache key: events_{ticker}_{start}_{end}
    """
    try:
        import streamlit as st
        cache_key = f"events_{ticker}_{start}_{end}"
        if cache_key not in st.session_state:
            st.session_state[cache_key] = EventProvider().fetch_events(ticker, start, end)
        return st.session_state[cache_key]
    except Exception:
        return EventProvider().fetch_events(ticker, start, end)
