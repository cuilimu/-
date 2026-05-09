"""
ui/app.py — Main entry point with page routing, simulation slots, config split.
Change 2: page routing (home / simulation).
Change 3: 4-slot simulation state management.
Change 4: sidebar = global config only; contextual config inside tabs.
Change 5: buy mode applies to both single and group.
Change 6: transaction sequencing rule enforced in transaction_panel.
"""

from __future__ import annotations
import math
import traceback
from typing import Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import pandas as pd
import streamlit as st

from stock_engine.analytics.engine import AnalyticsEngine, PerformanceMetrics
from stock_engine.backtest.base import BacktestResult
from stock_engine.backtest.runner import BacktestRunner
from stock_engine.backtest.multi_date_runner import MultiDateRunner
from stock_engine.config import Config
from stock_engine.data.search import PRICE_FIELDS
from stock_engine.data.yfinance_provider import YFinanceProvider
from stock_engine.portfolio.models import PortfolioGroup, TickerAllocation
from stock_engine.ui import theme
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.ui.components.home import render_home
from stock_engine.ui.components.saved_portfolios import render_saved_portfolios
from stock_engine.ui.components.session_io_sim import (
    delete_sim_session_from_disk, list_saved_sim_sessions, save_sim_session_to_disk,
)
from stock_engine.ui.components.simple_mode.simple_aa import render_simple_aa
from stock_engine.ui.components.group_dashboard import group_dashboard
from stock_engine.ui.components.holdings import allocation_table, holdings_table
from stock_engine.ui.components.summary_bar import summary_bar
from stock_engine.ui.components.ticker_search import ticker_search_widget
from stock_engine.ui.components.performance_table import render_multi_period_table
from stock_engine.ui.components.factor_regression_tab import render_factor_regression_tab
from stock_engine.ui.components.profiler_tab import render_profiler_tab
from stock_engine.ui.components.arimax_tab import render_arimax_tab
from stock_engine.ui.components.transaction_panel import (
    mode_toggle, render_transaction_panel, render_txn_subrows, validate_transactions,
)
from stock_engine.ui.components.rebalance_panel import rebalance_panel
from stock_engine.analytics.metrics import compute_constituent_returns, compute_multi_period_returns
from stock_engine.viz.charts import (
    cumulative_returns_chart, daily_returns_chart, drawdown_chart,
    multi_group_cumulative_chart, portfolio_composition_chart,
    price_series_chart, constituent_bar_chart,
)
from stock_engine.viz.theme import DEFAULT_THEME

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Simulation Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(theme.CUSTOM_CSS, unsafe_allow_html=True)
_inject_css("home")

# Hide sidebar + Streamlit chrome on home-like pages (custom column sidebar)
if st.session_state.get("page", "home") in ("home", "saved_portfolios"):
    _inject_css("app_home_hide")

# ── 4-slot simulation state ────────────────────────────────────────────────────
SIMULATION_SLOTS = {
    "single_same_day":   None,
    "single_multi_date": None,
    "group_same_day":    None,
    "group_multi_date":  None,
}

def get_slot_key(portfolio_mode: str, buy_mode: str) -> str:
    return f"{portfolio_mode}_{buy_mode}"


