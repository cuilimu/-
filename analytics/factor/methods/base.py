"""
analytics/factor/methods/base.py
Protocol and result dataclass shared by all analysis methods.
Adding a new method (Ridge, RF, etc.) = implement AnalysisMethod + register in __init__.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
import pandas as pd

@dataclass
class MethodResult:
    method: str                     # "ols", "robust", "ridge", ...
    y_name: str
    x_names: list[str]
    coef: pd.Series                 # index: ["const"] + x_names
    std_err: pd.Series
    t_stats: pd.Series
    p_values: pd.Series
    conf_int: pd.DataFrame          # columns [0.025, 0.975]
    residuals: pd.Series            # index = dates; use via  gen name = resid
    fitted: pd.Series
    r_squared: float
    adj_r_squared: float
    n_obs: int
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

class AnalysisMethod:
    """
    Base class (not Protocol, for easier subclassing).
    Subclasses override fit() and optionally format_output().
    """
    name: str = ""
    label: str = ""

    def fit(self, y: pd.Series, X: pd.DataFrame, **kwargs) -> MethodResult:
        raise NotImplementedError

    def format_output(self, result: MethodResult, cmd: str) -> str:
        """Return STATA-style text table."""
        if result.error:
            return f"error: {result.error}"
        lines = [
            "=" * 64,
            f". {cmd}",
            f"{'Method:':<20} {self.label:<20} {'N:':<8} {result.n_obs}",
            f"{'Dep. variable:':<20} {result.y_name:<20} {'R²:':<8} {result.r_squared:.4f}",
            f"{'':20} {'':20} {'Adj R²:':<8} {result.adj_r_squared:.4f}",
            "-" * 64,
            f"{'':>16} {'Coef':>10} {'Std Err':>10} {'t':>8} {'P>|t|':>8} {'[0.025':>8} {'0.975]':>8}",
            "-" * 64,
        ]
        for idx in result.coef.index:
            coef = result.coef[idx]
            se   = result.std_err.get(idx, float("nan"))
            t    = result.t_stats.get(idx, float("nan"))
            p    = result.p_values.get(idx, float("nan"))
            lo   = result.conf_int.loc[idx, 0.025] if idx in result.conf_int.index else float("nan")
            hi   = result.conf_int.loc[idx, 0.975] if idx in result.conf_int.index else float("nan")
            sig  = "**" if abs(t) > 2 else "  "
            lines.append(f"{str(idx):>16}{sig} {coef:>10.4f} {se:>10.4f} {t:>8.3f} {p:>8.3f} {lo:>8.4f} {hi:>8.4f}")
        lines += [
            "-" * 64,
            f"F-stat: {result.metadata.get('f_stat', float('nan')):.3f}   "
            f"Prob(F): {result.metadata.get('f_pvalue', float('nan')):.3f}   "
            f"AIC: {result.metadata.get('aic', float('nan')):.1f}   "
            f"BIC: {result.metadata.get('bic', float('nan')):.1f}",
            "=" * 64,
            f"Residuals saved — use  gen <name> = resid  to add to workspace",
        ]
        return "\n".join(lines)
