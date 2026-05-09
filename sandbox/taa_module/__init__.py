"""
sandbox/taa_module — independent TAA prototype.

Self-contained module that implements the planned TAA page (passthrough /
factor-mean-variance) and the equal-weight linkage with the Allocation page.
Runs on mock data via `app_standalone.py`; no dependency on the main app's
session, theme, or Streamlit page routing.

Public surface (used by app_standalone.py and, eventually, the integrated
TAA page in ui/components/simple_mode/):

    from stock_engine.sandbox.taa_module import (
        FactorBucket, MiniUniverse, BucketAssignment,
        MockReturnsProvider,
        compute_factor_mvo, TAAResult,
        apply_equal_weights_v2,
        REGISTRY,
    )
"""
from stock_engine.sandbox.taa_module.types import (
    FactorBucket, BucketAssignment, MiniUniverse,
)
from stock_engine.sandbox.taa_module.mvo_core import solve_mvo, MVOResult
from stock_engine.sandbox.taa_module.mock_data import MockReturnsProvider
from stock_engine.sandbox.taa_module.factor_mvo import compute_factor_mvo, TAAResult
from stock_engine.sandbox.taa_module.strategies import (
    REGISTRY, PassthroughStrategy, FactorMVOStrategy,
)
from stock_engine.sandbox.taa_module.equal_weight import (
    apply_equal_weights_v2, explain_equal_weight_rule,
)
from stock_engine.sandbox.taa_module.rebalance import rebalance_at

__all__ = [
    "FactorBucket", "BucketAssignment", "MiniUniverse",
    "solve_mvo", "MVOResult",
    "MockReturnsProvider",
    "compute_factor_mvo", "TAAResult",
    "REGISTRY", "PassthroughStrategy", "FactorMVOStrategy",
    "apply_equal_weights_v2", "explain_equal_weight_rule",
    "rebalance_at",
]
