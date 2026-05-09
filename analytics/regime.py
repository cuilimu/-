"""
analytics/regime.py — Heuristic macro regime classifier for Page 6 TAA.

Classifies current macro environment into one of 5 regimes based on
FRED signal thresholds. Returns probability estimates (rule-weighted scores,
NOT a statistical probability model).

# ML_EXTENSIBLE: classify() can be replaced by a trained ML classifier
# (e.g. HMM, Random Forest) via analytics/ml/regime_ml.py.
# Interface: Dict[str, float] -> Dict[str, float] (same output shape).
"""

from __future__ import annotations

from typing import Dict

# ── Regime names ──────────────────────────────────────────────────────────────
REGIMES = ["base", "high_inflation", "stagflation", "recession", "rapid_disinflation"]

# ── Threshold config ──────────────────────────────────────────────────────────
# Each rule returns a score contribution (0.0 – 1.0) toward a regime.
# Final scores are normalised to sum to 1.0.

def classify(signals: Dict[str, float]) -> Dict[str, float]:
    """
    Classify macro regime from FRED signal snapshot.

    Args:
        signals: output of FredFetcher.latest() — keys from SIGNAL_KEYS:
                 cpi_yoy, core_cpi_yoy, unemployment, yield_spread,
                 gdp_growth_qoq, hy_spread

    Returns:
        Dict mapping regime name → probability-like score (sums to 1.0).
        Highest score = auto-suggested tilt.
    """
    cpi       = signals.get("cpi_yoy",       2.5)
    core_cpi  = signals.get("core_cpi_yoy",  2.5)
    unemp     = signals.get("unemployment",  4.0)
    yld_sprd  = signals.get("yield_spread",  0.5)
    gdp       = signals.get("gdp_growth_qoq", 2.0)
    hy        = signals.get("hy_spread",     3.5)

    scores: Dict[str, float] = {r: 0.0 for r in REGIMES}

    # ── Base / Soft Landing ──────────────────────────────────────────────────
    # CPI 2-3%, unemployment < 4.5%, GDP 2-3%, hy spread benign
    if 2.0 <= cpi <= 3.2:       scores["base"] += 1.5
    if 2.0 <= core_cpi <= 3.2:  scores["base"] += 1.0
    if unemp <= 4.5:             scores["base"] += 0.8
    if 1.5 <= gdp <= 3.5:       scores["base"] += 1.0
    if hy <= 4.0:                scores["base"] += 0.7

    # ── High Inflation ───────────────────────────────────────────────────────
    # CPI > 3.5%, core sticky, growth not yet collapsed
    if cpi > 3.5:               scores["high_inflation"] += 2.0
    if cpi > 4.5:               scores["high_inflation"] += 1.0   # extra weight
    if core_cpi > 3.2:          scores["high_inflation"] += 1.5
    if gdp >= 1.5:              scores["high_inflation"] += 0.5   # growth still ok
    if yld_sprd < 0:            scores["high_inflation"] += 0.5   # inverted = tightening

    # ── Stagflation ──────────────────────────────────────────────────────────
    # High inflation AND slowing growth
    if cpi > 4.0 and gdp < 1.5: scores["stagflation"] += 3.0
    if unemp > 4.5:              scores["stagflation"] += 1.0
    if hy > 4.5:                 scores["stagflation"] += 0.8

    # ── Recession ────────────────────────────────────────────────────────────
    # GDP negative, unemployment rising sharply, credit spreads widening
    if gdp < 0:                  scores["recession"] += 3.0
    if gdp < -1.0:               scores["recession"] += 1.5   # extra weight
    if unemp > 5.5:              scores["recession"] += 2.0
    if hy > 6.0:                 scores["recession"] += 2.0
    if yld_sprd > 0.5:           scores["recession"] += 0.5   # curve steepening = late-cycle

    # ── Rapid Disinflation ───────────────────────────────────────────────────
    # CPI falling fast toward target, growth still positive, Fed signalling cuts
    if cpi < 2.5 and core_cpi < 3.0:   scores["rapid_disinflation"] += 2.5
    if cpi < 2.0:                        scores["rapid_disinflation"] += 1.5
    if gdp >= 1.5:                       scores["rapid_disinflation"] += 0.8
    if yld_sprd > 0:                     scores["rapid_disinflation"] += 0.5   # curve normalising

    # ── Normalise to sum = 1.0 ───────────────────────────────────────────────
    total = sum(scores.values())
    if total == 0:
        return {r: 1.0 / len(REGIMES) for r in REGIMES}

    return {r: round(s / total, 4) for r, s in scores.items()}


def top_regime(scores: Dict[str, float]) -> str:
    """Return the regime with the highest score."""
    return max(scores, key=lambda r: scores[r])


# ── Predefined scenario tilt playbook ─────────────────────────────────────────
# Each entry: regime → {asset_class_hint: delta_weight_pp}
# Actual per-ticker adjustments are computed in the UI layer (Page 6)
# using the factor_bucket assignments from Universe.

SCENARIO_TILTS = {
    "base": {
        "description": "Neutral — no deviation from SAA",
        "growth":      0,
        "fin_cond":    0,
        "inflation":   0,
        "diversifier": 0,
        "triggers": "CPI 2–3%, unemployment <4.5%, GDP 2–3%, curve normalising",
    },
    "high_inflation": {
        "description": "UW long-duration bonds; OW real assets + quality growth",
        "growth":      +5,
        "fin_cond":    -8,
        "inflation":   +5,
        "diversifier": 0,
        "triggers": "CPI >3.5% for 2 months, Core CPI sticky, real rates negative",
    },
    "stagflation": {
        "description": "Rotate to hard assets; reduce risk broadly",
        "growth":      -10,
        "fin_cond":    -5,
        "inflation":   +10,
        "diversifier": +5,
        "triggers": "CPI >4%, GDP <1%, unemployment rising, HY spreads widening",
    },
    "recession": {
        "description": "Flight to quality; long duration as rates cut",
        "growth":      -15,
        "fin_cond":    +10,
        "inflation":   +5,
        "diversifier": 0,
        "triggers": "GDP <0% (2 qtrs), unemployment >5.5%, HY spread >600bps",
    },
    "rapid_disinflation": {
        "description": "Risk-on; duration rally; reduce inflation hedge",
        "growth":      +10,
        "fin_cond":    +5,
        "inflation":   -8,
        "diversifier": -5,
        "triggers": "CPI falling to <2.5%, Fed signalling cuts, real rates still positive",
    },
}
