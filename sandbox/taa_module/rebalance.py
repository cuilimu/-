"""
rebalance.py — canonical rebalance order for TAA-aware allocation.

Rule (locked by design):
    on every rebalance date, the factor-internal MVO weights MUST be
    recomputed first, then the bucket-equal allocation is rebuilt on
    top of those fresh intra-bucket weights.

    rebalance(date)  ≡  compute_factor_mvo(<= date)  ⇒
                        apply_equal_weights_v2(universe, taa)

The reverse order (carry stale intra-bucket weights through, then re-do
bucket equal) defeats TAA: the weights inside each bucket would be
frozen from the last initialisation while only the bucket-level shares
adapt — exactly what passthrough already does.

For Manual allocations, rebalance is irrelevant (Manual is TAA-
independent by design); they keep the user-set weights regardless.
"""
from __future__ import annotations

from typing import Dict, Optional, Protocol

import pandas as pd

from stock_engine.sandbox.taa_module.equal_weight import apply_equal_weights_v2
from stock_engine.sandbox.taa_module.factor_mvo import (
    Pick, TAAResult, compute_factor_mvo, passthrough_result,
)
from stock_engine.sandbox.taa_module.types import MiniUniverse


class WindowedReturnsProvider(Protocol):
    """Provider that can return returns truncated up to a given date.
    The sandbox's MockReturnsProvider satisfies this trivially because
    it ignores `as_of` and returns the same panel every time. The
    real-data provider used after integration must respect `as_of`."""
    def get_returns(
        self, tickers: list[str], as_of: Optional[str] = None,
    ) -> pd.DataFrame: ...


def rebalance_at(
    as_of: Optional[str],
    universe: MiniUniverse,
    provider: WindowedReturnsProvider,
    *,
    taa_mode: str = "factor",                      # "passthrough" | "factor"
    rf: float = 0.04,
    pick: Pick = "max_sharpe",
    target_return: Optional[float] = None,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> tuple[Dict[str, float], TAAResult]:
    """Compute the rebalanced ticker weights for a given as-of date.

    Returns (weights, taa_result) so callers can also inspect the
    intra-bucket payload, factor exposures, etc.
    """
    if taa_mode == "passthrough":
        taa = passthrough_result(universe, rf=rf)
    else:
        # Inject a windowed provider lambda so compute_factor_mvo gets
        # only the slice of returns up to `as_of`.
        class _Win:
            def get_returns(self, tickers):
                try:
                    return provider.get_returns(tickers, as_of=as_of)
                except TypeError:
                    return provider.get_returns(tickers)

        taa = compute_factor_mvo(
            universe, _Win(), rf=rf, pick=pick,
            target_return=target_return,
            with_diagnostics_for_all_buckets=True,
            compute_factor_exposures=True,
            min_weight=min_weight,
            max_weight=max_weight,
        )

    weights = apply_equal_weights_v2(universe, taa,
                                     min_weight=min_weight,
                                     max_weight=max_weight)
    return weights, taa
