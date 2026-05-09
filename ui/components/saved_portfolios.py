"""
ui/components/saved_portfolios.py — Saved Portfolios hub page.

Lists all JSON-persisted research sessions across all modes:
  - Simple Mode · AA sessions  (session_io.py)
  - Advanced Watchlist sessions (session_io_sim.py)
"""
from __future__ import annotations

from datetime import date as _date

import streamlit as st

from stock_engine.ui.styles import inject as _inject_css
from stock_engine.ui.components.simple_mode.session import (
    SESSION_KEY, STEP_KEY, clear_taa_cache,
)
from stock_engine.ui.components.simple_mode.session_io import (
    delete_session_from_disk, list_saved_sessions, load_session_from_disk,
)
from stock_engine.ui.components.session_io_sim import (
    delete_sim_session_from_disk, list_saved_sim_sessions, load_sim_session_from_disk,
)

_LOGO_HTML = """
<div class="sb-logo-row">
  <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8"
       width="16" height="16" style="flex-shrink:0">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
  </svg>
  <div>
    <div class="sb-brand-title">Stock Engine</div>
    <div class="sb-brand-sub">Research Platform</div>
  </div>
</div>
<div class="sb-divider"></div>
"""

_HISTORY_HTML = """
<div class="sb-section">History</div>
<div class="sb-item">Sessions</div>
<div class="sb-item active">Saved Portfolios</div>
<div class="sb-section">Tools</div>
<div class="sb-item">Advanced Watchlist</div>
<div class="sb-item">Multi-date Mode</div>
"""

_STEP_NAMES = {
    1: "Macro Overview", 2: "Stock Selection", 3: "TAA",
    4: "Allocation",     5: "Performance",     6: "Risk",
    7: "SAA",            8: "ARIMAX",
}

_BUY_LABEL = {"same_day": "One-day Buy", "multi_date": "Multi-date Buy"}


def render_saved_portfolios() -> None:
    _inject_css("home")
    _inject_css("saved_portfolios")

    col_sb, col_main = st.columns([1.15, 5.85], gap="small")

    with col_sb:
        st.markdown('<span class="home-sidebar-marker"></span>', unsafe_allow_html=True)
        st.markdown(_LOGO_HTML, unsafe_allow_html=True)
        st.markdown('<div class="sb-section">Workspace</div>', unsafe_allow_html=True)
        if st.button("Home", key="sp_sb_home"):
            st.session_state["page"] = "home"
            st.rerun()
        st.markdown(_HISTORY_HTML, unsafe_allow_html=True)

    with col_main:
        _render_main()


