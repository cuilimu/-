"""
ui/components/portfolio_card.py — Portfolio summary display widget.
Renders NAV, cash, positions, and P&L as styled metric cards.
Input: PortfolioSnapshot — never raw Portfolio state.
"""

from typing import Optional

import streamlit as st

from stock_engine.portfolio.models import PortfolioSnapshot
from stock_engine.ui.theme import COLOR_GAIN, COLOR_LOSS


def portfolio_summary_card(snapshot: PortfolioSnapshot, initial_capital: float) -> None:
    """
    Renders a 4-column metric row:
      NAV | Cash | Unrealised P&L | Daily Return
    Colour-codes gain/loss values.
    """
    raise NotImplementedError


def positions_table(snapshot: PortfolioSnapshot, prices: dict[str, float]) -> None:
    """
    Renders a styled st.dataframe with columns:
      Ticker | Qty | Avg Cost | Current Price | Market Value | Unrealised P&L | Weight %
    No raw DataFrame exposed — table is styled before rendering.
    """
    raise NotImplementedError


def transaction_history_table(transactions: list, max_rows: int = 50) -> None:
    """
    Renders recent transactions as a compact styled table.
    Colour-codes BUY (gain colour) vs SELL (loss colour).
    Shows at most max_rows entries, newest first.
    """
    raise NotImplementedError
