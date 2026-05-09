"""
analytics/factor_investing/live_loader.py — Live factor returns from Fama-French library.

Downloads monthly factor returns directly from Kenneth French's Data Library
(no pandas_datareader dependency) and maps them to the engine's 7-factor names.

Factor mapping (Fama-French -> CORE_FACTORS):
  MOM       <- F-F_Momentum_Factor              "Mom"
  BP        <- F-F_Research_Data_5_Factors_2x3  "HML"   (High-Minus-Low / Value)
  LogMktCap <- F-F_Research_Data_5_Factors_2x3  "-SMB"  (negated: Big-Minus-Small)
  Beta      <- F-F_Research_Data_5_Factors_2x3  "Mkt-RF" (market risk premium proxy)
  HL1M      <- F-F_ST_Reversal_Factor            "ST_Rev" (1-month reversal proxy)
  LTGC      <- F-F_Research_Data_5_Factors_2x3  "RMW"   (Robust-Minus-Weak / Profitability)
  AnnVol12M <- F-F_LT_Reversal_Factor            "LT_Rev" (long-term reversal proxy)

All French series are in percent; this module converts to decimal on return.
"""
from __future__ import annotations

import io
import re
import warnings
import zipfile
from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from stock_engine.analytics.factor_investing.types import CORE_FACTORS

# ── Constants ──────────────────────────────────────────────────────────────────

_FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"

# (zip file name without _CSV.zip, column inside, sign multiplier)
_FF_MAP: dict[str, tuple[str, str, float]] = {
    "MOM":       ("F-F_Momentum_Factor",             "Mom",    +1.0),
    "BP":        ("F-F_Research_Data_5_Factors_2x3", "HML",    +1.0),
    "LogMktCap": ("F-F_Research_Data_5_Factors_2x3", "SMB",    -1.0),  # Big-Minus-Small
    "Beta":      ("F-F_Research_Data_5_Factors_2x3", "Mkt-RF", +1.0),
    "HL1M":      ("F-F_ST_Reversal_Factor",           "ST_Rev", +1.0),
    "LTGC":      ("F-F_Research_Data_5_Factors_2x3", "RMW",    +1.0),
    "AnnVol12M": ("F-F_LT_Reversal_Factor",           "LT_Rev", +1.0),
}

# Human-readable label shown in the UI for each factor + its FF proxy
FACTOR_FF_LABEL: dict[str, str] = {
    "MOM":       "MOM  <-  Momentum (FF)",
    "BP":        "BP  <-  HML / Value (FF)",
    "LogMktCap": "LogMktCap  <-  -SMB / Size (FF)",
    "Beta":      "Beta  <-  Mkt-RF / Market (FF)",
    "HL1M":      "HL1M  <-  ST-Rev / 1M Reversal (FF)",
    "LTGC":      "LTGC  <-  RMW / Profitability (FF)",
    "AnnVol12M": "AnnVol12M  <-  LT-Rev proxy (FF)",
}

# ── HTTP + parsing helpers ─────────────────────────────────────────────────────

def _download_french_zip(dataset_name: str, timeout: int = 30) -> Optional[str]:
    """Download French CSV ZIP and return the CSV content as a string."""
    url = f"{_FRENCH_BASE}/{dataset_name}_CSV.zip"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        warnings.warn(
            f"Failed to download Fama-French dataset '{dataset_name}': {exc}",
            UserWarning,
            stacklevel=4,
        )
        return None

    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        csv_name = zf.namelist()[0]
        return zf.read(csv_name).decode("latin-1")
    except Exception as exc:
        warnings.warn(
            f"Failed to unpack Fama-French ZIP '{dataset_name}': {exc}",
            UserWarning,
            stacklevel=4,
        )
        return None


