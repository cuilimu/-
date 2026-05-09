"""
factor_mvo.py — per-bucket MVO orchestrator.

Slices the universe by FactorBucket, calls solve_mvo() once per bucket,
and aggregates the results into a single TAAResult. UNASSIGNED tickers
are skipped (and listed in `ignored_tickers` for the UI to display).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Protocol

import numpy as np
import pandas as pd

from stock_engine.sandbox.taa_module.mvo_core import MVOResult, solve_mvo
from stock_engine.sandbox.taa_module.types import FactorBucket, MiniUniverse

Pick = Literal["max_sharpe", "gmv", "target"]


class ReturnsProvider(Protocol):
    def get_returns(self, tickers: List[str]) -> pd.DataFrame: ...


@dataclass
class BucketSolution:
    """Per-bucket payload: what the optimiser produced + which weights
    are currently being shown (depends on `pick`)."""
    bucket:        FactorBucket
    tickers:       List[str]
    weights:       Dict[str, float]      # the ones picked (sum=1, by ticker)
    pick:          Pick
    target_return_used: Optional[float]
    mvo_result:    MVOResult              # full record (for diagnostics)
    note:          str = ""               # e.g. "single asset", "ill-conditioned"


@dataclass
class TAAResult:
    mode: Literal["passthrough", "factor"]
    intra_bucket_weights: Dict[FactorBucket, Dict[str, float]] = field(default_factory=dict)
    bucket_solutions:     Dict[FactorBucket, BucketSolution]   = field(default_factory=dict)
    ignored_tickers:      List[str] = field(default_factory=list)   # UNASSIGNED bucket
    rf:                   float = 0.04
    pick:                 Pick = "max_sharpe"

    # ticker → {bucket: beta}; populated when compute_factor_exposures=True
    factor_exposures: Dict[str, Dict[FactorBucket, float]] = field(default_factory=dict)

    # ── Convenience for UI ───────────────────────────────────────────
    def buckets_used(self) -> List[FactorBucket]:
        return [b for b, w in self.intra_bucket_weights.items() if w]


# ── Orchestrator ───────────────────────────────────────────────────────────────

_FACTOR_ORDER = [FactorBucket.GROWTH, FactorBucket.FIN_COND,
                 FactorBucket.INFLATION, FactorBucket.DIVERSIFIER]


def _compute_factor_exposures(
    universe: MiniUniverse,
    provider: ReturnsProvider,
) -> Dict[str, Dict[FactorBucket, float]]:
    """For each ticker, regress its daily returns on the equal-weighted
    return series of each populated bucket. The bucket the ticker belongs
    to should come back with the highest beta; cross-bucket betas show
    spillover.

    Skips empty buckets. Single-asset bucket → that ticker's "self-beta"
    is 1.0 by construction.
    """
    all_tks = universe.tickers
    if not all_tks:
        return {}

    rets = provider.get_returns(all_tks)
    if rets.empty:
        return {}

    # Bucket factor returns: equal-weighted mean inside the bucket.
    factor_rets: Dict[FactorBucket, pd.Series] = {}
    for b in _FACTOR_ORDER:
        tks = universe.by_bucket(b)
        if tks:
            present = [t for t in tks if t in rets.columns]
            if present:
                factor_rets[b] = rets[present].mean(axis=1)

    if not factor_rets:
        return {}

    factor_keys = list(factor_rets.keys())
    X = np.column_stack([factor_rets[b].values for b in factor_keys])
    X1 = np.column_stack([np.ones(len(X)), X])

    out: Dict[str, Dict[FactorBucket, float]] = {}
    for tk in all_tks:
        if tk not in rets.columns:
            out[tk] = {b: 0.0 for b in _FACTOR_ORDER}
            continue
        y = rets[tk].values
        try:
            beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
            betas = beta[1:]                      # drop intercept
        except Exception:
            betas = np.zeros(len(factor_keys))
        # All four canonical buckets; un-populated ones get 0
        out[tk] = {b: 0.0 for b in _FACTOR_ORDER}
        for b, v in zip(factor_keys, betas):
            out[tk][b] = float(v)
    return out


def compute_factor_mvo(
    universe: MiniUniverse,
    provider: ReturnsProvider,
    rf: float = 0.04,
    pick: Pick = "max_sharpe",
    target_return: Optional[float] = None,
    target_return_per_bucket: Optional[Dict[FactorBucket, float]] = None,
    with_diagnostics: bool = False,
    with_diagnostics_for_all_buckets: bool = False,
    compute_factor_exposures: bool = False,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> TAAResult:
    """
    Run MVO inside every populated bucket.

    Parameters
    ----------
    pick                       which of the three portfolios feeds the
                                 intra_bucket_weights dict ('max_sharpe' /
                                 'gmv' / 'target').
    target_return              global target (annualised) for *all* buckets;
                                 ignored if `target_return_per_bucket` is given.
    target_return_per_bucket   per-bucket override (recommended; defaults
                                 to median(μ) inside each bucket if pick=='target'
                                 and no override is given).
    with_diagnostics           pass-through flag — only flip on the bucket
                                 whose expander is open in the UI.
    """
    target_return_per_bucket = dict(target_return_per_bucket or {})

    intra: Dict[FactorBucket, Dict[str, float]] = {}
    sols:  Dict[FactorBucket, BucketSolution]   = {}
    ignored: List[str] = []

    diag_flag = with_diagnostics or with_diagnostics_for_all_buckets

    for bucket in _FACTOR_ORDER:
        orig_tks = universe.by_bucket(bucket)
        if not orig_tks:
            continue

        rets = provider.get_returns(orig_tks)

        # Keep only tickers that came back with data; skip bucket if none remain.
        if rets.empty:
            ignored.extend(orig_tks)
            continue
        available = [t for t in orig_tks if t in rets.columns]
        missing   = [t for t in orig_tks if t not in rets.columns]
        if missing:
            ignored.extend(missing)
        if not available:
            continue
        tks  = available
        rets = rets[tks].dropna()          # aligned rows only

        if len(rets) < 2:                  # need ≥ 2 observations for cov
            ignored.extend(tks)
            continue

        # Decide the per-bucket target
        if pick == "target":
            tgt = target_return_per_bucket.get(bucket)
            if tgt is None:
                tgt = (target_return
                       if target_return is not None
                       else float(np.median(rets.mean().values * 252)))
        else:
            tgt = None

        if rets.empty or rets.shape[1] == 0 or len(rets) < 2:
            ignored.extend(tks)
            continue

        try:
            result = solve_mvo(
                rets, rf=rf, target_return=tgt,
                with_diagnostics=diag_flag,
                min_weight=min_weight,
                max_weight=max_weight,
            )
        except Exception:
            ignored.extend(tks)
            continue

        # Degenerate result: solver had no data (shouldn't reach here normally)
        if len(result.tickers) == 0:
            ignored.extend(tks)
            continue

        # Pick weights to surface
        if pick == "max_sharpe":
            w_arr = result.weights_max_sharpe
        elif pick == "gmv":
            w_arr = result.weights_gmv
        else:  # target
            w_arr = (result.weights_target
                     if result.weights_target is not None
                     else result.weights_max_sharpe)
            if result.weights_target is None:
                # fallback note will be in result.warnings already
                pass

        weights = {t: float(w) for t, w in zip(tks, w_arr)}
        intra[bucket] = weights

        note = ""
        if len(tks) == 1:
            note = "single-asset bucket"
        elif any("ill-conditioned" in w for w in result.warnings):
            note = "ill-conditioned cov → equal weight"

        sols[bucket] = BucketSolution(
            bucket=bucket, tickers=tks, weights=weights,
            pick=pick,
            target_return_used=result.target_return_used,
            mvo_result=result, note=note,
        )

    # UNASSIGNED in factor mode is dropped; merge with tickers skipped for no-data
    ignored += universe.by_bucket(FactorBucket.UNASSIGNED)

    exposures: Dict[str, Dict[FactorBucket, float]] = {}
    if compute_factor_exposures:
        exposures = _compute_factor_exposures(universe, provider)

    return TAAResult(
        mode="factor",
        intra_bucket_weights=intra,
        bucket_solutions=sols,
        ignored_tickers=ignored,
        rf=rf, pick=pick,
        factor_exposures=exposures,
    )


def passthrough_result(universe: MiniUniverse, rf: float = 0.04) -> TAAResult:
    """No-op TAA: returns an empty intra-bucket dict so the equal-weight
    helper falls through to global 1/N."""
    return TAAResult(
        mode="passthrough",
        intra_bucket_weights={},
        bucket_solutions={},
        ignored_tickers=[],
        rf=rf, pick="max_sharpe",
    )
