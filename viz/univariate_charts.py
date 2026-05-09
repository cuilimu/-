"""
viz/univariate_charts.py — Plotly figures for the univariate return profiler.
All charts use dark background to match the existing backtest chart theme.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from scipy import stats as scipy_stats

from stock_engine.analytics.univariate import UnivariateProfile, fmt_pct

# ── Shared style constants ────────────────────────────────────────────────────
_BG        = "#0e1117"
_GRID      = "#1e2130"
_TEXT      = "#c9d1d9"
_SUBTEXT   = "#8b949e"
_PURPLE    = "#660874"
_BLUE      = "#4c9be8"
_GREEN     = "#2ea043"
_RED       = "#f85149"
_AMBER     = "#d29922"
_FONT      = "Inter, sans-serif"


def _base_layout(**kwargs) -> dict:
    return dict(
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(family=_FONT, size=12, color=_TEXT),
        margin=dict(l=10, r=10, t=36, b=10),
        **kwargs,
    )


def _axis(title: str = "", **kwargs) -> dict:
    base = dict(
        gridcolor=_GRID,
        zerolinecolor=_GRID,
        tickfont=dict(size=11, color=_SUBTEXT),
    )
    if title:
        base["title"] = dict(text=title, font=dict(size=12, color=_SUBTEXT))
    base.update(kwargs)
    return base


# ── 1. Histogram with normal overlay ─────────────────────────────────────────

def return_histogram(profile: UnivariateProfile) -> go.Figure:
    edges  = profile.histogram["edges"]
    counts = profile.histogram["counts"]
    centers = [(edges[i] + edges[i + 1]) / 2 for i in range(len(counts))]
    bin_width = edges[1] - edges[0]

    # Normalise counts to density for the normal overlay
    total = sum(counts)
    density = [c / (total * bin_width) for c in counts]

    # Normal PDF overlay
    x_range = np.linspace(edges[0], edges[-1], 300)
    pdf = scipy_stats.norm.pdf(x_range, profile.mean, profile.std)

    fig = go.Figure()

    # Histogram bars (density)
    fig.add_trace(go.Bar(
        x=centers,
        y=density,
        width=bin_width * 0.9,
        marker_color=_PURPLE,
        marker_opacity=0.75,
        name="Return dist.",
        hovertemplate="%{x:.4f}: density %{y:.4f}<extra></extra>",
    ))

    # Normal overlay
    fig.add_trace(go.Scatter(
        x=x_range.tolist(),
        y=pdf.tolist(),
        mode="lines",
        line=dict(color=_AMBER, width=2, dash="dot"),
        name="Normal fit",
        hoverinfo="skip",
    ))

    # Vertical lines: mean and median
    for val, label, color in [
        (profile.mean,   "Mean",   _BLUE),
        (profile.median, "Median", _GREEN),
    ]:
        fig.add_vline(x=val, line_width=1, line_dash="dash", line_color=color,
                      annotation_text=label, annotation_font_color=color,
                      annotation_font_size=11)

    fig.update_layout(
        **_base_layout(title=dict(text="Return Distribution", font=dict(size=13, color=_TEXT))),
        xaxis=_axis("Daily Return"),
        yaxis=_axis("Density"),
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)),
        bargap=0,
        height=300,
    )
    return fig


# ── 2. Box plot ───────────────────────────────────────────────────────────────

def return_boxplot(profile: UnivariateProfile) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Box(
        y=["Daily Returns"],
        q1=[profile.q_q1],
        median=[profile.q_median],
        q3=[profile.q_q3],
        lowerfence=[profile.q_p05],
        upperfence=[profile.q_p95],
        mean=[profile.mean],
        sd=[profile.std],
        name="Daily Returns",
        orientation="h",
        marker_color=_PURPLE,
        line_color=_PURPLE,
        fillcolor="rgba(102,8,116,0.3)",
        boxmean="sd",
        hovertemplate=(
            "<b>Daily Returns</b><br>"
            "Median: %{median:.4f}<br>"
            "Q1: %{q1:.4f}  Q3: %{q3:.4f}<br>"
            "P5 fence: %{lowerfence:.4f}<br>"
            "P95 fence: %{upperfence:.4f}<extra></extra>"
        ),
    ))

    fig.update_layout(
        **_base_layout(title=dict(text="Box Plot (p05 – p95 whiskers)", font=dict(size=13, color=_TEXT))),
        xaxis=_axis("Daily Return"),
        yaxis=dict(showticklabels=False, gridcolor=_GRID),
        height=300,
        showlegend=False,
    )
    return fig


# ── 3. QQ plot ────────────────────────────────────────────────────────────────

def return_qq(profile: UnivariateProfile) -> go.Figure:
    theoretical = profile.qq["theoretical"]
    sample      = profile.qq["sample"]

    fig = go.Figure()

    if theoretical and sample:
        slope     = profile.qq.get("slope", 1.0)
        intercept = profile.qq.get("intercept", 0.0)
        r_sq      = profile.qq.get("r_squared", 0.0)

        fig.add_trace(go.Scatter(
            x=theoretical,
            y=sample,
            mode="markers",
            marker=dict(color=_PURPLE, size=4, opacity=0.7),
            name="Quantiles",
            hovertemplate="Theoretical: %{x:.4f}<br>Sample: %{y:.4f}<extra></extra>",
        ))

        x0, x1 = min(theoretical), max(theoretical)
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[slope * x0 + intercept, slope * x1 + intercept],
            mode="lines",
            line=dict(color=_AMBER, width=1.5, dash="dot"),
            name=f"Normal fit (R²={r_sq:.4f})",
            hoverinfo="skip",
        ))

    fig.update_layout(
        **_base_layout(title=dict(text="QQ Plot (vs Normal)", font=dict(size=13, color=_TEXT))),
        xaxis=_axis("Theoretical quantiles"),
        yaxis=_axis("Sample quantiles"),
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)),
        height=300,
    )
    return fig


# ── 4. ACF bar chart ──────────────────────────────────────────────────────────

def return_acf(profile: UnivariateProfile) -> go.Figure:
    lags   = profile.acf_data["lags"]
    values = profile.acf_data["values"]
    conf   = profile.acf_data["conf"]

    fig = go.Figure()

    if lags and values:
        lags_plot   = lags[1:]
        values_plot = values[1:]

        colors = [_GREEN if abs(v) > conf else _SUBTEXT for v in values_plot]

        fig.add_trace(go.Bar(
            x=lags_plot,
            y=values_plot,
            marker_color=colors,
            name="ACF",
            hovertemplate="Lag %{x}: %{y:.4f}<extra></extra>",
        ))

        for sign in [1, -1]:
            fig.add_hline(
                y=sign * conf,
                line_dash="dot",
                line_color=_AMBER,
                line_width=1,
                annotation_text=f"±{conf:.3f} (95%)" if sign == 1 else "",
                annotation_font_color=_AMBER,
                annotation_font_size=10,
            )

    fig.update_layout(
        **_base_layout(title=dict(text="Autocorrelation (ACF)", font=dict(size=13, color=_TEXT))),
        xaxis=_axis("Lag (days)", dtick=5),
        yaxis=_axis("ACF", range=[-1.05, 1.05]),
        showlegend=False,
        height=300,
    )
    return fig


# ── 5. Empirical CDF ──────────────────────────────────────────────────────────

def return_cdf(profile: UnivariateProfile) -> go.Figure:
    x = profile.cdf["x"]
    y = profile.cdf["y"]

    fig = go.Figure()

    if x and y:
        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode="lines",
            line=dict(color=_PURPLE, width=2),
            name="ECDF",
            hovertemplate="Return %{x:.4f}: CDF %{y:.3f}<extra></extra>",
        ))

        for val, label in [(profile.q_p05, "p5"), (profile.q_p95, "p95")]:
            fig.add_vline(
                x=val, line_width=1, line_dash="dash", line_color=_AMBER,
                annotation_text=label,
                annotation_font_color=_AMBER,
                annotation_font_size=10,
            )

        fig.add_hline(y=0.5, line_width=1, line_dash="dot", line_color=_SUBTEXT)

    fig.update_layout(
        **_base_layout(title=dict(text="Empirical CDF", font=dict(size=13, color=_TEXT))),
        xaxis=_axis("Daily Return"),
        yaxis=_axis("Cumulative probability", range=[-0.02, 1.02]),
        showlegend=False,
        height=280,
    )
    return fig
