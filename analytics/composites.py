"""
analytics/composites.py -- Z-score composites and regime classification (spec par.4).

Computes:
  - Rolling 36-month z-scores for growth/labor series (heatmap Row 2)
  - YoY pct for level series (CPI, PCE, INDPRO, WALCL, GDPC1)
  - 3-month annualised momentum (core CPI/PCE supercore read)
  - Regime composite scores: Growth, Liquidity, Credit (equal-weighted z-avg)
  - Regime label from logic tree
  - 12-month composite history for KPI sparklines

Input:  dict[series_id -> pd.Series]  (output of FredMacroClient.get_all)
Output: MacroComposites dataclass

Module: analytics -- no interface changes, pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# --- Z-score window -----------------------------------------------------------
ZSCORE_WINDOW = 36

# --- Series included in the Row-2 heatmap ------------------------------------
HEATMAP_SERIES: List[str] = [
    "CFNAI",
    "INDPRO",
    "PAYEMS",
    "UNRATE",
    "SAHMREALTIME",
    "GDPC1",
    "UMCSENT",
    "NEWORDER",
]

# --- Composite component definitions (spec par.4) ----------------------------
# Each tuple: (series_id, derived_key_or_None, sign_flip)
# sign_flip=True -> multiply z-score by -1 (series where higher = worse)
GROWTH_COMPONENTS: List[Tuple[str, Optional[str], bool]] = [
    ("CFNAI",  None,          False),
    ("INDPRO", "INDPRO_yoy",  False),
    ("PAYEMS", "PAYEMS_3m",   False),
]
LIQUIDITY_COMPONENTS: List[Tuple[str, Optional[str], bool]] = [
    ("DFII10", None,          True),   # higher real rate = tighter
    ("WALCL",  "WALCL_yoy",  False),
    ("NFCI",   None,          True),   # higher NFCI = tighter
]
CREDIT_COMPONENTS: List[Tuple[str, Optional[str], bool]] = [
    ("BAMLH0A0HYM2", None,   True),   # composite x -1 per spec
    ("BAMLC0A0CM",   None,   True),
    ("VIXCLS",       None,   True),
]


def regime_label(g: float, liq: float, cred: float) -> str:
    """Regime label logic tree (spec par.4)."""
    if g > 0.5 and liq > 0:
        return "Expansion / Easy"
    if g > 0.5 and liq < 0:
        return "Late-cycle / Tightening"
    if g < -0.5 and cred < 0:
        return "Contraction / Stress"
    if g < 0 and liq > 0.5:
        return "Recovery / Reflation"
    return "Mid-cycle / Mixed"


REGIME_COLORS: Dict[str, str] = {
    "Expansion / Easy":        "#16a34a",
    "Late-cycle / Tightening": "#ca8a04",
    "Contraction / Stress":    "#dc2626",
    "Recovery / Reflation":    "#2563eb",
    "Mid-cycle / Mixed":       "#6b7280",
}


@dataclass
class MacroComposites:
    # Latest composite z-scores
    growth_score:    float = 0.0
    liquidity_score: float = 0.0
    credit_score:    float = 0.0
    inflation_score: float = 0.0
    policy_score:    float = 0.0
    real_rate_score: float = 0.0

    label:       str = "Mid-cycle / Mixed"
    label_color: str = "#6b7280"

    # 12-month composite histories for KPI sparklines
    growth_hist:    pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    liquidity_hist: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    credit_hist:    pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    growth_dir:    str = "->"
    liquidity_dir: str = "->"
    credit_dir:    str = "->"

    # Z-score heatmap: index=series_id, columns=date
    heatmap_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    derived: Dict[str, pd.Series] = field(default_factory=dict)


# --- Pure helper functions (module-level, no closures) -----------------------

def compute_zscore(s: pd.Series, window: int = ZSCORE_WINDOW) -> pd.Series:
    """Rolling z-score with min_periods = window // 2."""
    roll_mean = s.rolling(window, min_periods=window // 2).mean()
    roll_std  = s.rolling(window, min_periods=window // 2).std()
    z = (s - roll_mean) / roll_std
    return z.replace([np.inf, -np.inf], np.nan)


def yoy_pct(s: pd.Series, freq: str = "M") -> pd.Series:
    """Year-over-year percent change. Resamples daily series to month-end first."""
    if freq == "D":
        s = s.resample("ME").last().ffill()
    return s.ffill().pct_change(12, fill_method=None) * 100


def mom_3m_ann(s: pd.Series) -> pd.Series:
    """3-month annualised MoM momentum (supercore read)."""
    monthly = s.resample("ME").last().ffill()
    return monthly.pct_change(3, fill_method=None) * 100 * 4


def _last_nonnan(s: pd.Series) -> float:
    """Return last non-NaN value, or 0.0."""
    dropped = s.dropna()
    if dropped.empty:
        return 0.0
    return float(dropped.iloc[-1])


def _direction_arrow(hist: pd.Series, months: int = 3) -> str:
    """Return up/right/down arrow based on 3-month delta of composite history."""
    dropped = hist.dropna()
    if len(dropped) < months + 1:
        return "->"
    delta = float(dropped.iloc[-1]) - float(dropped.iloc[-1 - months])
    if delta > 0.15:
        return "up"
    if delta < -0.15:
        return "down"
    return "->"


def _get_series(
    sid: str,
    derived_key: Optional[str],
    series: Dict[str, pd.Series],
    derived: Dict[str, pd.Series],
) -> pd.Series:
    """
    Safely pull a series: prefer derived[derived_key] if present and non-empty,
    else fall back to series[sid].
    Always returns a pd.Series (never None).
    """
    if derived_key is not None:
        candidate = derived.get(derived_key)
        if candidate is not None and isinstance(candidate, pd.Series) and not candidate.empty:
            return candidate
    raw = series.get(sid)
    if raw is None or not isinstance(raw, pd.Series) or raw.empty:
        return pd.Series(dtype=float, name=sid)
    return raw


def _composite_score(
    components: List[Tuple[str, Optional[str], bool]],
    series: Dict[str, pd.Series],
    derived: Dict[str, pd.Series],
) -> Tuple[float, pd.Series]:
    """
    Compute equal-weighted average z-score composite.
    Returns (latest_scalar, full_monthly_history_series).
    """
    zscore_list: List[pd.Series] = []
    for sid, dk, flip in components:
        raw = _get_series(sid, dk, series, derived)
        if raw.empty:
            continue
        monthly = raw.resample("ME").last().ffill()
        zs = compute_zscore(monthly)
        if flip:
            zs = -zs
        zscore_list.append(zs)

    if not zscore_list:
        return 0.0, pd.Series(dtype=float, index=pd.DatetimeIndex([]))

    aligned = pd.concat(zscore_list, axis=1).ffill()
    hist = aligned.mean(axis=1)
    last = _last_nonnan(hist)
    return last, hist


def _single_zscore(
    sid: str,
    series: Dict[str, pd.Series],
) -> Tuple[float, pd.Series]:
    """Z-score for a single raw series (used for Inflation/Policy/Real Rate tiles)."""
    raw = series.get(sid)
    if raw is None or not isinstance(raw, pd.Series) or raw.empty:
        return 0.0, pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    monthly = raw.resample("ME").last().ffill()
    zs = compute_zscore(monthly)
    return _last_nonnan(zs), zs


def _build_heatmap(
    series: Dict[str, pd.Series],
    derived: Dict[str, pd.Series],
) -> pd.DataFrame:
    """Build [HEATMAP_SERIES x last-24-months] z-score DataFrame."""
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=24)
    rows: Dict[str, pd.Series] = {}
    for sid in HEATMAP_SERIES:
        s = _get_series(sid, f"{sid}_yoy", series, derived)
        if s.empty:
            continue
        monthly = s.resample("ME").last().ffill()
        zs = compute_zscore(monthly)
        sliced = zs[zs.index >= cutoff]
        if not sliced.empty:
            rows[sid] = sliced
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).T


