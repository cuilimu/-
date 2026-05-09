"""
diagnostics_charts.py — plotly versions of the reference notebook's
two-panel figure: efficient frontier + Monte-Carlo cloud (left) and
weights comparison bar (right).

Input is a fully-populated MVOResult (with_diagnostics=True). The page
renders one expander per bucket and lazily calls solve_mvo with
diagnostics on the first open.

Colour tokens are kept in this file's `_THEME` dict — when integrating
into the main app, replace these with imports from stock_engine.ui.theme.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import plotly.graph_objects as go

from stock_engine.sandbox.taa_module.mvo_core import MVOResult

_THEME = {
    "bg_paper":   "#ffffff",
    "bg_plot":    "#ffffff",
    "grid":       "#e8e8e8",
    "text":       "#1a1a1a",
    "axis":       "#888888",
    "frontier":   "#660874",   # Tsinghua purple
    "max_sharpe": "#f4c542",
    "gmv":        "#5cb85c",
    "target":     "#5bc0de",
    "mc_low":     "#1e3a8a",
    "mc_high":    "#660874",
}


# ── Public ─────────────────────────────────────────────────────────────────────

def efficient_frontier_chart(res: MVOResult, title: str = "") -> Optional[go.Figure]:
    """Return None when diagnostics weren't computed."""
    if res.mc_returns is None or res.frontier_vols is None:
        return None

    fig = go.Figure()

    # ── Monte Carlo cloud ──────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=res.mc_vols, y=res.mc_returns,
        mode="markers",
        marker=dict(
            size=4, opacity=0.45,
            color=res.mc_sharpes,
            colorscale=[[0, _THEME["mc_low"]], [1, _THEME["mc_high"]]],
            colorbar=dict(title=dict(text="Sharpe", font=dict(size=10)),
                          thickness=10, len=0.7,
                          tickfont=dict(size=9, color=_THEME["axis"])),
            showscale=True,
        ),
        name="Random portfolios",
        hovertemplate="vol %{x:.2%}<br>ret %{y:.2%}<extra></extra>",
    ))

    # ── Efficient frontier ─────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=res.frontier_vols, y=res.frontier_rets,
        mode="lines",
        line=dict(color=_THEME["frontier"], width=2.5),
        name="Efficient frontier",
        hovertemplate="vol %{x:.2%}<br>ret %{y:.2%}<extra></extra>",
    ))

    # ── Three highlighted portfolios ───────────────────────────────────
    def _scatter_pt(w: np.ndarray, color: str, name: str):
        ret = float(w @ res.mu)
        vol = float(np.sqrt(w @ res.cov @ w))
        sr  = (ret - res.rf) / vol if vol > 0 else float("nan")
        fig.add_trace(go.Scatter(
            x=[vol], y=[ret], mode="markers",
            marker=dict(size=14, color=color,
                        line=dict(color="#000000", width=1.2)),
            name=name,
            hovertemplate=(f"<b>{name}</b><br>"
                           f"vol %{{x:.2%}}<br>ret %{{y:.2%}}<br>"
                           f"sharpe {sr:.2f}<extra></extra>"),
        ))

    _scatter_pt(res.weights_max_sharpe, _THEME["max_sharpe"], "Max Sharpe")
    _scatter_pt(res.weights_gmv,        _THEME["gmv"],        "Min Variance")
    if res.weights_target is not None:
        tgt_label = (f"Target {res.target_return_used:.0%}"
                     if res.target_return_used is not None
                     else "Target")
        _scatter_pt(res.weights_target, _THEME["target"], tgt_label)

    axis = dict(gridcolor=_THEME["grid"], showgrid=True, zeroline=False,
                tickfont=dict(color=_THEME["axis"], size=10))
    fig.update_layout(
        title=dict(text=title or "Efficient Frontier",
                   font=dict(color=_THEME["text"], size=12)),
        paper_bgcolor=_THEME["bg_paper"],
        plot_bgcolor=_THEME["bg_plot"],
        margin=dict(l=50, r=20, t=36, b=44),
        height=380,
        xaxis=dict(title=dict(text="Volatility (annual)",
                              font=dict(size=10, color=_THEME["axis"])),
                   tickformat=".0%", **axis),
        yaxis=dict(title=dict(text="Expected return (annual)",
                              font=dict(size=10, color=_THEME["axis"])),
                   tickformat=".0%", **axis),
        legend=dict(orientation="h", x=0, y=1.05, xanchor="left",
                    yanchor="bottom", bgcolor="rgba(0,0,0,0)",
                    font=dict(size=10, color=_THEME["text"])),
        hovermode="closest",
    )
    return fig


def weights_comparison_chart(res: MVOResult, title: str = "") -> go.Figure:
    """Grouped bar: Max Sharpe / GMV / (optional) Target weights side-by-side."""
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=res.tickers, y=res.weights_max_sharpe,
        name="Max Sharpe",
        marker=dict(color=_THEME["max_sharpe"], line=dict(width=0)),
        hovertemplate="%{x}: %{y:.1%}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=res.tickers, y=res.weights_gmv,
        name="Min Variance",
        marker=dict(color=_THEME["gmv"], line=dict(width=0)),
        hovertemplate="%{x}: %{y:.1%}<extra></extra>",
    ))
    if res.weights_target is not None:
        tgt_label = (f"Target {res.target_return_used:.0%}"
                     if res.target_return_used is not None
                     else "Target")
        fig.add_trace(go.Bar(
            x=res.tickers, y=res.weights_target,
            name=tgt_label,
            marker=dict(color=_THEME["target"], line=dict(width=0)),
            hovertemplate="%{x}: %{y:.1%}<extra></extra>",
        ))

    axis = dict(gridcolor=_THEME["grid"], showgrid=True, zeroline=False,
                tickfont=dict(color=_THEME["axis"], size=10))
    fig.update_layout(
        title=dict(text=title or "Portfolio Weights",
                   font=dict(color=_THEME["text"], size=12)),
        paper_bgcolor=_THEME["bg_paper"],
        plot_bgcolor=_THEME["bg_plot"],
        margin=dict(l=50, r=20, t=36, b=44),
        height=380,
        barmode="group",
        bargap=0.18, bargroupgap=0.06,
        xaxis=dict(**axis, type="category"),
        yaxis=dict(tickformat=".0%", **axis),
        legend=dict(orientation="h", x=0, y=1.05, xanchor="left",
                    yanchor="bottom", bgcolor="rgba(0,0,0,0)",
                    font=dict(size=10, color=_THEME["text"])),
    )
    return fig
