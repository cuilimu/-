"""
analytics/factor_investing/engine.py — Orchestration layer.

FactorInvestingEngine coordinates data loading and statistical computation.
It exposes a single public method, run_quick(), which executes the Tier-1
(pre-computed data) pipeline and returns a fully-populated FactorInvestingResult.
"""
from __future__ import annotations

import warnings
from typing import Optional

import pandas as pd

from stock_engine.analytics.factor_investing.live_loader import load_french_factors
from stock_engine.analytics.factor_investing.loader import (
    load_qspread_series,
    load_quintile_returns,
)
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

    Parameters
    ----------
    capitaliq_path:
        Optional path to CapitalIQ_extend.csv.  Required only for run_quick().
    factor_sp500_path:
        Optional path to Factor_SP500.xlsx.  Required only for run_quick().
    panel_path:
        Reserved for Tier-2 (stock-level panel).  Pass None to skip.
    """

    def __init__(
        self,
        capitaliq_path: str | None = None,
        factor_sp500_path: str | None = None,
        panel_path: str | None = None,
    ) -> None:
        self._capitaliq_path = capitaliq_path
        self._factor_sp500_path = factor_sp500_path
        self._panel_path = panel_path   # reserved for Tier-2

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_quick(
        self,
        factors: list[str] | None = None,
    ) -> FactorInvestingResult:
        """Execute the Tier-1 pipeline using pre-computed CapitalIQ data.

        Steps
        -----
        1. Load Q-spread series from CapitalIQ_extend.csv.
        2. Compute FactorStats for each factor.
        3. Compute the cross-factor correlation matrix.
        4. Attempt to load per-quintile returns from Factor_SP500.xlsx;
           degrade gracefully to an empty list if the file is missing or
           cannot be parsed.
        5. Return a FactorInvestingResult.

        Parameters
        ----------
        factors:
            Subset of factors to analyse.  Defaults to CORE_FACTORS.

        Returns
        -------
        FactorInvestingResult with source="precomputed".
        """
        factors = factors or CORE_FACTORS

        # ── Step 1: Load Q-spread series ──────────────────────────────────────
        qspread_dict = load_qspread_series(
            self._capitaliq_path,
            factors=factors,
        )

        # ── Step 2: Compute per-factor statistics ──────────────────────────────
        factor_stats: list[FactorStats] = []
        for factor_name in factors:
            series = qspread_dict.get(factor_name, pd.Series(dtype=float))
            stats = compute_factor_stats(factor_name, series)
            factor_stats.append(stats)

        # ── Step 3: Cross-factor correlation ──────────────────────────────────
        correlation = compute_correlation_matrix(qspread_dict)

        # ── Step 4: Per-quintile returns (optional) ───────────────────────────
        quintile_returns: list[QuintileResult] = []
        try:
            quintile_map = load_quintile_returns(
                self._factor_sp500_path,
                factors=factors,
            )
            quintile_returns = list(quintile_map.values())
        except Exception as exc:  # noqa: BLE001 — always degrade gracefully
            warnings.warn(
                f"Could not load quintile returns: {exc}",
                UserWarning,
                stacklevel=2,
            )

        # ── Step 5: Assemble and return result ────────────────────────────────
        as_of_date = self._determine_as_of_date(qspread_dict)

        return FactorInvestingResult(
            factor_stats=factor_stats,
            quintile_returns=quintile_returns,
            correlation=correlation,
            source="precomputed",
            as_of_date=as_of_date,
            qspread_series=qspread_dict,
        )

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
