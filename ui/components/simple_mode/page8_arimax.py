"""
ui/components/simple_mode/page8_arimax.py — Step 8: ARIMAX forecast.

Wraps the existing ARIMAX tab around the AA workflow's portfolio candidates.
Target = portfolio return derived from BacktestResult.snapshots.
MEVs   = FRED series (FEDFUNDS / CPI / UNRATE / …).

The ARIMAX tab now hosts its own sticky ← Back button inside the left config
pane (passed via the `on_back` callback), so this wrapper does not render its
own bottom bar.

Empty state (no computed candidates yet) is a structured terminal-themed gate
screen — gate card, dependency chain, CTAs, status line, and a 4-pillar action
preview — instead of a single ``st.info`` line.
"""
from __future__ import annotations

import streamlit as st

from stock_engine.config import Config
from stock_engine.portfolio.models import CandidateStatus
from stock_engine.ui.components.arimax_tab import render_arimax_tab
from stock_engine.ui.components.simple_mode.session import (
    get_session,
    prev_step,
    set_step,
)
from stock_engine.ui.styles import inject as _inject_css

# (group, key_chip, description, needs_combo)
_P8_EMPTY_ACTIONS: list[tuple[str, str, str, bool]] = [
    ("EDA",          "tsdisplay",  "Series + ACF + PACF (40 lags) of the training target.",          False),
    ("EDA",          "decomp",     "Seasonal decomposition (observed/trend/seasonal/residual).",      False),
    ("EDA",          "pacf",       "Partial autocorrelation of the training target.",                 False),
    ("Stationarity", "ndiffs",     "ADF / KPSS / PP unit-root tests and suggested d.",                False),
    ("Stationarity", "nsdiffs",    "CH / OCSB seasonal-difference tests and suggested D.",            False),
    ("Models",       "top-N",      "Soft-rule ranked top-N table (rank, MEVs, order, soft score).",   False),
    ("Models",       "all combos", "Every fitted (variable x lag) combination with metrics.",         False),
    ("Models",       "summary",    "SARIMAX statsmodels summary text for the selected combo.",        True),
    ("Plots / Other", "forecast",  "Forecast vs actual + CI band for the selected combo.",            True),
    ("Plots / Other", "cv",        "Sliding-window cross-validated forecast for the selected combo.", True),
    ("Plots / Other", "residuals", "Residual diagnostics (residuals/hist/QQ/ACF/Ljung-Box).",         True),
    ("Plots / Other", "exports",   "Download model artifacts + JSON config snapshots.",               False),
]

_P8_PILLAR_ORDER = ["EDA", "Stationarity", "Models", "Plots / Other"]



# ── Empty-state HTML builders ────────────────────────────────────────────────

def _gate_card_html() -> str:
    return (
        '<div class="p8-gate-card">'
        '<span class="p8-blocked-badge">BLOCKED</span>'
        '<h3 class="p8-gate-headline">ARIMAX Engine — No Computed Portfolios</h3>'
        '<p class="p8-gate-subcopy">'
        'Step 8 fits SARIMAX(p,d,q) models against FRED macroeconomic variables '
        'using a portfolio backtest as the forecast target. It needs at least one '
        'computed portfolio first. Complete Step 3 (Allocation), run a backtest, '
        'and Step 8 unlocks automatically.'
        '</p>'
        '<div class="p8-dep-chain">'
        # Step 3 — active
        '<div class="p8-dep-node">'
        '<div class="p8-dep-circle p8-dep-circle-active">3</div>'
        '<span class="p8-dep-label">Allocation</span>'
        '<span class="p8-dep-status">Run backtest</span>'
        '</div>'
        '<span class="p8-dep-arrow">&rarr;</span>'
        # Step 4 — active
        '<div class="p8-dep-node">'
        '<div class="p8-dep-circle p8-dep-circle-active">4</div>'
        '<span class="p8-dep-label">Performance</span>'
        '<span class="p8-dep-status">Confirm result</span>'
        '</div>'
        '<span class="p8-dep-arrow">&rarr;</span>'
        # Step 8 — locked
        '<div class="p8-dep-node">'
        '<div class="p8-dep-circle p8-dep-circle-locked">8</div>'
        '<span class="p8-dep-label p8-dep-label-locked">ARIMAX</span>'
        '<span class="p8-dep-status">Locked</span>'
        '</div>'
        '</div>'
        '</div>'
    )


def _terminal_status_html() -> str:
    return (
        '<div class="p8-terminal-status">'
        '<span class="p8-ts-prefix">ARIMAX ENGINE</span>'
        '<span class="p8-ts-sep">·</span>'
        '<span class="p8-ts-value">SARIMAX(p,d,q) × FRED MEVs · portfolio return target</span>'
        '<span class="p8-ts-sep">·</span>'
        '<span class="p8-ts-state">STATE: AWAITING BACKTEST DATA</span>'
        '</div>'
    )


def _pillar_grid_html() -> str:
    grouped: dict[str, list[tuple[str, str, bool]]] = {g: [] for g in _P8_PILLAR_ORDER}
    for group, key, desc, needs_combo in _P8_EMPTY_ACTIONS:
        grouped.setdefault(group, []).append((key, desc, needs_combo))

    cards: list[str] = []
    for group in _P8_PILLAR_ORDER:
        rows: list[str] = []
        for key, desc, needs_combo in grouped.get(group, []):
            combo_glyph = (
                '<span class="p8-action-needs-combo" title="needs combo">*</span>'
                if needs_combo else ""
            )
            rows.append(
                '<div class="p8-action-row">'
                f'<span class="p8-key-chip">{key}</span>'
                f'<span class="p8-action-desc">{desc}</span>'
                f'{combo_glyph}'
                '</div>'
            )
        cards.append(
            '<div class="p8-pillar-card">'
            f'<div class="p8-pillar-header">{group}</div>'
            + "".join(rows)
            + '</div>'
        )

    return '<div class="p8-pillar-grid">' + "".join(cards) + '</div>'


def _render_empty_state() -> None:
    """Structured gate screen for the no-computed-candidates branch."""
    _inject_css("page8_arimax")
    st.markdown(_gate_card_html(), unsafe_allow_html=True)
    st.markdown('<div class="p8-cta-spacer"></div>', unsafe_allow_html=True)

    c_primary, c_secondary, _ = st.columns([3, 2, 3])
    with c_primary:
        if st.button(
            "Go to Step 3 — Allocation",
            key="p8_goto_step3",
            type="primary",
            use_container_width=True,
        ):
            set_step(3)
    with c_secondary:
        if st.button(
            "← Back",
            key="p8_back_empty",
            use_container_width=True,
        ):
            prev_step()

    st.markdown(_terminal_status_html(), unsafe_allow_html=True)
    st.markdown(_pillar_grid_html(), unsafe_allow_html=True)


# ── Main render ──────────────────────────────────────────────────────────────

def render_page8_arimax(config: Config) -> None:
    sess = get_session()
    computed = [
        c for c in sess.portfolios
        if c.status == CandidateStatus.COMPUTED and c.backtest_result is not None
    ]

    if not computed:
        _render_empty_state()
        return

    single_result = computed[0].backtest_result
    group_results = {c.label: c.backtest_result for c in computed}

    render_arimax_tab(
        single_result=single_result,
        group_results=group_results,
        config=config,
        mode="group" if len(computed) > 1 else "single",
        on_back=prev_step,
    )
