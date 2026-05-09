"""
analytics/factor  —  Factor analysis sub-package.

Public surface (import from here, not from sub-modules):
  ReturnWorkspace  : the variable namespace / data panel
  load_into_workspace : populate workspace from BacktestResult(s) + FF factors
  execute          : run one STATA-style command string
  CommandOutput    : result container (kind, content, metadata)
  MethodResult     : regression result dataclass
  METHOD_REGISTRY  : dict of registered analysis methods
"""
from stock_engine.analytics.factor.workspace import ReturnWorkspace
from stock_engine.analytics.factor.loader import load_into_workspace
from stock_engine.analytics.factor.commands import execute, CommandOutput
from stock_engine.analytics.factor.methods import MethodResult, METHOD_REGISTRY

__all__ = [
    "ReturnWorkspace",
    "load_into_workspace",
    "execute",
    "CommandOutput",
    "MethodResult",
    "METHOD_REGISTRY",
]
