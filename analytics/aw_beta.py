"""
analytics/aw_beta.py -- All Weather factor beta estimator.

US tickers:
  Regress monthly returns on delta_gdp + delta_cpi (FRED).

Non-US tickers (suffix-detected: .HK .T .L .SS etc.):
  growth factor   = local market index monthly return (yfinance)
  inflation factor = delta_cpi_yoy from FRED (US CPI as global anchor)

Interface:
  compute_aw_betas(...) -> Dict[str, Tuple[float, float, float]]
      {ticker: (beta_growth, beta_inflation, r_squared)}

r_squared < R2_LOW_FIT flags the ticker as unreliable in the UI.
Fallback (hardcoded) used when FRED unavailable or < MIN_OBS obs.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

# ---- Constants ---------------------------------------------------------------
_MIN_OBS   = 12
R2_LOW_FIT = 0.05

# ---- Exchange suffix -> ISO country ------------------------------------------
_SUFFIX_COUNTRY: Dict[str, str] = {
    "HK":  "HK",  "T":   "JP",  "L":   "GB",
    "SS":  "CN",  "SZ":  "CN",  "PA":  "FR",
    "DE":  "DE",  "AX":  "AU",  "TO":  "CA",
    "AS":  "NL",  "MI":  "IT",  "MC":  "ES",
    "SW":  "CH",  "ST":  "SE",  "CO":  "DK",
    "OL":  "NO",  "HE":  "FI",  "KS":  "KR",
    "BO":  "IN",  "NS":  "IN",  "TW":  "TW",
    "TWO": "TW",  "BK":  "TH",  "SI":  "SG",
    "KL":  "MY",  "JK":  "ID",  "BA":  "AR",
    "MX":  "MX",  "BR":  "BR",  "SA":  "ZA",
}

# Country -> local broad market index (yfinance symbol)
_COUNTRY_INDEX: Dict[str, str] = {
    "HK": "^HSI",       "JP": "^N225",      "GB": "^FTSE",
    "CN": "000300.SS",  "FR": "^FCHI",      "DE": "^GDAXI",
    "AU": "^AXJO",      "CA": "^GSPTSE",    "NL": "^AEX",
    "IT": "FTSEMIB.MI", "ES": "^IBEX",      "CH": "^SSMI",
    "SE": "^OMX",       "KR": "^KS11",      "IN": "^BSESN",
    "TW": "^TWII",      "SG": "^STI",       "MY": "^KLSE",
    "TH": "^SET.BK",    "BR": "^BVSP",      "MX": "^MXX",
    "ZA": "^J203.JO",
}

# ---- Hardcoded fallback ------------------------------------------------------
_FALLBACK: Dict[str, Tuple[float, float, float]] = {
    "SPY":  ( 0.82, -0.52, 0.30), "QQQ":  ( 0.88, -0.62, 0.28),
    "VTI":  ( 0.78, -0.48, 0.29), "AAPL": ( 0.78, -0.62, 0.22),
    "MSFT": ( 0.73, -0.52, 0.20), "NVDA": ( 0.92, -0.72, 0.18),
    "AMZN": ( 0.68, -0.52, 0.19), "GOOGL": (0.76, -0.57, 0.21),
    "META": ( 0.70, -0.52, 0.18), "TSLA": ( 0.83, -0.42, 0.14),
    "AVGO": ( 0.78, -0.57, 0.20), "TSM":  ( 0.70, -0.52, 0.19),
    "GLD":  (-0.12,  0.78, 0.25), "IAU":  (-0.12,  0.76, 0.24),
    "GDX":  (-0.02,  0.73, 0.20), "USO":  ( 0.18,  0.82, 0.30),
    "DBO":  ( 0.13,  0.80, 0.28), "XLE":  ( 0.28,  0.72, 0.27),
    "PDBC": ( 0.08,  0.78, 0.25), "TIPS": (-0.42,  0.58, 0.22),
    "SCHP": (-0.47,  0.53, 0.21), "XLP":  (-0.52,  0.48, 0.18),
    "KO":   (-0.47,  0.38, 0.16), "PG":   (-0.52,  0.33, 0.15),
    "TLT":  (-0.78, -0.62, 0.35), "IEF":  (-0.73, -0.57, 0.33),
    "BND":  (-0.62, -0.52, 0.30), "LQD":  (-0.57, -0.42, 0.27),
    "AGG":  (-0.67, -0.52, 0.31), "SHY":  (-0.83, -0.72, 0.40),
    "VTIP": (-0.52,  0.18, 0.15), "XLF":  ( 0.53, -0.22, 0.20),
    "KBE":  ( 0.48, -0.17, 0.18), "VFH":  ( 0.50, -0.20, 0.19),
    "VNQ":  ( 0.28,  0.18, 0.14), "IYR":  ( 0.26,  0.20, 0.13),
    "DJP":  ( 0.08,  0.63, 0.22), "SOXX": ( 0.80, -0.54, 0.24),
    "MU":   ( 0.66, -0.42, 0.19),
}


# ---- Helpers -----------------------------------------------------------------

def _ticker_country(ticker: str) -> str:
    if "." not in ticker:
        return "US"
    suffix = ticker.rsplit(".", 1)[1].upper()
    return _SUFFIX_COUNTRY.get(suffix, "US")


def _ols_betas_r2(y: np.ndarray, X: np.ndarray) -> Tuple[float, float, float]:
    ones = np.ones((len(y), 1))
    A = np.hstack([ones, X])
    try:
        coefs, *_ = np.linalg.lstsq(A, y, rcond=None)
        y_hat  = A @ coefs
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
        return float(coefs[1]), float(coefs[2]), round(r2, 4)
    except Exception:
        return 0.0, 0.0, 0.0


def _fetch_macro_factors(fred_api_key: Optional[str]) -> Optional[pd.DataFrame]:
    try:
        from stock_engine.data.fred_fetcher import FredFetcher
        fetcher = FredFetcher(api_key=fred_api_key or None)
        hist = fetcher.history("2000-01-01")
        if hist.empty:
            return None
        return pd.DataFrame({
            "delta_gdp": hist["gdp_growth_qoq"].diff(),
            "delta_cpi": hist["cpi_yoy"].diff(),
        }).dropna()
    except Exception:
        return None


def _fetch_cpi_factor(fred_api_key: Optional[str]) -> Optional[pd.Series]:
    try:
        from stock_engine.data.fred_fetcher import FredFetcher
        fetcher = FredFetcher(api_key=fred_api_key or None)
        hist = fetcher.history("2000-01-01")
        if hist.empty:
            return None
        return hist["cpi_yoy"].diff().dropna().rename("delta_cpi")
    except Exception:
        return None


def _fetch_monthly_returns(
    ticker: str, start: str, end: str, provider
) -> Optional[pd.Series]:
    try:
        df = provider.fetch_historical(ticker, start, end, "1mo")
        col = "close" if "close" in df.columns else df.columns[0]
        prices = df[col].dropna()
        if len(prices) < _MIN_OBS + 1:
            return None
        return prices.pct_change().dropna()
    except Exception:
        return None


def _fetch_index_returns(
    index_ticker: str, start: str, end: str
) -> Optional[pd.Series]:
    try:
        import yfinance as yf
        df = yf.download(
            index_ticker, start=start, end=end,
            interval="1mo", auto_adjust=True, progress=False,
        )
        if df.empty or len(df) < _MIN_OBS + 1:
            return None
        prices = df["Close"].squeeze().dropna()
        return prices.pct_change().dropna().rename(index_ticker)
    except Exception:
        return None


def _align_monthly(
    rets: pd.Series, *factor_series: pd.Series
) -> Optional[pd.DataFrame]:
    def _to_me(s: pd.Series) -> pd.Series:
        s = s.copy()
        s.index = pd.to_datetime(s.index).to_period("M").to_timestamp("M")
        return s
    parts = [_to_me(rets).rename("r")] + [_to_me(s) for s in factor_series]
    aligned = pd.concat(parts, axis=1).dropna()
    return aligned if len(aligned) >= _MIN_OBS else None


# ---- Main entry point --------------------------------------------------------

def compute_aw_betas(
    tickers: list,
    fred_api_key: Optional[str],
    price_provider,
    start: str,
    end: str,
) -> Dict[str, Tuple[float, float, float]]:
    """
    Returns {ticker: (beta_growth, beta_inflation, r_squared)}.

    US tickers  : FRED delta_gdp + delta_cpi
    Non-US      : local index return + FRED delta_cpi
    Fallback    : hardcoded research values with r2=0
    """
    us_factors = _fetch_macro_factors(fred_api_key)
    cpi_factor = _fetch_cpi_factor(fred_api_key)

    result: Dict[str, Tuple[float, float, float]] = {}

    for ticker in tickers:
        country = _ticker_country(ticker)

        # US path
        if country == "US" and us_factors is not None:
            rets = _fetch_monthly_returns(ticker, start, end, price_provider)
            if rets is not None:
                aligned = _align_monthly(
                    rets,
                    us_factors["delta_gdp"],
                    us_factors["delta_cpi"],
                )
                if aligned is not None:
                    y = aligned["r"].values
                    X = aligned[["delta_gdp", "delta_cpi"]].values
                    bg, bi, r2 = _ols_betas_r2(y, X)
                    result[ticker] = (
                        float(np.clip(bg, -2.0, 2.0)),
                        float(np.clip(bi, -2.0, 2.0)),
                        r2,
                    )
                    continue

        # Non-US path
        if country != "US":
            idx_ticker = _COUNTRY_INDEX.get(country)
            if idx_ticker and cpi_factor is not None:
                rets     = _fetch_monthly_returns(ticker, start, end, price_provider)
                idx_rets = _fetch_index_returns(idx_ticker, start, end)
                if rets is not None and idx_rets is not None:
                    aligned = _align_monthly(rets, idx_rets, cpi_factor)
                    if aligned is not None:
                        y = aligned["r"].values
                        X = aligned[[idx_ticker, "delta_cpi"]].values
                        bg, bi, r2 = _ols_betas_r2(y, X)
                        result[ticker] = (
                            float(np.clip(bg, -2.0, 2.0)),
                            float(np.clip(bi, -2.0, 2.0)),
                            r2,
                        )
                        continue

        # Fallback
        result[ticker] = _FALLBACK.get(ticker, (0.0, 0.0, 0.0))

    return result
