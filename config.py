"""
Global configuration object. All tuneable parameters live here.
No module-level mutable state — pass Config instances explicitly.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Config:
    # Capital
    initial_capital: float = 100_000.0

    # Data
    default_frequency: str = "1d"          # "1d" | "1mo" | "1q"
    cache_dir: str = ".cache/parquet"
    cache_enabled: bool = True

    # Module 1: price field selection
    price_field: str = "Close"             # "Close" | "Open" | "High" | "Low"

    # Module 4: dynamic end date
    use_latest_end_date: bool = False

    # Global transaction cost — shared by backtest rebalancer and Return Analysis profiler
    slippage_bps: float = 7.5

    # Backtest
    default_benchmark: str = "SPY"
    fill_price: str = "open"

    # Analytics — annualisation factor set by frequency
    risk_free_rate: float = 0.04
    annualisation_factor: int = 252        # overridden by frequency selection

    # UI defaults
    default_tickers: list[str] = field(default_factory=lambda: ["AAPL", "MSFT", "SPY"])
    default_start_date: str = "2020-01-01"
    default_end_date: str = "2024-12-31"

    def effective_end_date(self) -> str:
        if self.use_latest_end_date:
            return date.today().isoformat()
        return self.default_end_date

    def set_frequency(self, freq: str) -> None:
        """Set frequency and update annualisation factor accordingly."""
        factors = {"1d": 252, "1mo": 12, "1q": 4}
        if freq not in factors:
            raise ValueError(f"Unsupported frequency: {freq}")
        self.default_frequency = freq
        self.annualisation_factor = factors[freq]