def _init():
    defaults = {
        "page":             "home",
        "mode":             "single",
        "portfolio_mode":   "single",
        "buy_mode_home":    "same_day",
        "buy_mode":         "same_day",
        "simulation_slots": dict(SIMULATION_SLOTS),
        "single_tickers":   [],
        "single_allocs":    {},
        "single_result":    None,
        "single_metrics":   None,
        "single_analytics": None,
        "txns_single":      [],
        "groups":           [],
        "group_results":    {},
        "home_q_idx":       0,
        # Simple Mode AA workflow
        "aa_step":          1,
        # research_session is created lazily by session.get_session()
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Hydrate API keys from disk into st.session_state[<key_id>] so chart
    # components (page_macro, page1_universe, page6_taa, aw_beta) read a
    # ready-to-use key on the very first render. Idempotent — only fills
    # gaps; existing in-memory values are preserved.
    try:
        from stock_engine.data.api_keys import hydrate_session_state
        hydrate_session_state(st.session_state)
    except Exception:
        pass   # missing module / read error → just skip, consumers handle empty key

_init()


# ── Simulation pages: purple fake-column sidebar ──────────────────────────────
_SIM_SB_LOGO = """
<div style="display:flex;align-items:center;gap:9px;margin-bottom:6px">
  <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8"
       width="15" height="15" style="flex-shrink:0">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
  </svg>
  <div>
    <div style="font-size:13px;font-weight:600;color:#fff;line-height:1.3">Stock Engine</div>
    <div style="font-size:8.5px;color:rgba(255,255,255,0.42);letter-spacing:.1em;
                text-transform:uppercase">Research Platform</div>
  </div>
</div>
"""


def _sim_sb_divider() -> None:
    st.markdown(
        '<div style="height:1px;background:rgba(255,255,255,0.12);margin:8px 0"></div>',
        unsafe_allow_html=True,
    )


def _sim_sb_section(title: str) -> None:
    st.markdown(
        f'<div style="font-size:8.5px;color:rgba(255,255,255,0.38);letter-spacing:.1em;'
        f'text-transform:uppercase;margin:10px 0 6px 2px">{title}</div>',
        unsafe_allow_html=True,
    )


_BENCHMARK_OPTIONS = [
    "SPY",  "QQQ",  "IWM",  "DIA",  "VTI",
    "TLT",  "GLD",  "SMH",  "SOXX", "BND",
]


def _benchmark_selectbox(current: str, key: str, label: str = "Benchmark") -> str:
    """Selectbox with common benchmark tickers; preserves any custom value."""
    opts = list(_BENCHMARK_OPTIONS)
    val = (current or "SPY").upper()
    if val not in opts:
        opts = [val] + opts
    return st.selectbox(label, opts, index=opts.index(val), key=key)


def _render_sim_sidebar(config: Config) -> Config:
    from datetime import date as _date

    # Apply any pending config from a session load (before widgets instantiate).
    _pending = st.session_state.pop("_pending_sim_cfg", None)
    if _pending:
        if _pending.get("start_date"):
            config.default_start_date = _pending["start_date"]
        if _pending.get("end_date"):
            config.default_end_date = _pending["end_date"]
        if _pending.get("capital") is not None:
            config.initial_capital = float(_pending["capital"])
        if _pending.get("price_field"):
            config.price_field = _pending["price_field"]
        if _pending.get("benchmark"):
            config.default_benchmark = _pending["benchmark"]
        if _pending.get("slippage_bps") is not None:
            config.slippage_bps = float(_pending["slippage_bps"])
        st.session_state["_config"] = config

    st.markdown('<span class="sim-sb-marker"></span>', unsafe_allow_html=True)

    # Top row: logo on the left, Home shortcut anchored to the top-right.
    top_l, top_r = st.columns([4, 1])
    with top_l:
        st.markdown(_SIM_SB_LOGO, unsafe_allow_html=True)
    with top_r:
        if st.button("🏠", key="sim_sb_home_top", help="Back to Home"):
            st.session_state["page"] = "home"
            st.rerun()
    _sim_sb_divider()

    # Mode label
    mode     = st.session_state.get("mode", "single")
    buy_mode = st.session_state.get("buy_mode_home", "same_day")
    _sim_sb_section("SIMULATION MODE")
    st.markdown(
        f'<div style="font-size:10.5px;color:rgba(255,255,255,0.78);'
        f'font-weight:500;margin-bottom:2px">'
        f'{"Single Portfolio" if mode == "single" else "Group Portfolio"}</div>'
        f'<div style="font-size:9px;color:rgba(255,255,255,0.45);margin-bottom:4px">'
        f'{"One-day Buy" if buy_mode == "same_day" else "Multi-date Buy"}</div>',
        unsafe_allow_html=True,
    )

    _sim_sb_divider()
    _sim_sb_section("BACKTEST CONFIG")

    today = _date.today()

    config.default_start_date = str(st.date_input(
        "Start",
        value=pd.Timestamp(config.default_start_date).date(),
        min_value=_date(2000, 1, 1),
        max_value=today,
        key="sim_sb_start",
    ))

    use_latest = st.checkbox(
        "Latest date",
        value=getattr(config, "use_latest_end_date", False),
        key="sim_sb_latest",
    )
    config.use_latest_end_date = use_latest
    if use_latest:
        st.caption(f"📅 {today.isoformat()}")
    else:
        config.default_end_date = str(st.date_input(
            "End",
            value=pd.Timestamp(config.default_end_date).date(),
            min_value=pd.Timestamp(config.default_start_date).date(),
            max_value=today,
            key="sim_sb_end",
        ))

    config.initial_capital = st.number_input(
        "Capital ($)",
        min_value=1_000.0, max_value=100_000_000.0,
        value=float(config.initial_capital),
        step=10_000.0, format="%.0f",
        key="sim_sb_capital",
    )

    _sim_sb_divider()
    _sim_sb_section("ADVANCED")

    freq_label = st.selectbox(
        "Frequency", ["Daily", "Monthly", "Quarterly"],
        index=0, key="sim_sb_freq",
    )
    config.set_frequency({"Daily": "1d", "Monthly": "1mo", "Quarterly": "1q"}[freq_label])

    config.price_field = st.selectbox(
        "Price field", PRICE_FIELDS,
        index=PRICE_FIELDS.index(config.price_field),
        key="sim_sb_price_field",
    )

    config.default_benchmark = _benchmark_selectbox(
        config.default_benchmark, key="sim_sb_benchmark",
    )

    config.slippage_bps = st.number_input(
        "Slippage (bps)", min_value=0.0, max_value=100.0,
        step=0.5, value=float(config.slippage_bps),
        format="%.1f", key="sim_sb_slippage",
    )

    st.session_state["_config"] = config

    _sim_sb_divider()
    _sim_sb_section("SESSIONS")

    sim_label = st.text_input(
        "Session name",
        key="sim_sb_save_label",
        placeholder="auto-name if blank",
        label_visibility="collapsed",
    )
    if st.button("Save session", key="sim_sb_save", use_container_width=True):
        _groups = st.session_state.get("groups", [])
        if _groups:
            save_sim_session_to_disk(
                _groups,
                mode=st.session_state.get("mode", "group"),
                buy_mode=st.session_state.get("buy_mode_home", "same_day"),
                start_date=config.default_start_date,
                end_date=config.default_end_date,
                capital=float(config.initial_capital),
                price_field=config.price_field,
                benchmark=config.default_benchmark,
                slippage_bps=float(config.slippage_bps),
                label=sim_label.strip(),
            )
            st.session_state["_sim_save_ok"] = True
        else:
            st.caption(":orange[No groups to save.]")

    if st.session_state.pop("_sim_save_ok", False):
        st.caption(":green[Saved.]")

    _n_sim = len(list_saved_sim_sessions())
    if _n_sim:
        st.caption(f"{_n_sim} saved session{'s' if _n_sim != 1 else ''}")
    if st.button("View saved sessions →", key="sim_sb_goto_saved",
                 use_container_width=True):
        st.session_state["page"] = "saved_portfolios"
        st.rerun()

    return config


# ── Sidebar — global config (kept for reference / fallback) ───────────────────
def sidebar() -> Config:
    with st.sidebar:
        if st.button("🏠 Home", key="nav_home"):
            st.session_state["page"] = "home"
            st.rerun()

        st.title("⚙️ Global Config")

        config = st.session_state.get("_config", Config())

        freq_label = st.segmented_control(
            "Frequency", ["Daily", "Monthly", "Quarterly"],
            default="Daily", key="freq_ctrl",
        )
        freq_map = {"Daily": "1d", "Monthly": "1mo", "Quarterly": "1q"}
        config.set_frequency(freq_map[freq_label])

        config.price_field = st.selectbox(
            "Price field", PRICE_FIELDS,
            index=PRICE_FIELDS.index(config.price_field),
            key="price_field_sel",
        )

        config.initial_capital = st.number_input(
            "Initial Capital ($)",
            min_value=1_000.0, max_value=1e8,
            value=config.initial_capital,
            step=1_000.0, format="%.0f",
        )

        config.default_start_date = str(st.date_input(
            "Start date",
            value=pd.Timestamp(config.default_start_date).date(),
        ))

        config.use_latest_end_date = st.toggle(
            "Use latest end date", value=config.use_latest_end_date,
        )
        if config.use_latest_end_date:
            st.caption("📅 End date: today (auto-updating)")
        else:
            config.default_end_date = str(st.date_input(
                "End date",
                value=pd.Timestamp(config.default_end_date).date(),
            ))

        config.default_benchmark = _benchmark_selectbox(
            config.default_benchmark, key="global_sb_benchmark",
        )

        config.slippage_bps = st.number_input(
            "Slippage (bps/trade)",
            min_value=0.0, max_value=100.0, step=0.5,
            value=config.slippage_bps,
            help="Applied to every trade in the backtest rebalancer and Return Analysis.",
        )

        st.session_state["_config"] = config

    return config


# ── Single portfolio panel ─────────────────────────────────────────────────────
def single_panel(config: Config):
    st.markdown('<div class="section-header">Single Portfolio Backtest</div>',
                unsafe_allow_html=True)

    buy_mode = st.session_state.get("buy_mode_home", "same_day")

    if buy_mode == "multi_date":
        txns = render_transaction_panel(
            session_key="txns_single",
            config=config,
            start_date=config.default_start_date,
            end_date=config.effective_end_date(),
            initial_capital=config.initial_capital,
        )
        errs = validate_transactions(txns)
        if st.button("▶ Run Multi-Date Backtest", type="primary", disabled=bool(errs)):
            _run_single_multi_date(config, txns)
        return

    selected = ticker_search_widget(
        key="single_search",
        existing_tickers=st.session_state.single_tickers,
        label="Search ticker",
    )
    if selected and selected not in st.session_state.single_tickers:
        st.session_state.single_tickers.append(selected)
        price = YFinanceProvider(config).fetch_price_at(
            selected, config.default_start_date, config.price_field
        ) or 0.0
        st.session_state.single_allocs[selected] = TickerAllocation(
            ticker=selected,
            allocated_dollars=config.initial_capital / len(st.session_state.single_tickers),
            price_used=price,
        )

    tickers  = st.session_state.single_tickers
    alloc_map: dict[str, TickerAllocation] = st.session_state.single_allocs

    if not tickers:
        st.info("Search and add tickers above to build your portfolio.")
        return

    start_prices = {t: alloc_map[t].price_used for t in tickers if t in alloc_map}
    alloc_list   = [alloc_map[t] for t in tickers if t in alloc_map]

    updated, to_remove = allocation_table(
        allocations=alloc_list,
        price_field=config.price_field,
        start_prices=start_prices,
        total_capital=config.initial_capital,
        key_prefix="single",
    )
    for t in to_remove:
        tickers.remove(t)
        alloc_map.pop(t, None)
    st.session_state.single_tickers = tickers
    st.session_state.single_allocs  = {a.ticker: a for a in updated if a.ticker not in to_remove}

    slot_key = get_slot_key("single", "same_day")
    prior    = st.session_state.get("single_result")
    capital  = (
        prior.snapshots[-1].nav if prior and prior.snapshots
        else config.initial_capital
    )
    rebalance_cfg = rebalance_panel(slot_key, config=config, prior_result=prior, capital_hint=capital)

    if st.button("▶ Run Backtest", type="primary"):
        _run_single(config, tickers, {t: alloc_map[t] for t in tickers if t in alloc_map}, rebalance_cfg)


def _run_single(config, tickers, alloc_map, rebalance_cfg=None):
    n_tickers    = len(tickers)
    status_label = f"Running backtest ({n_tickers} ticker{'s' if n_tickers != 1 else ''})…"

    with st.status(status_label, expanded=True) as status:
        try:
            allocs   = [a for a in alloc_map.values() if a.allocated_dollars > 0]
            provider = YFinanceProvider(config)
            runner   = BacktestRunner(strategy=None, data_provider=provider, config=config)

            prog_bar = st.progress(0, text="Fetching market data…")

            def _on_fetch(done: int, total: int, ticker: str) -> None:
                if total == 0:
                    return
                frac = done / total
                if ticker:
                    prog_bar.progress(frac, text=f"Fetching {ticker} ({done+1}/{total})…")
                else:
                    prog_bar.progress(1.0, text="Data fetch complete")

            result = runner.run(
                tickers=tickers,
                start=config.default_start_date,
                end=config.effective_end_date(),
                allocations=allocs,
                rebalance_config=rebalance_cfg,
                progress_cb=_on_fetch,
            )
            prog_bar.progress(1.0, text="Running event loop… done")

            st.write("Computing analytics…")
            analytics = AnalyticsEngine(config)
            metrics   = analytics.compute(result)

            st.session_state.single_result    = result
            st.session_state.single_metrics   = metrics
            st.session_state.single_analytics = analytics
            slot = get_slot_key("single", "same_day")
            st.session_state["simulation_slots"][slot] = result

            status.update(label="Backtest complete ✓", state="complete", expanded=False)
            st.toast("Backtest complete ✓", icon="✅")
            st.rerun()
        except Exception as exc:
            tb = traceback.format_exc()
            status.update(label=f"Backtest failed: {exc}", state="error", expanded=True)
            st.error(f"Backtest failed: {exc}")
            with st.expander("Show traceback (for debugging)", expanded=False):
                st.code(tb, language="python")


def _run_single_multi_date(config, txns):
    with st.spinner("Running multi-date backtest…"):
        try:
            provider = YFinanceProvider(config)
            runner   = MultiDateRunner(data_provider=provider, config=config)
            result   = runner.run(
                scheduled=txns,
                start_date=config.default_start_date,
                end_date=config.effective_end_date(),
                initial_capital=config.initial_capital,
            )
            analytics = AnalyticsEngine(config)
            metrics   = analytics.compute(result)
            st.session_state.single_result    = result
            st.session_state.single_metrics   = metrics
            st.session_state.single_analytics = analytics
            st.session_state.txns_single      = txns
            slot = get_slot_key("single", "multi_date")
            st.session_state["simulation_slots"][slot] = result
            st.toast("Multi-date backtest complete ✓", icon="✅")
            st.rerun()
        except Exception as exc:
            st.error(f"Multi-date backtest failed: {exc}")


# ── Group panel ────────────────────────────────────────────────────────────────
def group_panel(config: Config):
    if st.session_state.group_results:
        summary_bar(st.session_state.group_results)

    updated_groups, group_to_run, rb_cfg = group_dashboard(
        groups=st.session_state.groups,
        group_results=st.session_state.group_results,
        config=config,
    )
    st.session_state.groups = updated_groups

    # Prune results for groups that were deleted or renamed.
    current_names = {g.name for g in updated_groups}
    st.session_state.group_results = {
        k: v for k, v in st.session_state.group_results.items()
        if k in current_names
    }

    if group_to_run:
        _run_group(config, group_to_run, rb_cfg)


def _run_group(config: Config, group_name: str, rb_cfg=None):
    group = next((g for g in st.session_state.groups if g.name == group_name), None)
    if not group:
        return
    with st.spinner(f"Running {group_name}…"):
        try:
            buy_mode = st.session_state.get("buy_mode_home", "same_day")
            provider = YFinanceProvider(config)

            if buy_mode == "multi_date":
                txn_key = f"txns_group_{group_name}"
                txns    = st.session_state.get(txn_key, [])
                runner  = MultiDateRunner(data_provider=provider, config=config)
                result  = runner.run(
                    scheduled=txns,
                    start_date=config.default_start_date,
                    end_date=config.effective_end_date(),
                    initial_capital=group.starting_capital,
                )
            else:
                if rb_cfg is None:
                    rb_cfg = st.session_state.get(f"rebalance_config_group_{group_name}")
                runner = BacktestRunner(strategy=None, data_provider=provider, config=config)
                result = runner.run_group(
                    group, config.default_start_date, config.effective_end_date(),
                    rebalance_config=rb_cfg,
                )

            result.strategy_name = group_name
            st.session_state.group_results[group_name] = result
            slot = get_slot_key("group", buy_mode)
            st.session_state["simulation_slots"][slot] = dict(st.session_state.group_results)
            st.toast(f"{group_name} complete ✓", icon="✅")
            st.rerun()
        except Exception as exc:
            st.error(f"{group_name} failed: {exc}")


# ── Results section ────────────────────────────────────────────────────────────
def results_section(config: Config):
    result        = st.session_state.single_result
    metrics       = st.session_state.single_metrics
    analytics     = st.session_state.single_analytics
    group_results = st.session_state.group_results
    mode          = st.session_state.get("mode", "single")

    tab_overview, tab_backtest, tab_portfolio, tab_factor, tab_profiler, tab_arimax = st.tabs(
        ["Overview", "Backtest", "Portfolio", "Factor Decomposition", "Return Analysis", "ARIMAX"]
    )

    with tab_overview:
        if mode == "single" and result and metrics:
            # ── Metrics row ──────────────────────────────────────────────────
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Return", f"{metrics.total_return:.1%}")
            c2.metric("Ann. Return",  f"{metrics.annualised_return:.1%}")
            c3.metric("Volatility",   f"{metrics.annualised_volatility:.1%}")
            c4.metric("Sharpe",       f"{metrics.sharpe_ratio:.2f}")
            c5.metric("Max Drawdown", f"{metrics.max_drawdown:.1%}")

            # ── Cumulative returns of individual stocks ──────────────────────
            _last_ov    = result.snapshots[-1]
            _tickers_ov = result.tickers or list(_last_ov.positions.keys())
            if _tickers_ov:
                st.markdown('<div class="section-header">Individual Stock Returns</div>',
                            unsafe_allow_html=True)
                _PALETTE_OV = theme.CHART_SERIES_PALETTE
                _cum_fig_ov = go.Figure()
                for _i, _t in enumerate(_tickers_ov):
                    try:
                        _df_t = YFinanceProvider(config).fetch_historical(
                            _t, result.start_date, result.end_date, "1d"
                        )
                        _col_t = config.price_field.lower()
                        if _col_t not in _df_t.columns:
                            _col_t = "close"
                        _px_t = _df_t[_col_t].dropna()
                        if len(_px_t) > 0:
                            _cum_t = (_px_t / _px_t.iloc[0] - 1) * 100
                            _cum_fig_ov.add_trace(go.Scatter(
                                x=_cum_t.index, y=_cum_t.values,
                                name=_t, mode="lines",
                                line=dict(color=_PALETTE_OV[_i % len(_PALETTE_OV)], width=1.6),
                            ))
                    except Exception:
                        pass
                _ax_ov = dict(gridcolor=DEFAULT_THEME.grid_color, showgrid=True, zeroline=False,
                              tickfont=dict(color=DEFAULT_THEME.font_color, size=10))
                _cum_fig_ov.update_layout(
                    paper_bgcolor=DEFAULT_THEME.bg_paper,
                    plot_bgcolor=DEFAULT_THEME.bg_plot,
                    font=dict(family=DEFAULT_THEME.font_family, size=DEFAULT_THEME.font_size_base,
                              color=DEFAULT_THEME.font_color),
                    margin=dict(l=50, r=20, t=30, b=40),
                    hovermode="x unified",
                    legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom",
                                bgcolor="rgba(0,0,0,0)",
                                font=dict(color=DEFAULT_THEME.font_color, size=10)),
                )
                _cum_fig_ov.update_xaxes(**_ax_ov)
                _cum_fig_ov.update_yaxes(**_ax_ov, ticksuffix="%")
                st.plotly_chart(_cum_fig_ov, use_container_width=True, key="ov_cumret_stocks")

            # ── Price chart per stock (config-selected price field) ───────────
            if _tickers_ov:
                st.markdown('<div class="section-header">Individual Stock Price</div>',
                            unsafe_allow_html=True)
                _sel = st.selectbox("Select stock", _tickers_ov, key="ov_ticker_sel")
                try:
                    _df_px = YFinanceProvider(config).fetch_historical(
                        _sel, result.start_date, result.end_date, "1d"
                    )
                    st.plotly_chart(
                        _price_chart(_df_px, _sel, config.price_field.lower(), DEFAULT_THEME),
                        use_container_width=True, key=f"ov_price_{_sel}",
                    )
                except Exception as _e:
                    st.warning(f"Could not load price data for {_sel}: {_e}")

        elif mode == "group" and group_results:
            # ── Group metrics ────────────────────────────────────────────────
            eng  = AnalyticsEngine(config)
            cols = st.columns(min(len(group_results), 4))
            for i, (name, res) in enumerate(group_results.items()):
                m = eng.compute(res)
                with cols[i % len(cols)]:
                    st.markdown(f'<div class="section-header">{name}</div>',
                                unsafe_allow_html=True)
                    st.metric("Total Return", f"{m.total_return:.1%}")
                    st.metric("Sharpe",       f"{m.sharpe_ratio:.2f}")
                    st.metric("Max DD",       f"{m.max_drawdown:.1%}")

            # ── Cumulative returns of individual stocks (group) ──────────────
            _grp_names   = list(group_results.keys())
            _sel_grp     = st.selectbox("Select group", _grp_names, key="ov_grp_ret_sel")
            _res_grp     = group_results[_sel_grp]
            _last_grp    = _res_grp.snapshots[-1]
            _tickers_grp = _res_grp.tickers or list(_last_grp.positions.keys())
            if _tickers_grp:
                st.markdown(
                    f'<div class="section-header">{_sel_grp} — Individual Stock Returns</div>',
                    unsafe_allow_html=True)
                _PALETTE_GRP = theme.CHART_SERIES_PALETTE
                _cum_fig_grp = go.Figure()
                for _i, _t in enumerate(_tickers_grp):
                    try:
                        _df_t_g = YFinanceProvider(config).fetch_historical(
                            _t, _res_grp.start_date, _res_grp.end_date, "1d"
                        )
                        _col_t_g = config.price_field.lower()
                        if _col_t_g not in _df_t_g.columns:
                            _col_t_g = "close"
                        _px_t_g = _df_t_g[_col_t_g].dropna()
                        if len(_px_t_g) > 0:
                            _cum_t_g = (_px_t_g / _px_t_g.iloc[0] - 1) * 100
                            _cum_fig_grp.add_trace(go.Scatter(
                                x=_cum_t_g.index, y=_cum_t_g.values,
                                name=_t, mode="lines",
                                line=dict(color=_PALETTE_GRP[_i % len(_PALETTE_GRP)], width=1.6),
                            ))
                    except Exception:
                        pass
                _ax_grp = dict(gridcolor=DEFAULT_THEME.grid_color, showgrid=True, zeroline=False,
                               tickfont=dict(color=DEFAULT_THEME.font_color, size=10))
                _cum_fig_grp.update_layout(
                    paper_bgcolor=DEFAULT_THEME.bg_paper,
                    plot_bgcolor=DEFAULT_THEME.bg_plot,
                    font=dict(family=DEFAULT_THEME.font_family, size=DEFAULT_THEME.font_size_base,
                              color=DEFAULT_THEME.font_color),
                    margin=dict(l=50, r=20, t=30, b=40),
                    hovermode="x unified",
                    legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom",
                                bgcolor="rgba(0,0,0,0)",
                                font=dict(color=DEFAULT_THEME.font_color, size=10)),
                )
                _cum_fig_grp.update_xaxes(**_ax_grp)
                _cum_fig_grp.update_yaxes(**_ax_grp, ticksuffix="%")
                st.plotly_chart(_cum_fig_grp, use_container_width=True,
                                key="ov_grp_cumret_stocks")

            # ── Price chart for selected group stock ─────────────────────────
            if _tickers_grp:
                st.markdown('<div class="section-header">Individual Stock Price</div>',
                            unsafe_allow_html=True)
                _sel_tk_grp = st.selectbox("Select stock", _tickers_grp,
                                           key="ov_grp_ticker_sel")
                try:
                    _df_px_grp = YFinanceProvider(config).fetch_historical(
                        _sel_tk_grp, _res_grp.start_date, _res_grp.end_date, "1d"
                    )
                    st.plotly_chart(
                        _price_chart(_df_px_grp, _sel_tk_grp,
                                     config.price_field.lower(), DEFAULT_THEME),
                        use_container_width=True, key=f"ov_grp_price_{_sel_tk_grp}",
                    )
                except Exception as _e:
                    st.warning(f"Could not load price data for {_sel_tk_grp}: {_e}")

        else:
            st.info("Configure your portfolio and run a backtest.")

    with tab_backtest:
        if mode == "group" and group_results:
            _group_comparison_charts(config, group_results)
        elif result and analytics:
            dr = analytics.daily_returns(result)
            st.plotly_chart(cumulative_returns_chart(dr, result.benchmark_returns, DEFAULT_THEME),
                            use_container_width=True, key="bt_cumret")
            st.plotly_chart(drawdown_chart(analytics.drawdown_series(result), DEFAULT_THEME),
                            use_container_width=True, key="bt_drawdown")
            st.plotly_chart(daily_returns_chart(dr, DEFAULT_THEME), use_container_width=True,
                            key="bt_dailyret")
        else:
            st.info("Run a backtest to see charts.")

    with tab_portfolio:
        if mode == "group" and group_results:
            group_names    = list(group_results.keys())
            selected_group = st.selectbox("Select group", group_names, key="port_group_sel")
            res = group_results[selected_group]
            st.markdown(f'<div class="section-header">{selected_group} — Portfolio</div>',
                        unsafe_allow_html=True)
            _render_portfolio_tab(res, config, prefix="grp_port")
            st.divider()
            _render_analytics_group(config, group_results)
        elif result:
            st.markdown('<div class="section-header">Single Portfolio</div>',
                        unsafe_allow_html=True)
            _render_portfolio_tab(result, config, prefix="sng_port")
            if metrics:
                st.divider()
                _render_analytics_single(result, metrics, analytics, config)
        else:
            st.info("Run a backtest to see portfolio details.")

    with tab_factor:
        render_factor_regression_tab(
            single_result=result,
            group_results=group_results,
            config=config,
            mode=mode,
        )

    with tab_profiler:
        render_profiler_tab(
            single_result=result,
            group_results=group_results,
            config=config,
            mode=mode,
        )

    with tab_arimax:
        render_arimax_tab(
            single_result=result,
            group_results=group_results,
            config=config,
            mode=mode,
        )


