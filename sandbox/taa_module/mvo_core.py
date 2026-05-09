"""
mvo_core.py — Markowitz Mean-Variance Optimisation kernel.

Pure function: takes a returns DataFrame, returns weights + diagnostics.
No IO, no plotting, no session state. Mirrors the reference notebook
(Sections 2-6) one-to-one:
  • annualised mu, cov from daily returns (× 252 by default)
  • SLSQP, long-only, sum(w)=1
  • three portfolios: max-Sharpe, GMV, target-return
  • Monte-Carlo Dirichlet sampling and efficient frontier scan
    are gated by `with_diagnostics` so the fast path (just three weights)
    stays cheap when the UI hasn't asked for the chart yet.

Numerical guards added on top of the reference:
  • ill-conditioned cov (cond > 1e8) → fall back to in-bucket equal weight
  • single-asset bucket → trivial weights, no SLSQP call (caller must check)
  • SLSQP failure on max-Sharpe / GMV → equal weight + warning in result
  • target-return outside attainable range → res.weights_target = None
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd
import scipy.optimize as sco

TRADING = 252
_COND_LIMIT = 1e8
_FAST_NMC = 5000
_FAST_NFRONT = 60


@dataclass
class MVOResult:
    """All artefacts produced by one solve_mvo() call.

    `weights_*` are length-N numpy arrays aligned with `tickers`.
    Diagnostic arrays (mc_*, frontier_*) are populated only when
    with_diagnostics=True; otherwise None.
    """
    tickers: List[str]
    mu:      np.ndarray              # annualised expected return, shape (N,)
    cov:     np.ndarray              # annualised covariance,      shape (N,N)
    rf:      float

    weights_max_sharpe: np.ndarray
    weights_gmv:        np.ndarray
    weights_target:     Optional[np.ndarray] = None

    mc_returns:    Optional[np.ndarray] = None
    mc_vols:       Optional[np.ndarray] = None
    mc_sharpes:    Optional[np.ndarray] = None
    frontier_vols: Optional[np.ndarray] = None
    frontier_rets: Optional[np.ndarray] = None

    target_return_used: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    # ── Convenience: per-portfolio scalar metrics ───────────────────────
    def stats(self, w: np.ndarray) -> dict:
        ret = float(w @ self.mu)
        vol = float(np.sqrt(w @ self.cov @ w))
        sr  = (ret - self.rf) / vol if vol > 0 else float("nan")
        return {"return": ret, "vol": vol, "sharpe": sr}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cov_is_well_conditioned(cov: np.ndarray) -> bool:
    try:
        return float(np.linalg.cond(cov)) < _COND_LIMIT
    except Exception:
        return False


def _equal_weight(n: int) -> np.ndarray:
    return np.ones(n) / n


# ── Public entry ───────────────────────────────────────────────────────────────

def solve_mvo(
    returns: pd.DataFrame,
    rf: float = 0.04,
    trading: int = TRADING,
    target_return: Optional[float] = None,
    with_diagnostics: bool = False,
    n_mc: int = _FAST_NMC,
    n_frontier: int = _FAST_NFRONT,
    seed: int = 42,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> MVOResult:
    """
    Solve max-Sharpe / GMV / (optional) target-return on a returns panel.

    Parameters
    ----------
    returns          T × N daily returns (sign convention: +0.01 = +1 %)
    rf               annualised risk-free rate (decimal)
    trading          trading days per year (default 252)
    target_return    if given, also solve min-variance s.t. wᵀμ = target
    with_diagnostics if True, also run Monte-Carlo (n_mc) + efficient
                     frontier scan (n_frontier). Slower; UI calls this
                     only when an expander is opened.
    min_weight       lower bound per asset (0–1); clamped to 1/n if needed
                     so the problem stays feasible.
    max_weight       upper bound per asset (0–1); must be ≥ effective min.

    Returns MVOResult.
    """
    tickers = list(returns.columns)
    n = len(tickers)

    if n == 0 or returns.empty or len(returns) < 2:
        return MVOResult(
            tickers=tickers, mu=np.array([]), cov=np.zeros((0, 0)), rf=rf,
            weights_max_sharpe=np.array([]), weights_gmv=np.array([]),
            warnings=["no usable returns data for this bucket"],
        )
    if n == 1:
        w1 = np.array([1.0])
        mu  = (returns.mean().values * trading).astype(float)
        cov = (returns.cov().values  * trading).astype(float)
        return MVOResult(
            tickers=tickers, mu=mu, cov=cov, rf=rf,
            weights_max_sharpe=w1, weights_gmv=w1,
            weights_target=None,
            warnings=["single-asset bucket: trivial weights"],
        )

    # ── Annualised statistics ──────────────────────────────────────────
    mu  = (returns.mean().values * trading).astype(float)
    cov = (returns.cov().values  * trading).astype(float)

    warnings: List[str] = []
    if not _cov_is_well_conditioned(cov):
        warnings.append(f"covariance is ill-conditioned (cond > {_COND_LIMIT:.0e}); "
                        "falling back to in-bucket equal weight")
        ew = _equal_weight(n)
        return MVOResult(
            tickers=tickers, mu=mu, cov=cov, rf=rf,
            weights_max_sharpe=ew, weights_gmv=ew, weights_target=None,
            warnings=warnings,
        )

    # ── Weight bounds — keep feasible: n × min_w ≤ 1 ──────────────────
    eff_min = min(float(min_weight), 1.0 / n)
    eff_max = max(float(max_weight), eff_min)
    if eff_min < min_weight - 1e-9:
        warnings.append(
            f"min_weight clamped {min_weight:.0%} → {eff_min:.1%} "
            f"(feasibility: {n} assets)"
        )

    # ── Optimisation primitives ────────────────────────────────────────
    def port_return(w): return w @ mu
    def port_vol(w):    return float(np.sqrt(w @ cov @ w))
    def neg_sharpe(w):
        v = port_vol(w)
        return -(port_return(w) - rf) / v if v > 0 else 1e6

    sum_constraint = {"type": "eq", "fun": lambda w: w.sum() - 1}
    bounds = [(eff_min, eff_max)] * n
    # Warm-start within bounds, then normalize
    w0 = np.clip(_equal_weight(n), eff_min, eff_max)
    w0 = w0 / w0.sum()

    # ── ① Max Sharpe ───────────────────────────────────────────────────
    res_s = sco.minimize(
        neg_sharpe, w0, method="SLSQP",
        bounds=bounds, constraints=sum_constraint,
        options={"ftol": 1e-9, "maxiter": 200},
    )
    if res_s.success:
        w_sharpe = res_s.x
    else:
        warnings.append(f"max-Sharpe solver failed: {res_s.message}; using EW")
        w_sharpe = w0

    # ── ② Global Min Variance ──────────────────────────────────────────
    res_g = sco.minimize(
        port_vol, w0, method="SLSQP",
        bounds=bounds, constraints=sum_constraint,
        options={"ftol": 1e-9, "maxiter": 200},
    )
    if res_g.success:
        w_gmv = res_g.x
    else:
        warnings.append(f"GMV solver failed: {res_g.message}; using EW")
        w_gmv = w0

    # ── ③ Target return (optional) ─────────────────────────────────────
    w_target: Optional[np.ndarray] = None
    target_used: Optional[float] = None
    if target_return is not None:
        # Feasibility: target must lie between min(mu) and max(mu) (long-only).
        lo, hi = float(mu.min()), float(mu.max())
        if not (lo - 1e-9 <= target_return <= hi + 1e-9):
            warnings.append(
                f"target_return={target_return:.4f} outside attainable "
                f"[{lo:.4f}, {hi:.4f}] — skipped"
            )
        else:
            res_t = sco.minimize(
                port_vol, w0, method="SLSQP",
                bounds=bounds,
                constraints=[
                    sum_constraint,
                    {"type": "eq",
                     "fun": lambda w, t=target_return: port_return(w) - t},
                ],
                options={"ftol": 1e-9, "maxiter": 200},
            )
            if res_t.success:
                w_target = res_t.x
                target_used = float(target_return)
            else:
                warnings.append(f"target-return solver failed: {res_t.message}")

    # ── Diagnostics (lazy) ─────────────────────────────────────────────
    mc_ret = mc_vol = mc_sr = front_v = front_r = None
    if with_diagnostics:
        rng = np.random.default_rng(seed)
        raw = rng.dirichlet(np.ones(n), size=n_mc)        # N_MC × N
        # Project MC samples into the feasible [eff_min, eff_max] box.
        # Clip then renorm (2 passes) so the scatter cloud respects the same
        # bounds as the optimised portfolios shown on the chart.
        if eff_min > 0.0 or eff_max < 1.0:
            for _ in range(3):
                raw = np.clip(raw, eff_min, eff_max)
                s = raw.sum(axis=1, keepdims=True)
                raw = raw / np.where(s > 0, s, 1.0)
        mc_ret = raw @ mu
        # Vectorised vol: √diag(W Σ Wᵀ) = √Σ_j Σ_k w_ij Σ_jk w_ik
        mc_vol = np.sqrt(np.einsum("ij,jk,ik->i", raw, cov, raw))
        with np.errstate(divide="ignore", invalid="ignore"):
            mc_sr = np.where(mc_vol > 0, (mc_ret - rf) / mc_vol, 0.0)

        # Frontier: scan from GMV return up to 0.98 × max(mu)
        gmv_ret = float(port_return(w_gmv))
        targets = np.linspace(gmv_ret, mu.max() * 0.98, n_frontier)
        f_v, f_r = [], []
        for t in targets:
            try:
                rf_res = sco.minimize(
                    port_vol, w0, method="SLSQP", bounds=bounds,
                    constraints=[
                        sum_constraint,
                        {"type": "eq", "fun": lambda w, tt=t: port_return(w) - tt},
                    ],
                    options={"ftol": 1e-9, "maxiter": 200},
                )
                if rf_res.success:
                    f_v.append(port_vol(rf_res.x))
                    f_r.append(float(t))
            except Exception:
                continue
        front_v = np.asarray(f_v)
        front_r = np.asarray(f_r)

    return MVOResult(
        tickers=tickers, mu=mu, cov=cov, rf=rf,
        weights_max_sharpe=w_sharpe,
        weights_gmv=w_gmv,
        weights_target=w_target,
        mc_returns=mc_ret, mc_vols=mc_vol, mc_sharpes=mc_sr,
        frontier_vols=front_v, frontier_rets=front_r,
        target_return_used=target_used,
        warnings=warnings,
    )