def _parse_french_monthly(text: str) -> pd.DataFrame:
    """Parse Kenneth French CSV text -> monthly DataFrame.

    French CSVs use comma-separated format:
      Header:  ,Col1,Col2,...     (leading comma = empty date field)
      Data:    YYYYMM,val1,val2,...
      Annual section starts with 'Annual Factors:' — ignored.

    Returns an empty DataFrame on parse failure.
    """
    data_col_names: list[str] = []
    rows: list[list[str]] = []
    in_monthly = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Split on commas (French format is comma-delimited)
        parts = [p.strip() for p in stripped.split(",")]
        first = parts[0]

        # Monthly data row: first field is YYYYMM
        if re.fullmatch(r"\d{6}", first):
            in_monthly = True
            rows.append(parts)
            continue

        # After monthly section starts, any non-YYYYMM line ends it
        if in_monthly:
            break

        # Header row: first field empty, rest are column names
        if not first and len(parts) >= 2:
            names = [p for p in parts[1:] if p]
            if names:
                data_col_names = names

    if not rows:
        return pd.DataFrame()

    n_data = len(rows[0]) - 1  # exclude the date field
    if not data_col_names:
        data_col_names = [f"col{i+1}" for i in range(n_data)]

    # Pad column names if needed
    while len(data_col_names) < n_data:
        data_col_names.append(f"col{len(data_col_names)+1}")

    records: dict[str, list] = {c: [] for c in data_col_names}
    dates: list[str] = []
    for row in rows:
        dates.append(row[0])
        for i, col in enumerate(data_col_names):
            val = row[i + 1] if i + 1 < len(row) else "nan"
            records[col].append(val)

    df = pd.DataFrame(records, index=dates)
    df.index = (
        pd.to_datetime(
            pd.Series(df.index).str.strip(), format="%Y%m", errors="coerce"
        ).values
    )
    df.index = pd.DatetimeIndex(df.index) + pd.offsets.MonthEnd(0)
    df = df[~pd.isnull(df.index)]
    df = df.apply(pd.to_numeric, errors="coerce")
    df.columns = pd.Index([c.strip() for c in df.columns])
    return df.dropna(how="all")


# ── public API ─────────────────────────────────────────────────────────────────

def load_french_factors(
    factors: list[str] | None = None,
    start: str | None = "1990-01-01",
    end: str | None = None,
) -> dict[str, pd.Series]:
    """Download Fama-French factor returns and return as QSpread-equivalent series.

    Parameters
    ----------
    factors:
        Subset of CORE_FACTORS to download.  Defaults to all seven.
    start:
        ISO date string for the start of the data window.
    end:
        ISO date string for the end of the data window (default: today).

    Returns
    -------
    dict mapping factor_name -> pd.Series with month-end DatetimeIndex.
    Values are decimal returns (percent / 100).  Missing factors are warned
    and omitted rather than raising.
    """
    factors = factors or CORE_FACTORS

    start_ts = pd.Timestamp(start or "1990-01-01")
    end_ts   = pd.Timestamp(end or datetime.today().strftime("%Y-%m-%d"))

    # Download each unique dataset once
    _cache: dict[str, Optional[pd.DataFrame]] = {}

    def _get_df(name: str) -> Optional[pd.DataFrame]:
        if name in _cache:
            return _cache[name]
        text = _download_french_zip(name)
        df = _parse_french_monthly(text) if text else None
        _cache[name] = df
        return df

    result: dict[str, pd.Series] = {}
    for factor in factors:
        if factor not in _FF_MAP:
            warnings.warn(
                f"No Fama-French mapping for factor '{factor}'; skipping.",
                UserWarning,
                stacklevel=2,
            )
            continue

        dataset_name, col_name, sign = _FF_MAP[factor]
        df = _get_df(dataset_name)
        if df is None or df.empty:
            continue

        if col_name not in df.columns:
            # Try case-insensitive match
            matches = [c for c in df.columns if c.lower() == col_name.lower()]
            if not matches:
                warnings.warn(
                    f"Column '{col_name}' not found in dataset '{dataset_name}' "
                    f"(available: {list(df.columns)}); skipping factor '{factor}'.",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            col_name = matches[0]

        series = (
            df[col_name]
            .rename(factor)
            .astype(float)
            .mul(sign / 100.0)   # pct -> decimal, apply sign
        )
        series = series.loc[
            (series.index >= start_ts) & (series.index <= end_ts)
        ].dropna()

        result[factor] = series

    return result
