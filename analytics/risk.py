"""
analytics/risk.py — Market risk metrics for PortfolioCandidate.
Computes VaR, CVaR, drawdown analysis, stress testing, and tracking error.
All functions are stateless. No imports from ui/.
# ML_EXTENSIBLE: compute_var() can dispatch to analytics/ml/ for ML-based VaR.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from stock_engine.portfolio.models import RiskResult

STRESS_SCENARIOS = [
    {"name": "2008 GFC",         "start": "2008-09-01", "end": "2009-03-31"},
    {"name": "2020 COVID Crash",  "start": "2020-02-01", "end": "2020-03-31"},
    {"name": "2022 Rate Shock",   "start": "2022-01-01", "end": "2022-10-31"},
    {"name": "2000 Dot-com",      "start": "2000-03-01", "end": "2002-10-31"},
]
TOP_N_DRAWDOWNS = 5

def compute_risk(
    returns: pd.Series,
    weights: Dict[str, float],
    constituent_returns: Optional[pd.DataFrame] = None,
    benchmark_returns: Optional[pd.Series] = None,
    factor_betas: Optional[Dict[str, float]] = None,
    factor_r2: Optional[float] = None,
) -> RiskResult:
    result = RiskResult()
    if returns.empty or len(returns) < 10:
        return result
    result.annualised_vol = float(returns.std() * np.sqrt(252))
    result.var_95_param,  result.cvar_95_param  = _var_cvar_parametric(returns, 0.95)
    result.var_99_param,  result.cvar_99_param  = _var_cvar_parametric(returns, 0.99)
    result.var_95_hist,   result.cvar_95_hist   = _var_cvar_historical(returns, 0.95)
    result.var_99_hist,   result.cvar_99_hist   = _var_cvar_historical(returns, 0.99)
    dd_series = _drawdown_series(returns)
    result.max_drawdown = float(dd_series.min())
    trough_idx = dd_series.idxmin()
    cum = (1 + returns).cumprod()
    peak_idx = cum.loc[:trough_idx].idxmax()
    result.max_drawdown_start = peak_idx.date() if hasattr(peak_idx, "date") else None
    result.max_drawdown_end   = trough_idx.date() if hasattr(trough_idx, "date") else None
    post_trough = cum.loc[trough_idx:]
    peak_val = float(cum.loc[peak_idx])
    recovered = post_trough[post_trough >= peak_val]
    if not recovered.empty:
        result.max_drawdown_recovery = (recovered.index[0] - trough_idx).days
    result.drawdown_events = _top_n_drawdowns(returns, n=TOP_N_DRAWDOWNS)
    ann_ret = float((1 + returns).prod() ** (252 / len(returns)) - 1)
    if result.max_drawdown and result.max_drawdown != 0:
        result.calmar_ratio = ann_ret / abs(result.max_drawdown)
    if benchmark_returns is not None:
        aligned = returns.align(benchmark_returns, join="inner")
        active = aligned[0] - aligned[1]
        result.tracking_error = float(active.std() * np.sqrt(252))
        if result.tracking_error > 0:
            result.information_ratio = float(active.mean() * 252) / result.tracking_error
    if constituent_returns is not None:
        result.stress_results = _stress_test(weights, constituent_returns, benchmark_returns)
    if factor_betas:
        result.factor_betas = factor_betas
    if factor_r2 is not None:
        result.factor_r2 = factor_r2
    return result

def _var_cvar_parametric(returns: pd.Series, confidence: float) -> Tuple[float, float]:
    from scipy.stats import norm
    mu, sig = float(returns.mean()), float(returns.std())
    alpha = 1 - confidence
    var  = float(norm.ppf(alpha, loc=mu, scale=sig))
    cvar = float(mu - sig * norm.pdf(norm.ppf(alpha)) / alpha)
    return var, cvar

def _var_cvar_historical(returns: pd.Series, confidence: float) -> Tuple[float, float]:
    alpha = 1 - confidence
    var  = float(returns.quantile(alpha))
    cvar = float(returns[returns <= var].mean())
    return var, cvar

def _drawdown_series(returns: pd.Series) -> pd.Series:
    cum = (1 + returns).cumprod()
    return (cum - cum.cummax()) / cum.cummax()

def _top_n_drawdowns(returns: pd.Series, n: int = 5) -> List[Dict]:
    cum = (1 + returns).cumprod()
    dd  = _drawdown_series(returns)
    events, used_dates = [], set()
    for trough_idx in dd.sort_values().index.tolist():
        if len(events) >= n:
            break
        if trough_idx in used_dates:
            continue
        depth = float(dd.loc[trough_idx])
        if depth >= -0.03:
            continue
        peak_idx = cum.loc[:trough_idx].idxmax()
        post = cum.loc[trough_idx:]
        peak_val = float(cum.loc[peak_idx])
        recovered = post[post >= peak_val]
        recovery_end = recovered.index[0] if not recovered.empty else None
        recovery_days = (recovery_end - trough_idx).days if recovery_end else None
        end_mark = recovery_end or returns.index[-1]
        for d in pd.date_range(peak_idx, end_mark, freq="D"):
            used_dates.add(d)
        events.append({
            "period": f"{peak_idx.strftime('%b %Y')} – {trough_idx.strftime('%b %Y')}",
            "peak_date": peak_idx.date(), "trough_date": trough_idx.date(),
            "depth": depth, "recovery_days": recovery_days,
        })
    return sorted(events, key=lambda e: e["depth"])

def _stress_test(weights, constituent_returns, benchmark_returns=None):
    results = []
    for sc in STRESS_SCENARIOS:
        window = constituent_returns.loc[sc["start"]:sc["end"]]
        if window.empty:
            results.append({"scenario_name": sc["name"], "period": f"{sc['start']} – {sc['end']}",
                            "portfolio_return": None, "bm_return": None, "excess_return": None, "per_asset": {}})
            continue
        per_asset, port_return = {}, 0.0
        for ticker, w in weights.items():
            if ticker in window.columns:
                r = float((1 + window[ticker]).prod() - 1)
                per_asset[ticker] = r
                port_return += w * r
        bm_return = None
        if benchmark_returns is not None:
            bw = benchmark_returns.loc[sc["start"]:sc["end"]]
            if not bw.empty:
                bm_return = float((1 + bw).prod() - 1)
        excess = (port_return - bm_return) if bm_return is not None else None
        results.append({"scenario_name": sc["name"], "period": f"{sc['start']} – {sc['end']}",
                        "portfolio_return": port_return, "bm_return": bm_return,
                        "excess_return": excess, "per_asset": per_asset})
    return results
