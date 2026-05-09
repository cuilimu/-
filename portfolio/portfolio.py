"""
portfolio/portfolio.py — Portfolio engine.
Tracks positions, cash, transactions, cost basis.
MVP: long-only, no leverage. Interface designed to extend to short/leveraged.
"""

from datetime import datetime
from typing import Optional

from stock_engine.config import Config
from stock_engine.exceptions import PortfolioError
from stock_engine.portfolio.models import Position, PortfolioSnapshot, Transaction


class Portfolio:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._cash: float = config.initial_capital
        self._positions: dict[str, Position] = {}
        self._transactions: list[Transaction] = []

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def buy(
        self,
        ticker: str,
        quantity: float,
        price: float,
        timestamp: datetime,
        commission: float = 0.0,
    ) -> Transaction:
        actual_cost = quantity * price + commission
        if actual_cost > self._cash + 1e-9:  # tolerance for float rounding
            raise PortfolioError(
                f"Insufficient cash: need {actual_cost:.2f}, have {self._cash:.2f}"
            )
        # Deduct only actual cost — returned cash stays in _cash automatically
        self._cash -= actual_cost
        self._update_position(ticker, quantity, price)
        txn = Transaction(ticker=ticker, action="BUY", quantity=quantity,
                          price=price, timestamp=timestamp, commission=commission)
        self._record(txn)
        return txn

    def sell(
        self,
        ticker: str,
        quantity: float,
        price: float,
        timestamp: datetime,
        commission: float = 0.0,
    ) -> Transaction:
        if ticker not in self._positions:
            raise PortfolioError(f"No position in {ticker}")
        pos = self._positions[ticker]
        if quantity > pos.quantity:
            raise PortfolioError(
                f"Cannot sell {quantity} of {ticker}: only {pos.quantity} held"
            )
        self._cash += quantity * price - commission
        if abs(pos.quantity - quantity) < 1e-9:
            del self._positions[ticker]
        else:
            self._positions[ticker] = Position(
                ticker=ticker,
                quantity=pos.quantity - quantity,
                cost_basis=pos.cost_basis,
                opened_at=pos.opened_at,
            )
        txn = Transaction(ticker=ticker, action="SELL", quantity=quantity,
                          price=price, timestamp=timestamp, commission=commission)
        self._record(txn)
        return txn

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    @property
    def transactions(self) -> list[Transaction]:
        return list(self._transactions)

    def market_value(self, prices: dict[str, float]) -> float:
        return sum(
            pos.quantity * prices.get(ticker, pos.cost_basis)
            for ticker, pos in self._positions.items()
        )

    def nav(self, prices: dict[str, float]) -> float:
        return self._cash + self.market_value(prices)

    def snapshot(self, prices: dict[str, float], timestamp: datetime) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=self._cash,
            positions=dict(self._positions),
            nav=self.nav(prices),
        )

    def unrealised_pnl(self, ticker: str, current_price: float) -> float:
        if ticker not in self._positions:
            return 0.0
        pos = self._positions[ticker]
        return (current_price - pos.cost_basis) * pos.quantity

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_position(self, ticker: str, quantity: float, price: float) -> None:
        if ticker in self._positions:
            pos = self._positions[ticker]
            total_qty = pos.quantity + quantity
            vwap = (pos.quantity * pos.cost_basis + quantity * price) / total_qty
            self._positions[ticker] = Position(
                ticker=ticker,
                quantity=total_qty,
                cost_basis=vwap,
                opened_at=pos.opened_at,
            )
        else:
            self._positions[ticker] = Position(
                ticker=ticker,
                quantity=quantity,
                cost_basis=price,
            )

    def _record(self, txn: Transaction) -> None:
        self._transactions.append(txn)
