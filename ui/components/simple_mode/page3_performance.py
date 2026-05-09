"""
ui/components/simple_mode/page3_performance.py — Step 3: Performance Evaluation.

Tabs: Overview | BackTest | Portfolio | Factor Decomposition | Return Analysis
Multi-strategy aware: iterates over all computed PortfolioCandidates.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from stock_engine.analytics.engine import AnalyticsEngine
from stock_engine.config import Config
from stock_engine.data.yfinance_provider import YFinanceProvider
from stock_engine.portfolio.models import CandidateStatus, PortfolioCandidate
from stock_engine.ui.theme import (
    CHART_BENCHMARK as _GT10_LINE_COLOR, CHART_BENCHMARK as _BM_COLOR,
    CHART_SERIES_PALETTE as _PALETTE,
    COLOR_GAIN, COLOR_LOSS,
)
from stock_engine.ui.components.simple_mode.session import (
    get_session, next_step, prev_step,
)
from stock_engine.ui.components.factor_workspace_tab import render_factor_decomp_panel
from stock_engine.viz.theme import DEFAULT_THEME



def _hex_to_rgba(hex_str: str, alpha: float = 0.12) -> str:
    """Convert a 6-digit hex colour string to an rgba(...) string."""
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def render_page3(config: Config) -> None:
    sess = get_session()
    computed = [c for c in sess.portfolios if c.status == CandidateStatus.COMPUTED
                and c.backtest_result is not None]

    if not computed:
        st.info("No computed candidates yet. Return to Step 2 and run at least one backtest.")
        _bottom_bar(can_proceed=False)
        return

    tab_ov, tab_bt, tab_port, tab_factor, tab_return = st.tabs([
        "Overview", "BackTest", "Portfolio", "Factor Decomposition", "Return Analysis",
    ])

    analytics = AnalyticsEngine(config)

    with tab_ov:
        _render_overview(computed, analytics, config)

    with tab_bt:
        _render_backtest(computed, analytics, config)

    with tab_port:
        _render_portfolio(computed, analytics, config)

    with tab_factor:
        single_result = computed[0].backtest_result
        group_results = {c.label: c.backtest_result for c in computed}
        render_factor_decomp_panel(
            single_result=single_result,
            group_results=group_results,
            config=config,
            mode="group" if len(computed) > 1 else "single",
        )

    with tab_return:
        _render_return_analysis(computed, analytics, config)

    st.markdown("---")
    _bottom_bar(can_proceed=True)


# ── Overview ──────────────────────────────────────────────────────────────────

def _render_overview(computed, analytics, config):
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:10px">STRATEGY SCORECARD</div>',
        unsafe_allow_html=True,
    )
    rows = []
    for cand in computed:
        try:
            m = analytics.compute(cand.backtest_result)
            rows.append({
                "Strategy":        cand.label,
                "Total Return":    f"{m.total_return:.1%}",
                "Ann. Return":     f"{m.annualised_return:.1%}",
                "Volatility":      f"{m.annualised_volatility:.1%}",
                "Sharpe":          f"{m.sharpe_ratio:.2f}",
                "Max Drawdown":    f"{m.max_drawdown:.1%}",
                "Calmar":          f"{m.calmar_ratio:.2f}" if m.calmar_ratio and m.calmar_ratio != float('inf') else "∞",
            })
        except Exception:
            rows.append({"Strategy": cand.label, "Total Return": "—",
                         "Ann. Return": "—", "Volatility": "—",
                         "Sharpe": "—", "Max Drawdown": "—", "Calmar": "—"})

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Cumulative returns mini-chart
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin:12px 0 6px">CUMULATIVE RETURN</div>',
        unsafe_allow_html=True,
    )
    fig = _multi_cumret_chart(computed, analytics)
    if fig:
        st.plotly_chart(fig, use_container_width=True, key="p3_ov_cumret",
                        config=dict(displayModeBar=False))


# ── BackTest tab ──────────────────────────────────────────────────────────────

def _render_backtest(computed, analytics, config):
    # ── Cumulative returns — all strategies + BM overlaid ─────────────────────
    st.markdown("**Cumulative Return**", )
    fig_cum = _multi_cumret_chart(computed, analytics, show_bm=True, height=340)
    if fig_cum:
        st.plotly_chart(fig_cum, use_container_width=True, key="p3_bt_cumret",
                        config=dict(displayModeBar=False))

    st.markdown("**Drawdown**")
    fig_dd = _multi_drawdown_chart(computed, analytics, height=240)
    if fig_dd:
        st.plotly_chart(fig_dd, use_container_width=True, key="p3_bt_dd",
                        config=dict(displayModeBar=False))

    # ── Daily returns + GT10 volatility overlay ───────────────────────────────
    st.markdown("**Daily Returns · GT10 6-Month Yield Volatility**")
    names = [c.label for c in computed]
    sel   = st.selectbox("Strategy", names, key="p3_bt_daily_sel")
    cand  = next(c for c in computed if c.label == sel)
    try:
        dr  = analytics.daily_returns(cand.backtest_result)
        res = cand.backtest_result
        fig = _daily_returns_with_gt10_vol(
            dr,
            start_date=str(res.start_date),
            end_date=str(res.end_date),
            config=config,
        )
        st.plotly_chart(fig, use_container_width=True, key="p3_bt_daily")
    except Exception as e:
        st.caption(f"Daily returns unavailable: {e}")


# ── Portfolio tab ─────────────────────────────────────────────────────────────

def _render_portfolio(computed, analytics, config):
    names = [c.label for c in computed]
    sel   = st.selectbox("Strategy", names, key="p3_port_sel")
    cand  = next(c for c in computed if c.label == sel)
    res   = cand.backtest_result
    last  = res.snapshots[-1]

    c1, c2, c3 = st.columns(3)
    try:
        m = analytics.compute(res)
        c1.metric("NAV",           f"${last.nav:,.0f}")
        c2.metric("Total Return",  f"{m.total_return:.1%}")
        c3.metric("Sharpe",        f"{m.sharpe_ratio:.2f}")
    except Exception:
        c1.metric("NAV", f"${last.nav:,.0f}")

    if last.positions:
        # Weight pie
        provider = YFinanceProvider(config)
        end_prices = {}
        for t in last.positions:
            try:
                p = provider.fetch_price_at(t, res.end_date, config.price_field)
                end_prices[t] = p if p and p > 0 else last.positions[t].cost_basis
            except Exception:
                end_prices[t] = last.positions[t].cost_basis

        real_mv  = sum(pos.quantity * end_prices.get(t, pos.cost_basis)
                       for t, pos in last.positions.items())
        real_nav = last.cash + real_mv
        weights  = {t: (pos.quantity * end_prices.get(t, pos.cost_basis)) / real_nav
                    for t, pos in last.positions.items()}

        from stock_engine.viz.charts import portfolio_composition_chart
        col_pie, col_ret = st.columns(2)
        with col_pie:
            fig_pie = portfolio_composition_chart(weights, DEFAULT_THEME)
            fig_pie.update_layout(height=280)
            st.plotly_chart(fig_pie, use_container_width=True, key=f"p3_port_pie_{sel}")

        with col_ret:
            bar_data = sorted(
                [{"ticker": t, "ret": (end_prices.get(t, pos.cost_basis) / pos.cost_basis - 1) * 100}
                 for t, pos in last.positions.items()],
                key=lambda x: x["ret"], reverse=True,
            )
            fig_bar = go.Figure(go.Bar(
                y=[d["ticker"] for d in bar_data],
                x=[d["ret"]    for d in bar_data],
                orientation="h",
                marker_color=[(COLOR_GAIN if d["ret"] >= 0 else COLOR_LOSS) for d in bar_data],
            ))
            fig_bar.update_layout(
                paper_bgcolor=DEFAULT_THEME.bg_paper,
                plot_bgcolor=DEFAULT_THEME.bg_plot,
                height=280, margin=dict(l=10, r=40, t=20, b=30),
                xaxis=dict(ticksuffix="%", gridcolor=DEFAULT_THEME.grid_color,
                           tickfont=dict(color=DEFAULT_THEME.font_color, size=9)),
                yaxis=dict(tickfont=dict(color=DEFAULT_THEME.font_color, size=9)),
                font=dict(color=DEFAULT_THEME.font_color, family=DEFAULT_THEME.font_family),
            )
            st.plotly_chart(fig_bar, use_container_width=True, key=f"p3_port_bar_{sel}")

    # Holdings
    from stock_engine.ui.components.holdings import holdings_table
    holdings_table(last, end_prices if last.positions else {}, config.price_field,
                   key_prefix=f"p3_{sel}", closed_positions=res.closed_positions,
                   initial_capital=res.initial_capital)


# ── Factor Decomposition tab ──────────────────────────────────────────────────

def _render_factor_decomp(computed, config):
    """
    Two tables: Portfolio table (purple left border) + Individual Stocks table.
    Delegates to the existing factor regression tab component.
    """
    from stock_engine.ui.components.factor_regression_tab import render_factor_regression_tab

    # Build a pseudo group_results dict so the existing component works
    group_results = {c.label: c.backtest_result for c in computed}
    # Use the first computed result as the "single" result
    single_result = computed[0].backtest_result if computed else None

    render_factor_regression_tab(
        single_result=single_result,
        group_results=group_results,
        config=config,
        mode="group" if len(computed) > 1 else "single",
    )


# ── Return Analysis tab ───────────────────────────────────────────────────────

def _render_return_analysis(computed, analytics, config):
    """
    Summary card per strategy → click → full profiler page.
    """
    from stock_engine.ui.components.profiler_tab import render_profiler_tab

    # Summary cards row
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:10px">STRATEGY CARDS</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(min(len(computed), 3), gap="small")
    selected_label = st.session_state.get("p3_profiler_sel", computed[0].label)

    for col, cand in zip(cols, computed):
        with col:
            try:
                m    = analytics.compute(cand.backtest_result)
                tr   = m.total_return * 100
                sr   = m.sharpe_ratio
                mdd  = m.max_drawdown * 100
                cl   = COLOR_GAIN if tr >= 0 else COLOR_LOSS
                sign = "+" if tr >= 0 else ""
                is_sel = (cand.label == selected_label)
                border = "2px solid var(--theme-purple)" if is_sel else "1.5px solid var(--border)"
            except Exception:
                tr, sr, mdd, cl, sign, border = 0, 0, 0, "var(--text-mute)", "", "1.5px solid var(--border)"

            st.markdown(
                f'<div style="border:{border};border-radius:10px;padding:12px;'
                f'background:var(--bg);cursor:pointer">'
                f'<div style="font-size:10px;font-weight:600;color:var(--theme-purple);'
                f'margin-bottom:6px">{cand.label}</div>'
                f'<div style="font-size:16px;font-weight:600;color:{cl}">'
                f'{sign}{tr:.1f}%</div>'
                f'<div style="font-size:9px;color:#888;margin-top:2px">'
                f'Sharpe {sr:.2f} · MaxDD {mdd:.1f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button(f"View {cand.label}", key=f"p3_prof_sel_{cand.candidate_id}",
                         use_container_width=True):
                st.session_state["p3_profiler_sel"] = cand.label
                st.rerun()

    st.markdown("---")

    # Full profiler for selected strategy
    sel_cand = next((c for c in computed if c.label == selected_label), computed[0])
    group_results = {c.label: c.backtest_result for c in computed}

    render_profiler_tab(
        single_result=sel_cand.backtest_result,
        group_results=group_results,
        config=config,
        mode="single",
    )


# ── Multi-strategy chart helpers ──────────────────────────────────────────────

def _multi_cumret_chart(
    computed: list,
    analytics: AnalyticsEngine,
    show_bm: bool = False,
    height: int = 300,
) -> Optional[go.Figure]:
    fig = go.Figure()
    added = False
    for i, cand in enumerate(computed):
        try:
            dr = analytics.daily_returns(cand.backtest_result)
            cr = (1 + dr).cumprod() - 1
            fig.add_trace(go.Scatter(
                x=cr.index, y=(cr * 100).values,
                name=cand.label, mode="lines",
                line=dict(color=_PALETTE[i % len(_PALETTE)], width=1.8),
            ))
            added = True
            # Benchmark (once)
            if show_bm and i == 0:
                bm = cand.backtest_result.benchmark_returns
                if bm is not None and len(bm) > 1:
                    bm_cr = (1 + bm).cumprod() - 1
                    bm_label = cand.backtest_result.benchmark_ticker or "BM"
                    fig.add_trace(go.Scatter(
                        x=bm_cr.index, y=(bm_cr * 100).values,
                        name=bm_label, mode="lines",
                        line=dict(color=_BM_COLOR, width=1.2, dash="dot"),
                    ))
        except Exception:
            pass

    if not added:
        return None

    _apply_dark_layout(fig, height, yaxis_suffix="%")
    return fig


def _multi_drawdown_chart(
    computed: list,
    analytics: AnalyticsEngine,
    height: int = 220,
) -> Optional[go.Figure]:
    fig = go.Figure()
    added = False
    for i, cand in enumerate(computed):
        try:
            dd = analytics.drawdown_series(cand.backtest_result)
            color = _PALETTE[i % len(_PALETTE)]
            fig.add_trace(go.Scatter(
                x=dd.index, y=(dd * 100).values,
                name=cand.label, mode="lines",
                line=dict(color=color, width=1.5),
                fill="tozeroy",
                fillcolor=_hex_to_rgba(color, 0.12),
            ))
            added = True
        except Exception:
            pass

    if not added:
        return None

    _apply_dark_layout(fig, height, yaxis_suffix="%")
    return fig


def _daily_returns_with_gt10_vol(
    dr: pd.Series,
    start_date: str,
    end_date: str,
    config: Config,
    height: int = 280,
) -> go.Figure:
    """Daily return bars (left axis) + 6-month rolling GT10 yield vol (right axis).

    GT10 volatility = 126-day rolling std of daily yield changes × sqrt(252),
    expressed in annualised basis-point terms. Mirrors the reference chart style
    (return bars / volatility line overlaid on dual axes).
    """
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # ── Return bars ───────────────────────────────────────────────────────────
    colors = [DEFAULT_THEME.color_gain if r >= 0 else DEFAULT_THEME.color_loss for r in dr]
    fig.add_trace(
        go.Bar(
            x=dr.index, y=(dr * 100).values,
            marker_color=colors, name="Daily Return",
            opacity=0.80,
        ),
        secondary_y=False,
    )

    # ── GT10 6-month rolling vol ──────────────────────────────────────────────
    try:
        provider = YFinanceProvider(config)
        gt10_df  = provider.fetch_historical("^TNX", start_date, end_date, "1d")
        if gt10_df is not None and not gt10_df.empty:
            col = "close" if "close" in gt10_df.columns else gt10_df.columns[0]
            yield_lvl = gt10_df[col].dropna()
            # Daily changes in yield (basis points: multiply % by 100)
            yield_chg_bps = yield_lvl.diff().dropna() * 100
            # 6-month (126-day) rolling annualised vol in bps
            gt10_vol = (yield_chg_bps.rolling(126, min_periods=20).std()
                        * (252 ** 0.5))
            gt10_vol = gt10_vol.dropna()
            if len(gt10_vol) > 5:
                fig.add_trace(
                    go.Scatter(
                        x=gt10_vol.index, y=gt10_vol.values,
                        name="GT10 6M Vol",
                        mode="lines",
                        line=dict(color=_GT10_LINE_COLOR, width=2.0),
                    ),
                    secondary_y=True,
                )
    except Exception:
        pass

    # ── Layout ────────────────────────────────────────────────────────────────
    _axis = dict(
        gridcolor=DEFAULT_THEME.grid_color, showgrid=True, zeroline=False,
        tickfont=dict(color=DEFAULT_THEME.font_color, size=9),
    )
    fig.update_layout(
        paper_bgcolor=DEFAULT_THEME.bg_paper,
        plot_bgcolor=DEFAULT_THEME.bg_plot,
        font=dict(family=DEFAULT_THEME.font_family, size=10,
                  color=DEFAULT_THEME.font_color),
        height=height,
        margin=dict(l=45, r=60, t=20, b=36),
        hovermode="x unified",
        bargap=0.1,
        legend=dict(orientation="h", x=0, y=1.04, bgcolor="rgba(0,0,0,0)",
                    font=dict(color=DEFAULT_THEME.font_color, size=9)),
    )
    fig.update_xaxes(**_axis)
    fig.update_yaxes(ticksuffix="%", title_text="Return (%)", **_axis,
                     secondary_y=False)
    fig.update_yaxes(ticksuffix=" bp", title_text="GT10 Vol (ann. bps)",
                     showgrid=False,
                     tickfont=dict(color=_GT10_LINE_COLOR, size=9),
                     title_font=dict(color=_GT10_LINE_COLOR, size=9),
                     secondary_y=True)
    return fig


def _apply_dark_layout(fig: go.Figure, height: int, yaxis_suffix: str = "") -> None:
    axis = dict(
        gridcolor=DEFAULT_THEME.grid_color, showgrid=True, zeroline=False,
        tickfont=dict(color=DEFAULT_THEME.font_color, size=9),
    )
    fig.update_layout(
        paper_bgcolor=DEFAULT_THEME.bg_paper,
        plot_bgcolor=DEFAULT_THEME.bg_plot,
        font=dict(family=DEFAULT_THEME.font_family, size=10,
                  color=DEFAULT_THEME.font_color),
        height=height,
        margin=dict(l=45, r=20, t=20, b=36),
        hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.04, bgcolor="rgba(0,0,0,0)",
                    font=dict(color=DEFAULT_THEME.font_color, size=9)),
    )
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis, ticksuffix=yaxis_suffix)


# ── Bottom bar ────────────────────────────────────────────────────────────────

def _bottom_bar(can_proceed: bool) -> None:
    c_back, _, c_next = st.columns([1, 4, 1])
    with c_back:
        if st.button("← Back", key="p3_back", use_container_width=True):
            prev_step()
    with c_next:
        if st.button("Next →", key="p3_next", type="primary",
                     use_container_width=True, disabled=not can_proceed):
            next_step()
