"""
equal_weight.py — Allocation-page equal-weight rule under TAA.

Rules (from the spec):
  • passthrough  → w_i = 1/N for every ticker in the universe
  • factor       → bucket-equal × intra-bucket MVO weights
                   w_i = (1/k) × w_i^MVO_in_bucket   ; k = non-empty buckets

Manual weights are NOT touched by TAA — that's the caller's responsibility.

REBALANCE ORDER (important for callers):
  This function consumes a *given* TAAResult; it does NOT recompute the
  factor MVO. That decoupling is intentional. On every rebalance date the
  caller MUST first re-run compute_factor_mvo() with returns up to that
  date, then call apply_equal_weights_v2(universe, fresh_taa). Use
  rebalance.rebalance_at() for the canonical wrapper.
"""
from __future__ import annotations

from typing import Dict

from stock_engine.sandbox.taa_module.factor_mvo import TAAResult
from stock_engine.sandbox.taa_module.types import FactorBucket, MiniUniverse


def apply_equal_weights_v2(
    universe: MiniUniverse,
    taa: TAAResult,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> Dict[str, float]:
    """Return {ticker: weight} according to the active TAA mode.

    min_weight / max_weight are applied as portfolio-level fractions (0–1).
    Within each bucket, any asset floored to min_weight is renormalized so
    the bucket still sums to its inter-bucket share.

    Output sums to 1.0 (modulo float error). UNASSIGNED tickers in factor
    mode are excluded — the caller may re-add them as cash if they want.
    """
    if taa.mode == "passthrough":
        tickers = universe.tickers
        if not tickers:
            return {}
        n = len(tickers)
        # Apply bounds then renormalize
        raw = {t: 1.0 / n for t in tickers}
        return _apply_bounds(raw, min_weight, max_weight)

    # factor mode
    intra = taa.intra_bucket_weights
    non_empty = [b for b, w in intra.items() if w]
    if not non_empty:
        return {}

    k = len(non_empty)
    inter = 1.0 / k
    out: Dict[str, float] = {}
    for bucket in non_empty:
        bucket_weights = intra[bucket]
        if not bucket_weights:
            continue
        n_b = len(bucket_weights)
        # Effective per-asset bounds within this bucket's share (inter = 1/k)
        eff_min = min(min_weight, inter / n_b) if n_b > 0 else 0.0
        eff_max = max_weight
        # Floor + cap within bucket (intra weights sum to ~1 within bucket)
        w_raw = {t: float(w) for t, w in bucket_weights.items()}
        w_bounded = _apply_bounds(w_raw, eff_min / inter, eff_max / inter)
        for ticker, w_in in w_bounded.items():
            out[ticker] = inter * w_in
    return out


def _apply_bounds(weights: Dict[str, float],
                  min_w: float, max_w: float) -> Dict[str, float]:
    """Floor + cap a weight dict so every asset is in [min_w, max_w] and sum=1.

    Simple renorm-after-clip fails because it can push floored assets back
    below the minimum. Instead we iterate: identify assets pinned at the
    floor or cap, then rescale the remaining free assets to fill the budget
    left after the pinned share. Converges in at most n passes.
    """
    if not weights:
        return {}
    n = len(weights)
    eff_min = min(min_w, 1.0 / n)          # feasibility: n × min ≤ 1
    eff_max = max(max_w, eff_min)

    w = {t: max(eff_min, min(eff_max, v)) for t, v in weights.items()}

    for _ in range(n + 2):
        total = sum(w.values())
        if abs(total - 1.0) < 1e-9:
            break

        # Assets pinned at the floor or cap are "fixed"; scale only the rest.
        fixed = {t for t, v in w.items()
                 if v <= eff_min + 1e-10 or v >= eff_max - 1e-10}
        free  = [t for t in w if t not in fixed]

        if not free:
            # Constraints infeasible — equal weight clipped to bounds
            eq = 1.0 / n
            return {t: max(eff_min, min(eff_max, eq)) for t in weights}

        fixed_sum = sum(w[t] for t in fixed)
        free_sum  = sum(w[t] for t in free)
        remaining = 1.0 - fixed_sum

        if free_sum <= 0:
            break

        scale = remaining / free_sum
        for t in free:
            w[t] = max(eff_min, min(eff_max, w[t] * scale))

    total = sum(w.values())
    if total <= 0:
        return {t: 1.0 / n for t in weights}
    return {t: v / total for t, v in w.items()}


def explain_equal_weight_rule(taa: TAAResult, universe: MiniUniverse) -> str:
    """Human-readable line for the EW page caption."""
    if taa.mode == "passthrough":
        n = len(universe.tickers)
        return f"TAA = Passthrough · equal weight all stocks (1/{n} each)"
    k = len(taa.buckets_used())
    return (f"TAA = Factor MVO · equal weight across {k} bucket(s) "
            f"× MVO within each bucket ({taa.pick})")
