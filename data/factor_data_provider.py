"""
data/factor_data_provider.py — Fama-French 6-factor data from Ken French Data Library.
Fetches FF5 + UMD, merges, caches to parquet. Refreshes if stale > 30 days.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from stock_engine.config import Config
from stock_engine.exceptions import DataError

FACTOR_COLS        = ["mktrf", "smb", "hml", "rmw", "cma", "umd", "rf"]
CACHE_FILE         = "ff_factors.parquet"
CACHE_FILE_DAILY   = "ff_factors_daily.parquet"
STALE_DAYS         = 30

_FF5_DATASET       = "F-F_Research_Data_5_Factors_2x3"
_UMD_DATASET       = "F-F_Momentum_Factor"
_FF5_DAILY_DATASET = "F-F_Research_Data_5_Factors_2x3_daily"
_UMD_DAILY_DATASET = "F-F_Momentum_Factor_daily"


class FactorDataProvider:
    """
    Fetches monthly FF6 factors (Mkt-RF, SMB, HML, RMW, CMA, UMD, RF).
    All values returned in decimal form (divided by 100).
    Index: pd.DatetimeIndex (month-end).
    """

    def __init__(self, config: Config) -> None:
        self._cache_dir = Path(config.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path       = self._cache_dir / CACHE_FILE
        self._cache_path_daily = self._cache_dir / CACHE_FILE_DAILY

    def fetch(self, start: str, end: str) -> pd.DataFrame:
        """
        Returns DataFrame with columns = FACTOR_COLS, decimal form.
        Sliced to [start, end]. Raises DataError on failure.
        """
        df = self._load_or_refresh()
        start_ts = pd.Timestamp(start)
        end_ts   = pd.Timestamp(end)
        mask = (df.index >= start_ts) & (df.index <= end_ts)
        sliced = df.loc[mask]
        if sliced.empty:
            raise DataError(
                f"No factor data between {start} and {end}. "
                "Ken French library may have a ~1 month lag."
            )
        return sliced

    def fetch_daily(self, start: str, end: str) -> pd.DataFrame:
        """
        Returns DataFrame with columns = FACTOR_COLS, decimal form, daily frequency.
        Index: pd.DatetimeIndex (calendar days, trading days only).
        Sliced to [start, end]. Raises DataError on failure.
        """
        df = self._load_or_refresh_daily()
        start_ts = pd.Timestamp(start)
        end_ts   = pd.Timestamp(end)
        mask = (df.index >= start_ts) & (df.index <= end_ts)
        sliced = df.loc[mask]
        if sliced.empty:
            raise DataError(
                f"No daily factor data between {start} and {end}. "
                "Ken French daily library may have a ~1 week lag."
            )
        return sliced

    # ------------------------------------------------------------------
    def _load_or_refresh(self) -> pd.DataFrame:
        if self._cache_path.exists():
            age = datetime.now() - datetime.fromtimestamp(self._cache_path.stat().st_mtime)
            if age < timedelta(days=STALE_DAYS):
                try:
                    return pd.read_parquet(self._cache_path)
                except Exception:
                    pass
        return self._fetch_and_cache()

    def _fetch_and_cache(self) -> pd.DataFrame:
        try:
            from pandas_datareader.famafrench import FamaFrenchReader
        except ImportError as e:
            raise DataError("pandas_datareader not installed") from e

        try:
            # FF5
            ff5_reader = FamaFrenchReader(_FF5_DATASET, start="1960-01-01")
            ff5_raw = ff5_reader.read()[0]   # [0] = monthly table
            ff5 = ff5_raw.copy()
            ff5.columns = [c.strip().lower().replace("-", "") for c in ff5.columns]
            # Rename 'mkt-rf' -> 'mktrf' already handled by strip
            col_map = {"mktrf": "mktrf", "smb": "smb", "hml": "hml",
                       "rmw": "rmw", "cma": "cma", "rf": "rf"}
            # handle any variant
            rename = {}
            for c in ff5.columns:
                clean = c.replace("-", "").replace(" ", "")
                if clean in col_map:
                    rename[c] = col_map[clean]
            ff5 = ff5.rename(columns=rename)[list(col_map.keys())]

            # UMD
            umd_reader = FamaFrenchReader(_UMD_DATASET, start="1960-01-01")
            umd_raw = umd_reader.read()[0]
            umd = umd_raw.copy()
            umd.columns = [c.strip().lower() for c in umd.columns]
            # column is typically 'mom' or 'umd'
            umd_col = [c for c in umd.columns if c in ("mom", "umd", "wml")][0]
            umd = umd[[umd_col]].rename(columns={umd_col: "umd"})

            # Merge
            df = ff5.join(umd, how="inner").dropna()
            df = df / 100.0   # convert % to decimal

            # Normalise index to month-end DatetimeIndex
            df.index = pd.to_datetime(df.index.to_timestamp("M"))

            df.to_parquet(self._cache_path)
            return df

        except DataError:
            raise
        except Exception as exc:
            raise DataError(f"Failed to fetch Fama-French factors: {exc}") from exc

    def _load_or_refresh_daily(self) -> pd.DataFrame:
        if self._cache_path_daily.exists():
            age = datetime.now() - datetime.fromtimestamp(self._cache_path_daily.stat().st_mtime)
            if age < timedelta(days=STALE_DAYS):
                try:
                    return pd.read_parquet(self._cache_path_daily)
                except Exception:
                    pass
        return self._fetch_and_cache_daily()

    def _fetch_and_cache_daily(self) -> pd.DataFrame:
        try:
            from pandas_datareader.famafrench import FamaFrenchReader
        except ImportError as e:
            raise DataError("pandas_datareader not installed") from e

        try:
            # FF5 daily
            ff5_reader = FamaFrenchReader(_FF5_DAILY_DATASET, start="1960-01-01")
            ff5_raw = ff5_reader.read()[0]
            ff5 = ff5_raw.copy()
            ff5.columns = [c.strip().lower().replace("-", "").replace(" ", "") for c in ff5.columns]
            col_map = {"mktrf": "mktrf", "smb": "smb", "hml": "hml",
                       "rmw": "rmw", "cma": "cma", "rf": "rf"}
            rename = {}
            for c in ff5.columns:
                clean = c.replace("-", "").replace(" ", "")
                if clean in col_map:
                    rename[c] = col_map[clean]
            ff5 = ff5.rename(columns=rename)
            ff5 = ff5[[k for k in col_map if k in ff5.columns]]

            # UMD daily
            umd_reader = FamaFrenchReader(_UMD_DAILY_DATASET, start="1960-01-01")
            umd_raw = umd_reader.read()[0]
            umd = umd_raw.copy()
            umd.columns = [c.strip().lower() for c in umd.columns]
            umd_col = next((c for c in umd.columns if c in ("mom", "umd", "wml")), None)
            if umd_col:
                umd = umd[[umd_col]].rename(columns={umd_col: "umd"})
                df = ff5.join(umd, how="left")
            else:
                df = ff5.copy()

            df = df.dropna(subset=[c for c in col_map if c != "umd"])
            df = df / 100.0   # % -> decimal

            # Normalise index to plain DatetimeIndex
            if hasattr(df.index, "to_timestamp"):
                df.index = pd.to_datetime(df.index.to_timestamp())
            else:
                df.index = pd.to_datetime(df.index)

            df.to_parquet(self._cache_path_daily)
            return df

        except DataError:
            raise
        except Exception as exc:
            raise DataError(f"Failed to fetch daily Fama-French factors: {exc}") from exc
