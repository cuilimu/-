"""
ui/components/home.py — Home page (mode-selection entry point).

Single-focal-area layout: two segmented controls (scope, execution) drive a
live-updating "Selected Workflow" preview card. CTA lives inside the card.
API config moved behind an expander. Market ticker strip relocated to
ui/components/market_strip.py for reuse on research pages.

Design tokens are imported from theme.py — no hardcoded hex values here.
"""
from __future__ import annotations
from datetime import date as _date
import streamlit as st

from stock_engine.ui.styles import inject as _inject_css

_SIDEBAR_LOGO_HTML = """
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

_SIDEBAR_HISTORY_HTML = """
<div class="sb-section">History</div>
<div class="sb-item">Sessions</div>
"""

_SIDEBAR_TOOLS_HTML = """
<div class="sb-section">Tools</div>
<div class="sb-item">Advanced Watchlist</div>
<div class="sb-item">Multi-date Mode</div>
"""

# ── Combo content — drives the focal card ─────────────────────────────────────
_COMBO_DETAIL: dict[tuple[str, str], dict] = {
    ("single", "same_day"): {
        "title":   "Simple Mode · One-day Buy",
        "summary": "Full AA → SAA → TAA pipeline. Universe locked at the purchase date.",
        "bullets": [
            "6-step Asset Allocation workflow",
            "Bloomberg-style factor regression",
            "Multi-strategy backtest comparison",
        ],
        "is_aa":   True,
        "cta":     "Start AA Pipeline →",
    },
    ("single", "multi_date"): {
        "title":   "Simple Mode · Multi-date Buy",
        "summary": "Single portfolio with phased entries and mid-flight adjustments.",
        "bullets": [
            "Stage entries across multiple dates",
            "Mid-flight adds and sells supported",
            "Realistic retail accumulation behaviour",
        ],
        "is_aa":   False,
        "cta":     "Start Simulation →",
    },
    ("group", "same_day"): {
        "title":   "Advanced Watchlist · One-day Buy",
        "summary": "Parallel comparison across multiple asset groups, single entry date.",
        "bullets": [
            "Side-by-side group performance",
            "Sector-vs-sector watchlist analysis",
            "Universe fixed across all groups",
        ],
        "is_aa":   False,
        "cta":     "Start Simulation →",
    },
    ("group", "multi_date"): {
        "title":   "Advanced Watchlist · Multi-date Buy",
        "summary": "Staggered entries per group; multi-portfolio simulation in parallel.",
        "bullets": [
            "Independent entry dates per group",
            "Compare cohort timing strategies",
            "Multi-strategy × multi-cohort grid",
        ],
        "is_aa":   False,
        "cta":     "Start Simulation →",
    },
}

# Display ↔ internal-mode mapping for the segmented controls.
_SCOPE_DISPLAY = {"single": "Simple Mode", "group": "Advanced Watchlist"}
_SCOPE_REVERSE = {v: k for k, v in _SCOPE_DISPLAY.items()}
_EXEC_DISPLAY  = {"same_day": "One-day Buy", "multi_date": "Multi-date Buy"}
_EXEC_REVERSE  = {v: k for k, v in _EXEC_DISPLAY.items()}


# ── API Configuration panel — unchanged structurally; rendered inside an
#    expander so it doesn't compete with the focal area. The redundant
#    internal section header was removed (the expander label replaces it).
def _render_api_config() -> None:
    try:
        from stock_engine.data.api_keys import (
            KEY_REGISTRY, persist_one, keys_file_path,
        )
    except Exception:
        return

    for entry in KEY_REGISTRY:
        kid       = entry["id"]
        label     = entry["label"]
        desc      = entry["description"]
        signup    = entry.get("signup_url", "")
        test_fn   = entry.get("test")

        show_key  = f"_apicfg_show_{kid}"
        test_key  = f"_apicfg_test_{kid}"
        input_key = f"_apicfg_input_{kid}"
        clear_pending_key = f"_apicfg_clearpending_{kid}"
        if show_key not in st.session_state:
            st.session_state[show_key] = False

        # Honour pending Clear from previous render — must run BEFORE the
        # text_input widget instantiates (Streamlit forbids modifying
        # widget-tied session_state once the widget is registered).
        if st.session_state.get(clear_pending_key):
            st.session_state.pop(input_key, None)
            st.session_state.pop(clear_pending_key, None)

        current   = st.session_state.get(kid, "") or ""
        test_res  = st.session_state.get(test_key)

        if test_res:
            status_text = "✓ Connected" if test_res[0] == "ok" else f"✗ {test_res[1][:32]}"
            cls_str = "ok" if test_res[0] == "ok" else "bad"
        elif current:
            status_text, cls_str = "● Set — not tested", "idle"
        else:
            status_text, cls_str = "— Not set", "idle"

        link_html = (
            f' · <a class="api-cfg-link" href="{signup}" target="_blank">Get key</a>'
            if signup else ""
        )
        st.markdown(
            f'<div class="api-cfg-card">'
            f'  <div class="api-cfg-row1">'
            f'    <span class="api-cfg-name">{label}</span>'
            f'    <span class="api-cfg-status {cls_str}">{status_text}</span>'
            f'  </div>'
            f'  <div class="api-cfg-desc">{desc}{link_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col_input, col_show, col_test, col_clear = st.columns(
            [6, 1, 1, 1], vertical_alignment="bottom",
        )
        with col_input:
            new_val = st.text_input(
                f"{label} key",
                value=current,
                type="default" if st.session_state[show_key] else "password",
                key=input_key,
                placeholder=f"Paste your {label} API key",
                label_visibility="collapsed",
            )
        with col_show:
            toggle_label = "🙈" if st.session_state[show_key] else "👁"
            if st.button(toggle_label, key=f"_apicfg_showbtn_{kid}",
                         help="Show/hide the key", use_container_width=True):
                st.session_state[show_key] = not st.session_state[show_key]
                st.rerun()
        with col_test:
            test_disabled = (test_fn is None) or (not new_val)
            if st.button("Test", key=f"_apicfg_testbtn_{kid}",
                         disabled=test_disabled,
                         help="Validate the key against the provider",
                         use_container_width=True):
                with st.spinner(f"Testing {label}…"):
                    ok, msg = test_fn(new_val)
                st.session_state[test_key] = ("ok" if ok else "bad", msg)
                st.rerun()
        with col_clear:
            if st.button("Clear", key=f"_apicfg_clearbtn_{kid}",
                         disabled=not current,
                         help="Remove this key from disk and memory",
                         use_container_width=True):
                st.session_state[kid] = ""
                st.session_state.pop(test_key, None)
                # input_key is bound to a widget already instantiated this
                # run — Streamlit forbids the write here, so defer to top
                # of next render via clear_pending_key.
                st.session_state[clear_pending_key] = True
                try:
                    persist_one(kid, "")
                except Exception:
                    pass
                st.rerun()

        if new_val != current:
            st.session_state[kid] = new_val
            st.session_state.pop(test_key, None)
            try:
                persist_one(kid, new_val)
            except Exception:
                pass

    try:
        st.caption(f"Keys stored at: `{keys_file_path()}`")
    except Exception:
        pass


def render_home() -> None:
    _inject_css("home")

    # Default to Simple + One-day on first visit so a new user immediately
    # sees the recommended AA pipeline in the focal card.
    if "portfolio_mode" not in st.session_state:
        st.session_state["portfolio_mode"] = "single"
    if "buy_mode_home" not in st.session_state:
        st.session_state["buy_mode_home"] = "same_day"

    p_mode = st.session_state["portfolio_mode"]
    b_mode = st.session_state["buy_mode_home"]

    col_sb, col_main = st.columns([1.15, 5.85], gap="small")

    # ── LEFT: sidebar ────────────────────────────────────────────────────────
    with col_sb:
        st.markdown('<span class="home-sidebar-marker"></span>', unsafe_allow_html=True)
        st.markdown(_SIDEBAR_LOGO_HTML, unsafe_allow_html=True)
        st.markdown(
            '<div class="sb-section">Workspace</div>'
            '<div class="sb-item active">Home</div>',
            unsafe_allow_html=True,
        )
        st.markdown(_SIDEBAR_HISTORY_HTML, unsafe_allow_html=True)
        if st.button("Saved Portfolios", key="home_sb_saved"):
            st.session_state["page"] = "saved_portfolios"
            st.rerun()
        st.markdown(_SIDEBAR_TOOLS_HTML, unsafe_allow_html=True)

    # ── RIGHT: main content ──────────────────────────────────────────────────
    with col_main:
        st.markdown('<div class="home-main-pad">', unsafe_allow_html=True)

        # Page label row + meta line
        _today      = _date.today().isoformat()
        _slots      = st.session_state.get("simulation_slots") or {}
        _n_slots    = len(_slots)
        _n_active   = sum(1 for v in _slots.values() if v)
        st.markdown(
            f'<div class="home-eyebrow-row">'
            f'  <span class="home-eyebrow">New Research Session</span>'
            f'  <span class="home-build-pill">Beta 0.9</span>'
            f'</div>'
            f'<div class="home-meta">'
            f'{_today}'
            f'<span class="meta-sep">·</span>'
            f'{_n_active} active'
            f'<span class="meta-sep">·</span>'
            f'{_n_slots} slots'
            f'</div>'
            f'<div class="home-hairline"></div>',
            unsafe_allow_html=True,
        )

        # ── Portfolio Scope ──────────────────────────────────────────────────
        st.markdown('<p class="home-sec-label">Portfolio Scope</p>',
                    unsafe_allow_html=True)
        st.markdown('<div class="home-segment-marker"></div>',
                    unsafe_allow_html=True)
        scope_label = st.segmented_control(
            "Portfolio Scope",
            options=list(_SCOPE_DISPLAY.values()),
            default=_SCOPE_DISPLAY[p_mode],
            key="home_scope_seg",
            label_visibility="collapsed",
        )
        new_p = _SCOPE_REVERSE.get(scope_label, p_mode) if scope_label else p_mode
        if new_p != p_mode:
            st.session_state["portfolio_mode"] = new_p
            st.rerun()

        st.markdown('<div class="home-seg-spacer"></div>', unsafe_allow_html=True)

        # ── Execution Mode ───────────────────────────────────────────────────
        st.markdown('<p class="home-sec-label">Execution Mode</p>',
                    unsafe_allow_html=True)
        st.markdown('<div class="home-segment-marker"></div>',
                    unsafe_allow_html=True)
        exec_label = st.segmented_control(
            "Execution Mode",
            options=list(_EXEC_DISPLAY.values()),
            default=_EXEC_DISPLAY[b_mode],
            key="home_exec_seg",
            label_visibility="collapsed",
        )
        new_b = _EXEC_REVERSE.get(exec_label, b_mode) if exec_label else b_mode
        if new_b != b_mode:
            st.session_state["buy_mode_home"] = new_b
            st.rerun()

        # ── Selected Workflow focal card ─────────────────────────────────────
        detail = _COMBO_DETAIL[(p_mode, b_mode)]
        bullets_html = "".join(f"<li>{b}</li>" for b in detail["bullets"])
        recommend_html = (
            '<div class="home-focal-recommend">▶ Recommended for AA research</div>'
            if detail["is_aa"] else ''
        )
        st.markdown(
            f'<div class="home-focal">'
            f'  <div class="home-focal-eyebrow">Selected Workflow</div>'
            f'  <div class="home-focal-title">{detail["title"]}</div>'
            f'  <div class="home-focal-summary">{detail["summary"]}</div>'
            f'  <ul class="home-focal-bullets">{bullets_html}</ul>'
            f'  {recommend_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # CTA — sits visually below the focal card; styled via .st-key-home_start_btn
        if st.button(detail["cta"], key="home_start_btn", type="primary"):
            if detail["is_aa"]:
                st.session_state["aa_step"] = 1
                st.session_state["page"] = "simple_aa"
            else:
                st.session_state["mode"] = p_mode
                st.session_state["page"] = "simulation"
            st.rerun()

        # ── API keys & settings — collapsed by default ───────────────────────
        with st.expander("API keys & settings", expanded=False):
            _render_api_config()

        st.markdown('</div>', unsafe_allow_html=True)
