"""
ui/components/simple_mode/page2_allocation.py — Step 2: Allocation Research.

Layout:
  col_config (constraint panel)  |  col_candidates (EW + Manual candidate cards)
"""
from __future__ import annotations

import math
from typing import Any

import streamlit as st

from stock_engine.portfolio.models import (
    AllocationMethod, CandidateStatus, PortfolioCandidate,
)
from stock_engine.portfolio.rebalancer import RebalanceConfig
from stock_engine.ui.components.simple_mode.session import (
    get_session, save_session, apply_equal_weights,
    ensure_default_candidates, next_step, prev_step,
    build_mini_universe,
)
from stock_engine.sandbox.taa_module.equal_weight import (
    apply_equal_weights_v2, explain_equal_weight_rule,
)
from stock_engine.ui.components.simple_mode.page1_universe import (
    BUCKET_LABEL, BUCKET_COLOR, BUCKET_BG,
)
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.portfolio.models import FactorBucket

# ── Status tag colors ──────────────────────────────────────────────────────────
_STATUS_STYLE = {
    CandidateStatus.COMPUTED: ("computed",  "#00b050", "#052e16"),
    CandidateStatus.NOT_RUN:  ("not run",   "#8a0a9e", "#2e003e"),
    CandidateStatus.STALE:    ("stale",     "#ea580c", "#3a1500"),
}


# ── Page-wide CSS — Bloomberg + STATA + purple/white/black ─────────────────────

# ── Strategy registry ─────────────────────────────────────────────────────────
# Each strategy is a self-describing record. The grid iterates this list to
# render cards; the dispatcher in render_page2 looks up `id` to route to the
# matching sub-page renderer. Adding a new strategy = appending one entry
# here + writing one new _render_*_subpage function — no other edits needed.
_STRATEGIES: list[dict] = [
    {
        "id":          "equal_weight",
        "method":      AllocationMethod.EQUAL_WEIGHT,
        "label":       "Equal Weight",
        "description": "Distributes capital equally across all assets in the universe.",
        "status":      "available",
    },
    {
        "id":          "manual",
        "method":      AllocationMethod.MANUAL,
        "label":       "Manual",
        "description": "Set the USD amount for each asset directly. "
                       "Any unallocated capital is held as cash.",
        "status":      "available",
    },
    {
        "id":          "risk_parity",
        "method":      AllocationMethod.RISK_PARITY,
        "label":       "Risk Parity",
        "description": "Weight assets so each contributes equal risk "
                       "(inverse-volatility scaling).",
        "status":      "coming_soon",
    },
    {
        "id":          "min_variance",
        "method":      AllocationMethod.MVO,
        "label":       "Min Variance",
        "description": "Markowitz mean-variance optimisation — "
                       "minimum-variance portfolio under constraints.",
        "status":      "coming_soon",
    },
]


def _strategy_by_id(sid: str) -> dict | None:
    return next((s for s in _STRATEGIES if s["id"] == sid), None)


# ── Price fetching + share breakdown helpers ───────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_prices(tickers: tuple, date: str) -> dict:
    """Return {ticker: close_price} at *date* (nearest prior trading day). Cached 5 min."""
    from stock_engine.data.yfinance_provider import YFinanceProvider

    class _Cfg:
        # Use the project-standard parquet cache. Earlier `cache_dir = None`
        # combined with `cache_enabled = True` made the provider's __init__
        # call `Path(None).mkdir(...)` which raised, the caller swallowed the
        # exception, and every preview row showed N/A.
        cache_dir     = ".cache"
        cache_enabled = True
        fred_api_key  = None

    provider = YFinanceProvider(_Cfg())
    return {t: provider.fetch_price_at(t, date, "close") for t in tickers}


