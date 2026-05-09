"""
overview_chart.py — Plotly-based TAA overview sections for the sandbox.

Replaces the old matplotlib/PNG approach. Call render_taa_overview(universe, taa)
from taa_page.py; it renders directly via st.plotly_chart() / st.columns().
All text is English.

Sections:
  0  Asset pool table (full-width Plotly table)
  1  Efficient frontiers     — 4 columns, one per factor bucket
  2  MVO allocation bars     — 4 columns, horizontal bars
  3  Portfolio metrics       — 4 columns, Sharpe / Return / Vol
  4  Macro factor exposures  — 4 columns, grouped bars
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from stock_engine.sandbox.taa_module.factor_mvo import TAAResult
from stock_engine.sandbox.taa_module.mvo_core import MVOResult
from stock_engine.sandbox.taa_module.types import FactorBucket, MiniUniverse

_FACTOR_ORDER = [
    FactorBucket.GROWTH,
    FactorBucket.FIN_COND,
    FactorBucket.INFLATION,
    FactorBucket.DIVERSIFIER,
]

_BUCKET_EN = {
    FactorBucket.GROWTH:      "Growth",
    FactorBucket.FIN_COND:    "Fin. Conditions",
    FactorBucket.INFLATION:   "Inflation",
    FactorBucket.DIVERSIFIER: "Diversifier",
}

_P = {
    "dark_blue": "#1B3A6B",
    "gold":      "#E8A838",
    "green":     "#5cb85c",
    "teal":      "#5bc0de",
    "red":       "#cc4444",
    "grid":      "#e8e8e8",
    "text":      "#1a1a1a",
    "axis":      "#888888",
    "bg":        "#ffffff",
    "frontier":  "#660874",
    "mc_low":    "#1e3a8a",
    "mc_high":   "#660874",
}

_BUCKET_COLOR = {
    FactorBucket.GROWTH:      _P["dark_blue"],
    FactorBucket.FIN_COND:    _P["gold"],
    FactorBucket.INFLATION:   "#555555",
    FactorBucket.DIVERSIFIER: "#AAAAAA",
}


# ── Public entry ──────────────────────────────────────────────────────────────

def render_taa_overview(universe: MiniUniverse, taa: TAAResult) -> None:
    """Render all 5 TAA overview sections directly in Streamlit."""
    st.markdown("**Asset Pool**")
    _section_asset_pool(universe)

    st.markdown("**Mean-Variance Efficient Frontiers**")
    _section_efficient_frontiers(taa)

    st.markdown("**MVO Allocation — Picked Weights**")
    _section_allocation_bars(taa)

    st.markdown("**Portfolio Metrics — Sharpe · Return · Volatility**")
    _section_metrics(taa)

    if taa.factor_exposures:
        st.markdown("**Macro Factor Exposures**")
        _section_factor_exposures(universe, taa)


# ── Section 0: Asset pool table ───────────────────────────────────────────────

def _section_asset_pool(universe: MiniUniverse) -> None:
    bucket_tks: Dict[FactorBucket, List[str]] = {
        b: universe.by_bucket(b) for b in _FACTOR_ORDER
    }
    n_rows = max((len(v) for v in bucket_tks.values()), default=0)
    if n_rows == 0:
        st.info("No tickers assigned to any bucket.")
        return

    cells = [
        bucket_tks[b] + [""] * (n_rows - len(bucket_tks[b]))
        for b in _FACTOR_ORDER
    ]
    row_colors = ["#EEF2F8" if r % 2 == 0 else "#FFFFFF" for r in range(n_rows)]

    fig = go.Figure(go.Table(
        header=dict(
            values=[f"<b>{_BUCKET_EN[b]}</b>" for b in _FACTOR_ORDER],
            fill_color=_P["dark_blue"],
            font=dict(color="white", size=11),
            align="center",
            height=28,
        ),
        cells=dict(
            values=cells,
            fill_color=[row_colors] * 4,
            font=dict(color=_P["text"], size=11, family="monospace"),
            align="center",
            height=24,
        ),
    ))
    fig.update_layout(
        paper_bgcolor=_P["bg"],
        margin=dict(l=0, r=0, t=4, b=0),
        height=max(80, n_rows * 24 + 42),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Section 1: Efficient frontiers ────────────────────────────────────────────

def _section_efficient_frontiers(taa: TAAResult) -> None:
    cols = st.columns(4)
    for i, bucket in enumerate(_FACTOR_ORDER):
        with cols[i]:
            sol = taa.bucket_solutions.get(bucket)
            if sol is None:
                st.caption(f"{_BUCKET_EN[bucket]} — empty")
                continue
            fig = _frontier_fig(sol.mvo_result, taa.pick, title=_BUCKET_EN[bucket])
            st.plotly_chart(fig, use_container_width=True)


def _frontier_fig(res: MVOResult, pick: str, title: str = "") -> go.Figure:
    fig = go.Figure()
    ax = _axis_style()

    if res.mc_returns is not None and res.frontier_vols is not None:
        fig.add_trace(go.Scatter(
            x=res.mc_vols, y=res.mc_returns,
            mode="markers",
            marker=dict(
                size=4, opacity=0.45,
                color=res.mc_sharpes,
                colorscale=[[0, _P["mc_low"]], [1, _P["mc_high"]]],
                colorbar=dict(
                    title=dict(text="Sharpe", font=dict(size=9)),
                    thickness=8, len=0.6,
                    tickfont=dict(size=8),
                ),
                showscale=True,
            ),
            name="Random portfolios",
            hovertemplate="vol %{x:.2%}<br>ret %{y:.2%}<extra></extra>",
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=res.frontier_vols, y=res.frontier_rets,
            mode="lines",
            line=dict(color=_P["frontier"], width=2),
            name="Frontier",
            hovertemplate="vol %{x:.2%}<br>ret %{y:.2%}<extra></extra>",
            showlegend=False,
        ))

    def _add_pt(w: np.ndarray, color: str, name: str, symbol: str = "star") -> None:
        s = res.stats(w)
        fig.add_trace(go.Scatter(
            x=[s["vol"]], y=[s["return"]],
            mode="markers",
            marker=dict(size=12, symbol=symbol, color=color,
                        line=dict(color="#000", width=1)),
            name=name,
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"vol %{{x:.2%}}<br>ret %{{y:.2%}}<br>"
                f"sharpe {s['sharpe']:.2f}<extra></extra>"
            ),
        ))

    _add_pt(res.weights_max_sharpe, _P["gold"],  "Max Sharpe",   "star")
    _add_pt(res.weights_gmv,        _P["green"], "Min Variance", "circle")
    if res.weights_target is not None:
        lbl = (f"Target {res.target_return_used:.0%}"
               if res.target_return_used is not None else "Target")
        _add_pt(res.weights_target, _P["teal"], lbl, "diamond")

    fig.update_layout(
        **_layout_base(title, height=260),
        xaxis=dict(title="Volatility", tickformat=".0%", **ax),
        yaxis=dict(title="Return",     tickformat=".0%", **ax),
        legend=dict(
            orientation="h", x=0, y=1.15, xanchor="left",
            font=dict(size=8), bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=True,
    )
    return fig


# ── Section 2: Allocation bars ────────────────────────────────────────────────

def _section_allocation_bars(taa: TAAResult) -> None:
    cols = st.columns(4)
    for i, bucket in enumerate(_FACTOR_ORDER):
        with cols[i]:
            sol = taa.bucket_solutions.get(bucket)
            if sol is None or not sol.weights:
                st.caption(f"{_BUCKET_EN[bucket]} — empty")
                continue
            items = sorted(sol.weights.items(), key=lambda kv: kv[1])
            labels = [k for k, _ in items]
            vals   = [v for _, v in items]
            fig = go.Figure(go.Bar(
                x=vals, y=labels,
                orientation="h",
                marker=dict(color=_P["dark_blue"], line=dict(width=0)),
                text=[f"{v:.1%}" for v in vals],
                textposition="outside",
                textfont=dict(size=9),
                hovertemplate="%{y}: %{x:.1%}<extra></extra>",
            ))
            ax = _axis_style()
            fig.update_layout(
                **_layout_base(_BUCKET_EN[bucket],
                               height=max(180, len(labels) * 36 + 60)),
                xaxis=dict(tickformat=".0%", range=[0, 1.18], **ax),
                yaxis=dict(**ax),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Section 3: Portfolio metrics ──────────────────────────────────────────────

def _section_metrics(taa: TAAResult) -> None:
    cols = st.columns(4)
    for i, bucket in enumerate(_FACTOR_ORDER):
        with cols[i]:
            sol = taa.bucket_solutions.get(bucket)
            if sol is None:
                st.caption(f"{_BUCKET_EN[bucket]} — empty")
                continue
            res = sol.mvo_result
            if taa.pick == "max_sharpe":
                w = res.weights_max_sharpe
            elif taa.pick == "gmv":
                w = res.weights_gmv
            else:
                w = (res.weights_target if res.weights_target is not None
                     else res.weights_max_sharpe)
            s = res.stats(w)
            raw_vals  = [s["sharpe"], s["return"] * 100, s["vol"] * 100]
            bar_labels = ["Sharpe", "Return (%)", "Vol (%)"]
            text_vals  = [f"{s['sharpe']:.2f}",
                          f"{s['return']*100:.1f}%",
                          f"{s['vol']*100:.1f}%"]
            colors = [_P["dark_blue"] if v >= 0 else _P["red"] for v in raw_vals]
            ymax = max(abs(v) for v in raw_vals) * 1.35 or 1.0

            fig = go.Figure(go.Bar(
                x=bar_labels, y=raw_vals,
                marker=dict(color=colors, line=dict(width=0)),
                text=text_vals,
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate="%{x}: %{y:.3f}<extra></extra>",
            ))
            ax = _axis_style()
            fig.update_layout(
                **_layout_base(_BUCKET_EN[bucket], height=240),
                xaxis=dict(**ax),
                yaxis=dict(range=[-ymax, ymax], **ax),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Section 4: Factor exposures ───────────────────────────────────────────────

def _section_factor_exposures(universe: MiniUniverse, taa: TAAResult) -> None:
    cols = st.columns(4)
    for i, bucket in enumerate(_FACTOR_ORDER):
        with cols[i]:
            tks = universe.by_bucket(bucket)[:6]
            if not tks:
                st.caption(f"{_BUCKET_EN[bucket]} — empty")
                continue
            fig = go.Figure()
            for fb in _FACTOR_ORDER:
                vals = [taa.factor_exposures.get(tk, {}).get(fb, 0.0)
                        for tk in tks]
                fig.add_trace(go.Bar(
                    x=tks, y=vals,
                    name=_BUCKET_EN[fb],
                    marker=dict(color=_BUCKET_COLOR[fb], line=dict(width=0)),
                    hovertemplate=(
                        f"<b>{_BUCKET_EN[fb]}</b><br>"
                        f"%{{x}}: %{{y:.3f}}<extra></extra>"
                    ),
                    showlegend=(i == 0),
                ))
            ax = _axis_style()
            fig.update_layout(
                **_layout_base(_BUCKET_EN[bucket], height=260),
                barmode="group",
                xaxis=dict(**ax),
                yaxis={**ax, "title": "β", "zeroline": True,
                       "zerolinecolor": "#aaa"},
                legend=dict(
                    orientation="h", x=0, y=1.15, xanchor="left",
                    font=dict(size=8), bgcolor="rgba(0,0,0,0)",
                ),
                showlegend=(i == 0),
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Shared layout helpers ─────────────────────────────────────────────────────

def _axis_style() -> dict:
    return dict(
        gridcolor=_P["grid"],
        showgrid=True,
        zeroline=False,
        tickfont=dict(color=_P["axis"], size=10),
    )


def _layout_base(title: str = "", height: int = 280) -> dict:
    return dict(
        title=dict(text=title, font=dict(color=_P["text"], size=11)),
        paper_bgcolor=_P["bg"],
        plot_bgcolor=_P["bg"],
        margin=dict(l=44, r=14, t=30 if title else 10, b=40),
        height=height,
    )
