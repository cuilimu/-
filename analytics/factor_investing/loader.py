"""
analytics/factor_investing/loader.py — Tier-1 data loading from pre-computed files.

Reads CapitalIQ_extend.csv (Q-spread series) and Factor_SP500.xlsx (quintile
returns) and returns typed containers.  All I/O errors are caught and reported
via warnings rather than exceptions so callers can degrade gracefully.
"""
from __future__ import annotations

import warnings
from typing import Optional

import pandas as pd

from stock_engine.analytics.factor_investing.types import CORE_FACTORS, QuintileResult


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_yyyymmdd(series: pd.Series) -> pd.DatetimeIndex:
    """Convert an integer YYYYMMDD column to a month-end DatetimeIndex."""
    dt = pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")
    return pd.DatetimeIndex(dt).to_period("M").to_timestamp("M")


# ── public API ─────────────────────────────────────────────────────────────────

def load_qspread_series(
    capitaliq_path: str,
    factors: list[str] | None = None,
) -> dict[str, pd.Series]:
    """Load Q-spread return series from CapitalIQ_extend.csv.

    Parameters
    ----------
    capitaliq_path:
        Absolute path to CapitalIQ_extend.csv.
    factors:
        Factor names to load.  Defaults to CORE_FACTORS.

    Returns
    -------
    dict mapping factor_name → pd.Series with month-end DatetimeIndex.
    Each series contains decimal returns (raw CSV values divided by 100).
    Series are individually dropna'd, so start dates may differ across factors.
    """
    factors = factors or CORE_FACTORS

    try:
        raw = pd.read_csv(capitaliq_path)
    except FileNotFoundError:
        warnings.warn(
            f"CapitalIQ file not found: {capitaliq_path}",
            UserWarning,
            stacklevel=2,
        )
        return {}
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"Failed to read {capitaliq_path}: {exc}",
            UserWarning,
            stacklevel=2,
        )
        return {}

    # Normalise column names — strip whitespace
    raw.columns = raw.columns.str.strip()

    # Identify date column (case-insensitive)
    date_col = next(
        (c for c in raw.columns if c.lower() == "date"),
        None,
    )
    if date_col is None:
        warnings.warn(
            "No 'Date' column found in CapitalIQ CSV; returning empty dict.",
            UserWarning,
            stacklevel=2,
        )
        return {}

    index = _parse_yyyymmdd(raw[date_col])

    result: dict[str, pd.Series] = {}
    for factor in factors:
        if factor not in raw.columns:
            warnings.warn(
                f"Factor '{factor}' not found in CapitalIQ CSV; skipping.",
                UserWarning,
                stacklevel=2,
            )
            continue

        series = pd.Series(
            raw[factor].values / 100.0,   # percentage → decimal
            index=index,
            name=factor,
            dtype=float,
        ).dropna()
        result[factor] = series

    return result


def load_quintile_returns(
    factor_sp500_path: str,
    factors: list[str] | None = None,
) -> dict[str, QuintileResult]:
    """Load per-quintile return series from Factor_SP500.xlsx.

    Strategy
    --------
    1. Try ``pd.read_excel(path, sheet_name=None)`` — if sheets are named by
       factor, parse each sheet directly.
    2. If that yields no usable factor-named sheets, fall back to reading a
       single sheet with assumed multi-level columns (factor, quintile).

    Parameters
    ----------
    factor_sp500_path:
        Absolute path to Factor_SP500.xlsx.
    factors:
        Factor names to load.  Defaults to CORE_FACTORS.

    Returns
    -------
    dict mapping factor_name → QuintileResult.  Returns empty dict on any
    unrecoverable error.
    """
    factors = factors or CORE_FACTORS

    try:
        all_sheets: dict[str, pd.DataFrame] = pd.read_excel(
            factor_sp500_path, sheet_name=None
        )
    except FileNotFoundError:
        warnings.warn(
            f"Factor_SP500 file not found: {factor_sp500_path}",
            UserWarning,
            stacklevel=2,
        )
        return {}
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"Failed to read {factor_sp500_path}: {exc}",
            UserWarning,
            stacklevel=2,
        )
        return {}

    # ── Strategy 1: sheets named by factor ────────────────────────────────────
    factor_sheets = {
        k: v for k, v in all_sheets.items() if k in factors
    }
    if factor_sheets:
        return _parse_factor_sheets(factor_sheets)

    # ── Strategy 2: single sheet with multi-level columns ─────────────────────
    if len(all_sheets) == 1:
        single_df = next(iter(all_sheets.values()))
        return _parse_multilevel_sheet(single_df, factors)

    # If the first sheet contains all quintile columns for any factor, try it
    first_df = next(iter(all_sheets.values()))
    return _parse_multilevel_sheet(first_df, factors)


