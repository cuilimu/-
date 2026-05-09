"""
types.py — minimal data classes used by the sandbox.

`FactorBucket` is re-exported from the main project so the sandbox stays
naming-compatible with the real Universe; if the import fails (e.g. someone
copies the module out of the repo) we fall back to a local enum with the
same string values.

`MiniUniverse` is a deliberately light analogue of
`stock_engine.portfolio.models.Universe` — just (ticker, bucket) pairs
plus by-bucket lookup. The integrator writes a one-liner adapter from
the real `Universe` to `MiniUniverse`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

try:
    from stock_engine.portfolio.models import FactorBucket  # noqa: F401
except Exception:                                            # pragma: no cover
    from enum import Enum

    class FactorBucket(str, Enum):                            # type: ignore[no-redef]
        GROWTH      = "growth"
        FIN_COND    = "fin_cond"
        INFLATION   = "inflation"
        DIVERSIFIER = "diversifier"
        UNASSIGNED  = "unassigned"


@dataclass
class BucketAssignment:
    ticker: str
    bucket: FactorBucket


@dataclass
class MiniUniverse:
    assignments: List[BucketAssignment] = field(default_factory=list)

    @property
    def tickers(self) -> List[str]:
        return [a.ticker for a in self.assignments]

    def by_bucket(self, bucket: FactorBucket) -> List[str]:
        return [a.ticker for a in self.assignments if a.bucket == bucket]

    def buckets_in_use(self) -> List[FactorBucket]:
        seen, out = set(), []
        for a in self.assignments:
            if a.bucket in seen:
                continue
            seen.add(a.bucket)
            out.append(a.bucket)
        return out
