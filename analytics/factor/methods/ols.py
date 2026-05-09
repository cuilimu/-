"""analytics/factor/methods/ols.py — Standard OLS via statsmodels."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from stock_engine.analytics.factor.methods.base import AnalysisMethod, MethodResult


class OLSMethod(AnalysisMethod):
    name  = "ols"
    label = "OLS"

    def fit(self, y: pd.Series, X: pd.DataFrame, **kwargs) -> MethodResult:
        cov_type = kwargs.get("cov_type", "nonrobust")
        return _run(self.name, self.label, y, X, cov_type=cov_type)


class RobustOLSMethod(AnalysisMethod):
    name  = "robust"
    label = "OLS (HC3)"

    def fit(self, y: pd.Series, X: pd.DataFrame, **kwargs) -> MethodResult:
        return _run(self.name, self.label, y, X, cov_type="HC3")


def _run(method_name: str, label: str, y: pd.Series,
         X: pd.DataFrame, cov_type: str = "nonrobust") -> MethodResult:
    try:
        import statsmodels.api as sm
        from statsmodels.stats.stattools import durbin_watson
    except ImportError as e:
        return _err(method_name, y, X, "statsmodels not installed")

    try:
        df = pd.concat([y.rename("__y__"), X], axis=1).dropna()
        min_obs = max(8, X.shape[1] + 3)
        if len(df) < min_obs:
            return _err(method_name, y, X, f"Need ≥ {min_obs} observations, got {len(df)}")

        y_c  = df["__y__"]
        X_c  = sm.add_constant(df.drop(columns="__y__"), has_constant="add")
        mdl  = sm.OLS(y_c, X_c).fit(cov_type=cov_type)

        conf = mdl.conf_int()
        conf.columns = [0.025, 0.975]

        try:
            dw = float(durbin_watson(mdl.resid))
        except Exception:
            dw = float("nan")

        return MethodResult(
            method       = method_name,
            y_name       = str(y.name or "__y__"),
            x_names      = list(X.columns),
            coef         = mdl.params,
            std_err      = mdl.bse,
            t_stats      = mdl.tvalues,
            p_values     = mdl.pvalues,
            conf_int     = conf,
            residuals    = mdl.resid.rename("resid"),
            fitted       = mdl.fittedvalues.rename("fitted"),
            r_squared    = float(mdl.rsquared),
            adj_r_squared= float(mdl.rsquared_adj),
            n_obs        = int(mdl.nobs),
            metadata     = dict(
                aic=float(mdl.aic), bic=float(mdl.bic),
                f_stat=float(mdl.fvalue) if mdl.fvalue else float("nan"),
                f_pvalue=float(mdl.f_pvalue) if mdl.f_pvalue else float("nan"),
                durbin_watson=dw,
                cov_type=cov_type,
            ),
        )
    except Exception as exc:
        return _err(method_name, y, X, str(exc))


def _err(method_name: str, y: pd.Series, X: pd.DataFrame, msg: str) -> MethodResult:
    empty = pd.Series(dtype=float)
    return MethodResult(
        method=method_name, y_name=str(y.name or ""), x_names=list(X.columns),
        coef=empty, std_err=empty, t_stats=empty, p_values=empty,
        conf_int=pd.DataFrame(), residuals=empty, fitted=empty,
        r_squared=0.0, adj_r_squared=0.0, n_obs=0, error=msg,
    )