# ── private parsing helpers ────────────────────────────────────────────────────

_QUINTILE_COLS = ["Q1", "Q2", "Q3", "Q4", "Q5"]


def _parse_factor_sheets(
    sheets: dict[str, pd.DataFrame],
) -> dict[str, QuintileResult]:
    """Parse workbook where each sheet is one factor with Q1-Q5 columns."""
    results: dict[str, QuintileResult] = {}

    for factor_name, df in sheets.items():
        df.columns = df.columns.str.strip()

        # Locate date column
        date_col = next(
            (c for c in df.columns if c.lower() == "date"),
            None,
        )
        if date_col is None:
            warnings.warn(
                f"No 'Date' column in sheet '{factor_name}'; skipping.",
                UserWarning,
                stacklevel=3,
            )
            continue

        index = _parse_yyyymmdd(df[date_col])

        # Build quintile series
        q_series: dict[str, pd.Series] = {}
        for qcol in _QUINTILE_COLS:
            match = next(
                (c for c in df.columns if c.upper() == qcol),
                None,
            )
            if match is None:
                warnings.warn(
                    f"Column '{qcol}' missing in sheet '{factor_name}'.",
                    UserWarning,
                    stacklevel=3,
                )
                q_series[qcol] = pd.Series(float("nan"), index=index, name=qcol)
            else:
                q_series[qcol] = pd.Series(
                    df[match].values / 100.0,
                    index=index,
                    name=qcol,
                    dtype=float,
                )

        qspread = q_series["Q5"] - q_series["Q1"]
        qspread.name = "QSpread"

        results[factor_name] = QuintileResult(
            factor_name=factor_name,
            dates=pd.DatetimeIndex(index),
            q1=q_series["Q1"],
            q2=q_series["Q2"],
            q3=q_series["Q3"],
            q4=q_series["Q4"],
            q5=q_series["Q5"],
            qspread=qspread,
        )

    return results


def _parse_multilevel_sheet(
    df: pd.DataFrame,
    factors: list[str],
) -> dict[str, QuintileResult]:
    """Parse a single sheet with multi-level columns (factor, quintile)."""
    results: dict[str, QuintileResult] = {}

    if not isinstance(df.columns, pd.MultiIndex):
        # Cannot parse; return empty
        warnings.warn(
            "Factor_SP500 sheet does not have multi-level columns or "
            "factor-named sheets; quintile data unavailable.",
            UserWarning,
            stacklevel=3,
        )
        return {}

    # Top-level = factor name, second level = Q1..Q5 / Date
    for factor_name in factors:
        if factor_name not in df.columns.get_level_values(0):
            continue

        sub = df[factor_name].copy()
        sub.columns = sub.columns.str.strip()

        date_col = next(
            (c for c in sub.columns if c.lower() == "date"),
            None,
        )
        if date_col is None:
            warnings.warn(
                f"No 'Date' sub-column under factor '{factor_name}'; skipping.",
                UserWarning,
                stacklevel=3,
            )
            continue

        index = _parse_yyyymmdd(sub[date_col])
        q_series: dict[str, pd.Series] = {}
        for qcol in _QUINTILE_COLS:
            match = next(
                (c for c in sub.columns if c.upper() == qcol),
                None,
            )
            if match is None:
                q_series[qcol] = pd.Series(float("nan"), index=index, name=qcol)
            else:
                q_series[qcol] = pd.Series(
                    sub[match].values / 100.0,
                    index=index,
                    name=qcol,
                    dtype=float,
                )

        qspread = q_series["Q5"] - q_series["Q1"]
        qspread.name = "QSpread"

        results[factor_name] = QuintileResult(
            factor_name=factor_name,
            dates=pd.DatetimeIndex(index),
            q1=q_series["Q1"],
            q2=q_series["Q2"],
            q3=q_series["Q3"],
            q4=q_series["Q4"],
            q5=q_series["Q5"],
            qspread=qspread,
        )

    return results
