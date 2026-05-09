"""
ui/components/simple_mode/page4_risk.py — Step 4: Risk Evaluation.

Sub-page: Risk Management / Snapshot
Future sub-pages slot in as siblings at the same level.

Sections:
  KPI strip | VaR & CVaR panel | Drawdown panel | Stress Testing |
  Correlation matrix | Factor Exposure | Rolling Risk panel
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stock_engine.analytics.engine import AnalyticsEngine
from stock_engine.analytics.risk import compute_risk
from stock_engine.config import Config
from stock_engine.data.yfinance_provider import YFinanceProvider
from stock_engine.portfolio.models import CandidateStatus
from stock_engine.ui.components.simple_mode.session import (
    get_session, next_step, prev_step,
)
from stock_engine.viz.theme import DEFAULT_THEME

_PALETTE   = ["#8a0a9e", "#378add", "#4ade80", "#fb923c"]
_BM_COLOR  = "#9ca3af"


def render_page4(config: Config) -> None:
    sess     = get_session()
    computed = [c for c in sess.portfolios
                if c.status == CandidateStatus.COMPUTED and c.backtest_result is not None]

    if not computed:
        st.info("No computed candidates. Return to Step 2 and run at least one backtest.")
        _bottom_bar(False)
        return

    # Sub-page selector (extensibility hook — currently only Snapshot)
    sub_pages = ["Risk Management / Snapshot"]
    sel_sub   = st.selectbox("Sub-page", sub_pages, key="p4_sub",
                              label_visibility="collapsed")

    st.markdown(
        f'<div style="font-size:9px;color:#660874;font-weight:600;'
        f'letter-spacing:.08em;text-transform:uppercase;margin-bottom:12px">'
        f'{sel_sub}</div>',
        unsafe_allow_html=True,
    )

    analytics  = AnalyticsEngine(config)
    provider   = YFinanceProvider(config)

    # Strategy selector
    names    = [c.label for c in computed]
    sel_name = st.selectbox("Strategy", names, key="p4_strat_sel")
    cand     = next(c for c in computed if c.label == sel_name)
    res      = cand.backtest_result

    # Compute / cache RiskResult
    cache_key = f"p4_risk_{cand.candidate_id}"
    if cache_key not in st.session_state or cand.is_stale:
        with st.spinner("Computing risk metrics…"):
            try:
                dr      = analytics.daily_returns(res)
                bm_ret  = res.benchmark_returns

                # Build constituent returns DataFrame
                tickers = res.tickers or list(res.snapshots[-1].positions.keys())
                frames  = {}
                for t in tickers:
                    try:
                        df  = provider.fetch_historical(t, res.start_date, res.end_date, "1d")
                        col = config.price_field.lower()
                        if col not in df.columns: col = "close"
                        frames[t] = df[col].dropna().pct_change().dropna()
                    except Exception:
                        pass
                const_rets = pd.DataFrame(frames) if frames else None

                risk = compute_risk(
                    returns=dr,
                    weights=cand.weights,
                    constituent_returns=const_rets,
                    benchmark_returns=bm_ret,
                )
                cand.risk_result = risk
                st.session_state[cache_key] = risk
            except Exception as e:
                st.error(f"Risk computation failed: {e}")
                _bottom_bar(True)
                return
    else:
        risk = st.session_state[cache_key]

    dr = analytics.daily_returns(res)

    # ── 1. KPI strip ──────────────────────────────────────────────────────────
    _render_kpi_strip(risk, computed, analytics, names)

    st.markdown("---")

    # ── 2. VaR & CVaR panel ───────────────────────────────────────────────────
    _render_var_panel(computed, analytics, config, provider)

    st.markdown("---")

    # ── 3. Drawdown panel ─────────────────────────────────────────────────────
    _render_drawdown_panel(risk, dr, analytics, res)

    st.markdown("---")

    # ── 4. Stress Testing ─────────────────────────────────────────────────────
    _render_stress_test(risk)

    st.markdown("---")

    # ── 5. Correlation matrix (realized, backtest period) ─────────────────────
    _render_corr_matrix(res, config, provider)

    st.markdown("---")

    # ── 6. Factor Exposure ────────────────────────────────────────────────────
    _render_factor_exposure(risk, names, sel_name)

    st.markdown("---")

    # ── 7. Rolling Risk ───────────────────────────────────────────────────────
    _render_rolling_risk(computed, analytics)

    st.markdown("---")
    _bottom_bar(True)


# ── KPI strip ─────────────────────────────────────────────────────────────────

def _render_kpi_strip(risk, computed, analytics, names):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Max Drawdown",
              f"{risk.max_drawdown:.1%}" if risk.max_drawdown is not None else "—")
    c2.metric("VaR 95 (1D, param)",
              f"{risk.var_95_param:.2%}" if risk.var_95_param is not None else "—")
    c3.metric("CVaR 95 (1D, param)",
              f"{risk.cvar_95_param:.2%}" if risk.cvar_95_param is not None else "—")
    c4.metric("Calmar",
              f"{risk.calmar_ratio:.2f}" if risk.calmar_ratio is not None else "—")


# ── VaR & CVaR panel ──────────────────────────────────────────────────────────

def _render_var_panel(computed, analytics, config, provider):
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:8px">VAR & CVAR — 1-DAY</div>',
        unsafe_allow_html=True,
    )
    rows = []
    for cand in computed:
        risk = cand.risk_result
        if risk is None:
            continue
        bm_label = getattr(cand.backtest_result, "benchmark_ticker", None) or "BM"
        rows.append({
            "Strategy":             cand.label,
            "VaR 95% (param)":      f"{risk.var_95_param:.2%}"  if risk.var_95_param  is not None else "—",
            "CVaR 95% (param)":     f"{risk.cvar_95_param:.2%}" if risk.cvar_95_param is not None else "—",
            "VaR 99% (param)":      f"{risk.var_99_param:.2%}"  if risk.var_99_param  is not None else "—",
            "CVaR 99% (param)":     f"{risk.cvar_99_param:.2%}" if risk.cvar_99_param is not None else "—",
            "VaR 95% (hist)":       f"{risk.var_95_hist:.2%}"   if risk.var_95_hist   is not None else "—",
            "CVaR 95% (hist)":      f"{risk.cvar_95_hist:.2%}"  if risk.cvar_95_hist  is not None else "—",
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Tail distribution mini-chart (return histogram)
    sel = st.session_state.get("p4_strat_sel", computed[0].label)
    cand = next((c for c in computed if c.label == sel), computed[0])
    try:
        dr = analytics.daily_returns(cand.backtest_result)
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=(dr * 100).values, nbinsx=60,
            marker_color="#8a0a9e", opacity=0.7,
            name="Daily Returns",
        ))
        if cand.risk_result and cand.risk_result.var_95_param is not None:
            v = cand.risk_result.var_95_param * 100
            fig.add_vline(x=v, line_color="#e03030", line_dash="dash", line_width=1.5,
                          annotation_text="VaR 95%", annotation_font_size=9,
                          annotation_font_color="#e03030")
        _apply_dark_layout(fig, height=180)
        st.plotly_chart(fig, use_container_width=True, key="p4_tail_hist",
                        config=dict(displayModeBar=False))
    except Exception:
        pass


# ── Drawdown panel ────────────────────────────────────────────────────────────

def _render_drawdown_panel(risk, dr, analytics, res):
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:8px">DRAWDOWN ANALYSIS</div>',
        unsafe_allow_html=True,
    )
    col_events, col_bar = st.columns([3, 2])

    with col_events:
        st.caption("Top 5 Drawdown Events")
        if risk.drawdown_events:
            event_rows = []
            for ev in risk.drawdown_events:
                event_rows.append({
                    "Period":        ev.get("period", "—"),
                    "Depth":         f"{ev['depth']:.1%}" if ev.get("depth") is not None else "—",
                    "Recovery Days": str(ev.get("recovery_days") or "ongoing"),
                })
            st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No significant drawdown events.")

    with col_bar:
        # MaxDD comparison bar across strategies (from session)
        sess     = get_session()
        computed = [c for c in sess.portfolios
                    if c.status == CandidateStatus.COMPUTED and c.risk_result is not None]
        if computed:
            labels = [c.label for c in computed]
            mdd_vals = [abs(c.risk_result.max_drawdown or 0) * 100 for c in computed]
            fig = go.Figure(go.Bar(
                y=labels, x=mdd_vals, orientation="h",
                marker_color="#e03030", opacity=0.8,
            ))
            fig.update_layout(
                paper_bgcolor=DEFAULT_THEME.bg_paper,
                plot_bgcolor=DEFAULT_THEME.bg_plot,
                height=160, margin=dict(l=10, r=30, t=10, b=20),
                xaxis=dict(ticksuffix="%", gridcolor=DEFAULT_THEME.grid_color,
                           tickfont=dict(color=DEFAULT_THEME.font_color, size=9)),
                yaxis=dict(tickfont=dict(color=DEFAULT_THEME.font_color, size=9)),
                font=dict(color=DEFAULT_THEME.font_color, family=DEFAULT_THEME.font_family),
            )
            st.plotly_chart(fig, use_container_width=True, key="p4_mdd_bar",
                            config=dict(displayModeBar=False))


# ── Stress Testing ────────────────────────────────────────────────────────────

def _render_stress_test(risk):
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:8px">STRESS TESTING — CRISIS WINDOWS</div>',
        unsafe_allow_html=True,
    )
    if not risk.stress_results:
        st.caption("Stress test data unavailable (requires constituent returns).")
        return

    cols = st.columns(len(risk.stress_results))
    for col, sc in zip(cols, risk.stress_results):
        with col:
            pr = sc.get("portfolio_return")
            bm = sc.get("bm_return")
            ex = sc.get("excess_return")
            pr_str = f"{pr:.1%}" if pr is not None else "N/A"
            pr_col = "#e03030" if (pr is not None and pr < 0) else "#00b050"
            hedge  = ""
            if ex is not None:
                hedge = "hedge ✓" if ex > 0 else "underperformed"
                hedge_col = "#00b050" if ex > 0 else "#e03030"
            else:
                hedge_col = "#888"

            st.markdown(
                f'<div style="border:1.5px solid #e0d0e8;border-radius:8px;'
                f'padding:10px;background:#f8f8f8">'
                f'<div style="font-size:9px;font-weight:600;color:#660874;margin-bottom:4px">'
                f'{sc["scenario_name"]}</div>'
                f'<div style="font-size:9px;color:#888;margin-bottom:6px">{sc["period"]}</div>'
                f'<div style="font-size:18px;font-weight:600;color:{pr_col}">{pr_str}</div>'
                f'<div style="font-size:9px;color:#888">vs BM '
                f'{f"{bm:.1%}" if bm is not None else "N/A"}</div>'
                f'<div style="font-size:9px;color:{hedge_col};margin-top:3px">{hedge}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Correlation matrix ────────────────────────────────────────────────────────

def _render_corr_matrix(res, config, provider):
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:8px">'
        'REALIZED CORRELATION — BACKTEST PERIOD</div>',
        unsafe_allow_html=True,
    )
    tickers = res.tickers or list(res.snapshots[-1].positions.keys())
    if len(tickers) < 2:
        st.caption("Need ≥2 assets.")
        return

    with st.spinner("Loading…"):
        try:
            frames = {}
            for t in tickers:
                df  = provider.fetch_historical(t, res.start_date, res.end_date, "1d")
                col = config.price_field.lower()
                if col not in df.columns: col = "close"
                frames[t] = df[col].dropna().pct_change().dropna()

            corr = pd.DataFrame(frames).dropna().corr()
            fig  = go.Figure(go.Heatmap(
                z=corr.values, x=corr.columns.tolist(), y=corr.index.tolist(),
                colorscale=[[0, "#1e40af"], [0.5, "#1a1a2e"], [1, "#b91c1c"]],
                zmin=-1, zmax=1,
                text=[[f"{v:.2f}" for v in row] for row in corr.values],
                texttemplate="%{text}",
                textfont=dict(size=9, color="#e2e8f0"),
                hovertemplate="%{y} × %{x}: %{z:.3f}<extra></extra>",
            ))
            fig.update_layout(
                paper_bgcolor="#111111", plot_bgcolor="#111111",
                height=260, margin=dict(l=60, r=20, t=10, b=60),
                xaxis=dict(tickfont=dict(color="#ccc", size=9)),
                yaxis=dict(tickfont=dict(color="#ccc", size=9)),
            )
            st.plotly_chart(fig, use_container_width=True, key="p4_corr",
                            config=dict(displayModeBar=False))
        except Exception as e:
            st.caption(f"Correlation unavailable: {e}")


# ── Factor Exposure ───────────────────────────────────────────────────────────

def _render_factor_exposure(risk, names, sel_name):
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:8px">FACTOR EXPOSURE (FF5+UMD)</div>',
        unsafe_allow_html=True,
    )
    if not risk.factor_betas:
        st.caption("Run Factor Regression in Step 3 first — betas will populate here.")
        return

    factors = list(risk.factor_betas.keys())
    betas   = [risk.factor_betas[f] for f in factors]
    colors  = ["#00b050" if b >= 0 else "#e03030" for b in betas]

    fig = go.Figure(go.Bar(
        y=factors, x=betas, orientation="h",
        marker_color=colors, opacity=0.85,
    ))
    _apply_dark_layout(fig, height=200)
    fig.add_vline(x=0, line_color="rgba(255,255,255,0.3)", line_width=1)
    st.plotly_chart(fig, use_container_width=True, key="p4_factor_bar",
                    config=dict(displayModeBar=False))

    c_r2, c_te, c_ir = st.columns(3)
    c_r2.metric("R²",              f"{risk.factor_r2:.3f}"        if risk.factor_r2        is not None else "—")
    c_te.metric("Tracking Error",  f"{risk.tracking_error:.2%}"   if risk.tracking_error   is not None else "—")
    c_ir.metric("Info Ratio",      f"{risk.information_ratio:.2f}" if risk.information_ratio is not None else "—")


# ── Rolling Risk ──────────────────────────────────────────────────────────────

def _render_rolling_risk(computed, analytics):
    st.markdown(
        '<div style="font-size:9px;color:#999;letter-spacing:.08em;'
        'text-transform:uppercase;margin-bottom:8px">ROLLING RISK</div>',
        unsafe_allow_html=True,
    )
    col_win, col_met = st.columns([1, 1])
    with col_win:
        window = st.selectbox("Window", ["60D", "126D", "252D"], index=1, key="p4_roll_win")
    with col_met:
        metric = st.selectbox("Metric", ["Volatility", "VaR 95%", "Sharpe"], key="p4_roll_met")

    w = int(window.replace("D", ""))
    fig = go.Figure()
    for i, cand in enumerate(computed):
        try:
            dr = analytics.daily_returns(cand.backtest_result)
            if metric == "Volatility":
                series = dr.rolling(w).std() * np.sqrt(252) * 100
                ysfx   = "%"
            elif metric == "VaR 95%":
                series = dr.rolling(w).quantile(0.05) * 100
                ysfx   = "%"
            else:  # Sharpe
                roll_mean = dr.rolling(w).mean()
                roll_std  = dr.rolling(w).std()
                series    = (roll_mean / roll_std * np.sqrt(252)).where(roll_std > 0)
                ysfx      = ""

            fig.add_trace(go.Scatter(
                x=series.index, y=series.values,
                name=cand.label, mode="lines",
                line=dict(color=_PALETTE[i % len(_PALETTE)], width=1.5),
            ))
        except Exception:
            pass

    _apply_dark_layout(fig, height=220, yaxis_suffix=ysfx)
    st.plotly_chart(fig, use_container_width=True, key="p4_rolling",
                    config=dict(displayModeBar=False))


# ── Layout helpers ────────────────────────────────────────────────────────────

def _apply_dark_layout(fig, height=220, yaxis_suffix=""):
    axis = dict(gridcolor=DEFAULT_THEME.grid_color, showgrid=True, zeroline=False,
                tickfont=dict(color=DEFAULT_THEME.font_color, size=9))
    fig.update_layout(
        paper_bgcolor=DEFAULT_THEME.bg_paper,
        plot_bgcolor=DEFAULT_THEME.bg_plot,
        font=dict(family=DEFAULT_THEME.font_family, size=10, color=DEFAULT_THEME.font_color),
        height=height,
        margin=dict(l=45, r=20, t=20, b=36),
        hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.04, bgcolor="rgba(0,0,0,0)",
                    font=dict(color=DEFAULT_THEME.font_color, size=9)),
    )
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis, ticksuffix=yaxis_suffix)


# ── Bottom bar ────────────────────────────────────────────────────────────────

def _bottom_bar(can_proceed):
    c_back, _, c_next = st.columns([1, 4, 1])
    with c_back:
        if st.button("← Back", key="p4_back", use_container_width=True):
            prev_step()
    with c_next:
        if st.button("Next →", key="p4_next", type="primary",
                     use_container_width=True, disabled=not can_proceed):
            next_step()
