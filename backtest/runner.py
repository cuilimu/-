"""
backtest/runner.py — Event-driven backtesting loop.
Supports manual dollar allocation per ticker (Module 2) and PortfolioGroup (Module 3).
"""

import math
from typing import Callable, Optional

import pandas as pd

from stock_engine.backtest.base import BacktestResult, Strategy
from stock_engine.config import Config
from stock_engine.data.base import DataProvider
from stock_engine.exceptions import BacktestError
from stock_engine.portfolio.models import PortfolioGroup, TickerAllocation
from stock_engine.portfolio.portfolio import Portfolio
from stock_engine.portfolio.rebalancer import (
    RebalanceConfig, RebalanceEvent,
    compute_target_weights, compute_current_weights,
    check_threshold_trigger, compute_rebalance_trades,
    compute_periodic_dates,
)


class BacktestRunner:
    def __init__(
        self,
        strategy: Optional[Strategy],
        data_provider: DataProvider,
        config: Config,
    ) -> None:
        self._strategy = strategy
        self._data_provider = data_provider
        self._config = config

    def run(
        self,
        tickers: list[str],
        start: str,
        end: str,
        allocations: Optional[list[TickerAllocation]] = None,
        rebalance_config: Optional[RebalanceConfig] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> BacktestResult:
        """
        allocations: if provided, use dollar amounts (Module 2).
                     if None, fall back to equal-weight.
        rebalance_config: if provided and enabled, fire rebalance events during loop.
        """
        if not tickers:
            raise BacktestError("tickers list is empty")

        end = self._config.effective_end_date() if self._config.use_latest_end_date else end
        data = self._fetch_aligned_data(tickers, start, end, progress_cb=progress_cb)
        if data.empty:
            raise BacktestError(f"No data for {tickers} between {start} and {end}")

        portfolio = Portfolio(self._config)
        snapshots = []
        dates = data.index.tolist()
        price_col = self._config.price_field.lower()

        # ── Initial buy at first bar ──────────────────────────────────
        first_prices = self._prices_at(data, dates[0], price_col)

        alloc_map: dict[str, float] = {}
        if allocations:
            for a in allocations:
                alloc_map[a.ticker] = a.allocated_dollars
        else:
            # Equal-weight fallback
            per_ticker = portfolio.cash / len(tickers)
            alloc_map = {t: per_ticker for t in tickers}

        for ticker in tickers:
            price = first_prices.get(ticker, 0)
            if price <= 0:
                continue
            dollars = alloc_map.get(ticker, 0)
            qty = math.floor(dollars / price)   # no fractional shares (Module 2)
            if qty > 0 and portfolio.cash >= qty * price:
                portfolio.buy(ticker, float(qty), price, dates[0].to_pydatetime())

        # Update TickerAllocation with actual fills
        if allocations:
            for a in allocations:
                pos = portfolio.positions.get(a.ticker)
                if pos:
                    a.shares_bought = pos.quantity
                    a.price_used = pos.cost_basis

        snapshots.append(portfolio.snapshot(first_prices, dates[0].to_pydatetime()))

        # ── Rebalance setup ───────────────────────────────────────────
        rb = rebalance_config
        rebalance_events: list[RebalanceEvent] = []
        target_weights: dict[str, float] = {}
        periodic_dates: set[str] = set()

        if rb and rb.enabled and alloc_map:
            target_weights = rb.target_weights or compute_target_weights(alloc_map)
            if rb.trigger in ('periodic', 'both'):
                periodic_dates = compute_periodic_dates(start, end, rb.frequency)

        # ── Event loop ────────────────────────────────────────────────
        pending_signals: dict[str, float] = {}
        for i, date_ts in enumerate(dates[1:], start=1):
            prices = self._prices_at(data, date_ts, price_col)
            date_str = date_ts.strftime('%Y-%m-%d')

            # ── Rebalance check ───────────────────────────────────────
            # NOTE: threshold check runs every trading day — can be expensive
            # for very long backtests with many tickers.
            if rb and rb.enabled and target_weights:
                fire_periodic = date_str in periodic_dates
                fire_threshold = False
                drift_info: dict[str, float] = {}

                if rb.trigger in ('threshold', 'both'):
                    pos_shares = {t: p.quantity for t, p in portfolio.positions.items()}
                    curr_w = compute_current_weights(pos_shares, prices, portfolio.cash)
                    fire_threshold, drift_info = check_threshold_trigger(
                        curr_w, target_weights, rb.drift_threshold_pct
                    )

                if fire_periodic or fire_threshold:
                    pos_shares = {t: p.quantity for t, p in portfolio.positions.items()}
                    pre_w = compute_current_weights(pos_shares, prices, portfolio.cash)
                    trades, cost = compute_rebalance_trades(
                        pos_shares, prices, target_weights,
                        portfolio.cash, rb.slippage_bps,
                    )

                    if trades:
                        dt = date_ts.to_pydatetime()
                        for trade in trades:
                            try:
                                if trade['action'] == 'buy':
                                    portfolio.buy(
                                        trade['ticker'], float(trade['shares']),
                                        trade['price'], dt,
                                        commission=trade['slippage_cost'],
                                    )
                                else:
                                    portfolio.sell(
                                        trade['ticker'], float(trade['shares']),
                                        trade['price'], dt,
                                        commission=trade['slippage_cost'],
                                    )
                            except Exception:
                                pass

                        pos_shares = {t: p.quantity for t, p in portfolio.positions.items()}
                        post_w = compute_current_weights(pos_shares, prices, portfolio.cash)

                        if fire_periodic and fire_threshold:
                            ttype: str = 'both'
                        elif fire_threshold:
                            ttype = 'threshold'
                        else:
                            ttype = 'periodic'

                        rebalance_events.append(RebalanceEvent(
                            date=date_str,
                            trigger_type=ttype,
                            trades=trades,
                            pre_weights=pre_w,
                            post_weights=post_w,
                            total_cost=cost,
                            drift_detected=drift_info if fire_threshold else None,
                        ))

            if pending_signals and self._strategy is not None:
                self._execute_signals(pending_signals, prices, portfolio, date_ts.to_pydatetime())

            if self._strategy is not None:
                try:
                    pending_signals = self._strategy.generate_signals(data.iloc[: i + 1])
                except Exception:
                    pending_signals = {}

            snapshots.append(portfolio.snapshot(prices, date_ts.to_pydatetime()))

        benchmark_returns = self._fetch_benchmark(start, end)

        return BacktestResult(
            strategy_name=self._strategy.name if self._strategy else "Buy & Hold",
            tickers=tickers,
            start_date=start,
            end_date=end,
            initial_capital=self._config.initial_capital,
            snapshots=snapshots,
            transactions=portfolio.transactions,
            benchmark_ticker=self._config.default_benchmark,
            benchmark_returns=benchmark_returns,
            rebalance_events=rebalance_events,
            total_rebalance_cost=sum(e.total_cost for e in rebalance_events),
        )

    def run_group(
        self,
        group: PortfolioGroup,
        start: str,
        end: str,
        rebalance_config: Optional[RebalanceConfig] = None,
    ) -> BacktestResult:
        """Run an independent backtest for a PortfolioGroup (Module 3)."""
        cfg = Config(
            initial_capital=group.starting_capital,
            price_field=self._config.price_field,
            default_frequency=self._config.default_frequency,
            annualisation_factor=self._config.annualisation_factor,
            default_benchmark=self._config.default_benchmark,
            cache_dir=self._config.cache_dir,
            cache_enabled=self._config.cache_enabled,
            use_latest_end_date=self._config.use_latest_end_date,
            default_start_date=self._config.default_start_date,
            default_end_date=self._config.default_end_date,
        )
        runner = BacktestRunner(self._strategy, self._data_provider, cfg)
        result = runner.run(
            tickers=group.tickers,
            start=start,
            end=end,
            allocations=group.allocations,
            rebalance_config=rebalance_config,
        )
        result.strategy_name = group.name
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_aligned_data(
        self,
        tickers: list[str],
        start: str,
        end: str,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> pd.DataFrame:
        freq = self._config.default_frequency
        frames = {}
        n = len(tickers)
        for i, ticker in enumerate(tickers):
            if progress_cb:
                progress_cb(i, n, ticker)
            try:
                df = self._data_provider.fetch_historical(ticker, start, end, frequency=freq)
                frames[ticker] = df
            except Exception as exc:
                raise BacktestError(f"Data fetch failed for {ticker}: {exc}") from exc
        if progress_cb:
            progress_cb(n, n, "")
        if not frames:
            return pd.DataFrame()

        price_col = self._config.price_field.lower()

        price_series = {}
        open_series = {}
        for t, f in frames.items():
            # Defensive tz-strip: ensure all series are tz-naive before concat.
            if isinstance(f.index, pd.DatetimeIndex) and f.index.tz is not None:
                f.index = f.index.tz_convert(None)
            col = price_col if price_col in f.columns else "close"
            price_series[t] = f[col].rename(t)
            open_col = "open" if "open" in f.columns else col
            open_series[t] = f[open_col].rename(f"open_{t}")

        aligned = pd.concat(price_series.values(), axis=1).ffill()
        open_aligned = pd.concat(open_series.values(), axis=1).ffill()
        return pd.concat([aligned, open_aligned], axis=1).dropna(how="all")

    def _prices_at(self, data, date_ts, price_col: str) -> dict[str, float]:
        row = data.loc[date_ts]
        prices = {}
        for col in data.columns:
            if col.startswith("open_"):
                continue
            ticker = col
            open_col = f"open_{ticker}"
            val = row.get(open_col) if open_col in data.columns else None
            if val is None or pd.isna(val):
                val = row.get(ticker)
            if val is not None and not pd.isna(val):
                prices[ticker] = float(val)
        return prices

    def _execute_signals(self, signals, prices, portfolio, timestamp) -> None:
        nav = portfolio.nav(prices)
        for ticker, signal in signals.items():
            price = prices.get(ticker, 0)
            if price <= 0:
                continue
            target_value = nav * max(0.0, signal)
            current_pos = portfolio.positions.get(ticker)
            current_value = (current_pos.quantity * price) if current_pos else 0.0
            diff = target_value - current_value
            qty = math.floor(abs(diff) / price)
            if qty < 1:
                continue
            try:
                if diff > 0:
                    portfolio.buy(ticker, float(qty), price, timestamp)
                else:
                    portfolio.sell(ticker, float(qty), price, timestamp)
            except Exception:
                pass

    def _fetch_benchmark(self, start: str, end: str):
        try:
            df = self._data_provider.fetch_historical(
                self._config.default_benchmark, start, end,
                frequency=self._config.default_frequency,
            )
            price_col = self._config.price_field.lower()
            col = price_col if price_col in df.columns else "close"
            returns = df[col].pct_change().dropna()
            returns.name = self._config.default_benchmark
            return returns
        except Exception:
            return None
