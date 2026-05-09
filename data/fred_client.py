"""
data/fred_client.py — Comprehensive FRED API client for the macro dashboard.

Fetches all series defined in SERIES_CONFIG (spec §3).
SQLite cache at .cache/fred_macro.db — refresh per policy below.

━━━ ADDING A NEW SERIES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Add one entry to SERIES_CONFIG. Format:
    "FRED_ID": (label, bucket, fred_freq, refresh_policy)
  bucket         — grouping key used by composites.py
  fred_freq      — "D" | "W" | "M" | "Q"  (informational only, not used for fetch)
  refresh_policy — "daily" | "weekly" | "monthly"
That's it. Nothing else changes.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

# ── Series catalogue ── edit ONLY this dict to add/remove series ─────────────
#  key  → (label, bucket, fred_freq, refresh_policy)
SERIES_CONFIG: Dict[str, Tuple[str, str, str, str]] = {
    # Growth / Labor
    "GDPC1":            ("Real GDP",                   "growth",      "Q", "weekly"),
    "INDPRO":           ("Industrial Production",      "growth",      "M", "daily"),
    "PAYEMS":           ("Nonfarm Payrolls",            "growth",      "M", "daily"),
    "CFNAI":            ("Chicago Fed Nat'l Activity", "growth",      "M", "daily"),
    "UNRATE":           ("Unemployment Rate",           "growth",      "M", "daily"),
    "SAHMREALTIME":     ("Sahm Rule",                  "growth",      "M", "daily"),
    # Inflation
    "CPIAUCSL":         ("Headline CPI",               "inflation",   "M", "daily"),
    "CPILFESL":         ("Core CPI",                   "inflation",   "M", "daily"),
    "PCEPILFE":         ("Core PCE",                   "inflation",   "M", "daily"),
    "T10YIE":           ("10Y Breakeven",              "inflation",   "D", "daily"),
    "T5YIFR":           ("5Y5Y Forward",               "inflation",   "D", "daily"),
    # Rates
    "DFF":              ("Fed Funds Effective",        "rates",       "D", "daily"),
    "DGS3MO":           ("3M Treasury",                "rates",       "D", "daily"),
    "DGS2":             ("2Y Treasury",                "rates",       "D", "daily"),
    "DGS5":             ("5Y Treasury",                "rates",       "D", "daily"),
    "DGS10":            ("10Y Treasury",               "rates",       "D", "daily"),
    "DGS30":            ("30Y Treasury",               "rates",       "D", "daily"),
    "T10Y2Y":           ("10Y-2Y Spread",              "rates",       "D", "daily"),
    "DFII10":           ("10Y Real Yield (TIPS)",      "rates",       "D", "daily"),
    # Credit
    "BAMLH0A0HYM2":     ("HY OAS",                    "credit",      "D", "daily"),
    "BAMLC0A0CM":       ("IG OAS",                    "credit",      "D", "daily"),
    "VIXCLS":           ("VIX",                       "credit",      "D", "daily"),
    # Financial Conditions
    "NFCI":             ("Chicago Fed FCI",            "conditions",  "W", "weekly"),
    "ANFCI":            ("Adjusted NFCI",              "conditions",  "W", "weekly"),
    # Liquidity
    "WALCL":            ("Fed Balance Sheet",          "liquidity",   "W", "weekly"),
    "RRPONTSYD":        ("Overnight RRP",              "liquidity",   "D", "daily"),
    # Cross-asset
    "DTWEXBGS":         ("Broad Dollar Index",         "cross_asset", "D", "daily"),
    "DCOILWTICO":       ("WTI Oil",                   "cross_asset", "D", "daily"),
    "GOLDAMGBD228NLBM": ("Gold (London PM)",           "cross_asset", "D", "daily"),
    "NASDAQCOM":        ("Nasdaq Composite",           "cross_asset", "D", "daily"),
    # Demand
    "UMCSENT":          ("Consumer Sentiment",         "demand",      "M", "daily"),
    "NEWORDER":         ("Durable Goods ex-Trans",     "demand",      "M", "daily"),
    # Recession flag
    "USREC":            ("NBER Recession",             "recession",   "M", "weekly"),
}

# Max cache age in seconds per refresh policy
_CACHE_TTL: Dict[str, int] = {
    "daily":   6 * 3600,
    "weekly":  24 * 3600,
    "monthly": 7 * 24 * 3600,
}

# Typical release cadence in days (for staleness highlighting in release table)
TYPICAL_CADENCE: Dict[str, int] = {
    "D": 1, "W": 7, "M": 35, "Q": 100,
}


class FredMacroClient:
    """
    Full FRED macro client for the macro dashboard.
    Thread-safe; parallelises FRED calls on cold start or force-refresh.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: str = ".cache",
    ) -> None:
        # Strip whitespace defensively — a stray trailing space in the saved
        # key used to URL-encode as '+' and silently produce 400 Bad Request
        # for every series.
        self._api_key = (api_key or os.environ.get("FRED_API_KEY", "")).strip()
        if not self._api_key:
            raise ValueError(
                "FRED API key not set. "
                "Set env var FRED_API_KEY or pass api_key= to FredMacroClient()."
            )
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        self._db_path = str(cache_path / "fred_macro.db")
        self._init_db()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_series(
        self,
        series_id: str,
        start: Optional[str] = None,
    ) -> pd.Series:
        """Return a date-indexed float Series for one series_id."""
        self._ensure_fresh(series_id)
        return self._read_series(series_id, start)

    def get_all(
        self,
        start: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, pd.Series]:
        """
        Fetch all SERIES_CONFIG series; parallelise FRED calls.
        Returns dict[series_id → pd.Series].  Missing series → absent from dict.
        """
        def _one(sid: str) -> Tuple[str, Optional[pd.Series]]:
            # Try to refresh, but if it fails (network blip, rate limit, bad
            # key), still serve whatever's cached. Otherwise a single bad
            # daily refresh wipes 27 series from the dashboard even though
            # the cache is full of usable data.
            try:
                if force_refresh:
                    self._fetch_and_store(sid)
                else:
                    self._ensure_fresh(sid)
            except Exception:
                pass
            try:
                return sid, self._read_series(sid, start)
            except Exception:
                return sid, None

        # Use 4 workers (was 8) — the FRED free tier occasionally
        # rate-limits at high concurrency, surfacing as silent partial data.
        result: Dict[str, pd.Series] = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            for sid, s in (f.result() for f in as_completed(
                    {ex.submit(_one, sid): sid for sid in SERIES_CONFIG})):
                if s is not None and not s.empty:
                    result[sid] = s
        return result

    def last_value(self, series_id: str) -> Optional[float]:
        s = self._read_series(series_id).dropna()
        return float(s.iloc[-1]) if not s.empty else None

    def last_date(self, series_id: str) -> Optional[pd.Timestamp]:
        s = self._read_series(series_id).dropna()
        return s.index[-1] if not s.empty else None

    def prior_value(self, series_id: str) -> Optional[float]:
        """Second-to-last non-null value (for Δ column in release table)."""
        s = self._read_series(series_id).dropna()
        return float(s.iloc[-2]) if len(s) >= 2 else None

    def release_summary(self) -> List[Dict]:
        """
        Returns a list of dicts for the release calendar table (§5.7).
        Keys: series_id, label, bucket, fred_freq, last_value, prior_value,
              delta, last_date, days_since, typical_cadence, stale_flag
        """
        rows = []
        today = pd.Timestamp.now().normalize()
        for sid, (label, bucket, freq, _policy) in SERIES_CONFIG.items():
            s = self._read_series(sid).dropna()
            if s.empty:
                continue
            last_val   = float(s.iloc[-1])
            prior_val  = float(s.iloc[-2]) if len(s) >= 2 else None
            last_dt    = s.index[-1]
            days_since = (today - last_dt).days
            cadence    = TYPICAL_CADENCE.get(freq, 35)
            stale      = days_since > cadence
            rows.append(dict(
                series_id     = sid,
                label         = label,
                bucket        = bucket,
                fred_freq     = freq,
                last_value    = last_val,
                prior_value   = prior_val,
                delta         = (last_val - prior_val) if prior_val is not None else None,
                last_date     = last_dt,
                days_since    = days_since,
                typical_cadence = cadence,
                stale_flag    = stale,
            ))
        return sorted(rows, key=lambda r: r["days_since"])

    # ── Cache layer ────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS series_data (
                    series_id TEXT NOT NULL,
                    date      TEXT NOT NULL,
                    value     REAL,
                    PRIMARY KEY (series_id, date)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS series_meta (
                    series_id    TEXT PRIMARY KEY,
                    last_fetched REAL NOT NULL
                )
            """)

    def _is_stale(self, series_id: str) -> bool:
        policy = SERIES_CONFIG.get(series_id, ("", "", "D", "daily"))[3]
        ttl    = _CACHE_TTL.get(policy, 6 * 3600)
        with sqlite3.connect(self._db_path) as con:
            row = con.execute(
                "SELECT last_fetched FROM series_meta WHERE series_id=?",
                (series_id,),
            ).fetchone()
            if row is None:
                return True
            # Self-healing: if meta says "fresh" but the data table has zero
            # rows for this series, a prior fetch wrote an empty result and
            # poisoned the cache (older builds didn't reject empty obs).
            # Force a re-fetch so old caches recover automatically.
            has_rows = con.execute(
                "SELECT 1 FROM series_data WHERE series_id=? LIMIT 1",
                (series_id,),
            ).fetchone()
            if has_rows is None:
                return True
        return (time.time() - row[0]) > ttl

    def _ensure_fresh(self, series_id: str) -> None:
        if self._is_stale(series_id):
            self._fetch_and_store(series_id)

    def _fetch_and_store(self, series_id: str) -> None:
        """Pull full history from FRED and upsert into SQLite.

        Hardening:
          * Up to 3 attempts with 1s/2s back-off for transient HTTP failures
            (FRED free tier occasionally returns 429 or 5xx under load).
          * If `observations` comes back empty we treat it as a transient
            failure and DO NOT update last_fetched — otherwise the empty
            row gets cached as 'fresh' and we'd silently serve no data
            for hours until TTL expires."""
        params = {
            "series_id":         series_id,
            "api_key":           self._api_key,
            "file_type":         "json",
            "observation_start": "2000-01-01",
            "vintage_dates":     "",          # latest vintage
        }

        last_exc: Exception | None = None
        obs: list = []
        for attempt in range(3):
            try:
                resp = requests.get(FRED_OBS_URL, params=params, timeout=25)
                resp.raise_for_status()
                obs = resp.json().get("observations", [])
                break
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))   # 1s, 2s back-off
                    continue
        else:
            raise last_exc if last_exc else RuntimeError(
                f"FRED fetch failed for {series_id}"
            )

        if not obs:
            # Don't poison the cache — let the next call retry instead of
            # serving an empty series for 6h.
            raise RuntimeError(f"FRED returned no observations for {series_id}")

        rows = []
        for o in obs:
            v_str = o.get("value", ".")
            v = float(v_str) if v_str not in (".", "", "NA") else None
            rows.append((series_id, o["date"], v))

        with sqlite3.connect(self._db_path) as con:
            con.executemany(
                "INSERT OR REPLACE INTO series_data (series_id, date, value) VALUES (?,?,?)",
                rows,
            )
            con.execute(
                "INSERT OR REPLACE INTO series_meta (series_id, last_fetched) VALUES (?,?)",
                (series_id, time.time()),
            )

    def _read_series(
        self,
        series_id: str,
        start: Optional[str] = None,
    ) -> pd.Series:
        query = "SELECT date, value FROM series_data WHERE series_id=?"
        args: list = [series_id]
        if start:
            query += " AND date >= ?"
            args.append(start)
        query += " ORDER BY date"
        with sqlite3.connect(self._db_path) as con:
            rows = con.execute(query, args).fetchall()
        if not rows:
            return pd.Series(dtype=float, name=series_id)
        idx  = pd.to_datetime([r[0] for r in rows])
        vals = [r[1] for r in rows]
        return pd.Series(vals, index=idx, dtype=float, name=series_id)
