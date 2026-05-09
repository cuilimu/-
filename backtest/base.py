"""
backtest/base.py — Strategy interface and BacktestResult model.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from stock_engine.portfolio.models import PortfolioSnapshot, Transaction
from stock_engine.portfolio.transaction import ClosedPosition
from stock_engine.portfolio.rebalancer import RebalanceEvent


class Strategy(ABC):
    """
    Abstract base for all trading strategies.
    Receives a window of market data; returns per-ticker signals.
    No portfolio state is accessible here — signal generation must be pure.
    """

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> dict[str, float]:
        """
        data: OHLCV DataFrame slice up to (and including) current bar.
              MultiIndex columns: (field, ticker) -- e.g. ('close', 'AAPL').
        Returns: {ticker: signal} where signal in [-1.0, 1.0].
                 0 = hold, positive = long intent, negative = short intent (reserved).
        Raises BacktestError on misconfiguration.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy identifier for reports."""
        ...


@dataclass
class BacktestResult:
    """
    Standardised output of a backtest run.
    Consumed by analytics and viz layers -- neither layer touches raw OHLCV.
    """
    strategy_name: str
    tickers: list[str]
    start_date: str
    end_date: str
    initial_capital: float

    # Time series
    snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)

    # Benchmark (populated post-run)
    benchmark_ticker: Optional[str] = None
    benchmark_returns: Optional[pd.Series] = None   # DatetimeIndex -> daily return

    # Realized P&L from closed positions (Multi-Date mode only; empty for same-day)
    closed_positions: list[ClosedPosition] = field(default_factory=list)
    total_realized_pnl: float = 0.0

    # Rebalancing (Same Day mode only; empty list when rebalancing disabled)
    rebalance_events: list[RebalanceEvent] = field(default_factory=list)
    total_rebalance_cost: float = 0.0

    # Summary stats (populated by analytics layer, not backtest runner)
    summary: Optional[dict] = None
