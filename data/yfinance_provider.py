"""
data/yfinance_provider.py — yfinance-backed DataProvider.
Supports daily / monthly / quarterly frequencies and configurable price field.
"""

import hashlib
import os
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

from stock_engine.config import Config
from stock_engine.data.base import DataProvider
from stock_engine.exceptions import DataError

# Map internal frequency codes → yfinance intervals
_YF_INTERVAL = {"1d": "1d", "1mo": "1mo", "1q": "1d"}  # quarterly: pull daily, resample


def normalize_datetime_index(series: pd.Series) -> pd.Series:
    """
    Strip timezone from a Series' DatetimeIndex to ensure tz-naive throughout.
    Prevents 'Cannot compare tz-naive and tz-aware datetime-like objects' errors
    when merging NAV series (tz-aware) with plain Timestamps (tz-naive).

    Usage:
        from stock_engine.data.yfinance_provider import normalize_datetime_index
        nav = normalize_datetime_index(nav)
    """
    if isinstance(series.index, pd.DatetimeIndex) and series.index.tz is not None:
        series = series.copy()
        series.index = series.index.tz_convert(None)
    return series


class YFinanceProvider(DataProvider):
    SUPPORTED_FREQUENCIES = ["1d", "1mo", "1q"]

    def __init__(self, config: Config) -> None:
        self._config = config
        if config.cache_enabled:
            Path(config.cache_dir).mkdir(parents=True, exist_ok=True)

    def fetch_historical(
        self,
        ticker: str,
        start: str,
        end: str,
        frequency: str = "1d",
    ) -> pd.DataFrame:
        if frequency not in self.SUPPORTED_FREQUENCIES:
            raise DataError(f"Unsupported frequency '{frequency}'")

        # For "latest" end date, bypass cache
        is_latest = (end == date.today().isoformat())
        cache_key = f"{ticker}_{start}_{end}_{frequency}"

        if self._config.cache_enabled and not is_latest:
            path = self._cache_path(cache_key)
            cached = self._load_from_cache(path)
            if cached is not None:
                return cached

        try:
            interval = _YF_INTERVAL[frequency]
            df = yf.download(ticker, start=start, end=end, interval=interval,
                             auto_adjust=True, progress=False)
        except Exception as exc:
            raise DataError(f"Failed to fetch {ticker}: {exc}") from exc

        if df.empty:
            raise DataError(f"No data returned for {ticker} ({start} → {end})")

        df = self._normalise_columns(df)

        # Resample to quarterly if needed
        if frequency == "1q":
            df = self._resample_quarterly(df)

        if self._config.cache_enabled and not is_latest:
            path = self._cache_path(cache_key)
            self._save_to_cache(df, path)

        return df

    def fetch_quote(self, ticker: str) -> dict:
        try:
            info = yf.Ticker(ticker).fast_info
            price = info.last_price
            if price is None:
                raise DataError(f"No price available for {ticker}")
            return {"ticker": ticker, "price": float(price),
                    "timestamp": pd.Timestamp.utcnow()}
        except DataError:
            raise
        except Exception as exc:
            raise DataError(f"Quote fetch failed for {ticker}: {exc}") from exc

    def available_frequencies(self) -> list[str]:
        return self.SUPPORTED_FREQUENCIES

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cache_path(self, key: str) -> str:
        h = hashlib.md5(key.encode()).hexdigest()[:10]
        return os.path.join(self._config.cache_dir, f"{h}.parquet")

    def _load_from_cache(self, path: str) -> pd.DataFrame | None:
        try:
            if os.path.exists(path):
                df = pd.read_parquet(path)
                # Parquet preserves tz metadata — strip to tz-naive so cached
                # and freshly-fetched frames always have the same index type.
                if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
                    df.index = df.index.tz_convert(None)
                return df
        except Exception:
            pass
        return None

    def _save_to_cache(self, df: pd.DataFrame, path: str) -> None:
        try:
            df.to_parquet(path)
        except Exception:
            pass

    def _normalise_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
        # Strip tz → tz-naive UTC so all callers (metrics, profiler) work with plain dates.
        # multi_date_runner re-applies tz itself after calling fetch_historical, so safe.
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
        return df

    def _resample_quarterly(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resample daily OHLCV to quarter-end."""
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }
        if "volume" in df.columns:
            agg["volume"] = "sum"
        agg = {k: v for k, v in agg.items() if k in df.columns}
        return df.resample("QE").agg(agg).dropna(how="all")

    def fetch_price_at(
        self,
        ticker: str,
        date: str,
        price_field: str,
    ) -> float | None:
        """
        Returns price of ticker on date using price_field.
        If date is weekend/holiday, returns nearest prior trading day price.
        Reads from parquet cache first. Returns None if unavailable.
        Used by: Same Day allocation preview, Multi-Date add form, everywhere.
        """
        try:
            start_d = (pd.Timestamp(date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            end_d = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            df = self.fetch_historical(ticker, start_d, end_d, frequency="1d")
            price_col = price_field.lower()
            col = price_col if price_col in df.columns else "close"
            # Walk backwards from the target date to find the nearest trading day
            target = pd.Timestamp(date).tz_localize(None)
            available = df.index[df.index <= target]
            if available.empty:
                return None
            return float(df.loc[available[-1], col])
        except Exception:
            return None