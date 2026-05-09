"""
ui/components/univariate_panel.py — Streamlit rendering for the univariate profiler.
Displayed inline in the Overview tab below the existing 5-metric bar.
"""
from __future__ import annotations

import streamlit as st

from stock_engine.analytics.univariate import UnivariateProfile, fmt_pct, fmt_pct_plain, fmt_memory
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.viz.univariate_charts import (
    return_histogram, return_boxplot, return_qq, return_acf, return_cdf,
)


def _kpi(label: str, value: str, cls: str = "uv-kpi-value") -> str:
    return (
        f'<div class="uv-kpi-cell">'
        f'<div class="uv-kpi-label">{label}</div>'
        f'<div class="{cls}">{value}</div>'
        f'</div>'
    )


def render_univariate_panel(profile: UnivariateProfile) -> None:
    """
    Render the univariate profiler for a portfolio daily return series.
    Called from tab_overview in app.py, below the existing 5-metric bar.
    """
    _inject_css("univariate_panel")
    st.markdown(
        '<div class="uv-section">Daily Return Distribution — Univariate Profile</div>',
        unsafe_allow_html=True,
    )

    # ── Summary Counts KPI strip ──────────────────────────────────────────
    st.markdown(
        '<div class="uv-kpi-label" style="margin-bottom:4px">Summary Counts</div>',
        unsafe_allow_html=True,
    )
    strip_counts = (
        '<div class="uv-kpi-strip">'
        + _kpi("Observations", f"{profile.n_total:,}")
        + _kpi("Non-null", f"{profile.n_nonnull:,}")
        + _kpi("Null", f"{profile.n_null:,}")
        + _kpi("Zeros", f"{profile.n_zeros:,}")
        + _kpi("Inf", f"{profile.n_inf:,}")
        + _kpi("Memory", fmt_memory(profile.memory_bytes))
        + '</div>'
    )
    st.markdown(strip_counts, unsafe_allow_html=True)

    # ── Descriptive Stats KPI strip ───────────────────────────────────────
    st.markdown(
        '<div class="uv-kpi-label" style="margin-bottom:4px">Descriptive Statistics</div>',
        unsafe_allow_html=True,
    )
    mean_cls = "uv-kpi-value-pos" if profile.mean >= 0 else "uv-kpi-value-neg"
    ann_cls  = "uv-kpi-value-pos" if profile.annualised_mean >= 0 else "uv-kpi-value-neg"
    strip_desc = (
        '<div class="uv-kpi-strip">'
        + _kpi("Mean (daily)", fmt_pct(profile.mean, 3), mean_cls)
        + _kpi("Median",       fmt_pct(profile.median, 3))
        + _kpi("Std",          fmt_pct_plain(profile.std, 3))
        + _kpi("Ann. Return",  fmt_pct(profile.annualised_mean, 2), ann_cls)
        + _kpi("Ann. Vol",     fmt_pct_plain(profile.annualised_vol, 2))
        + _kpi("Skewness",     f"{profile.skewness:+.3f}")
        + _kpi("Kurtosis",     f"{profile.kurtosis:+.3f}")
        + _kpi("CV",           f"{profile.cv:.2f}" if profile.cv != float("inf") else "∞")
        + _kpi("MAD",          fmt_pct_plain(profile.mad, 4))
        + '</div>'
    )
    st.markdown(strip_desc, unsafe_allow_html=True)

    # ── Quantile Stats KPI strip ──────────────────────────────────────────
    st.markdown(
        '<div class="uv-kpi-label" style="margin-bottom:4px">Quantiles</div>',
        unsafe_allow_html=True,
    )
    strip_q = (
        '<div class="uv-kpi-strip">'
        + _kpi("Min",    fmt_pct(profile.q_min, 3), "uv-kpi-value-neg" if profile.q_min < 0 else "uv-kpi-value")
        + _kpi("P5",     fmt_pct(profile.q_p05, 3))
        + _kpi("Q1",     fmt_pct(profile.q_q1, 3))
        + _kpi("Median", fmt_pct(profile.q_median, 3))
        + _kpi("Q3",     fmt_pct(profile.q_q3, 3))
        + _kpi("P95",    fmt_pct(profile.q_p95, 3))
        + _kpi("Max",    fmt_pct(profile.q_max, 3), "uv-kpi-value-pos" if profile.q_max > 0 else "uv-kpi-value")
        + _kpi("Range",  fmt_pct_plain(profile.q_range, 3))
        + _kpi("IQR",    fmt_pct_plain(profile.q_iqr, 3))
        + '</div>'
    )
    st.markdown(strip_q, unsafe_allow_html=True)

    # ── Alerts ────────────────────────────────────────────────────────────
    if profile.alerts:
        for alert in profile.alerts:
            st.markdown(
                f'<div class="uv-alert">⚠ {alert}</div>',
                unsafe_allow_html=True,
            )

    # ── Charts ────────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(return_histogram(profile), use_container_width=True)
    with c2:
        st.plotly_chart(return_boxplot(profile),   use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(return_qq(profile),  use_container_width=True)
    with c4:
        st.plotly_chart(return_acf(profile), use_container_width=True)

    st.plotly_chart(return_cdf(profile), use_container_width=True)
