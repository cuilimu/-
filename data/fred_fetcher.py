"""
data/fred_fetcher.py — FRED (St. Louis Fed) macro signal fetcher for Page 6 TAA.

Fetches the 6 macro series used by the regime classifier and TAA playbook:
  CPIAUCSL   CPI YoY (calculated from level)
  CPILFESL   Core CPI YoY (calculated from level)
  UNRATE     Unemployment Rate (%)
  T10Y2Y     10Y-2Y Treasury yield spread (%)
  GDP        Real GDP growth QoQ annualised (calculated from level)
  BAMLH0A0HYM2  ICE BofA HY OAS spread (%)

Requires environment variable FRED_API_KEY or explicit api_key argument.
Caches to parquet; refreshes if stale > CACHE_HOURS hours.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests

from stock_engine.exceptions import DataError

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Series fetched as levels; YoY / QoQ computed locally
LEVEL_SERIES = {
    "CPIAUCSL":      "cpi_level",
    "CPILFESL":      "core_cpi_level",
    "UNRATE":        "unemployment",
    "T10Y2Y":        "yield_spread",
    "GDP":           "gdp_level",
    "BAMLH0A0HYM2":  "hy_spread",
}

# Final signal names exposed to callers
SIGNAL_KEYS = ["cpi_yoy", "core_cpi_yoy", "unemployment", "yield_spread",
               "gdp_growth_qoq", "hy_spread"]

CACHE_HOURS = 12


class FredFetcher:
    """
    Fetches and caches FRED macro signals.
    Returns a dict of the latest available value for each signal.
    # ML_EXTENSIBLE: regime classification can consume this output via analytics/regime.py
    """

    def __init__(self, api_key: Optional[str] = None, cache_dir: str = ".cache") -> None:
        self._api_key = api_key or os.environ.get("FRED_API_KEY", "")
        if not self._api_key:
            raise DataError(
                "FRED API key not set. "
                "Set environment variable FRED_API_KEY or pass api_key= to FredFetcher()."
            )
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self._cache_dir / "fred_signals.parquet"

    # ── Public API ──────────────────────────────────────────────────────────────

    def latest(self) -> Dict[str, float]:
        """
        Returns the most recent value for each signal.
        Uses cache if fresh; otherwise fetches from FRED.
        """
        df = self._load_or_refresh()
        row = df.iloc[-1]
        return {k: float(row[k]) for k in SIGNAL_KEYS if k in row and pd.notna(row[k])}

    def history(self, start: str, end: Optional[str] = None) -> pd.DataFrame:
        """
        Returns full signal history from start to end (YYYY-MM-DD).
        Columns = SIGNAL_KEYS.
        """
        df = self._load_or_refresh()
        start_ts = pd.Timestamp(start)
        end_ts   = pd.Timestamp(end) if end else pd.Timestamp.now()
        return df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()

    # ── Internal ────────────────────────────────────────────────────────────────

    def _load_or_refresh(self) -> pd.DataFrame:
        if self._cache_path.exists():
            age = datetime.now() - datetime.fromtimestamp(self._cache_path.stat().st_mtime)
            if age < timedelta(hours=CACHE_HOURS):
                return pd.read_parquet(self._cache_path)
        return self._fetch_and_cache()

    def _fetch_and_cache(self) -> pd.DataFrame:
        frames: Dict[str, pd.Series] = {}
        for series_id, col in LEVEL_SERIES.items():
            try:
                frames[col] = self._fetch_series(series_id)
            except Exception as exc:
                raise DataError(f"FRED fetch failed for {series_id}: {exc}") from exc

        df = pd.DataFrame(frames)
        df = df.sort_index()

        # Compute YoY for CPI and Core CPI (12-month % change)
        df["cpi_yoy"]      = df["cpi_level"].pct_change(12) * 100
        df["core_cpi_yoy"] = df["core_cpi_level"].pct_change(12) * 100

        # GDP: annualised QoQ growth (quarterly series, forward-fill to monthly)
        df["gdp_level"] = df["gdp_level"].ffill()
        df["gdp_growth_qoq"] = df["gdp_level"].pct_change(1) * 400  # annualised

        # Pass-through series (already in usable units)
        # unemployment, yield_spread, hy_spread already in df

        df = df[SIGNAL_KEYS].dropna(how="all")
        df.to_parquet(self._cache_path)
        return df

    def _fetch_series(self, series_id: str) -> pd.Series:
        params = {
            "series_id":   series_id,
            "api_key":     self._api_key,
            "file_type":   "json",
            "observation_start": "2000-01-01",
            "frequency":   "m",          # monthly
        }
        resp = requests.get(FRED_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "observations" not in data:
            raise DataError(f"Unexpected FRED response for {series_id}: {data}")

        records = [
            (obs["date"], float(obs["value"]))
            for obs in data["observations"]
            if obs["value"] not in (".", "")
        ]
        if not records:
            raise DataError(f"No observations returned for {series_id}")

        dates, values = zip(*records)
        return pd.Series(values, index=pd.to_datetime(dates), name=series_id)
