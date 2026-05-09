"""
analytics/factor_regression.py
Legacy module — kept for backward compatibility.
New code should import from  stock_engine.analytics.factor  instead.

OLS factor regression using statsmodels.
Excess return = asset_return - rf ~ const + selected_factors.
Alpha reported in monthly % (coef x 100).
"""
# ruff: noqa

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.data.factor_data_provider import FactorDataProvider
from stock_engine.data.yfinance_provider import YFinanceProvider
from stock_engine.exceptions import AnalyticsError

FACTOR_DISPLAY = {
    "mktrf": "Mkt-RF",
    "smb":   "SMB",
    "hml":   "HML",
    "rmw":   "RMW",
    "cma":   "CMA",
    "umd":   "UMD",
}
ALL_FACTORS = list(FACTOR_DISPLAY.keys())


@dataclass
class RegressionResult:
    ticker: str
    alpha: float               # monthly %, coef x 100
    t_alpha: float
    p_alpha: float
    betas: dict                # {factor_name: beta}
    t_stats: dict              # {factor_name: t_stat}
    p_values: dict             # {factor_name: p_value}
    conf_intervals: dict       # {factor_name: (lower, upper)}
    n_obs: int
    r_squared: float
    adj_r_squared: float
    f_statistic: float
    f_pvalue: float
    log_likelihood: float
    aic: float
    bic: float
    df_residuals: int
    df_model: int
    omnibus: float
    prob_omnibus: float
    skew: float
    kurtosis: float
    durbin_watson: float
    jarque_bera: float
    prob_jb: float
    cond_no: float
    significant_alpha: bool    # alpha > 0 AND t_alpha > 2
    error: Optional[str] = None  # set if regression failed / insufficient data


def run_regression(
    returns: pd.Series,
    factors: pd.DataFrame,
    selected_factors: list[str],
) -> RegressionResult:
    """OLS: excess_return ~ const + selected_factors."""
    try:
        import statsmodels.api as sm
        from statsmodels.stats.stattools import durbin_watson, omni_normtest
        from scipy import stats as scipy_stats
    except ImportError as e:
        raise AnalyticsError("statsmodels not installed") from e

    df = pd.concat([returns.rename("ret"), factors], axis=1).dropna()

    if len(df) < 12:
        return _empty_result(returns.name or "?", "Insufficient data (< 12 observations)")

    excess = df["ret"] - df["rf"]
    X = sm.add_constant(df[selected_factors])
    model = sm.OLS(excess, X).fit()

    params  = model.params
    tvalues = model.tvalues
    pvalues = model.pvalues
    conf    = model.conf_int()

    alpha_pct = float(params["const"]) * 100
    betas  = {f: float(params[f])   for f in selected_factors if f in params}
    tstats = {f: float(tvalues[f])  for f in selected_factors if f in tvalues}
    pvals  = {f: float(pvalues[f])  for f in selected_factors if f in pvalues}
    cis    = {f: (float(conf.loc[f, 0]), float(conf.loc[f, 1]))
              for f in selected_factors if f in conf.index}

    resid = model.resid
    dw    = float(durbin_watson(resid))

    try:
        omni_stat, omni_p = omni_normtest(resid)
    except Exception:
        omni_stat, omni_p = float("nan"), float("nan")

    try:
        jb_result = scipy_stats.jarque_bera(resid)
        jb_stat_val = float(jb_result[0])
        jb_p_val    = float(jb_result[1])
        skew_val    = float(resid.skew())
        kurt_val    = float(resid.kurtosis() + 3)
    except Exception:
        jb_stat_val = jb_p_val = skew_val = kurt_val = float("nan")

    try:
        cond_no = float(model.condition_number)
    except Exception:
        cond_no = float("nan")

    return RegressionResult(
        ticker          = str(returns.name or "?"),
        alpha           = alpha_pct,
        t_alpha         = float(tvalues["const"]),
        p_alpha         = float(pvalues["const"]),
        betas           = betas,
        t_stats         = tstats,
        p_values        = pvals,
        conf_intervals  = cis,
        n_obs           = int(model.nobs),
        r_squared       = float(model.rsquared),
        adj_r_squared   = float(model.rsquared_adj),
        f_statistic     = float(model.fvalue) if model.fvalue else float("nan"),
        f_pvalue        = float(model.f_pvalue) if model.f_pvalue else float("nan"),
        log_likelihood  = float(model.llf),
        aic             = float(model.aic),
        bic             = float(model.bic),
        df_residuals    = int(model.df_resid),
        df_model        = int(model.df_model),
        omnibus         = float(omni_stat),
        prob_omnibus    = float(omni_p),
        skew            = skew_val,
        kurtosis        = kurt_val,
        durbin_watson   = dw,
        jarque_bera     = jb_stat_val,
        prob_jb         = jb_p_val,
        cond_no         = cond_no,
        significant_alpha = (alpha_pct > 0 and float(tvalues["const"]) > 2),
    )


