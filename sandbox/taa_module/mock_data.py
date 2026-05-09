"""
mock_data.py — placeholder ReturnsProvider for the sandbox.

`MockReturnsProvider.get_returns(tickers)` returns a 1500-day random
returns panel. Generation parameters are derived from ticker hashes so
the same set of tickers always yields the same panel — UI reruns won't
make the heatmap jump.

When swapping in real data later, write a parallel class:

    class YFinanceReturnsProvider:
        def get_returns(self, tickers: list[str]) -> pd.DataFrame: ...

…with the same method signature, and inject it into compute_factor_mvo().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd


def _ticker_seed(seed: int, tickers: List[str]) -> int:
    """Deterministic seed derived from the ticker set."""
    h = sum(hash(t) % 9973 for t in sorted(tickers))
    return (seed + h) & 0x7FFF_FFFF


@dataclass
class MockReturnsProvider:
    seed: int = 42
    n_days: int = 1500
    trading: int = 252
    mu_low: float = 0.04
    mu_high: float = 0.20
    vol_low: float = 0.10
    vol_high: float = 0.30

    def get_returns(self, tickers: List[str]) -> pd.DataFrame:
        """Return a deterministic T × N daily-return panel for these tickers."""
        n = len(tickers)
        if n == 0:
            return pd.DataFrame()

        rng = np.random.default_rng(_ticker_seed(self.seed, list(tickers)))

        mu  = rng.uniform(self.mu_low,  self.mu_high,  size=n)
        vol = rng.uniform(self.vol_low, self.vol_high, size=n)

        # Random correlation matrix via A Aᵀ → standardise.
        # Add a small ridge so it stays positive-definite for small n.
        a = rng.normal(size=(n, n))
        psd = a @ a.T + np.eye(n) * 1e-3
        d = np.sqrt(np.diag(psd))
        corr = psd / np.outer(d, d)

        cov = np.diag(vol) @ corr @ np.diag(vol)

        daily = rng.multivariate_normal(
            mu / self.trading,
            cov / self.trading,
            size=self.n_days,
            check_valid="ignore",
        )
        return pd.DataFrame(daily, columns=list(tickers))
