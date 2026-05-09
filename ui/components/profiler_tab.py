"""
ui/components/profiler_tab.py — Portfolio Evaluation Profiler tab UI.

Placed after Factor Decomposition in the tab bar.
All computation delegated to analytics/profiler.py — this module is rendering only.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stock_engine.analytics.profiler import (
    CostAssumptions,
    PRESETS,
    ProfilerResult,
    annualize_arithmetic,
    annualize_geometric,
    arithmetic_mean_return,
    compute_profiler,
    geometric_mean_return,
    get_monthly_returns,
    leverage_scenarios,
    nav_series_from_result,
)
from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.ui.styles import inject as _inject_css


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct(v: float, decimals: int = 2) -> str:
    return f"{v * 100:+.{decimals}f}%"


def _pct_plain(v: float, decimals: int = 2) -> str:
    return f"{v * 100:.{decimals}f}%"


def _color_class(v: float) -> str:
    if v > 0.0001:
        return "prof-value-gain"
    if v < -0.0001:
        return "prof-value-loss"
    return "prof-value-neutral"


def _row(label: str, value: str, cls: str = "prof-value") -> str:
    return (
        f'<div class="prof-row">'
        f'<span class="prof-label">{label}</span>'
        f'<span class="{cls}">{value}</span>'
        f'</div>'
    )


# ── Section helpers ───────────────────────────────────────────────────────────

def _render_kpi_cards(pr: ProfilerResult) -> None:
    """2×2 KPI summary grid."""
    c1, c2 = st.columns(2)

    # ── Card 1: Return Metrics ───────────────────────────────────────────────
    cagr_str = _pct(pr.cagr_gross) if pr.cagr_gross is not None else "< 1 yr"
    real_str  = _pct(pr.cagr_net_real) if pr.cagr_net_real is not None else "< 1 yr"
    wf = pr.waterfall

    rows_1 = "".join([
        _row("CAGR Gross",        cagr_str,               _color_class(pr.cagr_gross or pr.hpr)),
        _row("CAGR Real Net",     real_str,                _color_class(pr.cagr_net_real or wf["real_net"])),
        _row("Total HPR",         _pct(pr.hpr),            _color_class(pr.hpr)),
        _row("Arith Mean (daily)", _pct(pr.arith_mean_daily, 4), "prof-value"),
        _row("Geo Mean (daily)",   _pct(pr.geo_mean_daily, 4),   "prof-value"),
    ])
    with c1:
        st.markdown(
            f'<div class="prof-card">'
            f'<div class="prof-card-header">Return Metrics</div>'
            f'{rows_1}</div>',
            unsafe_allow_html=True,
        )

    # ── Card 2: Timing & Attribution ────────────────────────────────────────
    te_sign = "▲" if pr.timing_effect_bps >= 0 else "▼"
    te_cls  = "prof-value-gain" if pr.timing_effect_bps >= 0 else "prof-value-loss"
    total_drag = pr.hpr - wf["real_net"]

    rows_2 = "".join([
        _row("TWR",             _pct(pr.twr),  _color_class(pr.twr)),
        _row("MWR",             _pct(pr.mwr),  _color_class(pr.mwr)),
        _row(f"Timing Effect",  f"{pr.timing_effect_bps:+.0f} bps {te_sign}", te_cls),
        _row("Arith−Geo Spread", _pct(pr.spread, 4), "prof-value"),
        _row("Total Cost Drag", _pct(-total_drag), "prof-value-loss"),
    ])
    with c2:
        st.markdown(
            f'<div class="prof-card">'
            f'<div class="prof-card-header">Timing & Attribution</div>'
            f'{rows_2}</div>',
            unsafe_allow_html=True,
        )

    c3, c4 = st.columns(2)
    ms = pr.measure_selection

    # ── Card 3: Annualization Check ──────────────────────────────────────────
    ann_label = "Not annualized (< 1 yr)" if pr.hpr_short else f"CAGR: {_pct(pr.cagr_gross)}"

    rows_3 = "".join([
        _row("Period",      f"{pr.start_date} → {pr.end_date}", "prof-value"),
        _row("Trading days", str(pr.n_days), "prof-value"),
        _row("Annualized",   ann_label, _color_class(pr.cagr_gross or pr.hpr)),
    ])
    with c3:
        st.markdown(
            f'<div class="prof-card">'
            f'<div class="prof-card-header">Annualization Check</div>'
            f'{rows_3}</div>',
            unsafe_allow_html=True,
        )

    # ── Card 4: Measure Selection Log ───────────────────────────────────────
    cf_str       = f"Yes ({ms['n_cash_flows']})" if ms["cash_flows_detected"] else "No"
    outlier_str  = "Yes ⚠️" if ms["outliers_detected"] else "No"
    primary_disp = {"TWR+MWR": "TWR + MWR", "geometric": "Geometric/CAGR",
                    "arithmetic": "Arithmetic Mean"}.get(ms["primary_measure"], ms["primary_measure"])

    rows_4 = "".join([
        _row("Cash flows",      cf_str,       "prof-value"),
        _row("Outliers",        outlier_str,  "prof-value"),
        _row("Primary measure", primary_disp, "prof-value"),
        _row("Period",          f"{ms['n_days']} days", "prof-value"),
    ])
    with c4:
        st.markdown(
            f'<div class="prof-card">'
            f'<div class="prof-card-header">Measure Selection Log</div>'
            f'{rows_4}</div>',
            unsafe_allow_html=True,
        )


def _render_cost_config(config=None) -> CostAssumptions:
    """Collapsible cost & tax config panel. Returns user-configured CostAssumptions."""
    with st.expander("⚙️ Cost & Tax Assumptions", expanded=True):
        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown("**Tax Scenario**")
            scenario = st.radio(
                "Tax scenario",
                options=["🇨🇦 Canada", "🇺🇸 USA", "Tax-exempt", "Custom"],
                horizontal=True,
                key="prof_tax_scenario",
                label_visibility="collapsed",
            )
            scenario_key = {
                "🇨🇦 Canada": "canada",
                "🇺🇸 USA":    "usa",
                "Tax-exempt": "exempt",
            }.get(scenario, "custom")

            preset = PRESETS.get(scenario_key, CostAssumptions())

            st.markdown("")
            incl = st.number_input(
                "Inclusion rate (%)",
                value=preset.inclusion_rate * 100,
                min_value=0.0, max_value=100.0, step=1.0,
                key="prof_inclusion",
            )
            marg = st.number_input(
                "Marginal tax rate (%)",
                value=preset.marginal_tax_rate * 100,
                min_value=0.0, max_value=100.0, step=1.0,
                key="prof_marginal",
            )
            div_tax = st.number_input(
                "Dividend tax rate (%)",
                value=preset.dividend_tax_rate * 100,
                min_value=0.0, max_value=100.0, step=1.0,
                key="prof_dividend_tax",
            )

        with col_r:
            st.markdown("**Other Costs**")
            # Slippage is set globally in the sidebar — read-only here
            global_cfg = config or st.session_state.get("_config")
            slip = float(global_cfg.slippage_bps) if global_cfg else 7.5
            st.markdown(
                f'<div style="font-size:13px;color:#555;margin-bottom:8px">'
                f'Slippage: <strong>{slip} bps/trade</strong>'
                f'<span style="color:#888;font-size:11px"> (global sidebar setting)</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            fee = st.number_input(
                "Mgmt fee (% annual)",
                value=0.0, min_value=0.0, max_value=5.0, step=0.1,
                key="prof_mgmt_fee",
            )
            infl = st.slider(
                "Assumed inflation (%)",
                min_value=0.0, max_value=10.0, value=2.5, step=0.1,
                key="prof_inflation",
            )
            st.markdown(
                '<div class="info-note">ℹ️ Manual inflation input. '
                'Reference: current CPI ≈ 2.7% (2025). '
                'Auto CPI pull via FRED reserved for P2.</div>',
                unsafe_allow_html=True,
            )

    return CostAssumptions(
        slippage_bps=slip,
        mgmt_fee_annual_pct=fee,
        inclusion_rate=incl / 100,
        marginal_tax_rate=marg / 100,
        dividend_tax_rate=div_tax / 100,
        inflation_rate=infl / 100,
        tax_scenario=scenario_key,
    )


def _flowchart_dot(sel: dict) -> str:
    """Build Graphviz DOT for the measure-selection decision tree."""
    primary = sel["primary_measure"]
    has_cf  = sel["cash_flows_detected"]
    multi   = sel["multi_period"]
    outlier = sel["outliers_detected"]

    P  = "#660874"   # active node fill
    PT = "#ffffff"   # active node font
    PE = "#660874"   # active edge
    G  = "#f4f4f4"   # inactive node fill
    GT = "#888888"   # inactive node font
    GE = "#cccccc"   # inactive edge
    PB = "#e8d0f0"   # active node border

    def nf(active: bool) -> str:
        return f'fillcolor="{P if active else G}", fontcolor="{PT if active else GT}", color="{PB if active else "#e0e0e0"}"'

    def ef(active: bool) -> str:
        return f'color="{PE if active else GE}", fontcolor="{PE if active else GE}"'

    active_twr  = primary == "TWR+MWR"
    active_geo  = primary == "geometric"
    active_trim = primary == "arithmetic" and outlier
    active_arith= primary == "arithmetic"

    dot = f"""