def run_regressions_for_result(
    result: BacktestResult,
    selected_factors: list[str],
    reg_start: str,
    reg_end: str,
    config: Config,
) -> list[RegressionResult]:
    """Run regressions for all tickers in a BacktestResult."""
    factor_prov = FactorDataProvider(config)
    asset_prov  = YFinanceProvider(config)
    price_col   = config.price_field.lower()

    try:
        factors = factor_prov.fetch(reg_start, reg_end)
    except Exception as exc:
        raise AnalyticsError(f"Factor data unavailable: {exc}") from exc

    results: list[RegressionResult] = []
    for ticker in result.tickers:
        try:
            fetch_end = (pd.Timestamp(reg_end) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            df = asset_prov.fetch_historical(ticker, reg_start, fetch_end, frequency="1d")
            col = price_col if price_col in df.columns else "close"
            monthly = df[col].resample("ME").last().dropna()
            monthly_ret = monthly.pct_change().dropna()
            monthly_ret.name = ticker
            monthly_ret.index = monthly_ret.index.to_period("M").to_timestamp("M")
            results.append(run_regression(monthly_ret, factors, selected_factors))
        except Exception as exc:
            results.append(_empty_result(ticker, str(exc)))

    return results


# -- NEW: Portfolio-level regression ------------------------------------------

def compute_portfolio_returns(
    result: BacktestResult,
    frequency: str = "monthly",
) -> pd.Series:
    """
    Derives portfolio-level returns from BacktestResult NAV series.
    NAV is already value-weighted -- no additional weighting needed.

    Steps:
    1. Extract daily NAV from result.snapshots
    2. Resample to month-end using last()
    3. Compute pct_change() and drop first NaN
    4. Return pd.Series with name='Portfolio'
    """
    if not result.snapshots:
        raise AnalyticsError("No snapshots in BacktestResult -- run backtest first.")

    nav = pd.Series(
        {s.timestamp: s.nav for s in result.snapshots}
    ).sort_index()

    monthly_nav = nav.resample("ME").last().dropna()
    monthly_ret = monthly_nav.pct_change().dropna()
    monthly_ret.index = monthly_ret.index.to_period("M").to_timestamp("M")
    monthly_ret.name = "Portfolio"
    return monthly_ret


def run_portfolio_regression(
    result: BacktestResult,
    selected_factors: list[str],
    reg_start: str,
    reg_end: str,
    config: Config,
) -> RegressionResult:
    """
    Portfolio-level OLS regression.
    Derives returns from NAV series (zero new price fetching).
    Calls run_regression() with identical signature to individual ticker path.
    """
    if not result.snapshots:
        return _empty_result("Portfolio", "No snapshots -- run backtest first.")

    factor_prov = FactorDataProvider(config)
    try:
        factors = factor_prov.fetch(reg_start, reg_end)
    except Exception as exc:
        return _empty_result("Portfolio", f"Factor data unavailable: {exc}")

    try:
        port_returns = compute_portfolio_returns(result)
    except Exception as exc:
        return _empty_result("Portfolio", f"NAV extraction failed: {exc}")

    return run_regression(port_returns, factors, selected_factors)


# -- Helpers ------------------------------------------------------------------

def _empty_result(ticker: str, error: str) -> RegressionResult:
    return RegressionResult(
        ticker=ticker, alpha=0.0, t_alpha=0.0, p_alpha=1.0,
        betas={}, t_stats={}, p_values={}, conf_intervals={},
        n_obs=0, r_squared=0.0, adj_r_squared=0.0,
        f_statistic=0.0, f_pvalue=1.0, log_likelihood=0.0,
        aic=0.0, bic=0.0, df_residuals=0, df_model=0,
        omnibus=0.0, prob_omnibus=1.0, skew=0.0, kurtosis=0.0,
        durbin_watson=0.0, jarque_bera=0.0, prob_jb=1.0,
        cond_no=0.0, significant_alpha=False, error=error,
    )


def format_full_report(
    reg: RegressionResult,
    reg_start: str,
    reg_end: str,
    header_note: str = "",
) -> str:
    """
    Formats a statsmodels-style text report for st.code() display.
    header_note: optional extra line below the title (composition info for portfolio).
    """
    sig_note = "  ** significant alpha" if reg.significant_alpha else ""

    lines = ["=" * 60, f"OLS Regression -- {reg.ticker}  {reg_start} to {reg_end}"]
    if header_note:
        lines.append(header_note)
    lines += [
        "=" * 60,
        f"{'Dep. Variable:':<24} Excess Return    {'R-squared:':<16} {reg.r_squared:.3f}",
        f"{'No. Observations:':<24} {reg.n_obs:<17}{'Adj. R-squared:':<16} {reg.adj_r_squared:.3f}",
        f"{'F-statistic:':<24} {reg.f_statistic:<17.3f}{'Prob(F-stat):':<16} {reg.f_pvalue:.3f}",
        f"{'Log-Likelihood:':<24} {reg.log_likelihood:<17.3f}{'AIC:':<16} {reg.aic:.3f}",
        f"{'Df Residuals:':<24} {reg.df_residuals:<17}{'BIC:':<16} {reg.bic:.3f}",
        f"{'Df Model:':<24} {reg.df_model}",
        "-" * 60,
        f"{'':>12} {'coef':>10} {'std err':>10} {'t':>8} {'P>|t|':>8} {'[0.025':>8} {'0.975]':>8}",
        "-" * 60,
    ]

    ci_lo, ci_hi = reg.conf_intervals.get("const", (float("nan"), float("nan")))
    std_err_alpha = reg.alpha / reg.t_alpha / 100 if reg.t_alpha != 0 else float("nan")
    alpha_label = "const" + ("**" if reg.significant_alpha else "  ")
    lines.append(
        f"{alpha_label:>12} {reg.alpha/100:>10.4f} {std_err_alpha:>10.4f} "
        f"{reg.t_alpha:>8.3f} {reg.p_alpha:>8.3f} "
        f"{ci_lo:>8.3f} {ci_hi:>8.3f}{sig_note}"
    )

    for f, beta in reg.betas.items():
        t  = reg.t_stats.get(f, float("nan"))
        p  = reg.p_values.get(f, float("nan"))
        ci = reg.conf_intervals.get(f, (float("nan"), float("nan")))
        se = abs(beta / t) if t != 0 else float("nan")
        lines.append(
            f"{FACTOR_DISPLAY.get(f, f):>12} {beta:>10.4f} {se:>10.4f} "
            f"{t:>8.3f} {p:>8.3f} "
            f"{ci[0]:>8.3f} {ci[1]:>8.3f}"
        )

    lines += [
        "-" * 60,
        f"{'Omnibus:':<24} {reg.omnibus:<12.3f} {'Durbin-Watson:':<16} {reg.durbin_watson:.3f}",
        f"{'Prob(Omnibus):':<24} {reg.prob_omnibus:<12.3f} {'Jarque-Bera:':<16} {reg.jarque_bera:.3f}",
        f"{'Skew:':<24} {reg.skew:<12.3f} {'Prob(JB):':<16} {reg.prob_jb:.3f}",
        f"{'Kurtosis:':<24} {reg.kurtosis:<12.3f} {'Cond. No.:':<16} {reg.cond_no:.1f}",
        "=" * 60,
    ]
    return "\n".join(lines)
