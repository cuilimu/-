"""
analytics/arimax/fred_mev.py
Fetch arbitrary FRED series IDs for use as ARIMAX exogenous variables.

Lighter than data/fred_fetcher.py (which is hard-wired to the TAA macro panel
and computes YoY/QoQ derivatives). This wrapper returns *raw levels* by series
ID, matching the engine's expectation that `MEVS_Guide` controls the
log_diff/diff transformation downstream.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

from stock_engine.exceptions import DataError

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Default presets shown in the UI. Each entry: (series_id, default_guide).
# 'log_diff' for level series (GDP, production indices); 'diff' for rate/spread
# series that are already near-stationary (yield spreads, credit spreads).
# Ordered by relevance for equity / portfolio return modeling.
DEFAULT_FRED_PRESETS: dict[str, str] = {
    # ── Core equity predictors (most literature-cited) ────────────────────
    "T10Y3M":       "diff",       # Term spread: 10Y − 3M Treasury — recession/risk-premium signal
    "BAAFFM":       "diff",       # Baa corp bond − Fed Funds — credit conditions / risk appetite
    "INDPRO":       "log_diff",   # Industrial production — real activity cycle, leads earnings
    "DGS10":        "diff",       # 10Y Treasury yield — discount rate effect on equity multiples
    "UMCSENT":      "diff",       # UMich consumer sentiment — forward-looking demand proxy
    # ── Additional equity / macro signals ─────────────────────────────────
    "BAMLH0A0HYM2": "diff",       # HY OAS spread — risk appetite / fear gauge
    "T10Y2Y":       "diff",       # 10Y − 2Y yield spread — alternative term spread
    "DTWEXBGS":     "log_diff",   # Trade-weighted USD — global risk / EM capital flows
    "PAYEMS":       "log_diff",   # Nonfarm payrolls — labour market cycle
    "GDP":          "log_diff",   # Nominal GDP (quarterly)
    "GDPC1":        "log_diff",   # Real GDP (quarterly)
    # ── Legacy / credit-model series (kept for backward compatibility) ────
    "FEDFUNDS":     "diff",       # Effective Fed Funds rate
    "CPIAUCSL":     "log_diff",   # CPI (headline, level)
    "CPILFESL":     "log_diff",   # Core CPI (level)
    "UNRATE":       "diff",       # Unemployment rate (%)
}


def fetch_fred_series(
    series_ids: Iterable[str],
    api_key: Optional[str] = None,
    start: str = "2000-01-01",
    end: Optional[str] = None,
    frequency: str = "m",
    cache_dir: str = ".cache/fred_mev",
    cache_hours: int = 12,
) -> pd.DataFrame:
    """
    Fetch raw level series for each FRED ID. Returns a DataFrame with
    a DatetimeIndex named 'DATE' and one column per series ID.

    Forward-fills *across series* so all columns share the same index, but
    does not reshape from level to growth — that happens in data_preprocess.
    """
    api_key = api_key or os.environ.get("FRED_API_KEY", "")
    if not api_key:
        raise DataError(
            "FRED API key not set. Set FRED_API_KEY env var or pass api_key= explicitly."
        )

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    frames: dict[str, pd.Series] = {}
    for sid in series_ids:
        cache_file = cache / f"{sid}_{frequency}.parquet"
        s: Optional[pd.Series] = None
        if cache_file.exists():
            age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if age < timedelta(hours=cache_hours):
                s = pd.read_parquet(cache_file).iloc[:, 0]

        if s is None:
            s = _fetch_one(sid, api_key, start, frequency)
            s.to_frame(name=sid).to_parquet(cache_file)

        frames[sid] = s

    df = pd.DataFrame(frames).sort_index()
    df.index.name = "DATE"
    # Bridge series whose native frequency is coarser than the merged index
    # (e.g. quarterly GDP joined with monthly CPI) so every row is populated.
    df = df.ffill()
    if end is not None:
        df = df.loc[: pd.Timestamp(end)]
    return df


def _fetch_one(series_id: str, api_key: str, start: str, frequency: str) -> pd.Series:
    common = {
        "series_id":         series_id,
        "api_key":           api_key,
        "file_type":         "json",
        "observation_start": start,
    }
    # FRED rejects requests that ask for a *finer* frequency than the series's
    # native one (e.g. frequency=m on quarterly GDP) with HTTP 400 and
    # message "Value of frequency is not one of: 'q', 'sa', 'a'." We try the
    # caller-requested frequency first, then 'q' (quarterly — most common
    # native fallback for macro aggregates), then native (no `frequency`
    # param at all). Whichever succeeds wins.
    attempts: list[dict] = [
        {**common, "frequency": frequency},
    ]
    if frequency != "q":
        attempts.append({**common, "frequency": "q"})
    attempts.append(common)  # native frequency, as a last resort

    last_resp = None
    last_body = ""
    for params in attempts:
        resp = requests.get(_FRED_BASE, params=params, timeout=15)
        last_resp = resp
        if resp.ok:
            break
        last_body = (resp.text or "")[:240]
        # 400 = frequency mismatch we want to retry past. Anything else
        # (auth / quota / server) won't be fixed by changing frequency.
        if resp.status_code != 400:
            break

    if last_resp is None or not last_resp.ok:
        # Surface FRED's own error message when available — much more
        # actionable than the generic "400 Client Error" text.
        suffix = f" — {last_body}" if last_body else ""
        if last_resp is not None:
            raise DataError(
                f"FRED fetch for {series_id} failed: "
                f"{last_resp.status_code} {last_resp.reason}{suffix}"
            )
        raise DataError(f"FRED fetch for {series_id} failed{suffix}")

    data = last_resp.json()
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
