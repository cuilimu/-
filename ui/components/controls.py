"""
ui/components/controls.py — Sidebar control widgets.
Each function renders a Streamlit widget and returns its value.
No business logic here — pure presentation layer.
"""

from datetime import date
from typing import Optional

import streamlit as st

from stock_engine.config import Config


def ticker_selector(config: Config, key: str = "tickers") -> list[str]:
    """
    Multi-select for ticker symbols.
    Defaults to config.default_tickers.
    Returns list of uppercase ticker strings.
    """
    raw = st.multiselect(
        "Tickers",
        options=config.default_tickers + ["GOOGL", "AMZN", "TSLA", "META", "NVDA"],
        default=config.default_tickers,
        key=key,
    )
    return [t.upper() for t in raw]


def date_range_picker(
    config: Config,
    key_start: str = "start_date",
    key_end: str = "end_date",
) -> tuple[str, str]:
    """
    Two date inputs for start / end.
    Returns (start_str, end_str) as ISO-format strings.
    """
    start = st.date_input(
        "Start date",
        value=date.fromisoformat(config.default_start_date),
        key=key_start,
    )
    end = st.date_input(
        "End date",
        value=date.fromisoformat(config.default_end_date),
        key=key_end,
    )
    return str(start), str(end)


def capital_input(config: Config, key: str = "capital") -> float:
    """
    Numeric input for initial capital.
    Returns float. Minimum enforced at $1,000.
    """
    return st.number_input(
        "Initial Capital ($)",
        min_value=1_000.0,
        max_value=100_000_000.0,
        value=config.initial_capital,
        step=1_000.0,
        format="%.0f",
        key=key,
    )
