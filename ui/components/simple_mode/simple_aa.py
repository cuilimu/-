"""
ui/components/simple_mode/simple_aa.py — 7-step AA workflow router.

Layout: persistent left sidebar (step nav + global config) | main content column.
Step nav buttons replaced by sidebar list; ugly top buttons removed entirely.
Called from ui/app.py when page == "simple_aa".

Steps:
  1 — Macro Overview   (NEW)
  2 — Stock Selection
  3 — Allocation
  4 — Performance
  5 — Risk
  6 — SAA
  7 — TAA
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from stock_engine.config import Config
from stock_engine.ui.components.simple_mode.session import (
    SESSION_KEY, STEP_KEY,
    clear_taa_cache,
    get_session, get_step, next_step, prev_step, save_session, set_step,
)
from stock_engine.ui.components.simple_mode.session_io import (
    list_saved_sessions, save_session_to_disk,
)
from stock_engine.ui.components.simple_mode.page1_universe import render_page1
from stock_engine.ui.components.simple_mode.page_taa import render_page_taa
from stock_engine.ui.components.simple_mode.page2_allocation import render_page2
from stock_engine.ui.components.simple_mode.page3_performance import render_page3
from stock_engine.ui.components.simple_mode.page4_risk import render_page4
from stock_engine.ui.components.simple_mode.page_daily_brief import render_page_daily_brief
# SAA intentionally stubbed — content paused pending review.
from stock_engine.ui.components.simple_mode.page8_arimax import render_page8_arimax
from stock_engine.ui.components.simple_mode.page_factor_investing import render_page_factor_investing
from stock_engine.ui.components.simple_mode.page_stub import render_stub
from stock_engine.ui.styles import inject as _inject_css

STEPS = [
    (1, "Macro Overview"),
    (2, "Stock Selection"),
    (3, "TAA"),
    (4, "Allocation"),
    (5, "Performance"),
    (6, "Risk"),
    (7, "SAA"),
]

WORKBENCH_STEPS = [
    ("wb_regression", "Regression"),
    ("wb_arimax", "ARIMAX"),
    ("wb_factor_investing", "Factor Investing"),
]

_STEP_FULL = {
    1: "MACRO OVERVIEW",
    2: "STOCK SELECTION",
    3: "TAA",
    4: "ALLOCATION RESEARCH",
    5: "PERFORMANCE EVAL.",
    6: "RISK EVALUATION",
    7: "SAA DECISION",
    "wb_regression": "LINEAR REGRESSION",
    "wb_arimax": "ARIMAX FORECAST",
    "wb_factor_investing": "FACTOR INVESTING",
}

# ── CSS ────────────────────────────────────────────────────────────────────────

_SIDEBAR_LOGO = """
<div class="aa-sb-logo">
  <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8"
       width="15" height="15" style="flex-shrink:0">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
  </svg>
  <div>
    <div class="aa-sb-title">Stock Engine</div>
    <div class="aa-sb-subtitle">Research Platform</div>
  </div>
