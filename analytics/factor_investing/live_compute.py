"""
analytics/factor_investing/live_compute.py — Real-time factor Q-spread from daily price data.

Downloads 3 years of daily close prices for S&P 500 constituents via yfinance,
computes monthly factor characteristics, performs equal-weighted quintile sorts,
and returns per-factor Q-spread (Q5 - Q1) monthly return series.

Computable factors (price data only):
  MOM       : 12-1 month cumulative return, skip most recent month
  HL1M      : prior 1-month return (short-term reversal signal)
  Beta      : 252-day rolling CAPM beta vs SPY
  AnnVol12M : 252-day rolling annualized daily volatility
  LogMktCap : log(close * shares_outstanding); shares fetched once via fast_info

Non-computable without fundamental data (BP, LTGC) — caller should supplement
those from the Fama-French live_loader or skip them.
"""
from __future__ import annotations

import math
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import numpy as np
import pandas as pd

from stock_engine.analytics.factor_investing.types import CORE_FACTORS

# ── Constants ──────────────────────────────────────────────────────────────────

PRICE_COMPUTABLE: set[str] = {"MOM", "HL1M", "Beta", "AnnVol12M", "LogMktCap"}

_BETA_WINDOW   = 252   # trading days for rolling beta
_VOL_WINDOW    = 252   # trading days for rolling volatility
_HISTORY_YEARS = 3     # years of daily price history to download

_WINSOR_LO, _WINSOR_HI = 0.01, 0.99
_MIN_STOCKS = 20       # min valid stocks per quintile sort date


# ── S&P 500 universe ───────────────────────────────────────────────────────────

_SP500_FALLBACK: list[str] = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "BRK-B",
    "JPM", "LLY", "UNH", "XOM", "V", "MA", "HD", "PG", "COST", "ABBV", "CVX", "MRK",
    "BAC", "CRM", "NFLX", "WMT", "KO", "PEP", "TMO", "ACN", "MCD", "CSCO", "ADBE",
    "ABT", "TXN", "ORCL", "PM", "NEE", "IBM", "QCOM", "AMD", "LIN", "DHR", "AMGN",
    "CAT", "INTU", "HON", "SPGI", "RTX", "AMAT", "GS", "BLK", "BKNG", "MS", "ISRG",
    "VRTX", "SYK", "AXP", "SCHW", "T", "PLD", "ELV", "NOW", "ETN", "GILD", "ADI",
    "MMC", "LRCX", "PANW", "MU", "DE", "C", "CB", "CI", "REGN", "BSX", "KLAC",
    "SO", "DUK", "MCO", "PH", "MDLZ", "SHW", "WM", "CME", "ICE", "ZTS", "USB",
    "CL", "CDNS", "MSI", "SNPS", "NOC", "WBA", "GD", "ITW", "TGT", "EMR", "CARR",
]


def fetch_sp500_tickers() -> list[str]:
    """Return S&P 500 ticker list from Wikipedia; falls back to a hardcoded subset."""
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"},
        )
        tickers = tables[0]["Symbol"].str.strip().str.replace(".", "-", regex=False).tolist()
        if len(tickers) > 400:
            return tickers
    except Exception as exc:
        warnings.warn(
            f"Could not fetch S&P 500 from Wikipedia ({exc}); using 100-stock fallback.",
            UserWarning,
            stacklevel=2,
        )
    return _SP500_FALLBACK


# ── Shares outstanding (for LogMktCap) ────────────────────────────────────────

def _fetch_shares_outstanding(
    tickers: list[str],
    max_workers: int = 20,
) -> dict[str, float]:
    """Fetch current shares outstanding via yfinance fast_info (parallel)."""
    try:
        import yfinance as yf
    except ImportError:
        return {}

    def _get(ticker: str) -> tuple[str, float]:
        try:
            fi = yf.Ticker(ticker).fast_info
            shares = getattr(fi, "shares", None) or getattr(fi, "shares_outstanding", None)
            if shares and shares > 0:
                return ticker, float(shares)
        except Exception:
            pass
        return ticker, float("nan")

    result: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_get, t): t for t in tickers}
        for fut in as_completed(futures):
            t, shares = fut.result()
            result[t] = shares

    valid = sum(1 for v in result.values() if not math.isnan(v))
    if valid < len(tickers) * 0.5:
        warnings.warn(
            f"Shares outstanding available for only {valid}/{len(tickers)} tickers; "
            "LogMktCap will use price as fallback rank for missing stocks.",
            UserWarning,
            stacklevel=2,
        )
    return result


