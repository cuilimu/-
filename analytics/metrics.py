"""
analytics/metrics.py — Constituent and multi-period return calculations.
All functions take BacktestResult as input — no direct UI or data fetching.
Prices come from DataProvider via the runner; lookbacks use cached parquet where available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.data.base import DataProvider
from stock_engine.data.yfinance_provider import normalize_datetime_index


# ── Constituent returns ────────────────────────────────────────────────────────

@dataclass
class ConstituentReturn:
    ticker: str
    exchange: str
    base_date: str            # actual base date used (first buy date or global start)
    start_price: float
    end_price: float
    total_return_pct: float   # (end - start) / start * 100


def compute_constituent_returns(
    result: BacktestResult,
    provider: DataProvider,
    config: Config,
) -> list[ConstituentReturn]:
    """
    For each ticker: compute total return % from its actual first BUY price to
    the last available price on or before end_date.

    start_price:
      Multi-Date mode — taken from the first executed BUY transaction's price.
      Same-Day mode   — taken from the position cost_basis in the first snapshot
                        that contains this ticker (== the initial open-bar buy price).

    end_price:
      Fetched via lookback window (date-7 → date+1) then filtered to the last
      trading day <= end_date, matching the same logic as fetch_price_at.
      Falls back to the position's cost_basis in the last snapshot on failure.

    Sorted descending by total_return_pct.
    """
    output: list[ConstituentReturn] = []
    price_col = config.price_field.lower()

    for ticker in result.tickers:
        try:
            # ── Start price: from the backtest result itself ───────────────
            ticker_buys = [
                tx for tx in result.transactions
                if tx.ticker == ticker and tx.action.upper() == "BUY"
            ]
            if ticker_buys:
                # Multi-Date: price of the earliest executed buy
                first_buy = min(ticker_buys, key=lambda tx: tx.timestamp)
                base_date  = first_buy.timestamp.strftime("%Y-%m-%d")
                start_price = float(first_buy.price)
            else:
                # Same-Day: cost_basis from the first snapshot holding this ticker
                base_date = result.start_date
                first_snap = next(
                    (s for s in result.snapshots if ticker in s.positions),
                    None,
                )
                start_price = (
                    float(first_snap.positions[ticker].cost_basis)
                    if first_snap else 0.0
                )

            # ── End price: lookback window to last trading day <= end_date ─
            end_dt   = pd.Timestamp(result.end_date)
            start_lb = (end_dt - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            end_lb   = (end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                df_end = provider.fetch_historical(ticker, start_lb, end_lb, "1d")
                if isinstance(df_end.index, pd.DatetimeIndex) and df_end.index.tz is not None:
                    df_end.index = df_end.index.tz_convert(None)
                col = price_col if price_col in df_end.columns else "close"
                end_dt_naive = end_dt.tz_localize(None) if end_dt.tzinfo is not None else end_dt
                available = df_end.index[df_end.index <= end_dt_naive]
                if not available.empty:
                    end_price = float(df_end.loc[available[-1], col])
                else:
                    end_price = 0.0
            except Exception:
                end_price = 0.0

            # Fallbacks
            if start_price <= 0:
                pos = result.snapshots[-1].positions.get(ticker)
                start_price = float(pos.cost_basis) if pos else 0.0
            if end_price <= 0:
                pos = result.snapshots[-1].positions.get(ticker)
                end_price = float(pos.cost_basis) if pos else start_price

            ret_pct = (
                (end_price - start_price) / start_price * 100
                if start_price > 0 else 0.0
            )

            # Exchange from yfinance fast_info
            exchange = ""
            try:
                import yfinance as yf
                info = yf.Ticker(ticker).fast_info
                exchange = getattr(info, "exchange", "") or ""
            except Exception:
                pass

            output.append(ConstituentReturn(
                ticker=ticker,
                exchange=exchange,
                base_date=base_date,
                start_price=start_price,
                end_price=end_price,
                total_return_pct=ret_pct,
            ))
        except Exception:
            output.append(ConstituentReturn(
                ticker=ticker,
                exchange="",
                base_date=result.start_date,
                start_price=0.0,
                end_price=0.0,
                total_return_pct=0.0,
            ))

    return sorted(output, key=lambda x: x.total_return_pct, reverse=True)


# ── Multi-period return table ──────────────────────────────────────────────────

_PERIOD_COLS = ["Ticker", "Last", "Chg", "%Chg", "WTD%", "MTD%", "1Mo%", "3Mo%", "YTD%", "12Mo%"]


def compute_multi_period_returns(  # ML_EXTENSIBLE: expected return vector replaceable by analytics/ml/
    result: BacktestResult,
    provider: DataProvider,
    config: Config,
) -> pd.DataFrame:
    """
    Returns a DataFrame with columns = _PERIOD_COLS.
    All periods anchored to backtest end_date, looking backwards.
    Cells with insufficient history show None (rendered as "—" by UI).
    """
    end_dt  = pd.Timestamp(result.end_date)
    freq    = "1d"    # always daily for price lookups
    price_col = config.price_field.lower()

    # Build lookback dates
    lookbacks: dict[str, Optional[pd.Timestamp]] = {
        "prev_day": _prior_trading_day(end_dt, 1),
        "wtd":      _prior_monday(end_dt),
        "mtd":      _month_start(end_dt),
        "1mo":      _offset_months(end_dt, -1),
        "3mo":      _offset_months(end_dt, -3),
        "ytd":      _year_start(end_dt),
        "12mo":     _offset_months(end_dt, -12),
    }

    rows = []
    for ticker in result.tickers:
        # Fetch a wide window covering all lookbacks in one call
        earliest = min(v for v in lookbacks.values() if v is not None)
        fetch_start = (earliest - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        fetch_end   = (end_dt + pd.Timedelta(days=7)).strftime("%Y-%m-%d")

        try:
            df = provider.fetch_historical(ticker, fetch_start, fetch_end, freq)
            col = price_col if price_col in df.columns else "close"
            # normalize_datetime_index strips tz so all comparisons are tz-naive
            price_series = normalize_datetime_index(df[col].dropna())
        except Exception:
            price_series = pd.Series(dtype=float)

        def _get_price(target_dt: Optional[pd.Timestamp]) -> Optional[float]:
            """Get nearest prior price to target_dt. Both series and target are tz-naive."""
            if target_dt is None or price_series.empty:
                return None
            # Ensure target is tz-naive to match normalized price_series index
            target = target_dt.tz_localize(None) if target_dt.tz is not None else target_dt
            candidates = price_series.index[price_series.index <= target]
            if candidates.empty:
                return None
            return float(price_series[candidates[-1]])

        end_price  = _get_price(end_dt)
        prev_price = _get_price(lookbacks["prev_day"])

        def _ret(base_dt: Optional[pd.Timestamp]) -> Optional[float]:
            base = _get_price(base_dt)
            if base is None or base <= 0 or end_price is None:
                return None
            # Guard: base_dt must be within backtest period
            if base_dt is not None and base_dt < pd.Timestamp(result.start_date).tz_localize(
                base_dt.tz if base_dt.tz else None
            ):
                return None
            return (end_price - base) / base * 100

        chg = (end_price - prev_price) if (end_price and prev_price) else None
        pct_chg = (chg / prev_price * 100) if (chg is not None and prev_price) else None

        rows.append({
            "Ticker": ticker,
            "Last":   end_price,
            "Chg":    chg,
            "%Chg":   pct_chg,
            "WTD%":   _ret(lookbacks["wtd"]),
            "MTD%":   _ret(lookbacks["mtd"]),
            "1Mo%":   _ret(lookbacks["1mo"]),
            "3Mo%":   _ret(lookbacks["3mo"]),
            "YTD%":   _ret(lookbacks["ytd"]),
            "12Mo%":  _ret(lookbacks["12mo"]),
        })

    return pd.DataFrame(rows, columns=_PERIOD_COLS)


# ── Date helpers ───────────────────────────────────────────────────────────────


# ── Date helpers ───────────────────────────────────────────────────────────────

def _prior_trading_day(dt: pd.Timestamp, n: int = 1) -> pd.Timestamp:
    """Return the nth prior calendar day (weekends count; not exchange-aware)."""
    result = dt - pd.Timedelta(days=1)
    for _ in range(n - 1):
        result -= pd.Timedelta(days=1)
    return result


def _prior_monday(dt: pd.Timestamp) -> pd.Timestamp:
    """
    Return the Monday that opened the current week.
    If dt IS Monday, return the prior Monday (prior week's open),
    so WTD% captures the full current-week move from prior close.
    """
    monday = dt - pd.Timedelta(days=dt.weekday())   # Monday of current week
    if monday == dt:                                  # dt is Monday → use prior week
        monday = dt - pd.Timedelta(days=7)
    return monday


def _month_start(dt: pd.Timestamp) -> pd.Timestamp:
    return dt.replace(day=1)


def _year_start(dt: pd.Timestamp) -> pd.Timestamp:
    return dt.replace(month=1, day=1)


def _offset_months(dt: pd.Timestamp, months: int) -> Optional[pd.Timestamp]:
    try:
        return dt + pd.DateOffset(months=months)
    except Exception:
        return None
