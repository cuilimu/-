"""
analytics/factor_investing/engine.py — Orchestration layer.

FactorInvestingEngine coordinates data fetching and statistical computation
using a single live data source: Kenneth French's Data Library.  It exposes
one public method, run_live(), which downloads factor return series and returns
a fully-populated FactorInvestingResult.
"""
from __future__ import annotations

import pandas as pd

from stock_engine.analytics.factor_investing.live_loader import load_french_factors
from stock_engine.analytics.factor_investing.statistics import (
    compute_correlation_matrix,
    compute_factor_stats,
)
from stock_engine.analytics.factor_investing.types import (
    CORE_FACTORS,
    FactorCorrelationMatrix,
    FactorInvestingResult,
    FactorStats,
    QuintileResult,
)


class FactorInvestingEngine:
    """Orchestrates the factor-investing analytics pipeline.

    The engine fetches long-short factor return series from Kenneth French's
    Data Library and computes summary statistics and cross-factor correlations.
    No local files are required.
    """

    def __init__(self) -> None:
        pass

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_live(
        self,
        factors: list[str] | None = None,
        start: str | None = "1990-01-01",
        end: str | None = None,
    ) -> FactorInvestingResult:
        """Execute the live pipeline using Fama-French data.

        Downloads monthly factor returns from Kenneth French's Data Library
        and maps them to the engine's 7-factor names.  No local files required.

        Parameters
        ----------
        factors:
            Subset of CORE_FACTORS to analyse.  Defaults to all seven.
        start:
            ISO date string for the start of the download window.
        end:
            ISO date string for the end of the download window (default: today).

        Returns
        -------
        FactorInvestingResult with source="live".
        """
        factors = factors or CORE_FACTORS

        # ── Step 1: Download live Q-spread series from French library ──────────
        qspread_dict = load_french_factors(factors=factors, start=start, end=end)

        # ── Step 2: Compute per-factor statistics ──────────────────────────────
        factor_stats: list[FactorStats] = []
        for factor_name in factors:
            series = qspread_dict.get(factor_name, pd.Series(dtype=float))
            stats = compute_factor_stats(factor_name, series)
            factor_stats.append(stats)

        # ── Step 3: Cross-factor correlation ──────────────────────────────────
        correlation = compute_correlation_matrix(qspread_dict)

        # ── Step 4: No quintile breakdown (French gives only spread) ──────────
        quintile_returns: list[QuintileResult] = []

        # ── Step 5: Assemble result ───────────────────────────────────────────
        as_of_date = self._determine_as_of_date(qspread_dict)

        return FactorInvestingResult(
            factor_stats=factor_stats,
            quintile_returns=quintile_returns,
            correlation=correlation,
            source="live",
            as_of_date=as_of_date,
            qspread_series=qspread_dict,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _determine_as_of_date(
        self,
        qspread_dict: dict[str, pd.Series],
    ) -> pd.Timestamp:
        """Return the latest date present across all loaded Q-spread series."""
        latest = pd.NaT
        for series in qspread_dict.values():
            if series.empty:
                continue
            series_max = series.index.max()
            if pd.isna(latest) or series_max > latest:
                latest = series_max
        if pd.isna(latest):
            return pd.Timestamp.now().normalize()
        return pd.Timestamp(latest)
