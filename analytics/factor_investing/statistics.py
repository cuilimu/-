"""
analytics/factor_investing/statistics.py — Stateless statistical computations.

All functions are pure: they accept pd.Series / dicts and return typed results.
No I/O, no UI, no side effects.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import scipy.stats
from statsmodels.tsa.stattools import acf

from stock_engine.analytics.factor_investing.types import (
    FactorCorrelationMatrix,
    FactorStats,
)


# ── Primary statistics computation ────────────────────────────────────────────

def compute_factor_stats(
    factor_name: str,
    qspread: pd.Series,
) -> FactorStats:
    """Compute summary statistics for a factor Q-spread return series.

    Parameters
    ----------
    factor_name:
        Human-readable label stored on the result.
    qspread:
        Monthly decimal return series with a DatetimeIndex.  NaNs are dropped
        before any calculation.

    Returns
    -------
    FactorStats dataclass.  Fields that cannot be computed (e.g. insufficient
    observations) are set to ``float('nan')``.
    """
    clean = qspread.dropna()
    n = len(clean)

    if n == 0:
        return FactorStats(
            factor_name=factor_name,
            n_months=0,
            mean_ann=float("nan"),
            std_ann=float("nan"),
            sharpe=float("nan"),
            skewness=float("nan"),
            kurtosis=float("nan"),
            max_monthly=float("nan"),
            min_monthly=float("nan"),
            avg_turnover=float("nan"),
            acf_lag1=float("nan"),
            acf_lag12=float("nan"),
            acf_lag24=float("nan"),
            t_stat=float("nan"),
            p_value=float("nan"),
        )

    arr = clean.to_numpy(dtype=float)

    # ── Annualised return & volatility ────────────────────────────────────────
    mean_ann = float(arr.mean()) * 12
    std_ann = float(arr.std(ddof=1)) * math.sqrt(12)
    sharpe = mean_ann / std_ann if std_ann > 0.0 else float("nan")

    # ── Higher moments ────────────────────────────────────────────────────────
    skewness = float(scipy.stats.skew(arr, bias=False))
    kurtosis = float(scipy.stats.kurtosis(arr, bias=False))   # excess kurtosis

    # ── Range ─────────────────────────────────────────────────────────────────
    max_monthly = float(arr.max())
    min_monthly = float(arr.min())

    # ── Autocorrelations ──────────────────────────────────────────────────────
    acf_lag1, acf_lag12, acf_lag24 = _compute_acf(arr, nlags=24)

    # ── Hypothesis test ───────────────────────────────────────────────────────
    t_stat, p_value = run_hypothesis_test(clean)

    return FactorStats(
        factor_name=factor_name,
        n_months=n,
        mean_ann=mean_ann,
        std_ann=std_ann,
        sharpe=sharpe,
        skewness=skewness,
        kurtosis=kurtosis,
        max_monthly=max_monthly,
        min_monthly=min_monthly,
        avg_turnover=float("nan"),   # not computable from Q-spread alone
        acf_lag1=acf_lag1,
        acf_lag12=acf_lag12,
        acf_lag24=acf_lag24,
        t_stat=t_stat,
        p_value=p_value,
    )


# ── Correlation matrix ─────────────────────────────────────────────────────────

def compute_correlation_matrix(
    qspread_dict: dict[str, pd.Series],
) -> FactorCorrelationMatrix:
    """Compute pairwise Pearson correlation across factor Q-spread series.

    Series are aligned on their common date index (inner join) before
    correlation is computed.  If fewer than two factors are supplied, the
    returned matrix will have size 0 or 1 (still valid, just trivial).

    Parameters
    ----------
    qspread_dict:
        Mapping factor_name → monthly decimal return series.

    Returns
    -------
    FactorCorrelationMatrix with ``labels`` and symmetric ``matrix``.
    """
    if not qspread_dict:
        empty = pd.DataFrame(dtype=float)
        return FactorCorrelationMatrix(labels=[], matrix=empty)

    labels = list(qspread_dict.keys())

    # Align all series on common index (inner join via DataFrame constructor)
    panel = pd.DataFrame(qspread_dict)  # outer join; NaNs where series differ
    panel = panel.dropna(how="any")      # inner-join equivalent

    if panel.empty or panel.shape[1] < 2:
        # Return identity-like correlation matrix with whatever columns exist
        corr = panel.corr()
        return FactorCorrelationMatrix(labels=list(corr.columns), matrix=corr)

    corr = panel.corr(method="pearson")
    return FactorCorrelationMatrix(labels=labels, matrix=corr)


# ── Hypothesis test ────────────────────────────────────────────────────────────

def run_hypothesis_test(qspread: pd.Series) -> tuple[float, float]:
    """One-sample t-test: H0: mean = 0, H1: mean > 0.

    Parameters
    ----------
    qspread:
        Monthly decimal return series.  NaNs are dropped before the test.

    Returns
    -------
    (t_stat, p_value) tuple.  Returns (nan, nan) if the series has fewer than
    two observations.
    """
    clean = qspread.dropna()
    if len(clean) < 2:
        return float("nan"), float("nan")

    result = scipy.stats.ttest_1samp(
        clean.to_numpy(dtype=float),
        popmean=0.0,
        alternative="greater",
    )
    return float(result.statistic), float(result.pvalue)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _compute_acf(
    arr: np.ndarray,
    nlags: int = 24,
) -> tuple[float, float, float]:
    """Return ACF values at lags 1, 12, and 24.

    Falls back to NaN if the series is too short or statsmodels raises.
    """
    nan3 = (float("nan"), float("nan"), float("nan"))

    if len(arr) < nlags + 1:
        return nan3

    try:
        acf_vals = acf(arr, nlags=nlags, fft=True, missing="drop")
    except Exception:  # noqa: BLE001
        return nan3

    def _safe(idx: int) -> float:
        return float(acf_vals[idx]) if idx < len(acf_vals) else float("nan")

    return _safe(1), _safe(12), _safe(24)
