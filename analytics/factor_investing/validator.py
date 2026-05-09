"""
analytics/factor_investing/validator.py — Cross-validation between live and static factor data.

Compares live Fama-French long-short returns against a static CapitalIQ Q-spread
dataset (user-supplied reference) over their overlapping date range.

High correlation (>= threshold) confirms that the live French data is a reliable
proxy for the custom quintile-sort methodology, and vice versa.
"""
from __future__ import annotations

import math
import warnings
from typing import Optional

import numpy as np
import pandas as pd

from stock_engine.analytics.factor_investing.live_loader import _FF_MAP
from stock_engine.analytics.factor_investing.types import ValidationResult

# Default correlation threshold for "validated" badge
DEFAULT_THRESHOLD = 0.80


def cross_validate(
    live_dict: dict[str, pd.Series],
    static_dict: dict[str, pd.Series],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[ValidationResult]:
    """Compute cross-validation metrics between live (FF) and static (CapitalIQ) series.

    Parameters
    ----------
    live_dict:
        Factor name -> Fama-French monthly return series (decimal).
    static_dict:
        Factor name -> CapitalIQ Q-spread monthly return series (decimal).
    threshold:
        Minimum Pearson r to set ValidationResult.validated = True.

    Returns
    -------
    list of ValidationResult, one per factor present in both dicts.
    Empty list if no overlap exists.
    """
    results: list[ValidationResult] = []

    common_factors = [f for f in live_dict if f in static_dict]
    if not common_factors:
        warnings.warn(
            "No common factors found between live and static datasets; "
            "cross-validation skipped.",
            UserWarning,
            stacklevel=2,
        )
        return []

    for factor in common_factors:
        live_s   = live_dict[factor].dropna()
        static_s = static_dict[factor].dropna()

        # Align on overlapping date range
        aligned = pd.concat(
            [live_s.rename("live"), static_s.rename("static")],
            axis=1,
            join="inner",
        ).dropna()

        n_overlap = len(aligned)
        if n_overlap < 12:
            warnings.warn(
                f"Factor '{factor}': only {n_overlap} overlapping months — skipping.",
                UserWarning,
                stacklevel=2,
            )
            continue

        x = aligned["static"].values
        y = aligned["live"].values

        # Pearson correlation
        pearson_r = float(np.corrcoef(x, y)[0, 1])
        if math.isnan(pearson_r):
            pearson_r = 0.0

        # OLS: live = alpha + beta * static
        # beta = cov(x,y) / var(x)
        var_x = float(np.var(x, ddof=1))
        if var_x > 0:
            beta = float(np.cov(x, y, ddof=1)[0, 1] / var_x)
        else:
            beta = float("nan")

        r_squared = pearson_r ** 2

        results.append(ValidationResult(
            factor_name=factor,
            ff_proxy=_FF_MAP.get(factor, (None, "—", 0))[1],
            period_start=aligned.index.min(),
            period_end=aligned.index.max(),
            n_overlap=n_overlap,
            pearson_r=pearson_r,
            r_squared=r_squared,
            beta=beta,
            validated=pearson_r >= threshold,
        ))

    return sorted(results, key=lambda r: -r.pearson_r)
