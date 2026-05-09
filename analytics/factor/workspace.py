"""
analytics/factor/workspace.py
ReturnWorkspace: an in-memory panel of aligned monthly return series.
Acts as the variable namespace for the STATA-style command interface.
"""
from __future__ import annotations
from typing import Optional
import pandas as pd


class ReturnWorkspace:
    """
    Thin wrapper around a pd.DataFrame.
    Columns = variable names (e.g. "portfolio", "mktrf", "resid_a").
    Index   = month-end DatetimeIndex, shared across all series.
    """

    def __init__(self) -> None:
        self._df: pd.DataFrame = pd.DataFrame()
        self._last_residuals: Optional[pd.Series] = None
        self._last_fitted: Optional[pd.Series] = None
        self._last_cmd: str = ""

    # ── Mutation ──────────────────────────────────────────────────────────

    def add(self, name: str, series: pd.Series) -> None:
        """Add or overwrite a column. Re-aligns index automatically."""
        name = _safe_name(name)
        s = series.copy()
        s.name = name
        if self._df.empty:
            self._df = s.to_frame()
        else:
            self._df = self._df.join(s.to_frame(), how="outer")

    def drop(self, name: str) -> bool:
        """Remove a column. Returns True if found."""
        name = _safe_name(name)
        if name in self._df.columns:
            self._df = self._df.drop(columns=[name])
            return True
        return False

    def set_last_result(self, residuals: pd.Series, fitted: pd.Series, cmd: str) -> None:
        self._last_residuals = residuals.copy()
        self._last_fitted    = fitted.copy()
        self._last_cmd       = cmd

    # ── Query ─────────────────────────────────────────────────────────────

    def ls(self) -> list[str]:
        return list(self._df.columns)

    def df(self) -> pd.DataFrame:
        return self._df.copy()

    def __contains__(self, name: str) -> bool:
        return _safe_name(name) in self._df.columns

    def __getitem__(self, name: str) -> pd.Series:
        return self._df[_safe_name(name)]

    def get_last_residuals(self) -> Optional[pd.Series]:
        return self._last_residuals

    def get_last_fitted(self) -> Optional[pd.Series]:
        return self._last_fitted

    def is_empty(self) -> bool:
        return self._df.empty

    def describe(self) -> pd.DataFrame:
        """Summary stats for all columns (n, mean, std, min, max)."""
        if self._df.empty:
            return pd.DataFrame()
        d = self._df.describe().T[["count", "mean", "std", "min", "max"]]
        d["count"] = d["count"].astype(int)
        return d


def _safe_name(name: str) -> str:
    """Normalise variable name: lowercase, spaces → underscores."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")
