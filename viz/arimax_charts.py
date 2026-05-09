"""
viz/arimax_charts.py
Plotly versions of the engine's matplotlib diagnostics: tsdisplay, decomposition,
PACF, forecast-with-CI, cross-validated forecast comparison, residual diagnostics.

Computation borrows from statsmodels (ACF/PACF/Ljung-Box) and pmdarima
(seasonal decompose) so we stay numerically faithful to the engine. Rendering
uses plotly.graph_objects + the project-wide DEFAULT_THEME.
"""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scipy.stats as stats
from statsmodels.tsa.stattools import acf, pacf
from statsmodels.stats.diagnostic import acorr_ljungbox

from stock_engine.viz.theme import ARX_LIGHT_THEME, DEFAULT_THEME, VizTheme
from stock_engine.ui.theme import CHART_AXIS


def _layout(theme: VizTheme, title: str, height: int) -> dict:
    return dict(
        title=dict(text=title, font=dict(color=theme.font_color, size=12)),
        paper_bgcolor=theme.bg_paper,
        plot_bgcolor=theme.bg_plot,
        font=dict(family=theme.font_family, size=theme.font_size_base, color=theme.font_color),
        margin=dict(l=40, r=16, t=36, b=36),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=theme.font_color, size=10),
            orientation="h", y=1.02, x=0,
        ),
        height=height,
        hovermode="x unified",
    )


def _ax(theme: VizTheme) -> dict:
    tick_color = theme.font_color if theme.font_color != "#FAFAFA" else CHART_AXIS
    return dict(gridcolor=theme.grid_color, showgrid=True, zeroline=False,
                tickfont=dict(color=tick_color, size=10))


def _conf_band_xy(n_lags: int, n_obs: int, alpha: float = 0.05) -> float:
    """Approximate ±z/sqrt(N) ACF/PACF confidence band."""
    z = stats.norm.ppf(1 - alpha / 2)
    return float(z / np.sqrt(n_obs))