def _trim_12m(s: pd.Series) -> pd.Series:
    """Keep only the last 12 months of a series."""
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=12)
    dropped = s.dropna()
    if dropped.empty:
        return dropped
    return dropped[dropped.index >= cutoff]


# --- Master entry point -------------------------------------------------------

def build_composites(series: Dict[str, pd.Series]) -> MacroComposites:
    """
    Master entry point. Pass the dict from FredMacroClient.get_all().
    Returns a fully populated MacroComposites dataclass.
    """
    # 1. Build derived series
    derived: Dict[str, pd.Series] = {}

    for sid in ("CPIAUCSL", "CPILFESL", "PCEPILFE", "WALCL", "GDPC1"):
        raw = series.get(sid)
        if raw is not None and isinstance(raw, pd.Series) and not raw.empty:
            derived[f"{sid}_yoy"] = yoy_pct(raw, "M")

    indpro = series.get("INDPRO")
    if indpro is not None and isinstance(indpro, pd.Series) and not indpro.empty:
        derived["INDPRO_yoy"] = yoy_pct(indpro, "M")

    for sid in ("CPILFESL", "PCEPILFE"):
        raw = series.get(sid)
        if raw is not None and isinstance(raw, pd.Series) and not raw.empty:
            derived[f"{sid}_3m_ann"] = mom_3m_ann(raw)

    payems = series.get("PAYEMS")
    if payems is not None and isinstance(payems, pd.Series) and not payems.empty:
        derived["PAYEMS_3m"] = payems.diff(3) / 3

    dgs10  = series.get("DGS10")
    t10yie = series.get("T10YIE")
    if (dgs10 is not None and isinstance(dgs10, pd.Series) and not dgs10.empty and
            t10yie is not None and isinstance(t10yie, pd.Series) and not t10yie.empty):
        combined = pd.concat([dgs10, t10yie], axis=1).ffill()
        derived["REAL_YIELD_ALT"] = combined.iloc[:, 0] - combined.iloc[:, 1]

    # 2. Composite scores
    growth_now,    growth_hist    = _composite_score(GROWTH_COMPONENTS,    series, derived)
    liquidity_now, liquidity_hist = _composite_score(LIQUIDITY_COMPONENTS, series, derived)
    credit_now,    credit_hist    = _composite_score(CREDIT_COMPONENTS,    series, derived)

    infl_now,     _ = _single_zscore("T10YIE", series)
    policy_now,   _ = _single_zscore("DFF",    series)
    realrate_now, _ = _single_zscore("DFII10", series)

    # 3. Heatmap
    heatmap_df = _build_heatmap(series, derived)

    # 4. Regime label
    label = regime_label(growth_now, liquidity_now, credit_now)
    color = REGIME_COLORS.get(label, "#6b7280")

    # 5. Direction arrows
    g_dir   = _direction_arrow(growth_hist,    3)
    liq_dir = _direction_arrow(liquidity_hist, 3)
    crd_dir = _direction_arrow(credit_hist,    3)

    # Map plain-text arrows to Unicode for display
    arrow_map = {"up": "↑", "down": "↓", "->": "→"}
    g_dir   = arrow_map.get(g_dir,   "→")
    liq_dir = arrow_map.get(liq_dir, "→")
    crd_dir = arrow_map.get(crd_dir, "→")

    return MacroComposites(
        growth_score    = growth_now,
        liquidity_score = liquidity_now,
        credit_score    = credit_now,
        inflation_score = infl_now,
        policy_score    = policy_now,
        real_rate_score = realrate_now,
        label           = label,
        label_color     = color,
        growth_hist     = _trim_12m(growth_hist),
        liquidity_hist  = _trim_12m(liquidity_hist),
        credit_hist     = _trim_12m(credit_hist),
        growth_dir      = g_dir,
        liquidity_dir   = liq_dir,
        credit_dir      = crd_dir,
        heatmap_df      = heatmap_df,
        derived         = derived,
    )
