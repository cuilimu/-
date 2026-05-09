"""
ui/components/simple_mode/page_taa.py — Step 3: TAA (Tactical Asset Allocation).

Bridges the main-app ResearchSession to the sandbox render_taa_page().

Data flow:
  sess.universe  →  build_mini_universe()   (BucketAssignment per ticker)
  YFinance       →  _YFReturnsProvider      (2-year daily returns, windowed)
  render_taa_page() → TAAResult             (cached in st.session_state["_taa_cache"])

The cached TAAResult is consumed by _ew_target_weights() in page2_allocation.py
(Step 4).  Passthrough → flat 1/N.  Factor MVO → 1/k bucket equal-weight ×
intra-bucket MVO weights.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st
import yfinance as yf

from stock_engine.sandbox.taa_module.taa_page import render_taa_page
from stock_engine.ui.components.simple_mode.session import (
    build_mini_universe, get_session, next_step, prev_step,
)

_LOOKBACK_DAYS = 504  # ~2 trading years of daily data for MVO


# ── Returns provider ──────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_returns_cached(
    tickers: tuple[str, ...],
    end: str,
    lookback_days: int,
) -> pd.DataFrame:
    """Fetch daily close returns for *tickers* ending at *end*. Cached 10 min."""
    start = (
        pd.Timestamp(end) - pd.DateOffset(days=lookback_days)
    ).strftime("%Y-%m-%d")

    raw = yf.download(
        list(tickers), start=start, end=end,
        auto_adjust=True, progress=False,
    )
    if raw.empty:
        return pd.DataFrame()

    closes = (
        raw["Close"]
        if isinstance(raw.columns, pd.MultiIndex)
        else raw[["Close"]].rename(columns={"Close": tickers[0]})
    )
    # Drop columns that are entirely NaN, then return per-column so that
    # one bad ticker doesn't wipe out all rows for the rest.
    closes = closes.dropna(axis=1, how="all")
    rets = closes.pct_change()
    # Drop only the first row (all-NaN from pct_change); keep partial rows so
    # tickers with different start dates don't eliminate shared observations.
    return rets.iloc[1:]


class _YFReturnsProvider:
    """Satisfies the WindowedReturnsProvider protocol used by render_taa_page."""

    def __init__(self, reference_end: str) -> None:
        self._end = reference_end

    def get_returns(
        self, tickers: list[str], as_of: Optional[str] = None
    ) -> pd.DataFrame:
        return _fetch_returns_cached(
            tuple(sorted(tickers)), as_of or self._end, _LOOKBACK_DAYS
        )


# ── Page entry ────────────────────────────────────────────────────────────────

def render_page_taa(config) -> None:  # noqa: ARG001
    sess = get_session()

    if not sess.universe.tickers:
        st.info("Return to Stock Selection to add assets first.")
        _render_nav(can_proceed=False)
        return

    ref_end = (
        str(sess.universe.backtest_start)
        if sess.universe.backtest_start
        else date.today().isoformat()
    )

    mini     = build_mini_universe(sess)
    provider = _YFReturnsProvider(reference_end=ref_end)

    taa = render_taa_page(mini, provider)

    _render_nav(can_proceed=(taa is not None))


def _render_nav(can_proceed: bool) -> None:
    st.markdown("---")
    c_back, _, c_next = st.columns([1, 5, 1])
    with c_back:
        if st.button("← Back", key="taa_page_back", use_container_width=True):
            prev_step()
    with c_next:
        if st.button(
            "Next →", key="taa_page_next",
            type="primary", use_container_width=True,
            disabled=not can_proceed,
        ):
            next_step()
