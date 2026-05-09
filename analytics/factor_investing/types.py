"""
analytics/factor_investing/types.py — Data containers for the factor-investing module.

All containers are plain dataclasses; no business logic lives here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict
from typing import Literal

import pandas as pd


# ── Factor universe ────────────────────────────────────────────────────────────

CORE_FACTORS: list[str] = [
    "HL1M",
    "LTGC",
    "MOM",
    "BP",
    "Beta",
    "LogMktCap",
    "AnnVol12M",
]


# ── Result containers ──────────────────────────────────────────────────────────

@dataclass
class FactorStats:
    """Summary statistics for a single factor's Q-spread return series."""

    factor_name: str
    n_months: int
    mean_ann: float
    std_ann: float
    sharpe: float
    skewness: float
    kurtosis: float
    max_monthly: float
    min_monthly: float
    avg_turnover: float   # NaN when not computable from Q-spread alone
    acf_lag1: float
    acf_lag12: float
    acf_lag24: float
    t_stat: float
    p_value: float


@dataclass
class QuintileResult:
    """Monthly returns for each quintile portfolio and the long-short spread."""

    factor_name: str
    dates: pd.DatetimeIndex
    q1: pd.Series
    q2: pd.Series
    q3: pd.Series
    q4: pd.Series
    q5: pd.Series
    qspread: pd.Series   # Q5 − Q1 (long high, short low)


@dataclass
class FactorCorrelationMatrix:
    """Pairwise Pearson correlation of Q-spread return series."""

    labels: list[str]
    matrix: pd.DataFrame   # symmetric DataFrame indexed and columned by labels


@dataclass
class ValidationResult:
    """Cross-validation metrics for one factor (live vs static reference)."""

    factor_name: str
    ff_proxy: str             # e.g. "HML", "Mom"
    period_start: pd.Timestamp
    period_end: pd.Timestamp
    n_overlap: int            # overlapping months
    pearson_r: float          # Pearson correlation between live and static series
    r_squared: float          # R² of live ~ static regression
    beta: float               # slope coefficient (static -> live)
    validated: bool           # True when pearson_r >= validation_threshold


@dataclass
class FactorInvestingResult:
    """Top-level result object returned by FactorInvestingEngine.run_quick()."""

    factor_stats: list[FactorStats]
    quintile_returns: list[QuintileResult]   # one per factor; empty for live/missing
    correlation: FactorCorrelationMatrix
    source: Literal["precomputed", "computed", "live"]
    as_of_date: pd.Timestamp
    qspread_series: Dict[str, pd.Series] = field(default_factory=dict)  # raw series for charts
