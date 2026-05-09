"""
analytics/engine.py — Compute performance metrics from BacktestResult or live Portfolio.
All methods are stateless — pass data in, get numbers out.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.exceptions import AnalyticsError


@dataclass
class PerformanceMetrics:
    annualised_return: float
    annualised_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_start: Optional[pd.Timestamp]
    max_drawdown_end: Optional[pd.Timestamp]
    total_return: float
    calmar_ratio: Optional[float] = None
    benchmark_ticker: Optional[str] = None
    benchmark_total_return: Optional[float] = None
    information_ratio: Optional[float] = None


class AnalyticsEngine:
    def __init__(self, config: Config) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def compute(self, result: BacktestResult) -> PerformanceMetrics:  # ML_EXTENSIBLE: return prediction can be augmented by analytics/ml/
        dr = self.daily_returns(result)
        if len(dr) < 2:
            raise AnalyticsError("Need at least 2 data points to compute metrics")

        cr = self.cumulative_returns(result)
        mdd, mdd_start, mdd_end = self._max_drawdown(cr)
        total = float(cr.iloc[-1])

        ann_ret = self._annualised_return(dr)
        calmar = self._calmar_ratio(ann_ret, mdd)

        bench_total = None
        ir = None
        if result.benchmark_returns is not None and len(result.benchmark_returns) > 1:
            bench_cr = (1 + result.benchmark_returns).cumprod() - 1
            bench_total = float(bench_cr.iloc[-1])
            try:
                ir = self._information_ratio(dr, result.benchmark_returns)
            except Exception:
                pass

        metrics = PerformanceMetrics(
            annualised_return=ann_ret,
            annualised_volatility=self._annualised_volatility(dr),
            sharpe_ratio=self._sharpe_ratio(dr),
            max_drawdown=mdd,
            max_drawdown_start=mdd_start,
            max_drawdown_end=mdd_end,
            total_return=total,
            calmar_ratio=calmar,
            benchmark_ticker=result.benchmark_ticker,
            benchmark_total_return=bench_total,
            information_ratio=ir,
        )
        result.summary = {
            "total_return": f"{total:.1%}",
            "annualised_return": f"{ann_ret:.1%}",
            "volatility": f"{metrics.annualised_volatility:.1%}",
            "sharpe": f"{metrics.sharpe_ratio:.2f}",
            "max_drawdown": f"{mdd:.1%}",
            "calmar": "∞" if calmar is not None and np.isinf(calmar) else (
                f"{calmar:.2f}" if calmar is not None else "N/A"
            ),
        }
        return metrics

    # ------------------------------------------------------------------
    # Intermediate series
    # ------------------------------------------------------------------

    def daily_returns(self, result: BacktestResult) -> pd.Series:
        navs = pd.Series(
            [s.nav for s in result.snapshots],
            index=[s.timestamp for s in result.snapshots],
            name="nav",
        )
        return navs.pct_change().dropna()

    def cumulative_returns(self, result: BacktestResult) -> pd.Series:
        dr = self.daily_returns(result)
        return (1 + dr).cumprod() - 1

    def drawdown_series(self, result: BacktestResult) -> pd.Series:
        cr = self.cumulative_returns(result)
        wealth = 1 + cr
        peak = wealth.cummax()
        return (wealth - peak) / peak

    # ------------------------------------------------------------------
    # Scalar metrics
    # ------------------------------------------------------------------

    def _annualised_return(self, daily_returns: pd.Series) -> float:
        n = len(daily_returns)
        if n < 2:
            return 0.0
        total = (1 + daily_returns).prod()
        return float(total ** (self._config.annualisation_factor / n) - 1)

    def _annualised_volatility(self, daily_returns: pd.Series) -> float:
        return float(daily_returns.std() * np.sqrt(self._config.annualisation_factor))

    def _sharpe_ratio(self, daily_returns: pd.Series) -> float:
        excess = daily_returns - self._config.risk_free_rate / self._config.annualisation_factor
        vol = excess.std()
        if vol == 0:
            return 0.0
        return float(excess.mean() / vol * np.sqrt(self._config.annualisation_factor))

    def _max_drawdown(
        self, cumulative_returns: pd.Series
    ) -> tuple[float, Optional[pd.Timestamp], Optional[pd.Timestamp]]:
        wealth = 1 + cumulative_returns
        peak = wealth.cummax()
        dd = (wealth - peak) / peak
        mdd = float(dd.min())
        end_idx = dd.idxmin()
        peak_idx = wealth[:end_idx].idxmax()
        return mdd, peak_idx, end_idx

    def _calmar_ratio(
        self, annualised_return: Optional[float], max_drawdown: Optional[float]
    ) -> Optional[float]:
        """Annualised return divided by abs(max drawdown). Returns inf for zero drawdown."""
        if annualised_return is None or max_drawdown is None:
            return None
        if np.isnan(annualised_return) or np.isnan(max_drawdown):
            return None
        if max_drawdown == 0.0:
            return float("inf") if annualised_return > 0 else None
        return float(annualised_return / abs(max_drawdown))

    def _information_ratio(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
    ) -> float:
        aligned = portfolio_returns.align(benchmark_returns, join="inner")
        active = aligned[0] - aligned[1]
        if active.std() == 0:
            return 0.0
        return float(active.mean() / active.std() * np.sqrt(self._config.annualisation_factor))
