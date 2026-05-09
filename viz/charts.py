"""
viz/charts.py -- Plotly-based chart builders.
Supports multi-series / multi-group overlays (Module 6).
Includes: stock_ohlcv_chart, constituent_bar_chart, multi_group_cumulative_chart.
"""

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stock_engine.exceptions import VisualizationError
from stock_engine.viz.theme import VizTheme

# Color palette for multi-series (Module 6)
from stock_engine.ui.theme import CHART_SERIES_PALETTE as SERIES_COLORS


def _base_layout(theme: VizTheme, title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(color=theme.font_color, size=16)),
        paper_bgcolor=theme.bg_paper,
        plot_bgcolor=theme.bg_plot,
        font=dict(family=theme.font_family, size=theme.font_size_base, color=theme.font_color),
        margin=theme.margin,
        xaxis=dict(gridcolor=theme.grid_color, showgrid=True),
        yaxis=dict(gridcolor=theme.grid_color, showgrid=True),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=theme.font_color)),
        hovermode="x unified",
    )


def price_series_chart(
    prices: pd.DataFrame,
    tickers: list[str],
    theme: VizTheme,
    title: str = "Price Series",
) -> go.Figure:
    if prices.empty:
        raise VisualizationError("prices DataFrame is empty")
    fig = go.Figure()
    for i, ticker in enumerate(tickers):
        if ticker not in prices.columns:
            continue
        series = prices[ticker].dropna()
        normalised = series / series.iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=normalised.index, y=normalised.values,
            name=ticker, mode="lines",
            line=dict(color=SERIES_COLORS[i % len(SERIES_COLORS)], width=1.5),
        ))
    fig.update_layout(**_base_layout(theme, title))
    fig.update_yaxes(title_text="Indexed (100 = start)")
    return fig


def multi_group_cumulative_chart(
    series_dict: dict[str, pd.Series],
    benchmark_returns: Optional[pd.Series],
    theme: VizTheme,
    title: str = "Cumulative Returns -- Group Comparison",
) -> go.Figure:
    """
    Module 6: plot multiple named cumulative return series on one chart.
    series_dict: {label: daily_return_series}
    Each series indexed to 100 at start for comparison.
    Benchmark plotted as grey dashed line.
    """
    fig = go.Figure()
    for i, (label, daily_ret) in enumerate(series_dict.items()):
        cum = (1 + daily_ret).cumprod()
        indexed = cum / cum.iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=indexed.index, y=indexed.values,
            name=label, mode="lines",
            line=dict(color=SERIES_COLORS[i % len(SERIES_COLORS)], width=2),
        ))

    if benchmark_returns is not None and not benchmark_returns.empty:
        cum_b = (1 + benchmark_returns).cumprod()
        indexed_b = cum_b / cum_b.iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=indexed_b.index, y=indexed_b.values,
            name=benchmark_returns.name or "Benchmark",
            mode="lines",
            line=dict(color=theme.color_neutral, width=1.5, dash="dash"),
        ))

    fig.update_layout(**_base_layout(theme, title))
    fig.update_yaxes(title_text="Indexed (100 = start)")
    return fig


def cumulative_returns_chart(
    portfolio_returns: pd.Series,
    benchmark_returns: Optional[pd.Series],
    theme: VizTheme,
    title: str = "Cumulative Returns",
) -> go.Figure:
    return multi_group_cumulative_chart(
        {"Portfolio": portfolio_returns},
        benchmark_returns,
        theme,
        title,
    )


def daily_returns_chart(
    daily_returns: pd.Series,
    theme: VizTheme,
    title: str = "Daily Returns",
) -> go.Figure:
    colors = [theme.color_gain if r >= 0 else theme.color_loss for r in daily_returns]
    fig = go.Figure(go.Bar(
        x=daily_returns.index,
        y=daily_returns.values * 100,
        marker_color=colors,
        name="Daily Return",
    ))
    fig.update_layout(**_base_layout(theme, title))
    fig.update_yaxes(title_text="Return (%)", ticksuffix="%")
    return fig


def drawdown_chart(
    drawdown_series: pd.Series,
    theme: VizTheme,
    title: str = "Drawdown",
) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=drawdown_series.index,
        y=drawdown_series.values * 100,
        fill="tozeroy",
        fillcolor="rgba(239,83,80,0.3)",
        line=dict(color=theme.color_loss, width=1),
        name="Drawdown",
    ))
    fig.update_layout(**_base_layout(theme, title))
    fig.update_yaxes(title_text="Drawdown (%)", ticksuffix="%")
    return fig


def portfolio_composition_chart(
    weights: dict[str, float],
    theme: VizTheme,
    title: str = "Portfolio Composition",
) -> go.Figure:
    cash_weight = max(0.0, 1.0 - sum(weights.values()))
    labels = list(weights.keys()) + (["Cash"] if cash_weight > 0.001 else [])
    values = list(weights.values()) + ([cash_weight] if cash_weight > 0.001 else [])
    colors = SERIES_COLORS[:len(labels) - 1] + [theme.color_cash]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.4,
        marker=dict(colors=colors[:len(labels)]),
        textfont=dict(color=theme.font_color),
    ))
    fig.update_layout(**_base_layout(theme, title))
    return fig


