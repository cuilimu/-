"""
analytics/profiler.py — Portfolio Evaluation Profiler: pure computation functions.

All functions are stateless (input → output, no side effects).
No data fetching — all inputs derived from existing BacktestResult.

Modules:
  A — Core Return Metrics
  B — Cost & Tax Adjustments
  C — Leverage Scenario
  D — Measure Selection Logic
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from stock_engine.backtest.base import BacktestResult
from stock_engine.data.yfinance_provider import normalize_datetime_index
from stock_engine.portfolio.models import ScheduledTransaction


# ── Module A — Core Return Metrics ────────────────────────────────────────────

def holding_period_return(p_begin: float, p_end: float, income: float = 0.0) -> float:
    """HPR = (P_end - P_begin + Income) / P_begin"""
    if p_begin == 0:
        return 0.0
    return (p_end - p_begin + income) / p_begin


def arithmetic_mean_return(periodic_returns: list[float]) -> float:
    """Simple unweighted average of sub-period returns.

    Input: list of per-period returns, e.g. monthly [0.03, -0.01, 0.02, ...]
    NOT cumulative, NOT annualized — raw periodic values.
    Requires at least 2 observations; returns 0.0 otherwise.
    """
    if not periodic_returns or len(periodic_returns) < 2:
        return 0.0
    return sum(periodic_returns) / len(periodic_returns)


def geometric_mean_return(periodic_returns: list[float]) -> float:
    """Chain-linked compound return per period: [(1+R1)(1+R2)...(1+Rn)]^(1/n) - 1

    Input: same sub-period returns as arithmetic_mean_return.
    Do NOT pre-add 1 — this function adds 1 internally.
    Requires at least 2 observations; returns 0.0 otherwise.
    """
    if not periodic_returns or len(periodic_returns) < 2:
        return 0.0
    product = 1.0
    for r in periodic_returns:
        product *= (1.0 + r)
        if product <= 0:
            return -1.0
    return product ** (1.0 / len(periodic_returns)) - 1


def annualized_return(total_return: float, n_days: int) -> Optional[float]:
    """(1 + R_total)^(252/n_days) - 1
    Returns None if n_days < 252 -- never annualize short periods."""
    if n_days < 252:
        return None
    if 1 + total_return <= 0:
        return None
    return (1 + total_return) ** (252 / n_days) - 1


def time_weighted_return(
    nav_series: pd.Series,
    cash_flows: list[ScheduledTransaction],
) -> float:
    """Chain-link HPRs between each external cash flow.
    If no executed cash flows: TWR = total HPR of NAV series."""
    if nav_series.empty or len(nav_series) < 2:
        return 0.0

    executed = [cf for cf in cash_flows if getattr(cf, "is_executed", False) and not cf.error]

    if not executed:
        return holding_period_return(nav_series.iloc[0], nav_series.iloc[-1])

    nav = nav_series.sort_index()
    sorted_flows = sorted(executed, key=lambda x: x.actual_date or x.date)

    # Build sub-period breakpoints from cash-flow dates
    breakpoints: list[pd.Timestamp] = []
    for cf in sorted_flows:
        dt = pd.Timestamp(cf.actual_date or cf.date)
        idx = nav.index.searchsorted(dt)
        if 0 < idx < len(nav):
            breakpoints.append(nav.index[idx])

    breakpoints = sorted(set(breakpoints))
    dates = [nav.index[0]] + breakpoints + [nav.index[-1]]

    sub_period_hprs: list[float] = []
    for i in range(len(dates) - 1):
        t0, t1 = dates[i], dates[i + 1]
        if t0 >= t1:
            continue
        sub = nav.loc[t0:t1]
        if len(sub) < 2:
            continue
        sub_period_hprs.append(holding_period_return(sub.iloc[0], sub.iloc[-1]))

    if not sub_period_hprs:
        return holding_period_return(nav.iloc[0], nav.iloc[-1])

    return math.prod(1 + r for r in sub_period_hprs) - 1


def money_weighted_return(
    cash_flows: list[ScheduledTransaction],
    final_nav: float,
    initial_capital: float,
) -> float:
    """Solve IRR: sum[CF_t / (1+r)^t] = 0  (annual periods).
    Uses scipy.optimize.brentq. Returns 0.0 if solve fails."""
    executed = [cf for cf in cash_flows if getattr(cf, "is_executed", False) and not cf.error]
    if not executed:
        return 0.0

    ref_date = pd.Timestamp(min(cf.actual_date or cf.date for cf in executed))
    end_date  = pd.Timestamp(max(cf.actual_date or cf.date for cf in executed))

    # (t_years, signed_cash_flow) -- outflows negative, inflows positive
    flows: list[tuple[float, float]] = [(0.0, -initial_capital)]

    for cf in executed:
        dt = pd.Timestamp(cf.actual_date or cf.date)
        t  = (dt - ref_date).days / 365.25
        if cf.is_buy():
            flows.append((t, -(cf.executed_value or 0.0)))
        else:
            flows.append((t, cf.executed_value or 0.0))

    # Terminal NAV as inflow
    t_end = max((end_date - ref_date).days / 365.25 + 1e-6, 1e-6)
    flows.append((t_end, final_nav))

    def npv(r: float) -> float:
        if r <= -1:
            return float("inf")
        return sum(cf / (1 + r) ** t for t, cf in flows)

    try:
        return float(brentq(npv, -0.9999, 100.0, maxiter=1000))
    except (ValueError, RuntimeError):
        return 0.0


def arith_geo_spread(arith: float, geo: float) -> float:
    """Delta = Arith - Geo ~= sigma^2/2 -- proxy for realized volatility."""
    return arith - geo


# ── Helpers ───────────────────────────────────────────────────────────────────

def nav_series_from_result(result: BacktestResult) -> pd.Series:
    """Extract NAV pd.Series (DatetimeIndex -> float) from BacktestResult.snapshots.
    Always returns tz-naive index so comparisons with plain Timestamps never raise
    'Cannot compare tz-naive and tz-aware datetime-like objects'.
    """
    if not result.snapshots:
        return pd.Series(dtype=float)
    nav = pd.Series(
        {s.timestamp: s.nav for s in result.snapshots},
        name="nav",
    ).sort_index()
    return normalize_datetime_index(nav)


def daily_returns_from_result(result: BacktestResult) -> list[float]:
    """Daily pct-change returns derived from NAV series.

    Uses nav.pct_change() -- NOT snapshot.daily_return, which is sparse
    and causes arith == geo when fewer than 2 non-None values are present.
    """
    nav = nav_series_from_result(result)
    if len(nav) < 2:
        return []
    return nav.pct_change().dropna().tolist()


def slice_returns_for_window(nav: pd.Series, window: str) -> list[float]:
    """Slice NAV to a trailing window then return daily pct-change list.

    window: '1Y' | '3Y' | '5Y' | 'full'
    Returns [] if the sliced window has fewer than 2 observations.
    """
    if nav.empty:
        return []
    end = nav.index[-1]
    if window == "1Y":
        start = end - pd.DateOffset(years=1)
    elif window == "3Y":
        start = end - pd.DateOffset(years=3)
    elif window == "5Y":
        start = end - pd.DateOffset(years=5)
    else:
        return nav.pct_change().dropna().tolist()
    sliced = nav[nav.index >= start]
    if len(sliced) < 2:
        return []
    return sliced.pct_change().dropna().tolist()


def slice_nav_to_window(nav: pd.Series, window: str) -> pd.Series:
    """Slice NAV Series to a trailing window. window: '1Y' | '3Y' | '5Y' | 'full'."""
    if window == "full" or nav.empty:
        return nav
    years = {"1Y": 1, "3Y": 3, "5Y": 5}.get(window)
    if years is None:
        return nav
    cutoff = nav.index[-1] - pd.DateOffset(years=years)
    return nav[nav.index >= cutoff]


def per_year_daily_returns(nav: pd.Series) -> dict[str, list[float]]:
    """Per-calendar-year lists of daily pct-change returns.

    Each value is a list suitable for arithmetic_mean_return / geometric_mean_return.
    Having n_daily > 1 per year is what makes arith != geo (Jensen's inequality).
    """
    if nav.empty:
        return {}
    out: dict[str, list[float]] = {}
    for year, group in nav.groupby(nav.index.year):
        if len(group) >= 2:
            out[str(year)] = group.pct_change().dropna().tolist()
    return out


def per_year_returns(nav: pd.Series) -> dict[str, float]:
    """Total HPR for each calendar year (display labels only)."""
    if nav.empty:
        return {}
    out: dict[str, float] = {}
    for year, group in nav.groupby(nav.index.year):
        if len(group) >= 2:
            out[str(year)] = holding_period_return(group.iloc[0], group.iloc[-1])
    return out

# ── Monthly return utilities (for Arith/Geo chart) ────────────────────────────

def get_monthly_returns(nav_series: pd.Series) -> pd.Series:
    """Resample NAV to month-end, compute pct_change.

    Returns pd.Series of monthly returns with tz-naive DatetimeIndex.
    Always strips timezone before resampling.
    """
    nav = normalize_datetime_index(nav_series.copy())
    monthly_nav = nav.resample("ME").last()
    return monthly_nav.pct_change().dropna()


def annualize_arithmetic(monthly_mean: float) -> float:
    """Arithmetic mean annualized by simple scaling: R_annual = R_monthly × 12.

    Never compound arithmetic mean — it is a forward-looking single-period
    estimate and simple scaling is the CFA-standard correct approach.
    """
    return monthly_mean * 12


def annualize_geometric(monthly_mean: float) -> float:
    """Geometric mean annualized by compounding: R_annual = (1 + R_monthly)^12 − 1.

    Compounding is correct here because geometric mean already accounts for
    the path of returns (chain-linking).
    """
    return (1.0 + monthly_mean) ** 12 - 1.0


# ── Module B — Cost & Tax Adjustments ─────────────────────────────────────────

@dataclass
class CostAssumptions:
    slippage_bps: float        = 7.5
    mgmt_fee_annual_pct: float = 0.0
    inclusion_rate: float      = 0.50
    marginal_tax_rate: float   = 0.33
    dividend_tax_rate: float   = 0.15
    inflation_rate: float      = 0.025
    tax_scenario: str          = "canada"


PRESETS: dict[str, CostAssumptions] = {
    "canada": CostAssumptions(
        inclusion_rate=0.50, marginal_tax_rate=0.33,
        dividend_tax_rate=0.15, tax_scenario="canada",
    ),
    "usa": CostAssumptions(
        inclusion_rate=1.00, marginal_tax_rate=0.20,
        dividend_tax_rate=0.15, tax_scenario="usa",
    ),
    "exempt": CostAssumptions(
        inclusion_rate=0.00, marginal_tax_rate=0.00,
        dividend_tax_rate=0.00, tax_scenario="exempt",
    ),
}


def apply_slippage(
    gross_return: float,
    n_trades: int,
    avg_position_size: float,
    slippage_bps: float,
) -> float:
    """Deduct slippage drag: drag = n_trades x bps/10000 x avg_weight."""
    drag = n_trades * (slippage_bps / 10_000) * avg_position_size
    return gross_return - drag


def apply_mgmt_fee(gross_return: float, n_years: float, fee_pct: float) -> float:
    """Compound annual fee drag over backtest period.
    after_fee = (1 + gross) x (1 - fee/100)^n_years - 1"""
    if fee_pct == 0.0 or n_years == 0.0:
        return gross_return
    return (1 + gross_return) * ((1 - fee_pct / 100) ** n_years) - 1


def apply_tax_drag(
    gross_return: float,
    dividends: float,
    cost: CostAssumptions,
) -> float:
    """Capital gains + dividend withholding drag."""
    cap_gains_drag = gross_return * cost.inclusion_rate * cost.marginal_tax_rate
    div_drag       = dividends * cost.dividend_tax_rate
    return gross_return - cap_gains_drag - div_drag


def real_return(nominal_return: float, inflation_rate: float) -> float:
    """Fisher equation: (1+nominal)/(1+inflation) - 1"""
    return (1 + nominal_return) / (1 + inflation_rate) - 1


def cost_waterfall(
    gross_return: float,
    cost: CostAssumptions,
    n_trades: int,
    n_years: float,
    dividends: float,
    avg_position_size: float = 1.0,
) -> OrderedDict:
    """Ordered step-by-step return deductions."""
    after_slippage = apply_slippage(gross_return, n_trades, avg_position_size, cost.slippage_bps)
    after_fees     = apply_mgmt_fee(after_slippage, n_years, cost.mgmt_fee_annual_pct)
    after_tax      = apply_tax_drag(after_fees, dividends, cost)
    real_net       = real_return(after_tax, cost.inflation_rate)

    od: OrderedDict = OrderedDict()
    od["gross"]          = gross_return
    od["after_slippage"] = after_slippage
    od["after_fees"]     = after_fees
    od["after_tax"]      = after_tax
    od["real_net"]       = real_net
    return od


# ── Module C — Leverage Scenario ──────────────────────────────────────────────

def leveraged_return(
    r_portfolio: float,
    leverage_ratio: float,
    borrowing_rate: float,
) -> float:
    """R_lev = R_port + (D/E) x (R_port - R_borrow)  where D/E = leverage_ratio - 1."""
    de = leverage_ratio - 1.0
    return r_portfolio + de * (r_portfolio - borrowing_rate)


def leverage_scenarios(
    base_cagr: float,
    base_drawdown: float,
    borrowing_rate: float,
    ratios: list[float] | None = None,
) -> list[dict]:
    """One scenario dict per leverage ratio."""
    if ratios is None:
        ratios = [1.0, 1.5, 2.0, 3.0]
    scenarios: list[dict] = []
    for ratio in ratios:
        lev_cagr  = leveraged_return(base_cagr, ratio, borrowing_rate)
        dd_amp    = base_drawdown * ratio          # amplified (more negative)
        mc_thresh = -1.0 / ratio                   # equity -> 0
        scenarios.append({
            "ratio":                  ratio,
            "leveraged_cagr":         lev_cagr,
            "max_drawdown_amplified": dd_amp,
            "margin_call_threshold":  mc_thresh,
            "warning":                ratio > 2.0,
        })
    return scenarios


# ── Module D — Measure Selection Logic ────────────────────────────────────────

def _detect_outliers(returns: list[float], sigma: float = 3.0) -> bool:
    if len(returns) < 10:
        return False
    arr  = np.array(returns, dtype=float)
    std  = arr.std()
    if std == 0:
        return False
    return bool(np.any(np.abs(arr - arr.mean()) > sigma * std))


def select_primary_measure(
    result: BacktestResult,
    transactions: list[ScheduledTransaction],
) -> dict:
    """
    Decision tree:
    1. External cash flows present? -> TWR + MWR
    2. Multi-period compounding?    -> Geometric / CAGR
    3. Outliers detected?           -> flag trimmed mean
    4. Default                      -> Arithmetic Mean
    """
    daily_rets = daily_returns_from_result(result)
    nav        = nav_series_from_result(result)
    n_days     = int((nav.index[-1] - nav.index[0]).days) if len(nav) > 1 else 0

    executed_flows      = [t for t in transactions if getattr(t, "is_executed", False) and not t.error]
    cash_flows_detected = len(executed_flows) > 0
    outliers_detected   = _detect_outliers(daily_rets)
    multi_period        = n_days >= 252

    if cash_flows_detected:
        primary = "TWR+MWR"
        reason  = (
            "External cash flows detected -- both TWR and MWR are shown. "
            "TWR isolates investment skill; MWR reflects your actual timing."
        )
    elif multi_period:
        primary = "geometric"
        reason  = (
            "Multi-period compounding (>=1 year). "
            "Geometric mean / CAGR avoids arithmetic upward bias over time."
        )
    elif outliers_detected:
        primary = "arithmetic"
        reason  = (
            "Outliers detected (|HPR| > 3sigma). "
            "Arithmetic mean is used; consider a trimmed mean for robustness."
        )
    else:
        primary = "arithmetic"
        reason  = "Short period (<1 year). Arithmetic mean is appropriate for single-period estimates."

    return {
        "primary_measure":      primary,
        "reason":               reason,
        "cash_flows_detected":  cash_flows_detected,
        "outliers_detected":    outliers_detected,
        "n_cash_flows":         len(executed_flows),
        "n_days":               n_days,
        "multi_period":         multi_period,
    }


# ── Aggregate ProfilerResult ──────────────────────────────────────────────────

@dataclass
class ProfilerResult:
    """All computed metrics for one BacktestResult + CostAssumptions."""
    # Period metadata
    n_days:   int
    n_years:  float
    n_trades: int
    start_date: str
    end_date:   str

    # Core returns (daily-level)
    hpr:              float           # total holding-period return
    hpr_short:        bool            # True if period < 1 year
    arith_mean_daily: float
    geo_mean_daily:   float
    spread:           float           # arith - geo

    # Annualized
    cagr_gross: Optional[float]       # None if < 1 year

    # TWR / MWR
    twr:               float
    mwr:               float
    timing_effect_bps: float          # (MWR - TWR) x 10 000

    # Cost waterfall
    waterfall:     OrderedDict
    cagr_net_real: Optional[float]    # annualized real net

    # Measure selection
    measure_selection: dict

    # Drawdown (for leverage scenarios)
    base_drawdown: float

    # Per-year total HPR (display labels)
    year_returns: dict[str, float] = field(default_factory=dict)

    # Per-year arithmetic / geometric means of daily returns (Arith/Geo chart).
    # Computed from per-year daily return lists -- n > 1 per year makes arith != geo.
    year_arith: dict[str, float] = field(default_factory=dict)
    year_geo:   dict[str, float] = field(default_factory=dict)

    # NAV series (for TWR/MWR equity curve; stored as dict for pickling)
    nav_dict: dict = field(default_factory=dict)


def compute_profiler(
    result: BacktestResult,
    transactions: list[ScheduledTransaction],
    cost: CostAssumptions,
) -> ProfilerResult:
    """Run all profiler modules and return a ProfilerResult.
    Pure: no session_state access, no side effects."""
    nav        = nav_series_from_result(result)
    daily_rets = daily_returns_from_result(result)

    if nav.empty or len(nav) < 2:
        raise ValueError("Insufficient NAV data for profiler (need >=2 snapshots).")

    n_days  = max(int((nav.index[-1] - nav.index[0]).days), 1)
    n_years = n_days / 365.25

    # n_trades: prefer executed scheduled transactions, fall back to Transaction log
    executed_txns = [t for t in transactions if getattr(t, "is_executed", False) and not t.error]
    n_trades = len(executed_txns) if executed_txns else len(result.transactions)

    # Average position weight (rough: equal weight across tickers)
    avg_weight = 1.0 / max(len(result.tickers), 1)

    # ── Module A ──────────────────────────────────────────────────────────────
    hpr        = holding_period_return(nav.iloc[0], nav.iloc[-1])
    hpr_short  = n_days < 252
    arith_mean = arithmetic_mean_return(daily_rets)
    geo_mean   = geometric_mean_return(daily_rets)
    spread     = arith_geo_spread(arith_mean, geo_mean)
    cagr_gross = annualized_return(hpr, n_days)

    twr = time_weighted_return(nav, transactions)
    mwr = money_weighted_return(transactions, float(nav.iloc[-1]), result.initial_capital)
    timing_bps = (mwr - twr) * 10_000

    # Drawdown
    running_max   = nav.cummax()
    dd_series     = (nav - running_max) / running_max
    base_drawdown = float(dd_series.min())

    # ── Module B ──────────────────────────────────────────────────────────────
    # Dividends: not yet tracked at position level; reserved for future extraction
    dividends = 0.0  # TODO P2: sum realized dividends from closed_positions

    wf = cost_waterfall(
        gross_return=hpr,
        cost=cost,
        n_trades=n_trades,
        n_years=n_years,
        dividends=dividends,
        avg_position_size=avg_weight,
    )
    cagr_net_real = annualized_return(wf["real_net"], n_days)

    # ── Module D ──────────────────────────────────────────────────────────────
    measure_sel = select_primary_measure(result, transactions)

    # Per-year data for Arith/Geo bar chart.
    # Use MONTHLY returns per year → annualize each mean.
    # Monthly granularity gives meaningful Arith−Geo spread (Jensen's inequality).
    year_rets        = per_year_returns(nav)
    monthly_rets     = get_monthly_returns(nav)
    year_arith_map: dict[str, float] = {}
    year_geo_map:   dict[str, float] = {}
    for year, group in monthly_rets.groupby(monthly_rets.index.year):
        yr_list = group.tolist()
        if len(yr_list) >= 2:
            year_arith_map[str(year)] = annualize_arithmetic(arithmetic_mean_return(yr_list))
            year_geo_map[str(year)]   = annualize_geometric(geometric_mean_return(yr_list))

    return ProfilerResult(
        n_days=n_days,
        n_years=n_years,
        n_trades=n_trades,
        start_date=str(nav.index[0].date()),
        end_date=str(nav.index[-1].date()),
        hpr=hpr,
        hpr_short=hpr_short,
        arith_mean_daily=arith_mean,
        geo_mean_daily=geo_mean,
        spread=spread,
        cagr_gross=cagr_gross,
        twr=twr,
        mwr=mwr,
        timing_effect_bps=timing_bps,
        waterfall=wf,
        cagr_net_real=cagr_net_real,
        measure_selection=measure_sel,
        base_drawdown=base_drawdown,
        year_returns=year_rets,
        year_arith=year_arith_map,
        year_geo=year_geo_map,
        nav_dict={str(k): v for k, v in nav.items()},
    )


# ── Self-test ─────────────────────────────────────────────────────────────────

def _test_mean_calculations() -> None:
    """Verify arith != geo on a known series (Jensen's inequality).
    Expected: arith=4.40%, geo~4.22%
    Raises AssertionError on failure -- run with STOCK_ENGINE_DEBUG=1.
    """
    test_returns = [0.10, -0.05, 0.08, -0.03, 0.12]
    arith = arithmetic_mean_return(test_returns)
    geo   = geometric_mean_return(test_returns)
    assert abs(arith - 0.044) < 0.001,  f"Arithmetic mean wrong: {arith:.6f} (expected ~0.044)"
    assert abs(geo   - 0.0422) < 0.001, f"Geometric mean wrong:  {geo:.6f} (expected ~0.0422)"
    