def tsdisplay_chart(
    y: np.ndarray,
    lag_max: int = 40,
    title: str = "Time Series Display",
    theme: VizTheme = ARX_LIGHT_THEME,
) -> go.Figure:
    """Series + ACF + PACF in one stacked figure (engine's tsdisplay equivalent)."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    lag_max = min(lag_max, n - 1)

    acf_vals = acf(y, nlags=lag_max, fft=True)
    pacf_vals = pacf(y, nlags=lag_max, method="ywmle")
    band = _conf_band_xy(lag_max, n)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=False,
        row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.08,
        subplot_titles=("Series", "ACF", "PACF"),
    )

    fig.add_trace(go.Scatter(
        x=np.arange(n), y=y, mode="lines",
        line=dict(color=theme.color_portfolio, width=1.4), name="y",
    ), row=1, col=1)

    for r, vals, name in [(2, acf_vals, "ACF"), (3, pacf_vals, "PACF")]:
        fig.add_trace(go.Bar(
            x=np.arange(len(vals)), y=vals,
            marker_color=theme.color_portfolio, name=name, showlegend=False,
        ), row=r, col=1)
        fig.add_hline(y=band, line=dict(color=theme.grid_color, dash="dash"), row=r, col=1)
        fig.add_hline(y=-band, line=dict(color=theme.grid_color, dash="dash"), row=r, col=1)

    fig.update_layout(**_layout(theme, title, height=620))
    for r in (1, 2, 3):
        fig.update_xaxes(_ax(theme), row=r, col=1)
        fig.update_yaxes(_ax(theme), row=r, col=1)
    return fig


def pacf_chart(
    y: np.ndarray,
    lags: int = 40,
    title: str = "Partial Autocorrelation",
    theme: VizTheme = ARX_LIGHT_THEME,
) -> go.Figure:
    y = np.asarray(y, dtype=float)
    n = len(y)
    lags = min(lags, n - 1)
    vals = pacf(y, nlags=lags, method="ywmle")
    band = _conf_band_xy(lags, n)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=np.arange(len(vals)), y=vals, marker_color=theme.color_portfolio, name="PACF",
    ))
    fig.add_hline(y=band, line=dict(color=theme.grid_color, dash="dash"))
    fig.add_hline(y=-band, line=dict(color=theme.grid_color, dash="dash"))
    fig.update_layout(**_layout(theme, title, height=320))
    fig.update_xaxes(_ax(theme), title="Lag")
    fig.update_yaxes(_ax(theme))
    return fig


def decomposition_chart(
    y: np.ndarray,
    period: int = 4,
    type_: str = "additive",
    title: str = "Seasonal Decomposition",
    theme: VizTheme = ARX_LIGHT_THEME,
) -> go.Figure:
    """Stacked Observed / Trend / Seasonal / Residual panels (matches engine cell 29)."""
    from pmdarima.arima import decompose

    y = np.asarray(y, dtype=float)
    res = decompose(y, type_=type_, m=period)

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        subplot_titles=("Observed", "Trend", "Seasonal", "Residual"),
    )
    panels = [
        np.asarray(res.x), np.asarray(res.trend),
        np.asarray(res.seasonal), np.asarray(res.random),
    ]
    for r, vals in enumerate(panels, start=1):
        fig.add_trace(go.Scatter(
            x=np.arange(len(vals)), y=vals, mode="lines",
            line=dict(color=theme.color_portfolio, width=1.2),
            showlegend=False,
        ), row=r, col=1)
        fig.update_xaxes(_ax(theme), row=r, col=1)
        fig.update_yaxes(_ax(theme), row=r, col=1)

    fig.update_layout(**_layout(theme, title, height=720))
    return fig


def forecast_with_ci_chart(
    train_idx,
    y_train,
    test_idx,
    y_test,
    y_pred,
    conf_int,
    title: str = "Forecast vs Actual",
    height: int = 720,
    theme: VizTheme = ARX_LIGHT_THEME,
) -> go.Figure:
    """
    Top panel: training + actual + predicted overlay.
    Bottom panel: training + predicted with CI band.
    """
    conf_int = np.asarray(conf_int)
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.10,
        subplot_titles=("Actual vs Predicted", "Predicted with Confidence Interval"),
    )

    # --- Top
    fig.add_trace(go.Scatter(
        x=list(train_idx), y=list(y_train), mode="lines",
        name="Train", line=dict(color=theme.color_portfolio, width=1.4),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=list(test_idx), y=list(y_test), mode="lines",
        name="Actual", line=dict(color=theme.color_neutral, width=1.6),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=list(test_idx), y=list(y_pred), mode="lines+markers",
        name="Predicted", line=dict(color=theme.color_gain, width=1.6),
        marker=dict(size=5),
    ), row=1, col=1)

    # --- Bottom
    fig.add_trace(go.Scatter(
        x=list(train_idx), y=list(y_train), mode="lines",
        name="Train ", line=dict(color=theme.color_portfolio, width=1.4), showlegend=False,
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=list(test_idx), y=list(y_pred), mode="lines",
        name="Predicted ", line=dict(color=theme.color_gain, width=1.6), showlegend=False,
    ), row=2, col=1)
    # CI band: upper trace then lower with fill='tonexty'
    fig.add_trace(go.Scatter(
        x=list(test_idx), y=conf_int[:, 1].tolist(), mode="lines",
        line=dict(color="rgba(0,0,0,0)"), showlegend=False, hoverinfo="skip",
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=list(test_idx), y=conf_int[:, 0].tolist(), mode="lines",
        line=dict(color="rgba(0,0,0,0)"), fill="tonexty",
        fillcolor="rgba(255,167,38,0.30)", name="CI",
    ), row=2, col=1)

    fig.update_layout(**_layout(theme, title, height=height))
    for r in (1, 2):
        fig.update_xaxes(_ax(theme), row=r, col=1)
        fig.update_yaxes(_ax(theme), row=r, col=1)
    return fig


def cv_forecasts_chart(
    y_train: np.ndarray,
    cv_predictions: list[np.ndarray],
    titles: list[str],
    overall_title: str = "Cross-Validated Forecasts",
    theme: VizTheme = ARX_LIGHT_THEME,
) -> go.Figure:
    """One panel per model: actual training series + the rolling-CV predictions tail."""
    n_models = len(cv_predictions)
    if n_models == 0:
        return go.Figure()

    fig = make_subplots(
        rows=n_models, cols=1, shared_xaxes=False,
        vertical_spacing=0.08, subplot_titles=titles,
    )
    x_axis = np.arange(len(y_train))
    for i, preds in enumerate(cv_predictions, start=1):
        fig.add_trace(go.Scatter(
            x=x_axis, y=y_train, mode="lines",
            line=dict(color=theme.color_portfolio, width=1.2, dash="dot"),
            name="Actual", showlegend=(i == 1),
        ), row=i, col=1)
        n_pred = len(preds)
        fig.add_trace(go.Scatter(
            x=x_axis[-n_pred:], y=preds, mode="lines",
            line=dict(color=theme.color_gain, width=1.6),
            name=f"CV pred (model {i - 1})", showlegend=True,
        ), row=i, col=1)
        fig.update_xaxes(_ax(theme), row=i, col=1)
        fig.update_yaxes(_ax(theme), row=i, col=1)

    fig.update_layout(**_layout(theme, overall_title, height=300 * n_models))
    return fig


def residual_diagnostics_chart(
    residuals: np.ndarray,
    title: str = "Residual Diagnostics",
    acf_lags: int = 20,
    lb_lags: Iterable[int] = range(1, 11),
    theme: VizTheme = ARX_LIGHT_THEME,
) -> go.Figure:
    """
    2x3 grid: residual series | histogram+normal | QQ
              ACF              | Ljung–Box       | (blank)
    """
    resid = np.asarray(residuals, dtype=float)
    resid = resid[~np.isnan(resid)]
    n = len(resid)

    fig = make_subplots(
        rows=2, cols=3, vertical_spacing=0.14, horizontal_spacing=0.08,
        subplot_titles=(
            "Residuals", "Histogram + Normal", "QQ Plot",
            "ACF", "Ljung–Box p-values", "",
        ),
    )

    # 1) Residual series
    fig.add_trace(go.Scatter(
        x=np.arange(n), y=resid, mode="lines",
        line=dict(color=theme.color_portfolio, width=1.0), showlegend=False,
    ), row=1, col=1)
    fig.add_hline(y=0, line=dict(color=theme.grid_color, dash="dash"), row=1, col=1)

    # 2) Histogram + normal fit
    mu, std = stats.norm.fit(resid)
    fig.add_trace(go.Histogram(
        x=resid, nbinsx=20, histnorm="probability density",
        marker_color=theme.color_portfolio, opacity=0.55, showlegend=False,
    ), row=1, col=2)
    grid = np.linspace(resid.min(), resid.max(), 200)
    fig.add_trace(go.Scatter(
        x=grid, y=stats.norm.pdf(grid, mu, std), mode="lines",
        line=dict(color=theme.color_gain, width=1.4), showlegend=False,
    ), row=1, col=2)

    # 3) QQ plot
    (osm, osr), (slope, intercept, _) = stats.probplot(resid, dist="norm", fit=True)
    fig.add_trace(go.Scatter(
        x=osm, y=osr, mode="markers",
        marker=dict(color=theme.color_portfolio, size=5), showlegend=False,
    ), row=1, col=3)
    qq_line_x = np.array([osm.min(), osm.max()])
    fig.add_trace(go.Scatter(
        x=qq_line_x, y=slope * qq_line_x + intercept, mode="lines",
        line=dict(color=theme.color_gain, width=1.2), showlegend=False,
    ), row=1, col=3)

    # 4) ACF
    acf_vals = acf(resid, nlags=acf_lags, fft=True)
    band = _conf_band_xy(acf_lags, n)
    fig.add_trace(go.Bar(
        x=np.arange(1, len(acf_vals)), y=acf_vals[1:],
        marker_color=theme.color_portfolio, showlegend=False,
    ), row=2, col=1)
    fig.add_hline(y=band, line=dict(color=theme.grid_color, dash="dash"), row=2, col=1)
    fig.add_hline(y=-band, line=dict(color=theme.grid_color, dash="dash"), row=2, col=1)

    # 5) Ljung–Box
    lb_lags_list = list(lb_lags)
    lb = acorr_ljungbox(resid, lags=lb_lags_list, return_df=True)
    fig.add_trace(go.Scatter(
        x=lb_lags_list, y=lb["lb_pvalue"].values, mode="markers",
        marker=dict(color=theme.color_gain, size=8, symbol="x"), showlegend=False,
    ), row=2, col=2)
    fig.add_hline(y=0.05, line=dict(color=theme.grid_color, dash="dash"), row=2, col=2)
    fig.update_yaxes(range=[-0.02, 1.02], row=2, col=2)

    fig.update_layout(**_layout(theme, title, height=560))
    for r in (1, 2):
        for c in (1, 2, 3):
            fig.update_xaxes(_ax(theme), row=r, col=c)
            fig.update_yaxes(_ax(theme), row=r, col=c)
    return fig
