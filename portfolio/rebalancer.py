"""
portfolio/rebalancer.py — Rebalancing data models and pure calculation functions.
Same Day mode only. No session_state, no I/O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class RebalanceConfig:
    enabled: bool = False

    # Trigger type
    trigger: Literal['periodic', 'threshold', 'both'] = 'periodic'

    # Periodic settings
    frequency: Literal['monthly', 'quarterly', 'annual'] = 'quarterly'

    # Threshold settings — check every trading day (can be expensive for long
    # backtests with many tickers; consider reducing if performance is a concern)
    drift_threshold_pct: float = 5.0

    # Cost settings
    slippage_bps: float = 7.5  # per trade, basis points

    # Target weights: None = derive from initial dollar allocations at run time
    target_weights: Optional[dict[str, float]] = None


@dataclass
class RebalanceEvent:
    date: str                                               # YYYY-MM-DD
    trigger_type: Literal['periodic', 'threshold', 'both']
    trades: list[dict]                                      # [{ticker, action, shares, price, trade_value, slippage_cost}]
    pre_weights: dict[str, float]                           # weights before rebalance
    post_weights: dict[str, float]                          # weights after rebalance
    total_cost: float                                       # total slippage dollars
    drift_detected: Optional[dict[str, float]]              # {ticker: drift_pct} when threshold fired


# ── Pure calculation functions ─────────────────────────────────────────────────

def compute_target_weights(initial_allocations: dict[str, float]) -> dict[str, float]:
    """
    Derive target weights from initial dollar allocations.
    weight_i = allocation_i / sum(all allocations)
    Fixed throughout the backtest.
    """
    total = sum(initial_allocations.values())
    if total == 0:
        return {t: 0.0 for t in initial_allocations}
    return {t: v / total for t, v in initial_allocations.items()}


def compute_current_weights(
    positions: dict[str, float],   # {ticker: shares}
    prices: dict[str, float],
    cash: float,                   # cash excluded from weight denominator
) -> dict[str, float]:
    """
    Compute current portfolio weights by invested market value.
    Cash is excluded — weights sum to 1 across invested positions only.
    """
    values = {t: positions[t] * prices.get(t, 0.0) for t in positions}
    total = sum(values.values())
    if total == 0:
        return {t: 0.0 for t in positions}
    return {t: v / total for t, v in values.items()}


def check_threshold_trigger(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    threshold_pct: float,
) -> tuple[bool, dict[str, float]]:
    """
    Returns (triggered, drift_dict).
    triggered = True if ANY ticker drifts > threshold_pct from its target.
    drift_dict = {ticker: drift_pct} for all target tickers.
    """
    drift = {
        t: abs(current_weights.get(t, 0.0) - target_weights.get(t, 0.0)) * 100
        for t in target_weights
    }
    triggered = any(d > threshold_pct for d in drift.values())
    return triggered, drift


def compute_rebalance_trades(
    positions: dict[str, float],   # {ticker: shares}
    prices: dict[str, float],
    target_weights: dict[str, float],
    cash: float,
    slippage_bps: float,
) -> tuple[list[dict], float]:
    """
    Compute integer-share trades needed to restore target weights.

    Logic:
      total_value = Σ(shares × price) + cash
      target_value_i = total_value × target_weight_i
      delta_i = target_value_i − current_value_i
      shares_delta = floor(|delta| / price)
      slippage = trade_value × (bps / 10_000)

    Returns (trades_list, total_cost_dollars).
    Skips tickers where delta < 1 share.
    """
    total_value = (
        sum(positions.get(t, 0) * prices.get(t, 0.0) for t in target_weights) + cash
    )
    trades: list[dict] = []
    total_cost = 0.0

    for ticker, target_w in target_weights.items():
        price = prices.get(ticker, 0.0)
        if price <= 0:
            continue

        target_value = total_value * target_w
        current_value = positions.get(ticker, 0) * price
        delta = target_value - current_value

        if abs(delta) < price:
            continue

        shares_delta = math.floor(abs(delta) / price)
        if shares_delta == 0:
            continue

        action = 'buy' if delta > 0 else 'sell'
        trade_value = shares_delta * price
        cost = trade_value * (slippage_bps / 10_000)
        total_cost += cost

        trades.append({
            'ticker':        ticker,
            'action':        action,
            'shares':        shares_delta,
            'price':         price,
            'trade_value':   trade_value,
            'slippage_cost': round(cost, 2),
        })

    return trades, round(total_cost, 2)


def compute_periodic_dates(
    start_date: str,
    end_date: str,
    frequency: str,
) -> set[str]:
    """
    Generate rebalance trigger dates strictly after start_date and ≤ end_date.
    monthly  → first of each calendar month
    quarterly→ first of Jan/Apr/Jul/Oct
    annual   → first of each calendar year
    """
    freq_map = {'monthly': 'MS', 'quarterly': 'QS', 'annual': 'YS'}
    dates = pd.date_range(
        start=pd.Timestamp(start_date) + pd.DateOffset(days=1),
        end=pd.Timestamp(end_date),
        freq=freq_map[frequency],
    )
    return set(d.strftime('%Y-%m-%d') for d in dates)