# ── Chart helpers ──────────────────────────────────────────────────────────────
def _price_chart(df: pd.DataFrame, ticker: str, price_col: str, theme) -> go.Figure:
    """Single price-field line + volume bars. Uses the config-selected price field."""
    col     = price_col if price_col in df.columns else "close"
    has_vol = "volume" in df.columns and df["volume"].notna().any()

    if has_vol:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.70, 0.30], vertical_spacing=0.04)
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], name=col.capitalize(), mode="lines",
            line=dict(color=theme.CHART_PORTFOLIO, width=1.8),
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            x=df.index, y=df["volume"], name="Volume",
            marker_color=theme.CHART_SERIES_PALETTE[2], opacity=0.55,
        ), row=2, col=1)
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], name=col.capitalize(), mode="lines",
            line=dict(color=theme.CHART_PORTFOLIO, width=1.8),
        ))

    axis_style = dict(gridcolor=theme.grid_color, showgrid=True, zeroline=False,
                      tickfont=dict(color=theme.font_color, size=10))
    fig.update_layout(
        title=dict(text=f"{ticker} — {col.capitalize()}",
                   font=dict(color=theme.font_color, size=14)),
        paper_bgcolor=theme.bg_paper,
        plot_bgcolor=theme.bg_plot,
        font=dict(family=theme.font_family, size=theme.font_size_base, color=theme.font_color),
        margin=dict(l=50, r=20, t=44, b=40),
        hovermode="x unified",
        legend=dict(orientation="h", x=0.01, y=0.99, xanchor="left", yanchor="top",
                    bgcolor="rgba(0,0,0,0)", font=dict(color=theme.font_color, size=10)),
    )
    fig.update_xaxes(**axis_style)
    fig.update_yaxes(**axis_style)
    if has_vol:
        fig.update_yaxes(title_text=col.capitalize(), row=1, col=1,
                         title_font=dict(color=theme.font_color, size=10))
        fig.update_yaxes(title_text="Volume", row=2, col=1,
                         title_font=dict(color=theme.font_color, size=10))
    return fig