def _shares_breakdown(
    weights: dict[str, float],
    capital: float,
    prices: dict[str, float | None],
) -> tuple[dict[str, dict], float]:
    """
    Given theoretical weights (0-1), capital, and per-ticker close prices,
    return (rows, cash) where rows = {ticker: {theory_w, alloc_$, price,
    shares, actual_$, actual_w}} and cash = leftover capital.
    """
    rows: dict[str, dict] = {}
    invested = 0.0
    for ticker, w in weights.items():
        price = prices.get(ticker)
        alloc = w * capital
        if price and price > 0:
            shares     = math.floor(alloc / price)
            actual_val = shares * price
        else:
            shares     = 0
            actual_val = 0.0
        rows[ticker] = {
            "theory_w": w,
            "alloc_$":  alloc,
            "price":    price,
            "shares":   shares,
            "actual_$": actual_val,
        }
        invested += actual_val

    cash = capital - invested
    for r in rows.values():
        r["actual_w"] = r["actual_$"] / capital if capital > 0 else 0.0

    return rows, cash


def _render_allocation_table(
    rows: dict[str, dict],
    cash: float,
    capital: float,
) -> None:
    """Bloomberg-style capital-allocation grid:
       # | SECURITY | PLANNED ALLOCATION (USD) | PRICE | SHARES | MKT VALUE | WEIGHT %
       Plus a totals row showing Deployed / Returned / Cash.
    """
    html = '<div class="bbg2-wrap">'
    # Group header (logical groupings above main column headers)
    html += (
        '<div class="bbg2-thgrp">'
        '<span class="bbg2-th">&nbsp;</span>'
        '<span class="bbg2-th">&nbsp;</span>'
        '<span class="bbg2-th">PLANNED ALLOCATION</span>'
        '<span class="bbg2-th r">MARKET PRICE</span>'
        '<span class="bbg2-th r">SHARES</span>'
        '<span class="bbg2-th r">MKT VALUE</span>'
        '<span class="bbg2-th r">WEIGHT</span>'
        '</div>'
        '<div class="bbg2-thead">'
        '<span class="bbg2-th">#</span>'
        '<span class="bbg2-th">SECURITY</span>'
        '<span class="bbg2-th">ALLOCATION (USD)</span>'
        '<span class="bbg2-th r">PRICE</span>'
        '<span class="bbg2-th r">SHARES</span>'
        '<span class="bbg2-th r">MKT VALUE</span>'
        '<span class="bbg2-th r">WEIGHT %</span>'
        '</div>'
    )

    total_planned  = 0.0
    total_deployed = 0.0
    for idx, (ticker, r) in enumerate(rows.items(), 1):
        alloc  = r["alloc_$"]
        price  = r["price"]
        shares = r["shares"]
        mkt    = r["actual_$"]
        weight = r["actual_w"] * 100
        total_planned  += alloc
        total_deployed += mkt

        price_html  = (f'&#36;{price:,.2f}' if price and price > 0
                       else '<span class="bbg2-warn">N/A</span>')
        shares_html = f'{shares:,}' if shares > 0 else '&mdash;'
        mkt_html    = f'&#36;{mkt:,.0f}' if mkt > 0 else '&mdash;'
        returned    = alloc - mkt
        ret_html    = (f'<div class="bbg2-warn">+&#36;{returned:,.0f} returned</div>'
                       if shares > 0 and returned > 0.5 else '')

        html += (
            f'<div class="bbg2-row">'
            f'<span class="bbg2-num">{idx})</span>'
            f'<span class="bbg2-tick">{ticker}</span>'
            f'<span>&#36;{alloc:,.0f}</span>'
            f'<span class="r">{price_html}</span>'
            f'<span class="r">{shares_html}{ret_html}</span>'
            f'<span class="r">{mkt_html}</span>'
            f'<span class="r bbg2-wt">{weight:.1f}%</span>'
            f'</div>'
        )

    total_returned = max(0.0, total_planned - total_deployed)
    cash_class = "cash-pos" if cash >= 0 else "cash-neg"
    html += (
        f'<div class="bbg2-row bbg2-tot">'
        f'<span class="lbl">TOTALS</span>'
        f'<span></span>'
        f'<span><span class="planned">&#36;{total_planned:,.0f}</span><br>'
        f'<span class="sub">of &#36;{capital:,.0f} capital</span></span>'
        f'<span class="summary">'
        f'<span class="k">Deployed: </span>'
        f'<b>&#36;{total_deployed:,.0f}</b>'
        f'&nbsp;&nbsp;<span class="k">Returned: </span>'
        f'<span style="color:#888">&#36;{total_returned:,.2f}</span>'
        f'&nbsp;&nbsp;<span class="k">Cash: </span>'
        f'<span class="{cash_class}">&#36;{cash:,.0f}</span>'
        f'</span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Page entry point ───────────────────────────────────────────────────────────

# Routing state. None = overview page; else = strategy id of the open sub-page.
_SUB_KEY = "p2_active_sub"


def render_page2(config) -> None:
    _inject_css("page2_allocation")
    sess = get_session()
    ensure_default_candidates(sess)

    active_sub = st.session_state.get(_SUB_KEY)

    if active_sub:
        strategy = _strategy_by_id(active_sub)
        if strategy is None:
            # Stale id — fall back to overview.
            st.session_state.pop(_SUB_KEY, None)
            st.rerun()
        elif strategy["status"] != "available":
            _render_subpage_header(strategy)
            _render_coming_soon_subpage(strategy)
        else:
            _render_subpage_header(strategy)
            cand = _candidate_for_strategy(sess, strategy)
            if strategy["id"] == "equal_weight":
                _render_eq_weight_subpage(sess, config, cand)
            elif strategy["id"] == "manual":
                _render_manual_subpage(sess, config, cand)
            else:
                _render_coming_soon_subpage(strategy)
    else:
        # ── Overview: constraints (left) + selector + summary cards (right) ──
        col_config, col_candidates = st.columns([1.4, 3.5], gap="medium")

        with col_config:
            with st.container(key="p2_constraints", border=False):
                _render_config_panel(sess, config)

        with col_candidates:
            with st.container(key="p2_methods", border=False):
                _render_strategy_selector(sess)
            with st.container(key="p2_cands", border=False):
                _render_candidate_summaries(sess)

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    _render_bottom_bar(sess)


def _candidate_for_strategy(sess, strategy: dict):
    """Find (or refuse to mint) the PortfolioCandidate that matches the chosen
    strategy. ensure_default_candidates() seeds one per AllocationMethod, so
    this should always resolve for an available strategy."""
    return next(
        (c for c in sess.portfolios if c.method == strategy["method"]),
        None,
    )


def _open_sub(strategy_id: str) -> None:
    st.session_state[_SUB_KEY] = strategy_id
    st.rerun()


def _close_sub() -> None:
    st.session_state.pop(_SUB_KEY, None)
    st.rerun()


# ── Left config panel ──────────────────────────────────────────────────────────

def _render_config_panel(sess, config) -> None:
    st.markdown('<div class="p2-sec">CONSTRAINTS</div>', unsafe_allow_html=True)

    # Weight bounds are set globally in the sidebar (WEIGHT BOUNDS section).
    min_w = float(st.session_state.get("_taa_min_w", 0.0))
    max_w = float(st.session_state.get("_taa_max_w", 100.0))
    st.caption(
        f"Weight bounds: **{min_w:.0f}% – {max_w:.0f}%** per asset "
        f"(set in sidebar)"
    )

    st.markdown(
        '<div class="p2-sec" style="margin-top:14px">BUCKET BOUNDS (%)</div>',
        unsafe_allow_html=True,
    )
    bucket_bounds: dict[str, dict[str, float]] = {}
    for bucket in [FactorBucket.GROWTH, FactorBucket.FIN_COND,
                   FactorBucket.INFLATION, FactorBucket.DIVERSIFIER]:
        lbl = BUCKET_LABEL[bucket]
        c_lo, c_hi = st.columns(2)
        with c_lo:
            lo = st.number_input(f"{lbl} min", 0.0, 100.0, 0.0, 5.0,
                                 key=f"p2_bk_lo_{bucket.value}", format="%.0f",
                                 label_visibility="visible")
        with c_hi:
            hi = st.number_input(f"{lbl} max", 0.0, 100.0, 100.0, 5.0,
                                 key=f"p2_bk_hi_{bucket.value}", format="%.0f",
                                 label_visibility="visible")
        bucket_bounds[bucket.value] = {"min": lo, "max": hi}

    # Rebalancing
    st.markdown(
        '<div class="p2-sec" style="margin-top:14px">REBALANCING</div>',
        unsafe_allow_html=True,
    )
    reb_freq = st.selectbox(
        "Frequency", ["None", "Monthly", "Quarterly", "Annually"],
        index=2, key="p2_reb_freq",
    )
    st.number_input("Slippage (bps)", 0.0, 50.0,
                    float(config.slippage_bps), 0.5,
                    key="p2_slippage", format="%.1f")
    st.caption(
        "Equal Weight rebalance: TAA runs first (MVO within each factor bucket), "
        "then equal-weight across buckets is applied. "
        "Manual rebalance always uses your saved weights unchanged."
    )

    # Benchmark
    st.markdown(
        '<div class="p2-sec" style="margin-top:14px">BENCHMARK</div>',
        unsafe_allow_html=True,
    )
    bm = st.text_input(
        "Benchmark ticker", value=config.default_benchmark,
        key="p2_benchmark",
        help="Any yfinance ticker, e.g. SPY, QQQ, ^HSI",
    ).upper().strip()
    if bm:
        config.default_benchmark = bm

    # Store constraints into session
    shared_constraints: dict[str, Any] = {
        "min_weight":     min_w / 100,
        "max_weight":     max_w / 100,
        "bucket_bounds":  bucket_bounds,
        "rebalance_freq": reb_freq,
    }
    for cand in sess.portfolios:
        cand.constraints.update(shared_constraints)
    save_session(sess)


# ── Compact strategy selector (replaces the showcase card grid) ──────────────

def _render_strategy_selector(sess) -> None:
    """One-row segmented-button selector. Clicking an available strategy
    jumps to its sub-page; coming-soon strategies are disabled with a
    tooltip. The bar is purely a navigation control — no descriptions
    inline; long copy lives on hover."""
    st.markdown('<div class="p2-sec">STRATEGY</div>', unsafe_allow_html=True)
    st.markdown('<div class="p2-strat-bar"></div>', unsafe_allow_html=True)
    cols = st.columns(len(_STRATEGIES), gap="small")
    for col, strategy in zip(cols, _STRATEGIES):
        with col:
            available = strategy["status"] == "available"
            tooltip   = strategy["description"] if available else \
                        f"Coming soon — {strategy['description']}"
            if st.button(
                strategy["label"],
                key=f"p2_strat_{strategy['id']}",
                use_container_width=True,
                disabled=not available,
                help=tooltip,
            ):
                _open_sub(strategy["id"])


# ── Candidate summary rows (replaces the inline expanded panels) ─────────────

def _render_candidate_summaries(sess) -> None:
    """Each candidate appears as a compact summary card showing strategy
    name, status badge, and (if computed) headline metrics. The whole card
    is a button — clicking it opens the strategy's dedicated sub-page."""
    st.markdown('<div class="p2-sec">CANDIDATES</div>', unsafe_allow_html=True)

    if not sess.universe.tickers:
        st.info("Return to Step 1 to add assets.")
        return

    # Render one row per registered strategy (in registry order, not session
    # order — keeps the layout stable as candidates get computed/cleared).
    for strategy in _STRATEGIES:
        cand      = _candidate_for_strategy(sess, strategy)
        available = strategy["status"] == "available"
        _render_candidate_summary_row(strategy, cand, available)


def _render_candidate_summary_row(strategy: dict, cand, available: bool) -> None:
    label    = strategy["label"]
    sid      = strategy["id"]

    if not available:
        line2 = "Coming soon"
    elif cand is None:
        line2 = "Not initialised"
    else:
        line2 = _summary_metrics_line(cand)

    btn_label = f"{label}\n{line2}"
    if st.button(
        btn_label,
        key=f"p2_summary_{sid}",
        use_container_width=True,
        disabled=not available,
        help=strategy["description"],
    ):
        _open_sub(sid)


def _summary_metrics_line(cand) -> str:
    """Status badge + (if computed) Total Return / Sharpe / Max DD as a
    single status line for the summary card."""
    status_label = _STATUS_STYLE[cand.status][0].upper()
    if cand.status != CandidateStatus.COMPUTED or cand.backtest_result is None:
        return f"● {status_label}        →  Open"

    res     = cand.backtest_result
    summary = getattr(res, "summary", {}) or {}

    def _g(*keys):
        for k in keys:
            v = summary.get(k)
            if v not in (None, ""):
                return v
        return None

    tr     = _g("total_return", "total_return_pct", "Total Return")
    sharpe = _g("sharpe_ratio", "sharpe", "Sharpe")
    mdd    = _g("max_drawdown", "max_dd", "Max Drawdown", "Max DD")

    parts = [f"● {status_label}"]
    if tr is not None:
        parts.append(f"TR {_fmt_metric(tr, '%')}")
    if sharpe is not None:
        parts.append(f"Sharpe {_fmt_metric(sharpe, '')}")
    if mdd is not None:
        parts.append(f"DD {_fmt_metric(mdd, '%')}")
    parts.append(" →  Open")
    return "    ".join(parts)


def _fmt_metric(v, suffix: str) -> str:
    try:
        # If `v` is already a formatted string, just return as-is.
        if isinstance(v, str):
            return v
        return f"{float(v):.2f}{suffix}"
    except Exception:
        return "—"


# ── Sub-page header + back navigation ─────────────────────────────────────────

def _render_subpage_header(strategy: dict) -> None:
    if st.button("← Back to Allocation", key="p2_back_overview"):
        _close_sub()
    st.markdown(
        f'<div class="p2-sub-header">'
        f'  <div class="p2-sub-title">{strategy["label"]} Allocation</div>'
        f'  <div class="p2-sub-subtitle">{strategy["description"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_coming_soon_subpage(strategy: dict) -> None:
    st.markdown(
        f'<div class="p2-coming-soon">'
        f'  <b>{strategy["label"]}</b> is not yet implemented.<br>'
        f'  {strategy["description"]}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Equal-Weight sub-page (own layout, full width) ───────────────────────────

def _render_eq_weight_subpage(sess, config, cand) -> None:
    if cand is None:
        st.warning("Equal-weight candidate not initialised. Return to overview.")
        return

    tickers = sess.universe.tickers
    capital = float(config.initial_capital)
    start_date = (str(sess.universe.backtest_start)
                  if sess.universe.backtest_start else None)

    prices: dict[str, float | None] = {}
    if start_date and tickers:
        try:
            prices = _fetch_prices(tuple(tickers), start_date)
        except Exception:
            pass

    # Status pill
    status_label, status_color, status_bg = _STATUS_STYLE[cand.status]
    st.markdown(
        f'<span class="tag" style="background:{status_bg};color:{status_color};'
        f'border:1px solid {status_color};padding:2px 9px;font-size:9px;'
        f'font-weight:700;letter-spacing:.08em;text-transform:uppercase">'
        f'{status_label}</span>',
        unsafe_allow_html=True,
    )

    n         = len(tickers)
    taa       = st.session_state.get("_taa_cache")
    preview_w = _ew_target_weights(sess)

    if taa is not None:
        ew_rule = explain_equal_weight_rule(taa, build_mini_universe(sess))
    else:
        ew_rule = f"1/{n} per asset (no TAA — run Step 3 to apply factor weights)"

    st.markdown(
        f'<div class="p2-cap" style="margin-top:8px">'
        f'{ew_rule} · Capital: <b>${capital:,.0f}</b>'
        + (f' · Prices at <b>{start_date}</b>' if start_date else '')
        + '</div>',
        unsafe_allow_html=True,
    )

    if n > 0:
        rows, cash = _shares_breakdown(preview_w, capital, prices or {})
        _render_allocation_table(rows, cash, capital)

    col_apply, col_run = st.columns([2, 1])
    with col_apply:
        if st.button("Apply EW weights", key="p2_apply_ew_sub"):
            apply_equal_weights(sess)
            st.rerun()
    with col_run:
        _render_run_button(sess, cand, config)

    if cand.weights:
        _render_bucket_bar(cand, sess)

    if cand.status == CandidateStatus.COMPUTED and cand.backtest_result is not None:
        _render_perf_summary(cand)


# ── Manual sub-page (own layout, full width) ─────────────────────────────────

def _render_manual_subpage(sess, config, cand) -> None:
    if cand is None:
        st.warning("Manual candidate not initialised. Return to overview.")
        return

    tickers = sess.universe.tickers
    capital = float(config.initial_capital)
    start_date = (str(sess.universe.backtest_start)
                  if sess.universe.backtest_start else None)

    prices: dict[str, float | None] = {}
    if start_date and tickers:
        try:
            prices = _fetch_prices(tuple(tickers), start_date)
        except Exception:
            pass

    status_label, status_color, status_bg = _STATUS_STYLE[cand.status]
    hdr_l, hdr_r = st.columns([3, 1])
    with hdr_l:
        st.markdown(
            f'<span class="tag" style="background:{status_bg};color:{status_color};'
            f'border:1px solid {status_color};padding:2px 9px;font-size:9px;'
            f'font-weight:700;letter-spacing:.08em;text-transform:uppercase">'
            f'{status_label}</span>',
            unsafe_allow_html=True,
        )
    with hdr_r:
        st.markdown(
            f'<div class="p2-cap" style="text-align:right">'
            f'Capital: <b>${capital:,.0f}</b></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="p2-cap">Set each asset by % weight or USD amount. '
        'Any unallocated capital is held as cash.</div>',
        unsafe_allow_html=True,
    )

    cid = cand.candidate_id

    # ── Two-way binding between % slider and $ number_input ──
    # Both widgets share a logical state. Init once from cand.weights, then
    # keep them in sync via on_change callbacks (Streamlit's standard pattern
    # for linked widgets). Capital is captured at init and re-synced whenever
    # it changes between renders.
    cap_seen_key = f"p2_cap_seen_{cid}"
    capital_changed = st.session_state.get(cap_seen_key) != capital
    st.session_state[cap_seen_key] = capital

    def _on_pct(pct_k, dol_k, cap):
        st.session_state[dol_k] = float(st.session_state[pct_k]) / 100.0 * cap

    def _on_dol(pct_k, dol_k, cap):
        v = (float(st.session_state[dol_k]) / cap * 100.0) if cap > 0 else 0.0
        st.session_state[pct_k] = max(0.0, min(100.0, v))

    for ticker in tickers:
        pct_key = f"p2_w_{cid}_{ticker}"
        dol_key = f"p2_d_{cid}_{ticker}"
        if pct_key not in st.session_state:
            init_w = cand.weights.get(ticker, 0.0) * 100
            st.session_state[pct_key] = init_w
            st.session_state[dol_key] = init_w / 100.0 * capital
        elif capital_changed:
            # Keep dollar amount consistent with the (preserved) % weight.
            st.session_state[dol_key] = (
                float(st.session_state[pct_key]) / 100.0 * capital
            )

    updated_weights: dict[str, float] = {}
    total = 0.0
    for ticker in tickers:
        pct_key = f"p2_w_{cid}_{ticker}"
        dol_key = f"p2_d_{cid}_{ticker}"
        col_t, col_s, col_dol, col_pct = st.columns([0.9, 2.6, 1.4, 0.7])
        with col_t:
            st.markdown(
                f'<div style="font-size:11px;font-weight:500;padding-top:10px;'
                f'white-space:nowrap">{ticker}</div>',
                unsafe_allow_html=True,
            )
        with col_s:
            st.slider(
                f"w_{ticker}", 0.0, 100.0, step=0.5,
                key=pct_key,
                on_change=_on_pct, args=(pct_key, dol_key, capital),
                label_visibility="collapsed",
            )
        with col_dol:
            st.number_input(
                f"$_{ticker}",
                min_value=0.0, max_value=float(capital),
                step=100.0, format="%.0f",
                key=dol_key,
                on_change=_on_dol, args=(pct_key, dol_key, capital),
                label_visibility="collapsed",
            )
        w = float(st.session_state[pct_key])
        with col_pct:
            st.markdown(
                f'<div style="font-size:11px;padding-top:10px;text-align:right;'
                f'color:#660874;font-weight:600">{w:.1f}%</div>',
                unsafe_allow_html=True,
            )
        updated_weights[ticker] = w / 100
        total += w

    # Soft notice: red only when *over* 100% (truly invalid). Under-100% is fine —
    # leftover stays as cash.
    if total > 100.0 + 0.5:
        total_color = "#e03030"
    elif total > 0:
        total_color = "#00b050"
    else:
        total_color = "#888"
    st.markdown(
        f'<div style="font-size:10px;font-weight:600;color:{total_color};'
        f'margin:2px 0 6px;text-align:right">'
        f'Total: {total:.1f}%   ·   Cash: {max(0.0, 100.0 - total):.1f}%'
        f'</div>',
        unsafe_allow_html=True,
    )

    if total > 0:
        rows, cash = _shares_breakdown(updated_weights, capital, prices or {})
        _render_allocation_table(rows, cash, capital)

    if start_date and tickers and not any(
        (prices or {}).get(t) for t in tickers
    ):
        st.warning(
            f"Could not fetch market prices for {start_date}. Allocation will "
            "still run — the backtest fetches its own prices when executed."
        )

    col_save, col_run = st.columns([2, 1])
    with col_save:
        if st.button("Save weights", key="p2_save_manual_sub"):
            cand.set_weights(updated_weights)
            save_session(sess)
            st.rerun()
    with col_run:
        # Allow running with partial allocation. The backtest runner leaves
        # any unallocated capital as cash. The only invalid state is >100%.
        over_allocated = total > 100.0 + 0.5
        _render_run_button(sess, cand, config, disabled=over_allocated)

    if cand.weights:
        _render_bucket_bar(cand, sess)

    if cand.status == CandidateStatus.COMPUTED and cand.backtest_result is not None:
        _render_perf_summary(cand)


def _render_perf_summary(cand) -> None:
    res     = cand.backtest_result
    summary = getattr(res, "summary", {}) or {}
    if not summary:
        return
    st.markdown('<div class="p2-sec" style="margin-top:14px">PERFORMANCE</div>',
                unsafe_allow_html=True)
    cols = st.columns(4)
    for col, (k, v) in zip(cols, list(summary.items())[:4]):
        with col:
            st.metric(k.replace("_", " ").title(), v)


def _render_run_button(sess, cand: PortfolioCandidate, config, disabled=False) -> None:
    label = "▶ Run" if cand.status == CandidateStatus.NOT_RUN else "↻ Re-run"
    if st.button(label, key=f"p2_run_{cand.candidate_id}",
                 type="primary", disabled=disabled):
        _run_candidate(sess, cand, config)


def _ew_target_weights(sess) -> dict[str, float]:
    """Return the EW target weights, TAA-aware when a TAAResult is cached.

    TAA Passthrough  → flat 1/N across all tickers (same as no TAA).
    TAA Factor MVO   → 1/k bucket equal-weight × intra-bucket MVO weights.
    No TAA result    → flat 1/N fallback.
    """
    tickers = sess.universe.tickers
    if not tickers:
        return {}
    taa = st.session_state.get("_taa_cache")
    min_w = float(st.session_state.get("_taa_min_w", 0.0)) / 100.0
    max_w = float(st.session_state.get("_taa_max_w", 100.0)) / 100.0
    if taa is not None:
        return apply_equal_weights_v2(build_mini_universe(sess), taa,
                                      min_weight=min_w, max_weight=max_w)
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def _run_candidate(sess, cand: PortfolioCandidate, config) -> None:
    from stock_engine.backtest.runner import BacktestRunner
    from stock_engine.analytics.engine import AnalyticsEngine
    from stock_engine.data.yfinance_provider import YFinanceProvider
    from stock_engine.portfolio.models import TickerAllocation

    universe = sess.universe
    tickers  = universe.tickers

    if not tickers or not cand.weights:
        st.warning("Set weights before running.")
        return
    if universe.backtest_start is None or universe.backtest_end is None:
        st.warning("Set backtest period in Step 1.")
        return

    total_capital = float(config.initial_capital)

    if cand.method == AllocationMethod.EQUAL_WEIGHT:
        apply_equal_weights(sess)
        cand = get_session().get_candidate(cand.candidate_id) or cand

    start_str = str(universe.backtest_start)

    # Use actual share-adjusted allocations when prices available
    prices: dict[str, float | None] = {}
    try:
        prices = _fetch_prices(tuple(tickers), start_str)
    except Exception:
        pass

    allocs = []
    if prices:
        rows, _cash = _shares_breakdown(
            {t: cand.weights.get(t, 0.0) for t in tickers if cand.weights.get(t, 0.0) > 0},
            total_capital,
            prices,
        )
        for t, r in rows.items():
            if r["shares"] > 0:
                allocs.append(TickerAllocation(
                    ticker=t,
                    allocated_dollars=r["actual_$"],
                ))
    else:
        allocs = [
            TickerAllocation(
                ticker=t,
                allocated_dollars=cand.weights.get(t, 0.0) * total_capital,
            )
            for t in tickers
            if cand.weights.get(t, 0.0) > 0
        ]

    end_str = str(universe.backtest_end)

    # ── Rebalance config ─────────────────────────────────────────────────
    _FREQ_MAP = {"Monthly": "monthly", "Quarterly": "quarterly", "Annually": "annual"}
    reb_freq_label = cand.constraints.get("rebalance_freq", "None")
    reb_cfg: RebalanceConfig | None = None
    if reb_freq_label in _FREQ_MAP:
        slippage = float(st.session_state.get("p2_slippage", config.slippage_bps))
        if cand.method == AllocationMethod.EQUAL_WEIGHT:
            target_w = _ew_target_weights(sess)
        else:
            target_w = {t: w for t, w in cand.weights.items() if w > 0}
        reb_cfg = RebalanceConfig(
            enabled=True,
            trigger="periodic",
            frequency=_FREQ_MAP[reb_freq_label],
            slippage_bps=slippage,
            target_weights=target_w,
        )

    with st.spinner(f"Running {cand.label}…"):
        try:
            provider = YFinanceProvider(config)
            runner   = BacktestRunner(strategy=None, data_provider=provider, config=config)
            result   = runner.run(
                tickers=tickers,
                start=start_str,
                end=end_str,
                allocations=allocs,
                rebalance_config=reb_cfg,
            )
            analytics = AnalyticsEngine(config)
            analytics.compute(result)

            cand.backtest_result = result
            cand.mark_computed()
            save_session(sess)
            st.toast(f"{cand.label} complete ✓", icon="✅")
            st.rerun()
        except Exception as e:
            st.error(f"{cand.label} failed: {e}")


def _render_bucket_bar(cand: PortfolioCandidate, sess) -> None:
    """Stacked bar showing weight breakdown by factor bucket."""
    universe = sess.universe
    bucket_weights: dict[FactorBucket, float] = {}
    for ticker, w in cand.weights.items():
        meta   = universe.assets.get(ticker)
        bucket = meta.factor_bucket if meta else FactorBucket.UNASSIGNED
        bucket_weights[bucket] = bucket_weights.get(bucket, 0.0) + w

    if not bucket_weights:
        return

    bar_html = '<div style="display:flex;height:8px;border-radius:4px;overflow:hidden;margin:8px 0 4px">'
    for bucket, w in bucket_weights.items():
        if w > 0.001:
            color = BUCKET_COLOR[bucket]
            bar_html += (
                f'<div style="width:{w*100:.1f}%;background:{color};opacity:0.85"'
                f' title="{BUCKET_LABEL[bucket]}: {w*100:.1f}%"></div>'
            )
    bar_html += "</div>"
    bar_html += '<div style="display:flex;gap:8px;flex-wrap:wrap">'
    for bucket, w in bucket_weights.items():
        if w > 0.001:
            color = BUCKET_COLOR[bucket]
            bar_html += (
                f'<span style="font-size:9px;color:{color}">'
                f'■ {BUCKET_LABEL[bucket]} {w*100:.0f}%</span>'
            )
    bar_html += "</div>"
    st.markdown(bar_html, unsafe_allow_html=True)


# ── Bottom bar ───────────────────────────────────────────────────────────────────────────────

def _render_bottom_bar(sess) -> None:
    c_info, c_back, c_next = st.columns([4, 1, 1])
    with c_info:
        n_computed = sum(1 for c in sess.portfolios
                         if c.status == CandidateStatus.COMPUTED)
        st.markdown(
            f'<div style="font-size:11px;color:#888;padding-top:8px">'
            f'{n_computed}/{len(sess.portfolios)} candidates computed</div>',
            unsafe_allow_html=True,
        )
    with c_back:
        if st.button("← Back", key="p2_back", use_container_width=True):
            prev_step()
    with c_next:
        can_proceed = any(c.status == CandidateStatus.COMPUTED for c in sess.portfolios)
        if st.button(
            "Next →", key="p2_next",
            use_container_width=True, disabled=not can_proceed,
        ):
            next_step()
