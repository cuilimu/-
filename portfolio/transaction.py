"""
portfolio/transaction.py -- Cash utilities and closed-position model for Multi-Date mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from stock_engine.portfolio.models import ScheduledTransaction


@dataclass
class ClosedPosition:
    """Records one fully or partially closed trade lot (FIFO matched)."""
    ticker: str
    buy_date: str
    sell_date: str
    shares: int
    buy_price: float
    sell_price: float
    realized_pnl: float         # (sell_price - buy_price) * shares
    realized_pnl_pct: float     # realized_pnl / (buy_price * shares)
    holding_days: int


def compute_cash_at_date(
    txns: list[ScheduledTransaction],
    as_of_date: str,
    initial_capital: float,
) -> float:
    """
    Compute available cash as of as_of_date from the transaction log.

    BUYs  (pre-exec):  cash -= preview_shares * preview_price
    BUYs  (executed):  cash -= executed_value; cash += returned_cash
    SELLs (pre-exec):  cash += shares * preview_price
    SELLs (executed):  cash += executed_value
    Errored txns are skipped.
    """
    cash = initial_capital
    for t in sorted(txns, key=lambda x: x.date):
        if t.date > as_of_date:
            break
        if t.error:
            continue
        if t.is_buy():
            if t.is_executed:
                cash -= (t.executed_value or 0.0)
                cash += (t.returned_cash or 0.0)
            else:
                cash -= (t.preview_shares or 0) * (t.preview_price or 0.0)
        else:
            if t.is_executed:
                cash += (t.executed_value or 0.0)
            else:
                cash += (t.shares or 0) * (t.preview_price or 0.0)
    return cash
