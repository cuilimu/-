"""
analytics/arimax/portfolio_target.py
Convert a BacktestResult into the (DatetimeIndex, target) series the engine expects.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from stock_engine.backtest.base import BacktestResult


TargetKind = Literal["return", "log_return", "excess_return", "nav"]


def portfolio_nav_series(result: BacktestResult) -> pd.Series:
    """Daily NAV series indexed on snapshot timestamp."""
    if not result.snapshots:
        raise ValueError("BacktestResult has no snapshots — run a backtest first.")
    s = pd.Series(
        {pd.Timestamp(snap.timestamp).normalize(): float(snap.nav) for snap in result.snapshots},
        name="nav",
    ).sort_index()
    s.index.name = "DATE"
    return s


def portfolio_target_frame(
    result: BacktestResult,
    kind: TargetKind = "return",
    risk_free_annual: float = 0.0,
    target_name: str = "y",
) -> pd.DataFrame:
    """
    Build a single-column target DataFrame the ARIMAX engine can consume:

      • DatetimeIndex (named 'DATE')
      • one column named `target_name`

    Caller can then concatenate MEV columns and pass the result into
    `ARIMAXPipeline.run(raw=..., ds_column='DATE')`.

    `kind`:
      - "return"        : simple daily return = nav.pct_change()
      - "log_return"    : log(nav).diff()
      - "excess_return" : simple return minus daily-equivalent of risk_free_annual
      - "nav"           : raw NAV (no transformation; rare for ARIMAX)
    """
    nav = portfolio_nav_series(result)

    if kind == "nav":
        y = nav
    elif kind == "return":
        y = nav.pct_change()
    elif kind == "log_return":
        y = np.log(nav).diff()
    elif kind == "excess_return":
        rf_daily = (1.0 + risk_free_annual) ** (1.0 / 252.0) - 1.0
        y = nav.pct_change() - rf_daily
    else:
        raise ValueError(f"Unknown target kind '{kind}'")

    df = y.dropna().to_frame(name=target_name)
    df.index.name = "DATE"
    return df


def merge_target_with_mevs(
    target_df: pd.DataFrame,
    mev_df: pd.DataFrame,
    how: Literal["inner", "left"] = "left",
) -> pd.DataFrame:
    """
    Merge (target, MEVs) on a common DatetimeIndex named 'DATE'.

    MEVs are typically lower-frequency (monthly / quarterly); we forward-fill
    them onto the target's daily index before merging so the resampling step
    in `data_preprocess` has full coverage to pick from.
    """
    if not isinstance(target_df.index, pd.DatetimeIndex):
        raise TypeError("target_df must have a DatetimeIndex")
    if not isinstance(mev_df.index, pd.DatetimeIndex):
        raise TypeError("mev_df must have a DatetimeIndex")

    # Reindex MEVs onto target's daily frequency, forward-filling
    mev_aligned = mev_df.reindex(target_df.index.union(mev_df.index)).sort_index().ffill()
    merged = target_df.join(mev_aligned, how=how)
    merged.index.name = "DATE"
    return merged.dropna()