def _render_main() -> None:
    st.markdown('<div class="sp-main-pad">', unsafe_allow_html=True)

    aa_sessions  = list_saved_sessions()
    sim_sessions = list_saved_sim_sessions()
    total = len(aa_sessions) + len(sim_sessions)
    _today = _date.today().isoformat()

    st.markdown(
        f'<div class="home-eyebrow-row">'
        f'  <span class="home-eyebrow">Saved Portfolios</span>'
        f'  <span class="home-build-pill">Beta 0.9</span>'
        f'</div>'
        f'<div class="home-meta">'
        f'{_today}'
        f'<span class="meta-sep">·</span>'
        f'{total} saved session{"s" if total != 1 else ""}'
        f'</div>'
        f'<div class="home-hairline"></div>',
        unsafe_allow_html=True,
    )

    if not aa_sessions and not sim_sessions:
        st.markdown(
            '<div class="sp-empty">'
            '  <div class="sp-empty-title">No saved sessions yet</div>'
            '  <div class="sp-empty-sub">'
            '    Save a session from the Simple Mode AA workflow '
            '    or the Advanced Watchlist to see it here.'
            '  </div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)
        return

    if aa_sessions:
        st.markdown(
            '<p class="home-sec-label">Simple Mode · AA Sessions</p>',
            unsafe_allow_html=True,
        )
        for s in aa_sessions:
            _render_aa_card(s)

    if sim_sessions:
        if aa_sessions:
            st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="home-sec-label">Advanced Watchlist Sessions</p>',
            unsafe_allow_html=True,
        )
        for s in sim_sessions:
            _render_sim_card(s)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_aa_card(s: dict) -> None:
    sid      = s["session_id"]
    label    = s["label"]
    step_n   = s["step"]
    n_t      = s["n_tickers"]
    saved_at = s.get("saved_at", "")[:10] or "—"

    step_label = f"Step {step_n} · {_STEP_NAMES.get(step_n, '—')}"
    ticker_str = f'{n_t} ticker{"s" if n_t != 1 else ""}'

    st.markdown(
        f'<div class="sp-card">'
        f'  <div class="sp-card-row1">'
        f'    <span class="sp-card-label">{label}</span>'
        f'    <span class="sp-card-date">{saved_at}</span>'
        f'  </div>'
        f'  <div class="sp-card-meta">'
        f'    <span class="sp-card-tag">{step_label}</span>'
        f'    <span class="sp-card-sep">·</span>'
        f'    <span>{ticker_str}</span>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    c_load, c_del, _ = st.columns([2, 1, 8])
    with c_load:
        if st.button("Load →", key=f"sp_load_{sid}",
                     type="primary", use_container_width=True):
            result = load_session_from_disk(sid)
            if result:
                loaded_sess, loaded_step, min_w, max_w, cap = result
                st.session_state[SESSION_KEY] = loaded_sess
                st.session_state[STEP_KEY]    = loaded_step
                st.session_state["_pending_load"] = {
                    "taa_min_w":      min_w,
                    "taa_max_w":      max_w,
                    "capital":        cap,
                    "backtest_start": loaded_sess.universe.backtest_start,
                    "purchase_date":  loaded_sess.universe.purchase_date,
                }
                clear_taa_cache()
                st.session_state["page"] = "simple_aa"
                st.rerun()
    with c_del:
        if st.button("Delete", key=f"sp_del_{sid}", use_container_width=True):
            delete_session_from_disk(sid)
            st.rerun()


def _render_sim_card(s: dict) -> None:
    sid      = s["session_id"]
    label    = s["label"]
    n_groups = s["n_groups"]
    n_tickers = s["n_tickers"]
    saved_at = s.get("saved_at", "")[:10] or "—"
    buy_label = _BUY_LABEL.get(s.get("buy_mode", "same_day"), s.get("buy_mode", ""))

    group_str  = f'{n_groups} group{"s" if n_groups != 1 else ""}'
    ticker_str = f'{n_tickers} ticker{"s" if n_tickers != 1 else ""}'

    st.markdown(
        f'<div class="sp-card">'
        f'  <div class="sp-card-row1">'
        f'    <span class="sp-card-label">{label}</span>'
        f'    <span class="sp-card-date">{saved_at}</span>'
        f'  </div>'
        f'  <div class="sp-card-meta">'
        f'    <span class="sp-card-tag">Advanced Watchlist · {buy_label}</span>'
        f'    <span class="sp-card-sep">·</span>'
        f'    <span>{group_str} · {ticker_str}</span>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    c_load, c_del, _ = st.columns([2, 1, 8])
    with c_load:
        if st.button("Load →", key=f"sp_load_sim_{sid}",
                     type="primary", use_container_width=True):
            result = load_sim_session_from_disk(sid)
            if result:
                groups, mode, buy_mode, cfg = result
                # Clear sim widget keys so they reinitialise from loaded config.
                for _k in ["sim_sb_start", "sim_sb_end", "sim_sb_capital",
                           "sim_sb_freq", "sim_sb_price_field",
                           "sim_sb_benchmark", "sim_sb_slippage"]:
                    st.session_state.pop(_k, None)
                # Restore groups and clear stale results.
                st.session_state["groups"]       = groups
                st.session_state["group_results"] = {}
                st.session_state["mode"]          = mode
                st.session_state["buy_mode_home"] = buy_mode
                # Apply config via _pending_sim_cfg; _render_sim_sidebar picks it up.
                st.session_state["_pending_sim_cfg"] = cfg
                st.session_state["page"]          = "simulation"
                st.rerun()
    with c_del:
        if st.button("Delete", key=f"sp_del_sim_{sid}", use_container_width=True):
            delete_sim_session_from_disk(sid)
            st.rerun()
