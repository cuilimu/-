"""
ui/components/rebalance_panel.py — Rebalancing configuration UI.
Same Day mode only. Rendered below allocation inputs, above Run Backtest button.
Session state key: rebalance_config_{slot_key}
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import streamlit as st

from stock_engine.portfolio.rebalancer import RebalanceConfig

if TYPE_CHECKING:
    from stock_engine.backtest.base import BacktestResult
    from stock_engine.config import Config


def rebalance_panel(
    slot_key: str,
    config: Optional["Config"] = None,
    prior_result: Optional["BacktestResult"] = None,
    capital_hint: float = 0.0,
) -> RebalanceConfig:
    """
    Render rebalance config UI, persist to session state, return config.

    slot_key      — e.g. "single_same_day", "group_My Group"
    config        — global Config; slippage_bps is read from here (not set locally).
    prior_result  — last BacktestResult for this slot; used to compute effective
                    slippage from actual rebalance trades and offer auto-fill.
    capital_hint  — portfolio NAV/capital used to show dollar equivalent of bps.
    """
    state_key = f"rebalance_config_{slot_key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = RebalanceConfig()

    cfg: RebalanceConfig = st.session_state[state_key]

    enabled = st.checkbox(
        "☑ Enable Rebalancing",
        value=cfg.enabled,
        key=f"reb_enabled_{slot_key}",
    )
    cfg.enabled = enabled

    if not enabled:
        st.session_state[state_key] = cfg
        return cfg

    with st.container(border=True):
        trigger = st.radio(
            "Trigger",
            options=["periodic", "threshold", "both"],
            format_func=lambda x: x.capitalize(),
            index=["periodic", "threshold", "both"].index(cfg.trigger),
            horizontal=True,
            key=f"reb_trigger_{slot_key}",
        )
        cfg.trigger = trigger

        if trigger in ("periodic", "both"):
            st.markdown("**Periodic settings**")
            freq = st.selectbox(
                "Frequency",
                options=["monthly", "quarterly", "annual"],
                format_func=lambda x: x.capitalize(),
                index=["monthly", "quarterly", "annual"].index(cfg.frequency),
                key=f"reb_freq_{slot_key}",
            )
            cfg.frequency = freq

        if trigger in ("threshold", "both"):
            st.markdown("**Threshold settings**")
            drift = st.number_input(
                "Drift tolerance (%)",
                min_value=0.5,
                max_value=50.0,
                step=0.5,
                value=float(cfg.drift_threshold_pct),
                key=f"reb_drift_{slot_key}",
                help="Rebalance when any position drifts more than this % from its target weight",
            )
            cfg.drift_threshold_pct = drift

        # ── Cost assumption (global slippage from Config) ─────────────────────
        st.markdown("**Cost assumption**")

        # Read global slippage; fall back to cfg value if config not passed
        global_cfg = config or st.session_state.get("_config")
        bps: float = float(global_cfg.slippage_bps) if global_cfg else float(cfg.slippage_bps)
        cfg.slippage_bps = bps

        # Auto-fill from prior run effective rate
        eff_bps: Optional[float] = None
        if prior_result and prior_result.rebalance_events:
            events = prior_result.rebalance_events
            total_traded = sum(
                sum(t["trade_value"] for t in e.trades) for e in events
            )
            if total_traded > 0:
                eff_bps = (prior_result.total_rebalance_cost / total_traded) * 10_000

        col_info, col_btn = st.columns([3, 1])
        with col_info:
            dollar_hint = f" ≈ ${capital_hint * (bps / 10_000):,.2f}/trade" if capital_hint > 0 else ""
            st.caption(
                f"**{bps} bps/trade** (global sidebar setting){dollar_hint}"
            )
        with col_btn:
            if eff_bps is not None:
                st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
                if st.button(
                    f"↺ {eff_bps:.1f} bps",
                    key=f"reb_autofill_{slot_key}",
                    help=f"Update global slippage to last-run effective rate: {eff_bps:.2f} bps "
                         f"({len(events)} events, ${prior_result.total_rebalance_cost:,.2f} total cost)",
                    use_container_width=True,
                ):
                    if global_cfg:
                        global_cfg.slippage_bps = round(eff_bps, 1)
                        st.session_state["_config"] = global_cfg
                    cfg.slippage_bps = round(eff_bps, 1)
                    st.session_state[state_key] = cfg
                    st.rerun()

        if eff_bps is not None:
            st.caption(
                f"last run effective: {eff_bps:.1f} bps "
                f"(${prior_result.total_rebalance_cost:,.2f} total drag)"
            )

        st.caption("Target weights: Initial allocation (fixed — rebalances back to buy-in ratio)")

    st.session_state[state_key] = cfg
    return cfg