# ── Core computation ───────────────────────────────────────────────────────────

def _winsorize(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile(_WINSOR_LO), s.quantile(_WINSOR_HI)
    return s.clip(lo, hi)


def _quintile_qspread(
    chars: pd.Series,
    next_month_ret: pd.Series,
) -> float:
    """Given factor characteristics and next-month returns, compute Q5-Q1 spread."""
    chars = _winsorize(chars.dropna())
    aligned = chars.align(next_month_ret.dropna(), join="inner")
    chars_a, ret_a = aligned[0], aligned[1]
    if len(chars_a) < _MIN_STOCKS:
        return float("nan")

    try:
        quintiles = pd.qcut(chars_a, 5, labels=False, duplicates="drop")
    except Exception:
        return float("nan")

    q5 = ret_a[quintiles == 4]
    q1 = ret_a[quintiles == 0]
    if q5.empty or q1.empty:
        return float("nan")

    return float(q5.mean() - q1.mean())


def compute_live_factors(
    factors: list[str] | None = None,
    start: str | None = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> dict[str, pd.Series]:
    """Download S&P 500 daily data and compute factor Q-spread series.

    Parameters
    ----------
    factors:
        Subset of PRICE_COMPUTABLE factors to compute. Defaults to all five.
    start:
        ISO date string for the start of the Q-spread output series.
        Input data always covers an additional 14 months before this date
        to allow factor lookback windows to warm up.
    progress_cb:
        Optional callable(message: str) called at key stages for UI feedback.

    Returns
    -------
    dict mapping factor_name -> pd.Series (month-end DatetimeIndex, decimal returns).
    Factors not in PRICE_COMPUTABLE are silently skipped.
    """
    try:
        import yfinance as yf
    except ImportError:
        warnings.warn("yfinance not installed; live compute unavailable.", UserWarning, stacklevel=2)
        return {}

    requested = [f for f in (factors or list(PRICE_COMPUTABLE)) if f in PRICE_COMPUTABLE]
    if not requested:
        return {}

    def _cb(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    # ── 1. Universe ────────────────────────────────────────────────────────────
    _cb("Fetching S&P 500 constituent list…")
    tickers = fetch_sp500_tickers()

    # ── 2. Download daily prices ───────────────────────────────────────────────
    data_start = pd.Timestamp(start or "1990-01-01") - pd.DateOffset(months=15)
    data_start_str = data_start.strftime("%Y-%m-%d")

    _cb(f"Downloading daily prices for {len(tickers)} stocks (3+ years)…")
    all_syms = tickers + ["SPY"]
    try:
        raw = yf.download(
            all_syms,
            start=data_start_str,
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        warnings.warn(f"yfinance download failed: {exc}", UserWarning, stacklevel=2)
        return {}

    # Normalise to a Close DataFrame
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            close = raw["Close"].copy()
        else:
            close = raw.iloc[:, 0].to_frame()  # fallback
    else:
        close = raw.copy()

    close = close.dropna(how="all")
    if close.empty or "SPY" not in close.columns:
        warnings.warn("Price data empty or SPY missing.", UserWarning, stacklevel=2)
        return {}

    # ── 3. Shares outstanding for LogMktCap ───────────────────────────────────
    shares_dict: dict[str, float] = {}
    if "LogMktCap" in requested:
        _cb(f"Fetching shares outstanding for {len(tickers)} tickers (parallel)…")
        shares_dict = _fetch_shares_outstanding(tickers)

    # ── 4. Compute factor characteristics (daily → resampled monthly) ──────────
    _cb("Computing factor characteristics…")
    spy_ret = close["SPY"].pct_change()
    var_spy = spy_ret.rolling(_BETA_WINDOW).var()

    stock_close = close.drop(columns=["SPY"], errors="ignore")
    daily_ret = stock_close.pct_change()

    # MOM and HL1M: use monthly prices
    monthly_close = stock_close.resample("ME").last()
    monthly_ret   = monthly_close.pct_change()

    # LogMktCap: daily close × shares
    log_mktcap_daily: Optional[pd.DataFrame] = None
    if "LogMktCap" in requested:
        shares_series = pd.Series({
            t: shares_dict.get(t, float("nan"))
            for t in stock_close.columns
        })
        valid_shares = shares_series.dropna()
        if not valid_shares.empty:
            log_mktcap_daily = np.log(
                stock_close[valid_shares.index].multiply(valid_shares, axis=1)
            )
        else:
            log_mktcap_daily = np.log(stock_close)  # price-only fallback

    # ── 5. Month-by-month quintile sort ──────────────────────────────────────
    _cb("Running monthly quintile sorts…")
    month_ends = monthly_ret.index
    output_start = pd.Timestamp(start or "1990-01-01")

    qspread_records: dict[str, list[tuple[pd.Timestamp, float]]] = {f: [] for f in requested}

    for i, t in enumerate(month_ends[:-1]):
        t_next = month_ends[i + 1]

        # Only collect output from the requested start date
        if t_next < output_start:
            continue

        # Next month returns (used as holding period return for all factors)
        ret_next = monthly_ret.loc[t_next].dropna()
        if ret_next.empty:
            continue

        # ── MOM: cumulative return months t-12 to t-2 ────────────────────────
        if "MOM" in requested and i >= 12:
            t_12 = month_ends[i - 11]   # 12 months ago
            t_2  = month_ends[i - 1]    # 2 months ago  (skip last month)
            with_start = monthly_close.loc[t_12:t_2]
            if len(with_start) >= 2:
                mom_chars = (monthly_close.loc[t_2] / monthly_close.loc[t_12] - 1)
                qspread_records["MOM"].append((t_next, _quintile_qspread(mom_chars, ret_next)))

        # ── HL1M: prior month return ─────────────────────────────────────────
        if "HL1M" in requested and i >= 1:
            hl1m_chars = monthly_ret.loc[t].dropna()
            qspread_records["HL1M"].append((t_next, _quintile_qspread(hl1m_chars, ret_next)))

        # ── AnnVol12M: annualized 252-day daily vol as of month-end t ────────
        if "AnnVol12M" in requested:
            vol_start  = t - pd.offsets.BDay(_VOL_WINDOW)
            daily_to_t = daily_ret.loc[vol_start:t]
            if len(daily_to_t) >= 60:
                vol_chars = daily_to_t.std() * math.sqrt(252)
                qspread_records["AnnVol12M"].append((t_next, _quintile_qspread(vol_chars, ret_next)))

        # ── Beta: 252-day rolling OLS beta vs SPY as of month-end t ─────────
        if "Beta" in requested:
            beta_start = t - pd.offsets.BDay(_BETA_WINDOW)
            daily_to_t = daily_ret.loc[beta_start:t]
            spy_to_t   = spy_ret.loc[beta_start:t]
            if len(daily_to_t) >= 60:
                spy_var = float(spy_to_t.var(ddof=1))
                if spy_var > 0:
                    cov_with_spy = daily_to_t.apply(
                        lambda col: col.cov(spy_to_t.reindex(col.index))
                    )
                    beta_chars = cov_with_spy / spy_var
                    qspread_records["Beta"].append((t_next, _quintile_qspread(beta_chars, ret_next)))

        # ── LogMktCap: log market cap as of month-end t ─────────────────────
        if "LogMktCap" in requested and log_mktcap_daily is not None:
            lmc_snap = log_mktcap_daily.asof(t)
            if isinstance(lmc_snap, pd.Series):
                qspread_records["LogMktCap"].append((t_next, _quintile_qspread(lmc_snap, ret_next)))

    # ── 6. Assemble results ────────────────────────────────────────────────────
    _cb("Assembling factor series…")
    result: dict[str, pd.Series] = {}
    for factor, records in qspread_records.items():
        if not records:
            continue
        dates, vals = zip(*records)
        s = pd.Series(vals, index=pd.DatetimeIndex(dates), name=factor, dtype=float).dropna()
        if not s.empty:
            result[factor] = s

    _cb(f"Done. Computed {len(result)} factor Q-spread series.")
    return result
