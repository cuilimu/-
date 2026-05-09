"""
analytics/factor_investing — Factor-investing analytics sub-package.

End-to-end pipeline: load pre-computed Q-spread series from CapitalIQ →
compute summary statistics (annualised return, Sharpe, ACF, t-stat) →
cross-factor correlation matrix → optional per-quintile return loading →
FactorInvestingResult.

Public surface (import from here, not from sub-modules):

  FactorInvestingEngine   : orchestrates the full pipeline
  FactorInvestingResult   : top-level result container
  FactorStats             : per-factor summary statistics
  QuintileResult          : Q1–Q5 and Q-spread return series
  FactorCorrelationMatrix : pairwise Pearson correlation matrix
  CORE_FACTORS            : default list of seven factors
"""
from stock_engine.analytics.factor_investing.types import (
    CORE_FACTORS,
    FactorCorrelationMatrix,
    FactorInvestingResult,
    FactorStats,
    QuintileResult,
    ValidationResult,
)
from stock_engine.analytics.factor_investing.engine import FactorInvestingEngine
from stock_engine.analytics.factor_investing.live_loader import FACTOR_FF_LABEL
from stock_engine.analytics.factor_investing.validator import cross_validate

__all__ = [
    "FactorStats",
    "QuintileResult",
    "FactorCorrelationMatrix",
    "FactorInvestingResult",
    "ValidationResult",
    "FactorInvestingEngine",
    "CORE_FACTORS",
    "FACTOR_FF_LABEL",
    "cross_validate",
]