def stock_ohlcv_chart(
    df: pd.DataFrame,
    ticker: str,
    theme: VizTheme,
) -> go.Figure:
    """
    Two-panel chart: OHLC lines (row 1, 70%) + Volume bars (row 2, 30%).
    Shared x-axis. Dark theme consistent with the rest of the chart suite.
    If 'volume' column is absent, renders row 1 only as a single-panel figure.
    """
    has_volume = "volume" in df.columns and df["volume"].notna().any()

    if has_volume:
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.70, 0.30],
            vertical_spacing=0.04,
        )
    else:
        fig = go.Figure()

    # OHLC lines
    _add = (lambda trace, **kw: fig.add_trace(trace, row=1, col=1, **kw)
            if has_volume else fig.add_trace(trace))

    if "close" in df.columns:
        _add(go.Scatter(
            x=df.index, y=df["close"],
            name="Close", mode="lines",
            line=dict(color=SERIES_COLORS[0], width=1.8),
        ))
    if "open" in df.columns:
        _add(go.Scatter(
            x=df.index, y=df["open"],
            name="Open", mode="lines",
            line=dict(color=SERIES_COLORS[1], width=1.2, dash="dot"),
            opacity=0.85,
        ))
    if "high" in df.columns:
        _add(go.Scatter(
            x=df.index, y=df["high"],
            name="High", mode="lines",
            line=dict(color="#00b050", width=1.2),
            opacity=0.85,
        ))
    if "low" in df.columns:
        _add(go.Scatter(
            x=df.index, y=df["low"],
            name="Low", mode="lines",
            line=dict(color="#e03030", width=1.2),
            opacity=0.85,
        ))

    # Volume bars
    if has_volume:
        fig.add_trace(go.Bar(
            x=df.index,
            y=df["volume"],
            name="Volume",
            marker_color=SERIES_COLORS[2],
            opacity=0.55,
            showlegend=True,
        ), row=2, col=1)

    # Layout
    common_axis = dict(
        gridcolor=theme.grid_color,
        showgrid=True,
        zeroline=False,
        tickfont=dict(color=theme.font_color, size=10),
    )
    layout = dict(
        title=dict(
            text=f"{ticker} -- Price & Volume",
            font=dict(color=theme.font_color, size=14),
        ),
        paper_bgcolor=theme.bg_paper,
        plot_bgcolor=theme.bg_plot,
        font=dict(family=theme.font_family, size=theme.font_size_base,
                  color=theme.font_color),
        margin=dict(l=50, r=20, t=44, b=40),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            x=0.01, y=0.99,
            xanchor="left", yanchor="top",
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=theme.font_color, size=10),
        ),
    )

    if has_volume:
        fig.update_layout(**layout)
        fig.update_xaxes(**common_axis)
        fig.update_yaxes(**common_axis)
        fig.update_yaxes(title_text="Price", row=1, col=1,
                         title_font=dict(color=theme.font_color, size=10))
        fig.update_yaxes(title_text="Volume", row=2, col=1,
                         title_font=dict(color=theme.font_color, size=10))
    else:
        layout["xaxis"] = common_axis
        layout["yaxis"] = dict(**common_axis, title_text="Price",
                               title_font=dict(color=theme.font_color, size=10))
        fig.update_layout(**layout)

    return fig


def constituent_bar_chart(
    constituent_returns: list,
    theme: VizTheme,
    price_field: str = "Close",
    title: str = "Constituents -- Total Return %",
) -> go.Figure:
    """
    Horizontal bar chart of per-ticker total return %.
    Sorted descending (best at top). Green/red bars. Vertical line at x=0.
    White background (exception to dark chart rule -- this is a table-style chart).
    """
    if not constituent_returns:
        fig = go.Figure()
        fig.update_layout(title=title, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
        return fig

    tickers  = [r.ticker for r in constituent_returns]
    returns  = [r.total_return_pct for r in constituent_returns]
    labels   = [
        f"{r.ticker} -- {r.exchange}" if r.exchange else r.ticker
        for r in constituent_returns
    ]
    colors   = [
        theme.color_gain if v >= 0 else theme.color_loss
        for v in returns
    ]
    text     = [f"{v:+.2f}%" for v in returns]

    fig = go.Figure(go.Bar(
        x=returns,
        y=labels,
        orientation="h",
        marker_color=colors,
        text=text,
        textposition="outside",
        cliponaxis=False,
    ))

    fig.add_vline(x=0, line_width=1, line_color="#cccccc")

    fig.update_layout(
        title=dict(text=title, font=dict(color="#1a1a1a", size=14)),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family=theme.font_family, size=12, color="#1a1a1a"),
        margin=dict(l=20, r=80, t=40, b=20),
        xaxis=dict(
            gridcolor="#eeeeee",
            showgrid=True,
            zeroline=False,
            ticksuffix="%",
        ),
        yaxis=dict(
            gridcolor="#eeeeee",
            showgrid=False,
            autorange="reversed",
        ),
        showlegend=False,
        height=max(200, len(constituent_returns) * 44),
    )
    return fig
