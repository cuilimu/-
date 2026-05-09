"""
analytics/factor/loader.py
Populates a ReturnWorkspace from BacktestResult(s) + Fama-French factors.
Mode-agnostic: handles single, group, or both simultaneously.

All portfolio and stock return series are stored as EXCESS returns
(raw monthly return minus risk-free rate rf).  FF factor series are
kept as-is (mktrf is already excess; rf stored as the rate itself).
"""
from __future__ import annotations
from typing import Optional
import re
import pandas as pd
from stock_engine.analytics.factor.workspace import ReturnWorkspace
from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.data.factor_data_provider import FactorDataProvider, FACTOR_COLS

FF_FACTOR_NAMES = set(FACTOR_COLS)   # mktrf smb hml rmw cma umd rf


def load_into_workspace(
    workspace: ReturnWorkspace,
    config: Config,
    single_result: Optional[BacktestResult] = None,
    group_results: Optional[dict[str, BacktestResult]] = None,
) -> list[str]:
    """
    Populate workspace.  Returns list of variable names added.
    Step 1: load raw portfolio + ticker returns.
    Step 2: load FF factors (includes rf).
    Step 3: convert raw returns → excess returns (subtract rf, aligned by date).
    """
    raw_series: dict[str, pd.Series] = {}   # name → raw monthly return

    # ── Step 1: portfolio & ticker returns ─────────────────────────────
    if single_result is not None and single_result.snapshots:
        _sname = _safe(getattr(single_result, "strategy_name", None) or "portfolio")
        raw_series[_sname] = _portfolio_returns(single_result)
        for ticker in single_result.tickers:
            s = _ticker_returns(single_result, ticker)
            if s is not None:
                raw_series[ticker.lower()] = s

    if group_results:
        for grp_name, result in group_results.items():
            if not result.snapshots:
                continue
            vname = _safe(grp_name)
            raw_series[vname] = _portfolio_returns(result)
            for ticker in result.tickers:
                tvname = f"{vname}_{ticker.lower()}"
                s = _ticker_returns(result, ticker)
                if s is not None:
                    raw_series[tvname] = s

    # ── Step 2: Fama-French factors ─────────────────────────────────────
    start, end = _date_range(single_result, group_results)
    rf_series: Optional[pd.Series] = None
    if start and end:
        try:
            prov = FactorDataProvider(config)
            factors = prov.fetch(start, end)
            for col in factors.columns:
                workspace.add(col, factors[col])
            if "rf" in factors.columns:
                rf_series = factors["rf"]
        except Exception:
            pass

    # ── Step 3: convert raw → excess returns ─────────────────────────────
    added: list[str] = list(workspace.ls())   # FF factor names already added
    for name, raw in raw_series.items():
        if rf_series is not None:
            aligned_rf = rf_series.reindex(raw.index).fillna(0)
            excess = (raw - aligned_rf).rename(name)
        else:
            excess = raw.rename(name)
        workspace.add(name, excess)
        added.append(name)

    return added


# ── Helpers ───────────────────────────────────────────────────────────────

def _portfolio_returns(result: BacktestResult) -> pd.Series:
    nav = pd.Series(
        {s.timestamp: s.nav for s in result.snapshots}
    ).sort_index()
    monthly = nav.resample("ME").last().dropna()
    ret = monthly.pct_change().dropna()
    ret.index = ret.index.to_period("M").to_timestamp("M")
    return ret


def _ticker_returns(result: BacktestResult, ticker: str) -> Optional[pd.Series]:
    try:
        prices = {}
        for snap in result.snapshots:
            price_map = getattr(snap, "price_map", {}) or {}
            if ticker in price_map:
                prices[snap.timestamp] = price_map[ticker]
        if len(prices) < 4:
            return None
        s = pd.Series(prices).sort_index()
        monthly = s.resample("ME").last().dropna()
        ret = monthly.pct_change().dropna()
        ret.index = ret.index.to_period("M").to_timestamp("M")
        return ret
    except Exception:
        return None


def _date_range(
    single_result: Optional[BacktestResult],
    group_results: Optional[dict[str, BacktestResult]],
) -> tuple[Optional[str], Optional[str]]:
    starts, ends = [], []
    all_results = []
    if single_result:
        all_results.append(single_result)
    if group_results:
        all_results.extend(group_results.values())
    for r in all_results:
        if r.start_date:
            starts.append(r.start_date)
        if r.end_date:
            ends.append(r.end_date)
    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def _safe(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    return s.strip("_") or "portfolio"