digraph G {{
    rankdir=LR;
    size="9,3!";
    dpi=72;
    nodesep=0.28;
    ranksep=0.5;
    node [shape=box, style="rounded,filled", fontname="Arial", fontsize=9, margin="0.16,0.1", width=1.0, height=0.55];
    edge [fontname="Arial", fontsize=8];

    Q1 [{nf(True)}, label="External\\ncash flows?"];
    TWR [{nf(active_twr)}, label="TWR + MWR\\n(both shown)\\nSkill vs timing"];
    Q2  [{nf(not has_cf)}, label="Multi-period\\ncompounding?"];
    GEO [{nf(active_geo)}, label="Geometric\\nMean / CAGR\\nAvoids arith bias"];
    Q3  [{nf(not has_cf and not multi)}, label="Outliers\\ndetected?"];
    TRM [{nf(active_trim)}, label="Trimmed Mean\\nConsider for\\nrobustness"];
    ARM [{nf(active_arith and not outlier)}, label="Arithmetic\\nMean\\nSingle-period"];

    Q1 -> TWR [{ef(has_cf)}, label="YES"];
    Q1 -> Q2  [{ef(not has_cf)}, label="NO"];
    Q2 -> GEO [{ef(not has_cf and multi)}, label="YES"];
    Q2 -> Q3  [{ef(not has_cf and not multi)}, label="NO"];
    Q3 -> TRM [{ef(not has_cf and not multi and outlier)}, label="YES"];
    Q3 -> ARM [{ef(not has_cf and not multi and not outlier)}, label="NO"];
}}
"""
    return dot


def _render_flowchart(pr: ProfilerResult) -> None:
    st.markdown(
        '<div class="section-header">Measure Selection Flowchart</div>',
        unsafe_allow_html=True,
    )
    # Scale SVG to fill its column width proportionally — no height clipping
    # (rules live in ui/styles/profiler_tab.css alongside the rest of this page's CSS)
    ms = pr.measure_selection
    st.graphviz_chart(_flowchart_dot(ms), use_container_width=True)
    st.caption(f"**Why {ms['primary_measure']}?** {ms['reason']}")


def build_arith_geo_chart(
    nav_series: pd.Series,
    selected_window: str = "full",
) -> go.Figure:
    """
    Horizontal grouped bar chart — Arithmetic vs Geometric annualized return by year.

    Pipeline:
        NAV → monthly returns → group by calendar year
        → arithmetic_mean_return / geometric_mean_return on monthly series
        → annualize_arithmetic (×12) / annualize_geometric (^12−1)
        → display as annualized %

    selected_window: '1y' | '3y' | '5y' | 'full'
    """
    monthly_returns = get_monthly_returns(nav_series)

    if len(monthly_returns) < 2:
        fig = go.Figure()
        fig.add_annotation(
            text="Insufficient data (minimum 2 monthly observations required)",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#888888"),
        )
        fig.update_layout(paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", height=200)
        return fig

    # Determine start year for window filter
    end_year   = monthly_returns.index[-1].year
    start_year = {
        "1y": end_year - 1,
        "3y": end_year - 3,
        "5y": end_year - 5,
    }.get(selected_window, monthly_returns.index[0].year)

    years = sorted(
        y for y in monthly_returns.index.year.unique() if y >= start_year
    )

    window_labels: list[str]   = []
    arith_values:  list[float] = []
    geo_values:    list[float] = []

    for year in years:
        yr_list = monthly_returns[monthly_returns.index.year == year].tolist()
        if len(yr_list) < 2:
            continue
        is_partial  = len(yr_list) < 12
        label       = str(year) + (" *" if is_partial else "")
        arith_annual = annualize_arithmetic(arithmetic_mean_return(yr_list)) * 100
        geo_annual   = annualize_geometric(geometric_mean_return(yr_list))   * 100
        window_labels.append(label)
        arith_values.append(round(arith_annual, 2))
        geo_values.append(round(geo_annual,    2))

    # Full Period row — all months in window
    all_in_window = monthly_returns[monthly_returns.index.year >= start_year].tolist()
    if len(all_in_window) >= 2:
        window_labels.append("Full Period")
        arith_values.append(round(annualize_arithmetic(arithmetic_mean_return(all_in_window)) * 100, 2))
        geo_values.append(round(annualize_geometric(geometric_mean_return(all_in_window))   * 100, 2))

    if not window_labels:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available for selected window",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#888888"),
        )
        fig.update_layout(paper_bgcolor="#111111", plot_bgcolor="#111111", height=200)
        return fig

    # Reverse so most-recent / Full Period is at the top of the chart.
    window_labels = window_labels[::-1]
    arith_values  = arith_values[::-1]
    geo_values    = geo_values[::-1]

    _PURPLE = "#660874"
    _YELLOW = "#f5c518"
    _BG     = "#111111"
    _GRID   = "#222222"
    _TEXT   = "#FAFAFA"

    n_rows   = len(window_labels)
    # Numeric y positions: 0 = bottom, n_rows-1 = top
    # Use explicit offsets so bars never collapse — avoids barmode="group" categorical bug
    offset   = 0.20          # half-width of each bar
    y_geo    = [i + offset for i in range(n_rows)]
    y_arith  = [i - offset for i in range(n_rows)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Geometric Mean (CAGR)",
        y=y_geo, x=geo_values,
        orientation="h",
        width=offset * 2,
        marker_color=_PURPLE,
        marker_line_width=0,
        opacity=1.0,
    ))
    fig.add_trace(go.Bar(
        name="Arithmetic Mean",
        y=y_arith, x=arith_values,
        orientation="h",
        width=offset * 2,
        marker_color=_YELLOW,
        marker_line_width=0,
        opacity=0.9,
    ))

    # Δ annotations — Arith − Geo gap, anchored right of the longer bar
    x_max = max(max(geo_values + arith_values, default=1), 1)
    annotations = []
    for i, (label, geo, arith) in enumerate(zip(window_labels, geo_values, arith_values)):
        delta    = arith - geo
        x_anchor = max(geo, arith, 0) + x_max * 0.04
        annotations.append(dict(
            x=x_anchor, y=i,
            text=f"Δ {delta:+.2f}%",
            showarrow=False,
            font=dict(size=10, color="#aaaaaa"),
            xanchor="left",
            yanchor="middle",
        ))

    fig.update_layout(
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(family="Inter, sans-serif", size=11, color=_TEXT),
        xaxis=dict(
            title=dict(text="Annualized Return (%)", font=dict(color=_TEXT)),
            zeroline=True, zerolinecolor="#444444", zerolinewidth=1,
            gridcolor=_GRID,
            tickfont=dict(color=_TEXT),
        ),
        yaxis=dict(
            tickvals=list(range(n_rows)),
            ticktext=window_labels,
            gridcolor=_GRID,
            tickfont=dict(color=_TEXT),
            range=[-0.6, n_rows - 0.4],   # tight bounds so bars fill the space
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(color=_TEXT),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=100, t=45, b=40),
        annotations=annotations,
        height=max(280, n_rows * 80),
        barmode="overlay",   # traces are manually offset — overlay keeps them independent
    )
    return fig


def _render_arith_geo_chart(pr: ProfilerResult) -> None:
    st.markdown(
        '<div class="section-header">Arithmetic vs Geometric Return by Period</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Based on monthly returns, annualized — "
        "Arithmetic: R̄ × 12 | Geometric (CAGR): (1 + R̄)¹² − 1"
    )

    window = st.radio(
        "Window",
        options=["1Y", "3Y", "5Y", "Full"],
        index=3,
        horizontal=True,
        key="prof_ag_window",
    )

    # Reconstruct nav from stored dict (same pattern as TWR/MWR curve)
    nav = pd.Series(
        {pd.Timestamp(k): v for k, v in pr.nav_dict.items()}
    ).sort_index()

    fig = build_arith_geo_chart(nav, selected_window=window.lower())
    st.plotly_chart(fig, use_container_width=True)

    # Footnote for partial years
    if any(label.endswith(" *") for label in
           (get_monthly_returns(nav).pipe(lambda s: [
               str(y) + " *"
               for y in s.index.year.unique()
               if len(s[s.index.year == y]) < 12
           ]))):
        st.caption(
            r"\* Partial year — fewer than 12 monthly observations; "
            "annualized from available months only."
        )


def _render_twr_mwr_curves(pr: ProfilerResult, transactions: list) -> None:
    """Only shown if external cash flows exist."""
    ms = pr.measure_selection
    if not ms["cash_flows_detected"]:
        st.markdown(
            '<div class="info-note">ℹ️ TWR = MWR when no external cash flows are present.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<div class="section-header">TWR vs MWR Equity Curve</div>',
        unsafe_allow_html=True,
    )

    # Reconstruct NAV series
    nav = pd.Series(
        {pd.Timestamp(k): v for k, v in pr.nav_dict.items()}
    ).sort_index()

    if nav.empty or len(nav) < 2:
        st.info("NAV data unavailable for equity curve.")
        return

    # TWR curve: normalized NAV
    twr_curve = nav / nav.iloc[0]

    # MWR curve: hypothetical constant-rate compound growth
    mwr_annual = pr.mwr  # already annualized IRR
    days_from_start = [(idx - nav.index[0]).days for idx in nav.index]
    mwr_curve = pd.Series(
        [(1 + mwr_annual) ** (d / 365.25) for d in days_from_start],
        index=nav.index,
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=twr_curve.index, y=twr_curve.values,
        name="TWR (actual NAV)",
        line=dict(color="#818cf8", width=2),
        mode="lines",
    ))
    fig.add_trace(go.Scatter(
        x=mwr_curve.index, y=mwr_curve.values,
        name="MWR (implied)",
        line=dict(color="#34d399", width=2, dash="dash"),
        mode="lines",
    ))

    # Event markers from executed scheduled transactions
    executed = [t for t in transactions if getattr(t, "is_executed", False) and not t.error]
    buy_dates, buy_vals, buy_labels = [], [], []
    sell_dates, sell_vals, sell_labels = [], [], []

    for t in executed:
        dt = pd.Timestamp(t.actual_date or t.date)
        idx = nav.index.searchsorted(dt)
        if idx >= len(nav):
            idx = len(nav) - 1
        val = twr_curve.iloc[idx]
        label = (
            f"{'BUY' if t.is_buy() else 'SELL'} {t.ticker}<br>"
            f"Date: {dt.date()}<br>"
            f"Value: ${t.executed_value:,.0f}" if t.executed_value else ""
        )
        if t.is_buy():
            buy_dates.append(dt); buy_vals.append(val); buy_labels.append(label)
        else:
            sell_dates.append(dt); sell_vals.append(val); sell_labels.append(label)

    if buy_dates:
        fig.add_trace(go.Scatter(
            x=buy_dates, y=buy_vals,
            mode="markers",
            name="BUY",
            marker=dict(color="#fbbf24", size=9, symbol="circle"),
            hovertext=buy_labels,
            hoverinfo="text",
        ))
    if sell_dates:
        fig.add_trace(go.Scatter(
            x=sell_dates, y=sell_vals,
            mode="markers",
            name="SELL",
            marker=dict(color="#f43f5e", size=9, symbol="circle"),
            hovertext=sell_labels,
            hoverinfo="text",
        ))

    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, sans-serif", size=12),
        xaxis=dict(gridcolor="#f0f0f0"),
        yaxis=dict(title="Growth of $1", gridcolor="#f0f0f0", tickformat=".2f"),
        legend=dict(orientation="h", y=1.06, x=0),
        margin=dict(l=10, r=10, t=40, b=10),
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True)

    # KPI chips
    te_sign = "▲" if pr.timing_effect_bps >= 0 else "▼"
    te_cls  = "chip" if pr.timing_effect_bps >= 0 else "chip-neutral"
    st.markdown(
        f'<span class="chip">TWR: {_pct(pr.twr)}</span>'
        f'<span class="chip">MWR: {_pct(pr.mwr)}</span>'
        f'<span class="{te_cls}">Timing Effect: {pr.timing_effect_bps:+.0f} bps {te_sign}</span>',
        unsafe_allow_html=True,
    )


def _build_waterfall_chart(wf: dict) -> go.Figure:
    """Manual waterfall via go.Bar — avoids go.Waterfall marker= ValueError."""
    labels = ["Gross Return", "Slippage", "Mgmt Fee", "Tax", "Inflation", "Real Net"]
    colors = ["#2563eb", "#b45309", "#7c3aed", "#be123c", "#065f46", "#0e7490"]

    # Drag columns expressed as negative bar values
    bar_values = [
        wf["gross"] * 100,
        -(wf["gross"]          - wf["after_slippage"]) * 100,
        -(wf["after_slippage"] - wf["after_fees"])     * 100,
        -(wf["after_fees"]     - wf["after_tax"])      * 100,
        -(wf["after_tax"]      - wf["real_net"])       * 100,
        wf["real_net"] * 100,
    ]

    fig = go.Figure(go.Bar(
        x=labels,
        y=bar_values,
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in bar_values],
        textposition="outside",
    ))
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, sans-serif", size=12),
        yaxis=dict(
            title="Return (%)",
            zeroline=True,
            zerolinecolor="#cccccc",
            gridcolor="#f0f0f0",
        ),
        xaxis=dict(gridcolor="#f0f0f0"),
        showlegend=False,
        margin=dict(l=10, r=10, t=20, b=60),
        height=350,
    )
    gross = wf["gross"] * 100
    net   = wf["real_net"] * 100
    drag  = gross - net
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=-0.22,
        text=f"Total drag: −{drag:.2f}% | Gross: {gross:.2f}% → Real Net: {net:.2f}%",
        showarrow=False,
        font=dict(size=11, color="#666666"),
        xanchor="left",
    )
    return fig


def _render_waterfall(pr: ProfilerResult) -> None:
    st.markdown(
        '<div class="section-header">Gross → Real Net Return Waterfall</div>',
        unsafe_allow_html=True,
    )

    fig = _build_waterfall_chart(pr.waterfall)
    st.plotly_chart(fig, use_container_width=True)

    wf = pr.waterfall
    total_drag = wf["gross"] - wf["real_net"]
    cagr_gross_str = _pct(pr.cagr_gross) if pr.cagr_gross is not None else "N/A (< 1 yr)"
    real_str       = _pct(pr.cagr_net_real) if pr.cagr_net_real is not None else "N/A (< 1 yr)"
    st.caption(
        f"**Total drag:** {_pct(-total_drag)} | "
        f"**Gross CAGR:** {cagr_gross_str} → **Real Net CAGR:** {real_str}"
    )


def _render_leverage_cards(pr: ProfilerResult) -> None:
    st.markdown(
        '<div class="section-header">Leverage Sensitivity</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="amber-banner">⚠️ Hypothetical analysis — based on historical backtest results. '
        'Not a simulation of real leveraged trading.</div>',
        unsafe_allow_html=True,
    )

    borrow_col, _ = st.columns([1, 2])
    with borrow_col:
        borrow_rate = st.number_input(
            "Borrowing rate (%/year)",
            value=4.0, min_value=0.0, max_value=30.0, step=0.25,
            key="prof_borrow_rate",
        ) / 100

    base_cagr = pr.cagr_gross or pr.hpr
    st.caption(f"Base CAGR (auto-filled from profiler): **{_pct(base_cagr)}**")

    scenarios = leverage_scenarios(
        base_cagr=base_cagr,
        base_drawdown=pr.base_drawdown,
        borrowing_rate=borrow_rate,
    )

    cols = st.columns(4)
    ratio_colors = {1.0: "#6366f1", 1.5: "#059669", 2.0: "#d97706", 3.0: "#be123c"}

    for col, sc in zip(cols, scenarios):
        ratio    = sc["ratio"]
        lev_cagr = sc["leveraged_cagr"]
        dd_amp   = sc["max_drawdown_amplified"]
        mc       = sc["margin_call_threshold"]
        warn     = sc["warning"]

        cagr_color = (
            "#059669" if lev_cagr > 0.05
            else "#d97706" if lev_cagr > 0
            else "#be123c"
        )
        rc = ratio_colors.get(ratio, "#6366f1")

        warn_html = ""
        if warn:
            warn_html = (
                f'<div style="background:#fee2e2;color:#be123c;border-radius:6px;'
                f'padding:4px 8px;font-size:11px;margin-top:6px;">'
                f'⚠️ DD {_pct(dd_amp)} — margin call at {_pct(mc)} move</div>'
            )

        with col:
            st.markdown(
                f'<div class="lev-card">'
                f'<div class="lev-ratio" style="color:{rc};">{ratio:.1f}×</div>'
                f'<div class="lev-metric-label">CAGR (Net)</div>'
                f'<div class="lev-metric-value" style="color:{cagr_color};">{_pct(lev_cagr)}</div>'
                f'<div class="lev-metric-label">Max Drawdown</div>'
                f'<div class="lev-metric-value" style="color:#be123c;">{_pct(dd_amp)}</div>'
                f'<div class="lev-metric-label">Margin call at</div>'
                f'<div class="lev-metric-value" style="color:#be123c;">{_pct(mc)} move</div>'
                f'{warn_html}'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Public entry point ────────────────────────────────────────────────────────

def render_profiler_tab(
    single_result: Optional[BacktestResult],
    group_results: dict[str, BacktestResult],
    config: Config,
    mode: str,
) -> None:
    """Main render function — called from ui/app.py results_section."""
    _inject_css("profiler_tab")

    # ── Group selector ────────────────────────────────────────────────────────
    if mode == "group" and group_results:
        group_names    = list(group_results.keys())
        selected_group = st.selectbox(
            "Select group", group_names, key="prof_group_sel"
        )
        active_result = group_results[selected_group]
        txn_key       = f"txns_group_{selected_group}"
        transactions  = st.session_state.get(txn_key, [])
        cache_key     = f"profiler_result_group_{selected_group}"
    else:
        # Fix 2: scope cache key to the active slot so switching Same Day ↔ Multi-Date
        # never surfaces a stale profiler result from the other mode.
        buy_mode    = st.session_state.get("buy_mode_home", "same_day")
        slot_key    = f"single_{buy_mode}"
        slots       = st.session_state.get("simulation_slots", {})
        # Read result from the slot that matches the CURRENT mode, not the last-run result.
        slot_result   = slots.get(slot_key)
        active_result = slot_result if slot_result is not None else single_result
        transactions  = st.session_state.get("txns_single", [])
        cache_key     = f"profiler_result_{slot_key}"

    # ── Guard: no backtest ────────────────────────────────────────────────────
    if not active_result:
        st.warning("⚠️ Run a backtest first to enable the Return Analysis.")
        return

    # ── Cost & Tax configuration (always at top) ──────────────────────────────
    cost = _render_cost_config(config)

    run_disabled = active_result is None
    if st.button(
        "▶ Run Return Analysis",
        type="primary",
        disabled=run_disabled,
        use_container_width=True,
        key="prof_run_btn",
    ):
        with st.spinner("Computing profiler metrics…"):
            try:
                profiler_result = compute_profiler(active_result, transactions, cost)
                st.session_state[cache_key] = profiler_result
                st.rerun()
            except Exception as exc:
                st.error(f"Profiler error: {exc}")
                return

    # ── Results (KPI cards + visualizations) rendered below settings ──────────
    profiler_result: Optional[ProfilerResult] = st.session_state.get(cache_key)
    if profiler_result is None:
        st.info("Configure assumptions above and click **▶ Run Return Analysis**.")
        return

    st.markdown("---")
    _render_kpi_cards(profiler_result)
    st.markdown("---")
    _render_flowchart(profiler_result)

    st.markdown("---")
    _render_arith_geo_chart(profiler_result)

    st.markdown("---")
    st.markdown(
        '<div class="section-header">TWR vs MWR Equity Curve</div>',
        unsafe_allow_html=True,
    )
    _render_twr_mwr_curves(profiler_result, transactions)

    st.markdown("---")
    _render_waterfall(profiler_result)

    st.markdown("---")
    _render_leverage_cards(profiler_result)
