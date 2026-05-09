"""
analytics/factor/methods/__init__.py
Central registry.  To add a new method:
  1. Create methods/mymethod.py implementing AnalysisMethod
  2. Add one line here: METHOD_REGISTRY["mymethod"] = MyMethod()
"""
from stock_engine.analytics.factor.methods.base import AnalysisMethod, MethodResult
from stock_engine.analytics.factor.methods.ols import OLSMethod, RobustOLSMethod

METHOD_REGISTRY: dict[str, AnalysisMethod] = {
    "ols":    OLSMethod(),
    "robust": RobustOLSMethod(),
    # Future:
    # "ridge":  RidgeMethod(),
    # "lasso":  LassoMethod(),
    # "rf":     RandomForestMethod(),
    # "gbm":    GradientBoostingMethod(),
}

__all__ = ["AnalysisMethod", "MethodResult", "METHOD_REGISTRY"]