# ── Portfolio tab renderer ─────────────────────────────────────────────────────
def _render_portfolio_tab(result: BacktestResult, config: Config, prefix: str):
    last = result.snapshots[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("NAV",       f"${last.nav:,.2f}")
    c2.metric("Cash",      f"${last.cash:,.2f}")
    c3.metric("Positions", str(len(last.positions)))

    closed_pos = result.closed_positions
    if not last.positions and not closed_pos:
        st.info("No open positions.")
        return

    end_prices: dict[str, float] = {}
    if last.positions:
        prov = YFinanceProvider(config)
        for t in last.positions:
            try:
                price = prov.fetch_price_at(t, result.end_date, config.price_field)
                end_prices[t] = price if price and price > 0 else last.positions[t].cost_basis
            except Exception:
                end_prices[t] = last.positions[t].cost_basis

    if last.positions:
        real_mv  = sum(pos.quantity * end_prices.get(t, pos.cost_basis)
                       for t, pos in last.positions.items())
        real_nav = last.cash + real_mv
        weights  = {t: (pos.quantity * end_prices.get(t, pos.cost_basis)) / real_nav
                    for t, pos in last.positions.items()}
        _CHART_H = 350
        col_pie, col_ret = st.columns(2)
        with col_pie:
            _fig_pie = portfolio_composition_chart(weights, DEFAULT_THEME)
            _fig_pie.update_layout(height=_CHART_H)
            st.plotly_chart(_fig_pie, use_container_width=True, key=f"{prefix}_pie")
        with col_ret:
            import types as _types
            _cr_list = sorted(
                [
                    _types.SimpleNamespace(
                        ticker=t,
                        total_return_pct=(
                            (end_prices.get(t, pos.cost_basis) / pos.cost_basis - 1) * 100
                            if pos.cost_basis > 0 else 0.0
                        ),
                        exchange="",
                    )
                    for t, pos in last.positions.items()
                ],
                key=lambda r: r.total_return_pct,
                reverse=True,
            )
            _fig_bar = constituent_bar_chart(
                _cr_list, DEFAULT_THEME, config.price_field, "Constituent Returns"
            )
            _fig_bar.update_layout(
                height=_CHART_H,
                paper_bgcolor=DEFAULT_THEME.bg_paper,
                plot_bgcolor=DEFAULT_THEME.bg_plot,
                title=dict(text="Constituent Returns",
                           font=dict(color=DEFAULT_THEME.font_color, size=13)),
                font=dict(family=DEFAULT_THEME.font_family, size=10,
                          color=DEFAULT_THEME.font_color),
                xaxis=dict(gridcolor=DEFAULT_THEME.grid_color, showgrid=True,
                           zeroline=False, ticksuffix="%",
                           tickfont=dict(color=DEFAULT_THEME.font_color)),
                yaxis=dict(gridcolor=DEFAULT_THEME.grid_color, showgrid=False,
                           autorange="reversed",
                           tickfont=dict(color=DEFAULT_THEME.font_color)),
                margin=dict(l=20, r=80, t=40, b=30),
            )
            _fig_bar.update_traces(textfont=dict(color=DEFAULT_THEME.font_color))
            st.plotly_chart(_fig_bar, use_container_width=True, key=f"{prefix}_constbar")

    holdings_table(last, end_prices, config.price_field, key_prefix=prefix,
                   closed_positions=closed_pos, initial_capital=result.initial_capital)

    if result.rebalance_events:
        _render_rebalance_history(result)

    buy_mode = st.session_state.get("buy_mode_home", "same_day")
    if buy_mode == "multi_date":
        txns = st.session_state.get("txns_single", [])
        if txns:
            st.markdown("**Transaction History**")
            for ticker in last.positions:
                render_txn_subrows(ticker, txns)


def _render_rebalance_history(result):
    events     = result.rebalance_events
    n          = len(events)
    total_cost = result.total_rebalance_cost
    avg_cost   = total_cost / n if n else 0.0
    drag_pct   = (total_cost / result.initial_capital * 100) if result.initial_capital > 0 else 0.0
    with st.expander("Rebalance History", expanded=False):
        st.caption(f"Events: {n} | Cost: ${total_cost:,.2f} | Avg: ${avg_cost:,.2f}")
        rows = []
        for ev in events:
            post_w_str = "  ".join(
                f"{t} {w*100:.0f}%"
                for t, w in sorted(ev.post_weights.items(), key=lambda x: -x[1])
            )

            rows.append({
                "Date":         ev.date,
                "Trigger":      ev.trigger_type.capitalize(),
                "Post-weights": post_w_str,
                "Cost ($)":     f"${ev.total_cost:.2f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── Group comparison charts ────────────────────────────────────────────────────
def _group_comparison_charts(config: Config, group_results: dict):
    if not group_results:
        st.info("Run group backtests to see comparisons.")
        return
    cum_fig = go.Figure()
    palette = theme.CHART_SERIES_PALETTE
    eng = AnalyticsEngine(config)
    for i, (name, res) in enumerate(group_results.items()):
        try:
            dr    = eng.daily_returns(res)
            cum_r = (1 + dr).cumprod() - 1
            cum_fig.add_trace(go.Scatter(
                x=cum_r.index, y=(cum_r * 100).values, name=name, mode="lines",
                line=dict(color=palette[i % len(palette)], width=1.8),
            ))
        except Exception:
            pass
    ax = dict(gridcolor=DEFAULT_THEME.grid_color, showgrid=True, zeroline=False,
              tickfont=dict(color=DEFAULT_THEME.font_color, size=10))
    cum_fig.update_layout(
        paper_bgcolor=DEFAULT_THEME.bg_paper, plot_bgcolor=DEFAULT_THEME.bg_plot,
        font=dict(family=DEFAULT_THEME.font_family, size=DEFAULT_THEME.font_size_base,
                  color=DEFAULT_THEME.font_color),
        margin=dict(l=50, r=20, t=30, b=40), hovermode="x unified",
        yaxis=dict(ticksuffix="%", **ax), xaxis=dict(**ax),
        legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom",
                    bgcolor="rgba(0,0,0,0)", font=dict(color=DEFAULT_THEME.font_color, size=10)),
    )
    st.plotly_chart(cum_fig, use_container_width=True, key="bt_grp_cumret")


# ── Single analytics section ───────────────────────────────────────────────────
def _render_analytics_single(result: BacktestResult, metrics, analytics, config: Config):
    st.markdown('<div class="section-header">Multi-Period Return Analysis</div>',
                unsafe_allow_html=True)
    try:
        period_returns = compute_multi_period_returns(result, config)
        render_multi_period_table(period_returns)
    except Exception as exc:
        st.caption(f"Period returns unavailable: {exc}")
    st.markdown('<div class="section-header">Constituent Returns</div>',
                unsafe_allow_html=True)
    try:
        cr_list = compute_constituent_returns(result, config)
        if cr_list:
            fig_cr = constituent_bar_chart(cr_list, DEFAULT_THEME, config.price_field,
                                           "Constituent Returns")
            fig_cr.update_layout(height=350)
            st.plotly_chart(fig_cr, use_container_width=True, key="anal_constbar")
    except Exception as exc:
        st.caption(f"Constituent returns unavailable: {exc}")


# ── Group analytics section ────────────────────────────────────────────────────
def _render_analytics_group(config: Config, group_results: dict):
    if not group_results:
        return
    st.markdown('<div class="section-header">Group Multi-Period Analysis</div>',
                unsafe_allow_html=True)
    eng = AnalyticsEngine(config)
    for name, res in group_results.items():
        with st.expander(name, expanded=False):
            try:
                period_returns = compute_multi_period_returns(res, config)
                render_multi_period_table(period_returns)
            except Exception as exc:
                st.caption(f"Unavailable: {exc}")


# ── Main page routing ──────────────────────────────────────────────────────────
page   = st.session_state.get("page", "home")
config = st.session_state.get("_config", Config())

if page == "home":
    render_home()

elif page == "saved_portfolios":
    render_saved_portfolios()

elif page == "simple_aa":
    render_simple_aa(config)

else:
    # "simulation" and any other page
    _inject_css("sim_sidebar")
    col_sb, col_main = st.columns([1.2, 5.8], gap="small")
    with col_sb:
        config = _render_sim_sidebar(config)
    with col_main:
        mode = st.session_state.get("mode", "single")
        if mode == "single":
            single_panel(config)
        else:
            group_panel(config)
        results_section(config)
