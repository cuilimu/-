"""
analytics/univariate.py — Univariate statistical profiler for a return series.
Input:  pd.Series of daily returns (float)
Output: UnivariateProfile dataclass — pure computation, no UI/plotting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from statsmodels.tsa.stattools import acf as sm_acf


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class UnivariateProfile:
    # ── Summary counts ─────────────────────────────────────────────────────
    n_total:      int
    n_null:       int
    n_nonnull:    int
    n_zeros:      int
    n_inf:        int
    memory_bytes: int          # series.memory_usage(deep=True)

    # ── Descriptive statistics ─────────────────────────────────────────────
    mean:             float
    median:           float
    std:              float
    variance:         float
    skewness:         float
    kurtosis:         float    # excess kurtosis (Fisher definition, normal = 0)
    cv:               float    # std / |mean|, inf when mean ≈ 0
    mad:              float    # mean absolute deviation from mean
    annualised_mean:  float
    annualised_vol:   float

    # ── Quantile statistics ────────────────────────────────────────────────
    q_min:   float
    q_p05:   float
    q_q1:    float
    q_median: float
    q_q3:    float
    q_p95:   float
    q_max:   float
    q_range: float
    q_iqr:   float

    # ── Pre-computed chart data (plain dicts, JSON-serialisable) ──────────
    histogram: dict   # {edges: list[float], counts: list[int]}
    cdf:       dict   # {x: list[float], y: list[float]}
    qq:        dict   # {theoretical: list[float], sample: list[float]}
    acf_data:  dict   # {lags: list[int], values: list[float], conf: float}
    line:      dict   # {dates: list[str], values: list[float]}

    # ── Alerts ────────────────────────────────────────────────────────────
    alerts: list[str] = field(default_factory=list)


# ── Main computation ──────────────────────────────────────────────────────────

def compute_univariate(
    series: pd.Series,
    annualisation_factor: int = 252,
    acf_lags: int = 30,
    histogram_bins: int = 40,
) -> UnivariateProfile:
    """
    Compute a full univariate profile of a daily return series.

    Parameters
    ----------
    series               : pd.Series of float (daily returns, e.g. 0.012 = 1.2%)
    annualisation_factor : 252 for daily, 12 for monthly, 4 for quarterly
    acf_lags             : number of ACF lags to compute
    histogram_bins       : number of histogram bins
    """
    # ── Memory ────────────────────────────────────────────────────────────
    memory_bytes = int(series.memory_usage(deep=True))

    # ── Summary counts ────────────────────────────────────────────────────
    n_total   = len(series)
    n_null    = int(series.isna().sum())
    n_inf     = int(np.isinf(series.replace([np.nan], 0)).sum())
    clean     = series.dropna().replace([np.inf, -np.inf], np.nan).dropna()
    n_nonnull = len(clean)
    n_zeros   = int((clean == 0).sum())

    # ── Descriptive ───────────────────────────────────────────────────────
    vals = clean.values.astype(float)

    mean_     = float(np.mean(vals))
    median_   = float(np.median(vals))
    std_      = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
    variance_ = float(np.var(vals, ddof=1)) if len(vals) > 1 else 0.0
    skew_     = float(scipy_stats.skew(vals)) if len(vals) > 2 else 0.0
    kurt_     = float(scipy_stats.kurtosis(vals, fisher=True)) if len(vals) > 3 else 0.0
    cv_       = (std_ / abs(mean_)) if abs(mean_) > 1e-10 else float("inf")
    mad_      = float(np.mean(np.abs(vals - mean_)))

    ann_mean  = mean_ * annualisation_factor
    ann_vol   = std_ * np.sqrt(annualisation_factor)

    # ── Quantiles ─────────────────────────────────────────────────────────
    pcts = np.percentile(vals, [0, 5, 25, 50, 75, 95, 100]) if len(vals) > 0 else [0] * 7
    q_min, q_p05, q_q1, q_med, q_q3, q_p95, q_max = (float(p) for p in pcts)
    q_range = q_max - q_min
    q_iqr   = q_q3 - q_q1

    # ── Histogram ─────────────────────────────────────────────────────────
    counts, edges = np.histogram(vals, bins=histogram_bins)
    histogram = {
        "edges":  edges.tolist(),
        "counts": counts.tolist(),
    }

    # ── Empirical CDF ─────────────────────────────────────────────────────
    sorted_vals = np.sort(vals)
    cdf_y = np.arange(1, len(sorted_vals) + 1) / len(sorted_vals)
    cdf = {
        "x": sorted_vals.tolist(),
        "y": cdf_y.tolist(),
    }

    # ── QQ plot (vs normal) ───────────────────────────────────────────────
    if len(vals) >= 4:
        (osm, osr), (slope, intercept, r_val) = scipy_stats.probplot(vals, dist="norm")
        qq = {
            "theoretical": list(osm),
            "sample":      list(osr),
            "slope":       float(slope),
            "intercept":   float(intercept),
            "r_squared":   float(r_val ** 2),
        }
    else:
        qq = {"theoretical": [], "sample": [], "slope": 1.0, "intercept": 0.0, "r_squared": 0.0}

    # ── ACF ───────────────────────────────────────────────────────────────
    n_lags = min(acf_lags, len(vals) // 2 - 1)
    if n_lags >= 1 and len(vals) > n_lags + 1:
        acf_vals = sm_acf(vals, nlags=n_lags, fft=True)
        conf_int = 1.96 / np.sqrt(len(vals))
        acf_data = {
            "lags":   list(range(len(acf_vals))),
            "values": acf_vals.tolist(),
            "conf":   float(conf_int),
        }
    else:
        acf_data = {"lags": [], "values": [], "conf": 0.0}

    # ── Line (raw series for time chart) ──────────────────────────────────
    if isinstance(clean.index, pd.DatetimeIndex):
        dates = [d.strftime("%Y-%m-%d") for d in clean.index]
    else:
        dates = [str(i) for i in clean.index]
    line = {"dates": dates, "values": vals.tolist()}

    # ── Alerts ────────────────────────────────────────────────────────────
    alerts: list[str] = []
    if abs(skew_) > 1.0:
        direction = "right" if skew_ > 0 else "left"
        alerts.append(
            f"High skewness ({skew_:+.2f}) — distribution is {direction}-skewed"
        )
    if kurt_ > 3.0:
        alerts.append(
            f"Fat tails (excess kurtosis {kurt_:.2f}) — heavier than normal distribution"
        )
    if n_nonnull > 0 and n_zeros / n_nonnull > 0.05:
        alerts.append(
            f"Many zero-return days ({n_zeros / n_nonnull * 100:.1f}%) — "
            "check for non-trading days or data gaps"
        )
    if cv_ != float("inf") and cv_ > 5.0:
        alerts.append(
            f"Very high CV ({cv_:.1f}) — returns are highly dispersed relative to mean"
        )

    return UnivariateProfile(
        n_total=n_total,
        n_null=n_null,
        n_nonnull=n_nonnull,
        n_zeros=n_zeros,
        n_inf=n_inf,
        memory_bytes=memory_bytes,
        mean=mean_,
        median=median_,
        std=std_,
        variance=variance_,
        skewness=skew_,
        kurtosis=kurt_,
        cv=cv_,
        mad=mad_,
        annualised_mean=ann_mean,
        annualised_vol=ann_vol,
        q_min=q_min,
        q_p05=q_p05,
        q_q1=q_q1,
        q_median=q_med,
        q_q3=q_q3,
        q_p95=q_p95,
        q_max=q_max,
        q_range=q_range,
        q_iqr=q_iqr,
        histogram=histogram,
        cdf=cdf,
        qq=qq,
        acf_data=acf_data,
        line=line,
        alerts=alerts,
    )


# ── Formatting helpers (used by both panel and any future export) ─────────────

def fmt_pct(v: float, decimals: int = 3) -> str:
    return f"{v * 100:+.{decimals}f}%"


def fmt_pct_plain(v: float, decimals: int = 3) -> str:
    return f"{v * 100:.{decimals}f}%"


def fmt_memory(n_bytes: int) -> str:
    if n_bytes >= 1_048_576:
        return f"{n_bytes / 1_048_576:.2f} MB"
    if n_bytes >= 1_024:
        return f"{n_bytes / 1_024:.1f} KB"
    return f"{n_bytes} B"
