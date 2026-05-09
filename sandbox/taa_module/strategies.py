"""
strategies.py — strategy registry for the TAA selector.

Each strategy is a self-describing record. Adding a new TAA mode in the
future = drop one new dataclass instance into REGISTRY and write its
`run()` method. The UI iterates the registry to render the radio group.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from stock_engine.sandbox.taa_module.factor_mvo import (
    Pick, TAAResult, compute_factor_mvo, passthrough_result,
)
from stock_engine.sandbox.taa_module.types import MiniUniverse


class TAAStrategy(Protocol):
    id:    str
    label: str
    description: str
    available: bool

    def run(self, universe: MiniUniverse, provider, **kwargs) -> TAAResult: ...


@dataclass
class PassthroughStrategy:
    id:    str = "passthrough"
    label: str = "Passthrough (no constraint)"
    description: str = ("No tactical constraint applied. Equal-weight uses "
                        "1/N across all stocks; Allocation page is unaffected.")
    available: bool = True

    def run(self, universe: MiniUniverse, provider, **kwargs) -> TAAResult:
        return passthrough_result(universe, rf=kwargs.get("rf", 0.04))


@dataclass
class FactorMVOStrategy:
    id:    str = "factor_mvo"
    label: str = "Factor MVO"
    description: str = ("Run Markowitz mean-variance optimisation independently "
                        "within each factor bucket. Equal-weight: 1/k across "
                        "buckets × MVO weights within each bucket.")
    available: bool = True

    def run(self, universe: MiniUniverse, provider, **kwargs) -> TAAResult:
        return compute_factor_mvo(
            universe, provider,
            rf=kwargs.get("rf", 0.04),
            pick=kwargs.get("pick", "max_sharpe"),
            target_return=kwargs.get("target_return"),
            target_return_per_bucket=kwargs.get("target_return_per_bucket"),
            with_diagnostics=kwargs.get("with_diagnostics", False),
        )


@dataclass
class ComingSoonStrategy:
    """Placeholder for future TAA modes (book-value, momentum tilt, etc).
    Picked up by the UI as a disabled radio option."""
    id:    str
    label: str
    description: str
    available: bool = False

    def run(self, universe, provider, **kwargs) -> TAAResult:           # pragma: no cover
        raise NotImplementedError(f"{self.id} is not implemented yet")


# ── Registry ──────────────────────────────────────────────────────────────────
# Order = display order in the radio selector.
REGISTRY: list[TAAStrategy] = [
    PassthroughStrategy(),
    FactorMVOStrategy(),
    ComingSoonStrategy(
        id="factor_book_value",
        label="Factor Book-Value Weighting (coming soon)",
        description="Within each bucket, weight by inverse book-to-market ratio.",
    ),
    ComingSoonStrategy(
        id="factor_momentum",
        label="Factor Momentum Weighting (coming soon)",
        description="Within each bucket, weight by 12-1 month momentum score.",
    ),
]


def get_strategy(strategy_id: str) -> Optional[TAAStrategy]:
    return next((s for s in REGISTRY if s.id == strategy_id), None)
