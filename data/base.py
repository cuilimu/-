"""
data/base.py — Abstract DataProvider interface.
Swap implementations (yfinance, Bloomberg, CSV) without touching callers.
"""

from abc import ABC, abstractmethod
import pandas as pd


class DataProvider(ABC):
    """
    Contract every data source must fulfil.
    Returns tidy DataFrames: DatetimeIndex, columns = OHLCV, ticker as metadata.
    """

    @abstractmethod
    def fetch_historical(
        self,
        ticker: str,
        start: str,
        end: str,
        frequency: str = "1d",
    ) -> pd.DataFrame:
        """
        Returns DataFrame with columns [open, high, low, close, volume].
        Index: pd.DatetimeIndex (UTC-normalised).
        Raises DataError on fetch failure or unsupported frequency.
        """
        ...

    @abstractmethod
    def fetch_quote(self, ticker: str) -> dict:
        """
        Returns latest quote as dict with keys: ticker, price, timestamp.
        Raises DataError if ticker is invalid or market is closed.
        """
        ...

    @abstractmethod
    def available_frequencies(self) -> list[str]:
        """Returns list of frequency strings this provider supports, e.g. ['1d', '1mo']."""
        ...
