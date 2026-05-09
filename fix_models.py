"""
Run this once from the stock_engine directory:
    python fix_models.py
It rewrites portfolio/models.py with the correct content including all new AA classes.
"""
import pathlib

content = '''"""
portfolio/models.py — Core data models for portfolio state.

Existing classes (unchanged):
  Position, Transaction, PortfolioSnapshot, TickerAllocation,
  PortfolioGroup, ScheduledTransaction

New classes (Simple Mode AA workflow):
  FactorBucket, AllocationMethod, CandidateStatus,
  AssetMeta, Universe, RiskResult, PortfolioCandidate,
  TAAScenario, ResearchSession
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


# ── Existing classes (unchanged) ───────────────────────────────────────────────

@dataclass
class Position:
    ticker: str
    quantity: float
    cost_basis: float
    opened_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_cost(self) -> float:
        return self.quantity * self.cost_basis


@dataclass
class Transaction:
    ticker: str
    action: str           # "BUY" | "SELL"
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    cash: float
    positions: dict[str, Position]
    nav: float
    daily_return: Optional[float] = None
    cumulative_return: Optional[float] = None


@dataclass
class TickerAllocation:
    """Dollar allocation for one ticker within a group."""
    ticker: str
    allocated_dollars: float
    shares_bought: float = 0.0
    price_used: float = 0.0

    @property
    def actual_weight(self) -> float:
        return 0.0  # computed externally after all allocations are known


@dataclass
class PortfolioGroup:
    """
    Independent portfolio for group comparison (Module 3).
    Each group runs its own BacktestResult -- no shared state.
    """
    name: str
    starting_capital: float
    allocations: list[TickerAllocation] = field(default_factory=list)

    @property
    def tickers(self) -> list[str]:
        return [a.ticker for a in self.allocations]

    @property
    def total_allocated(self) -> float:
        return sum(a.allocated_dollars for a in self.allocations)


@dataclass
class ScheduledTransaction:
    """
    User-defined transaction for Multi-Date mode.
    Created in UI, executed by MultiDateRunner.
    Completely separate from the existing Transaction (execution record).
    """
    ticker: str
    action: Literal["BUY", "SELL"]
    date: str                           # YYYY-MM-DD, target execution date
    amount_usd: Optional[float]         # Buy: dollar amount; None for Sell
    shares: Optional[int]               # Sell: explicit shares; None for Buy
    price_field: str                    # inherits global price field setting

    preview_price: Optional[float]      = None
    preview_shares: Optional[int]       = None

    executed_price: Optional[float]     = None
    executed_shares: Optional[int]      = None
    executed_value: Optional[float]     = None
    returned_cash: Optional[float]      = None
    actual_date: Optional[str]          = None   # may differ if weekend/holiday
    date_adjusted: bool                 = False
    is_executed: bool                   = False
    error: Optional[str]                = None

    txn_id: int                         = 0

    def display_date(self) -> str:
        return self.actual_date or self.date

    def is_buy(self) -> bool:
        return self.action == "BUY"


# ── Simple Mode AA Workflow -- New Data Classes ────────────────────────────────

class FactorBucket(str, Enum):
    GROWTH      = "growth"
    FIN_COND    = "fin_cond"
    INFLATION   = "inflation"
    DIVERSIFIER = "diversifier"
    UNASSIGNED  = "unassigned"


class AllocationMethod(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    MANUAL       = "manual"
    MVO          = "mvo"          # placeholder -- not yet implemented
    RISK_PARITY  = "risk_parity"  # placeholder -- not yet implemented


class CandidateStatus(str, Enum):
    NOT_RUN  = "not_run"   # weights set, backtest not executed
    COMPUTED = "computed"  # backtest + risk results up to date
    STALE    = "stale"     # weights changed after results were computed


@dataclass
class AssetMeta:
    """Metadata for one ticker in the universe."""
    ticker:        str
    asset_class:   Literal["equity", "bond", "commodity", "cash", "etf"] = "equity"
    factor_bucket: FactorBucket = FactorBucket.UNASSIGNED
    sector:        Optional[str] = None
    region:        Optional[str] = None
    user_tags:     List[str]     = field(default_factory=list)


@dataclass
class Universe:
    """Locked asset universe for one Simple Mode session."""
    tickers:        List[str]            = field(default_factory=list)
    assets:         Dict[str, AssetMeta] = field(default_factory=dict)
    purchase_date:  Optional[date]       = None   # set in Page 1, locked downstream
    backtest_start: Optional[date]       = None
    backtest_end:   Optional[date]       = None

    def assigned(self) -> List[str]:
        return [t for t, m in self.assets.items()
                if m.factor_bucket != FactorBucket.UNASSIGNED]

    def by_bucket(self, bucket: FactorBucket) -> List[str]:
        return [t for t, m in self.assets.items() if m.factor_bucket == bucket]


@dataclass
class RiskResult:
    """
    Output of analytics/risk.py for one PortfolioCandidate.
    VaR/CVaR are 1-day, negative decimals (e.g. -0.0182).
    # ML_EXTENSIBLE: var_parametric/cvar_parametric replaceable by ML forecasts.
    """
    var_95_param:  Optional[float] = None
    var_99_param:  Optional[float] = None
    cvar_95_param: Optional[float] = None
    cvar_99_param: Optional[float] = None

    var_95_hist:   Optional[float] = None
    var_99_hist:   Optional[float] = None
    cvar_95_hist:  Optional[float] = None
    cvar_99_hist:  Optional[float] = None

    max_drawdown:          Optional[float] = None
    max_drawdown_start:    Optional[date]  = None
    max_drawdown_end:      Optional[date]  = None
    max_drawdown_recovery: Optional[int]   = None

    # list of dicts: period/peak_date/trough_date/depth/recovery_days
    drawdown_events: List[Dict[str, Any]] = field(default_factory=list)

    # list of dicts: scenario_name/period/portfolio_return/bm_return/excess_return
    stress_results: List[Dict[str, Any]] = field(default_factory=list)

    tracking_error:    Optional[float] = None
    information_ratio: Optional[float] = None
    calmar_ratio:      Optional[float] = None

    factor_betas: Dict[str, float] = field(default_factory=dict)
    factor_r2:    Optional[float]  = None

    annualised_vol: Optional[float] = None


@dataclass
class PortfolioCandidate:
    """
    One allocation strategy within a ResearchSession.
    Weights normalised to sum to 1.0.
    """
    candidate_id: str
    label:        str
    method:       AllocationMethod        = AllocationMethod.EQUAL_WEIGHT
    weights:      Dict[str, float]        = field(default_factory=dict)
    constraints:  Dict[str, Any]          = field(default_factory=dict)

    backtest_result: Optional[Any]        = None   # backtest.base.BacktestResult
    risk_result:     Optional[RiskResult] = None

    status: CandidateStatus = CandidateStatus.NOT_RUN

    def mark_stale(self) -> None:
        if self.backtest_result is not None or self.risk_result is not None:
            self.status = CandidateStatus.STALE

    def mark_computed(self) -> None:
        self.status = CandidateStatus.COMPUTED

    def set_weights(self, weights: Dict[str, float]) -> None:
        self.weights = weights
        self.mark_stale()

    @property
    def is_stale(self) -> bool:
        return self.status == CandidateStatus.STALE


@dataclass
class TAAScenario:
    """
    Tactical deviations from SAA baseline.
    # ML_EXTENSIBLE: active_scenario/adjustments replaceable by ML signal module.
    """
    base_saa_id:     str
    active_scenario: str              = "base"
    adjustments:     Dict[str, float] = field(default_factory=dict)
    taa_weights:     Dict[str, float] = field(default_factory=dict)
    rationale:       str              = ""
    horizon_months:  int              = 3
    backtest_result: Optional[Any]    = None

    # FRED series snapshot: CPIAUCSL/CPILFESL/UNRATE/T10Y2Y/GDP/BAMLH0A0HYM2
    macro_snapshot: Dict[str, float] = field(default_factory=dict)


@dataclass
class ResearchSession:
    """
    Single source of truth for one Simple Mode AA research session.
    All 6 pages read from / write to this object.
    Compute layer (analytics/, backtest/, portfolio/) never imports this class.
    """
    session_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    universe:   Universe                 = field(default_factory=Universe)
    portfolios: List[PortfolioCandidate] = field(default_factory=list)

    saa:          Optional[PortfolioCandidate] = None
    taa:          Optional[TAAScenario]        = None
    ml_extension: Optional[Dict[str, Any]]     = None

    def get_candidate(self, candidate_id: str) -> Optional[PortfolioCandidate]:
        return next((p for p in self.portfolios if p.candidate_id == candidate_id), None)

    def add_candidate(self, candidate: PortfolioCandidate) -> None:
        if self.get_candidate(candidate.candidate_id) is not None:
            raise ValueError(f"candidate_id \'{candidate.candidate_id}\' already exists")
        self.portfolios.append(candidate)

    def any_stale(self) -> bool:
        return any(p.is_stale for p in self.portfolios)

    def lock_saa(self, candidate_id: str) -> None:
        """Set SAA baseline. Raises if candidate not found or backtest missing."""
        candidate = self.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate \'{candidate_id}\' not found.")
        if candidate.backtest_result is None:
            raise ValueError("Cannot lock SAA: backtest not yet computed.")
        self.saa = candidate
'''

target = pathlib.Path(__file__).parent / "portfolio" / "models.py"
target.write_text(content, encoding="utf-8")

# Verify
lines = target.read_text(encoding="utf-8").splitlines()
has_session = any("class ResearchSession" in l for l in lines)
print(f"Written {len(lines)} lines to {target}")
print(f"ResearchSession present: {has_session}")

# Quick import test
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stock_engine.portfolio.models import ResearchSession, FactorBucket, PortfolioCandidate
print("Import test passed OK")
