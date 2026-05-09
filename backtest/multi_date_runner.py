"""
backtest/multi_date_runner.py — Event-driven runner for Multi-Date transaction mode.
Completely separate code path from BacktestRunner — zero changes to existing engine.
Outputs the same BacktestResult structure so all downstream tabs work unchanged.
"""

from __future__ import annotations

import math
from collections import deque
from datetime import datetime
from typing import Optional

import pandas as pd

from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.data.base import DataProvider
from stock_engine.exceptions import BacktestError
from stock_engine.portfolio.models import (
    Position,
    PortfolioSnapshot,
    ScheduledTransaction,
    Transaction,
)
from stock_engine.portfolio.transaction import ClosedPosition


class MultiDateRunner:
    """
    Executes a list of ScheduledTransactions across a date range.
    Between transactions, marks positions to market daily.
    Same BacktestResult output as BacktestRunner.
    """

    def __init__(self, data_provider: DataProvider, config: Config) -> None:
        self._provider = data_provider
        self._config   = config

    def run(
        self,
        scheduled: list[ScheduledTransaction],
        start_date: str,
        end_date: str,
        initial_capital: float,
    ) -> BacktestResult:
        if not scheduled:
            raise BacktestError("No transactions scheduled.")

        price_col = self._config.price_field.lower()
        tickers   = list({t.ticker for t in scheduled})

        # ── Fetch all price data ──────────────────────────────────────────────
        price_data: dict[str, pd.Series] = {}
        for ticker in tickers:
            try:
                df = self._provider.fetch_historical(ticker, start_date, end_date, "1d")
                col = price_col if price_col in df.columns else "close"
                s = df[col].dropna()
                s.index = pd.to_datetime(s.index, utc=True).normalize()
                price_data[ticker] = s
            except Exception as exc:
                raise BacktestError(f"Price fetch failed for {ticker}: {exc}") from exc

        # ── Build trading day index ───────────────────────────────────────────
        all_idx = pd.DatetimeIndex([])
        for s in price_data.values():
            all_idx = all_idx.union(s.index)
        all_idx = all_idx.sort_values()

        if all_idx.empty:
            raise BacktestError("No trading days found in date range.")

        # ── Sort transactions, resolve weekend/holiday dates ──────────────────
        scheduled = sorted(scheduled, key=lambda t: t.date)
        for txn in scheduled:
            target = pd.Timestamp(txn.date, tz="UTC").normalize()
            # Find nearest trading day >= target
            candidates = all_idx[all_idx >= target]
            if candidates.empty:
                txn.error = f"No trading day on or after {txn.date}"
                txn.actual_date = txn.date
            else:
                actual = candidates[0]
                txn.actual_date = actual.strftime("%Y-%m-%d")
                txn.date_adjusted = (actual != target)

        # ── Group transactions by actual execution date ───────────────────────
        txn_by_day: dict[pd.Timestamp, list[ScheduledTransaction]] = {}
        for txn in scheduled:
            if txn.error:
                continue
            day = pd.Timestamp(txn.actual_date, tz="UTC").normalize()
            txn_by_day.setdefault(day, []).append(txn)

        # ── Event loop ────────────────────────────────────────────────────────
        cash: float = initial_capital
        positions: dict[str, float] = {}        # {ticker: shares}
        cost_basis: dict[str, float] = {}        # {ticker: avg_price}
        lots: dict[str, deque] = {}              # FIFO: {ticker: deque([(date, price, shares)])}
        closed_positions: list[ClosedPosition] = []
        snapshots: list[PortfolioSnapshot] = []
        exec_transactions: list[Transaction] = []

        for day in all_idx:
            day_prices = {t: float(s.loc[day]) for t, s in price_data.items() if day in s.index}

            # Execute scheduled transactions for this day (BUY before SELL)
            if day in txn_by_day:
                day_txns = sorted(txn_by_day[day], key=lambda t: (0 if t.is_buy() else 1))
                for txn in day_txns:
                    price = day_prices.get(txn.ticker, 0.0)
                    if price <= 0:
                        txn.error = f"No price available on {txn.actual_date}"
                        continue

                    if txn.is_buy():
                        shares = math.floor(txn.amount_usd / price)
                        if shares < 1:
                            txn.error = (
                                f"Insufficient amount — minimum 1 share = ${price:,.2f}, "
                                f"got ${txn.amount_usd:,.2f}"
                            )
                            continue
                        actual_cost = shares * price
                        returned = txn.amount_usd - actual_cost
                        if actual_cost > cash + 1e-6:
                            txn.error = f"Insufficient cash — need ${actual_cost:,.2f}, have ${cash:,.2f}"
                            continue
                        cash -= actual_cost
                        # VWAP cost basis update
                        prev_qty = positions.get(txn.ticker, 0.0)
                        prev_cb  = cost_basis.get(txn.ticker, 0.0)
                        new_qty  = prev_qty + shares
                        cost_basis[txn.ticker] = (
                            (prev_qty * prev_cb + shares * price) / new_qty
                        )
                        positions[txn.ticker]  = new_qty

                        # FIFO: record buy lot
                        if txn.ticker not in lots:
                            lots[txn.ticker] = deque()
                        lots[txn.ticker].append((txn.actual_date, price, shares))

                        txn.executed_price  = price
                        txn.executed_shares = shares
                        txn.executed_value  = actual_cost
                        txn.returned_cash   = returned
                        txn.is_executed     = True

                        exec_transactions.append(Transaction(
                            ticker=txn.ticker, action="BUY",
                            quantity=float(shares), price=price,
                            timestamp=day.to_pydatetime(),
                        ))

                    else:  # SELL
                        held = positions.get(txn.ticker, 0.0)
                        sell_qty = txn.shares or 0
                        if sell_qty > held + 1e-6:
                            txn.error = f"Only {int(held)} shares held — cannot sell {sell_qty}"
                            continue
                        proceeds = sell_qty * price
                        cash += proceeds
                        new_qty = held - sell_qty
                        if new_qty < 1e-6:
                            positions.pop(txn.ticker, None)
                            cost_basis.pop(txn.ticker, None)
                        else:
                            positions[txn.ticker] = new_qty

                        # FIFO: match sell qty against buy lots
                        remaining = sell_qty
                        ticker_lots = lots.get(txn.ticker, deque())
                        while remaining > 0 and ticker_lots:
                            buy_date, buy_price, lot_qty = ticker_lots[0]
                            matched = min(lot_qty, remaining)
                            if matched >= lot_qty:
                                ticker_lots.popleft()
                            else:
                                ticker_lots[0] = (buy_date, buy_price, lot_qty - matched)
                            sell_ts = pd.Timestamp(txn.actual_date)
                            buy_ts  = pd.Timestamp(buy_date)
                            pnl     = (price - buy_price) * matched
                            cost    = buy_price * matched
                            closed_positions.append(ClosedPosition(
                                ticker=txn.ticker,
                                buy_date=buy_date,
                                sell_date=txn.actual_date,
                                shares=int(matched),
                                buy_price=buy_price,
                                sell_price=price,
                                realized_pnl=pnl,
                                realized_pnl_pct=(pnl / cost) if cost > 0 else 0.0,
                                holding_days=(sell_ts - buy_ts).days,
                            ))
                            remaining -= matched
                        if new_qty < 1e-6:
                            lots.pop(txn.ticker, None)

                        txn.executed_price  = price
                        txn.executed_shares = sell_qty
                        txn.executed_value  = proceeds
                        txn.is_executed     = True

                        exec_transactions.append(Transaction(
                            ticker=txn.ticker, action="SELL",
                            quantity=float(sell_qty), price=price,
                            timestamp=day.to_pydatetime(),
                        ))

            # Mark to market — build snapshot
            pos_objects = {
                t: Position(
                    ticker=t,
                    quantity=qty,
                    cost_basis=cost_basis.get(t, 0.0),
                    opened_at=day.to_pydatetime(),
                )
                for t, qty in positions.items()
            }
            market_value = sum(
                qty * day_prices.get(t, cost_basis.get(t, 0.0))
                for t, qty in positions.items()
            )
            nav = cash + market_value
            snapshots.append(PortfolioSnapshot(
                timestamp=day.to_pydatetime(),
                cash=cash,
                positions=pos_objects,
                nav=nav,
            ))

        # ── Benchmark ─────────────────────────────────────────────────────────
        benchmark_returns = None
        try:
            df_b = self._provider.fetch_historical(
                self._config.default_benchmark, start_date, end_date, "1d"
            )
            col = price_col if price_col in df_b.columns else "close"
            benchmark_returns = df_b[col].pct_change().dropna()
            benchmark_returns.name = self._config.default_benchmark
        except Exception:
            pass

        return BacktestResult(
            strategy_name="Multi-Date Transactions",
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            snapshots=snapshots,
            transactions=exec_transactions,
            benchmark_ticker=self._config.default_benchmark,
            benchmark_returns=benchmark_returns,
            closed_positions=closed_positions,
            total_realized_pnl=sum(cp.realized_pnl for cp in closed_positions),
        )