</div>
"""


# ── Main entry point ───────────────────────────────────────────────────────────

def render_simple_aa(config: Config) -> None:
    _inject_css("simple_aa")

    # Legacy migration: saved sessions may store aa_step=8 (old ARIMAX step number).
    if st.session_state.get(STEP_KEY) == 8:
        st.session_state[STEP_KEY] = "wb_arimax"

    current_step = get_step()
    sess = get_session()

    col_sb, col_main = st.columns([1.3, 5.7], gap="small")

    with col_sb:
        _render_sidebar(config, sess, current_step)

    with col_main:
        _render_topbar(current_step)
        if current_step == 1:
            render_page_daily_brief()
        elif current_step == 2:
            render_page1(config)
        elif current_step == 3:
            render_page_taa(config)
        elif current_step == 4:
            render_page2(config)
        elif current_step == 5:
            render_page3(config)
        elif current_step == 6:
            render_page4(config)
        elif current_step == 7:
            render_stub(current_step)        # SAA Decision — content paused
        elif current_step == "wb_regression":
            _render_workbench_regression(config)
        elif current_step == "wb_arimax":
            render_page8_arimax(config)
        elif current_step == "wb_factor_investing":
            render_page_factor_investing(config)
        else:
            render_stub(current_step)


# ── Sidebar ────────────────────────────────────────────────────────────────────

def _apply_pending_load(config: Config) -> None:
    """Flush _pending_load into widget keys before any widget is instantiated."""
    pending = st.session_state.pop("_pending_load", None)
    if pending is None:
        return
    st.session_state["_taa_min_w"]    = pending.get("taa_min_w", 5.0)
    st.session_state["_taa_max_w"]    = pending.get("taa_max_w", 80.0)
    st.session_state["aa_sb_capital"] = pending.get("capital", config.initial_capital)
    if pending.get("backtest_start"):
        st.session_state["aa_sb_start"] = pending["backtest_start"]
    if pending.get("purchase_date"):
        st.session_state["aa_sb_end"] = pending["purchase_date"]


def _render_sidebar(config: Config, sess, current_step: int) -> None:
    # Apply any pending session-load values BEFORE widgets are instantiated.
    # (Streamlit forbids setting a widget's key after it has been rendered.)
    _apply_pending_load(config)

    st.markdown('<span class="aa-sb-marker"></span>', unsafe_allow_html=True)

    # Top row: logo on the left, Home shortcut anchored to the top-right.
    top_l, top_r = st.columns([4, 1])
    with top_l:
        st.markdown(_SIDEBAR_LOGO, unsafe_allow_html=True)
    with top_r:
        if st.button("🏠", key="aa_sb_home", help="Back to Home"):
            st.session_state["page"] = "home"
            st.rerun()

    is_wb = isinstance(current_step, str)
    st.markdown('<div class="aa-sb-section">SIMPLE MODE</div>', unsafe_allow_html=True)
    for n, label in STEPS:
        if n == current_step:
            st.markdown(
                f'<span class="aa-sb-step-active">&#9658; {n}. {label}</span>',
                unsafe_allow_html=True,
            )
        elif is_wb or n < current_step:
            if st.button(f"✓ {n}. {label}", key=f"aa_sb_s{n}"):
                set_step(n)
        else:
            if st.button(f"{n}. {label}", key=f"aa_sb_s{n}"):
                set_step(n)

    st.markdown('<div class="aa-sb-divider"></div>', unsafe_allow_html=True)
    group_cls = "aa-sb-section-group aa-sb-section-group--open" if is_wb else "aa-sb-section-group"
    st.markdown(
        f'<div class="{group_cls}">ANALYTICS WORKBENCH <span>&#8250;</span></div>',
        unsafe_allow_html=True,
    )
    for key, label in WORKBENCH_STEPS:
        if key == current_step:
            st.markdown(
                f'<span class="aa-sb-subitem-active">&#9658; {label}</span>',
                unsafe_allow_html=True,
            )
        else:
            if st.button(label, key=f"aa_sb_{key}"):
                set_step(key)

    st.markdown('<div class="aa-sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="aa-sb-section">MODES</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="aa-sb-step-done">Advanced Watchlist</div>'
        '<div class="aa-sb-step-done">Multi-date</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="aa-sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="aa-sb-section">BACKTEST CONFIG</div>', unsafe_allow_html=True)

    today = date.today()

    bt_start_default = sess.universe.backtest_start or (today - timedelta(days=365))
    bt_start = st.date_input(
        "Start",
        value=bt_start_default,
        min_value=date(2000, 1, 1),
        max_value=today,
        key="aa_sb_start",
    )

    use_latest = st.checkbox(
        "Latest date",
        value=getattr(config, "use_latest_end_date", False),
        key="aa_sb_latest",
    )
    if use_latest:
        end_date = today
        st.caption(f"Latest: {today.isoformat()}")
    else:
        end_default = sess.universe.purchase_date or today
        end_date = st.date_input(
            "End",
            value=end_default,
            min_value=bt_start,
            max_value=today,
            key="aa_sb_end",
        )

    capital = st.number_input(
        "Capital ($)",
        min_value=1_000.0,
        max_value=100_000_000.0,
        value=float(config.initial_capital),
        step=10_000.0,
        format="%.0f",
        key="aa_sb_capital",
    )

    if (sess.universe.backtest_start != bt_start
            or sess.universe.purchase_date != end_date):
        sess.universe.backtest_start = bt_start
        sess.universe.purchase_date = end_date
        sess.universe.backtest_end = end_date
        save_session(sess)

    config.default_start_date = str(bt_start)
    config.default_end_date = str(end_date)
    config.use_latest_end_date = use_latest
    config.initial_capital = capital
    st.session_state["_config"] = config

    st.markdown('<div class="aa-sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="aa-sb-section">WEIGHT BOUNDS</div>', unsafe_allow_html=True)
    st.number_input(
        "Min weight / asset (%)", 0.0, 50.0, 5.0, 1.0,
        key="_taa_min_w", format="%.0f",
        on_change=clear_taa_cache,
        help="Lower bound per asset inside each factor bucket. "
             "Prevents MVO from zeroing out positions. "
             "Also applied on rebalance dates.",
    )
    st.number_input(
        "Max weight / asset (%)", 10.0, 100.0, 80.0, 5.0,
        key="_taa_max_w", format="%.0f",
        on_change=clear_taa_cache,
        help="Upper bound per asset. Limits concentration within a bucket.",
    )
    st.session_state["_taa_global_bounds_set"] = True

    st.markdown('<div class="aa-sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="aa-sb-section">SESSIONS</div>', unsafe_allow_html=True)
    _render_session_panel(sess, current_step, config)

    st.markdown('<div class="aa-sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="aa-sb-section">API KEYS</div>', unsafe_allow_html=True)

    # Read-only status indicator — the actual key input lives on the Home
    # page now. Falls back to the FRED_API_KEY env var if no key has been
    # entered through the UI yet.
    import os as _os
    _key = (st.session_state.get("fred_api_key", "")
            or _os.environ.get("FRED_API_KEY", "")
            or "")
    if _key:
        # Keep the canonical slot mirrored if env-var was the source.
        st.session_state["fred_api_key"] = _key
        st.caption(":green[FRED · Connected]")
    else:
        st.caption(":red[FRED · Not set]")
    st.caption("Manage keys on the Home page (🏠 top-right).")

# ── Session save / load panel ──────────────────────────────────────────────────

def _render_session_panel(sess, current_step: int, config: Config) -> None:
    # ── Save ──────────────────────────────────────────────────────────────
    label_in = st.text_input(
        "Name (optional)",
        key="aa_sb_save_label",
        placeholder="auto-name if blank",
        label_visibility="collapsed",
    )
    if st.button("Save session", key="aa_sb_save", use_container_width=True):
        save_session_to_disk(
            sess,
            step=current_step,
            label=label_in.strip(),
            capital=float(st.session_state.get("aa_sb_capital",
                                               config.initial_capital)),
            taa_min_w=float(st.session_state.get("_taa_min_w", 5.0)),
            taa_max_w=float(st.session_state.get("_taa_max_w", 80.0)),
        )
        st.session_state["_sb_save_ok"] = True

    if st.session_state.pop("_sb_save_ok", False):
        st.caption(":green[Saved.]")

    # ── Quick link to the full sessions hub ───────────────────────────────
    saved = list_saved_sessions()
    n = len(saved)
    if n:
        st.caption(f"{n} saved session{'s' if n != 1 else ''}")
    if st.button("View saved sessions →", key="aa_sb_goto_saved",
                 use_container_width=True):
        st.session_state["page"] = "saved_portfolios"
        st.rerun()


# ── Topbar + breadcrumb ────────────────────────────────────────────────────────

def _render_topbar(current_step: "int | str") -> None:
    step_title = _STEP_FULL.get(current_step, f"STEP {current_step}")
    is_wb = isinstance(current_step, str)
    step_label = "ANALYTICS WORKBENCH" if is_wb else f"STEP {current_step}"
    st.markdown(
        f'<div class="bbg-header">'
        f'<span class="bbg-tag">AA</span>'
        f'<span>SIMPLE &middot; ONE-DAY</span>'
        f'<span class="bbg-header-sep"></span>'
        f'<span>{step_label}: {step_title}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    bc_html = ""
    for n, label in STEPS:
        if is_wb:
            cls, icon = "done", "&#9679;"
        else:
            cls = "active" if n == current_step else ("done" if n < current_step else "")
            icon = "&#9679;" if n < current_step else ("&#9658;" if n == current_step else str(n))
        bc_html += f'<span class="aa-bc-step {cls}">{icon} {label}</span>'
        bc_html += '<span class="aa-bc-sep">&#8250;</span>'
    for key, label in WORKBENCH_STEPS:
        cls = "active" if key == current_step else ""
        prefix = "&#9658; " if cls else ""
        bc_html += f'<span class="aa-bc-step {cls}">{prefix}{label}</span>'
        if key != WORKBENCH_STEPS[-1][0]:
            bc_html += '<span class="aa-bc-sep">&#8250;</span>'
    st.markdown(f'<div class="aa-breadcrumb">{bc_html}</div>', unsafe_allow_html=True)


# ── Analytics Workbench: Regression ───────────────────────────────────────────

def _render_workbench_regression(config: Config) -> None:
    from stock_engine.ui.components.factor_regression_tab import render_factor_regression_tab
    from stock_engine.portfolio.models import CandidateStatus

    sess = get_session()
    computed = [
        c for c in sess.portfolios
        if c.status == CandidateStatus.COMPUTED and c.backtest_result is not None
    ]

    if not computed:
        st.info(
            "No backtest results available. "
            "Run a backtest in the Performance step first."
        )
        if st.button("→ Go to Performance", key="wb_reg_goto_perf"):
            set_step(5)
        return

    group_results = {c.label: c.backtest_result for c in computed}
    single_result = computed[0].backtest_result
    render_factor_regression_tab(
        single_result=single_result,
        group_results=group_results,
        config=config,
        mode="group" if len(computed) > 1 else "single",
    )
