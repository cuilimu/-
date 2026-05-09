"""
analytics/factor/bivariate.py
Bivariate statistical analysis between two return series.
No AI functions. Pure computation + Plotly charts.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class BivariateStats:
    n_obs: int
    pearson_r: float
    pearson_p: float
    spearman_r: float
    spearman_p: float
    kendall_tau: float      # Kendall Tau-b (more robust for fat-tailed returns)
    kendall_p: float
    covariance: float       # Sample covariance
    beta_yx: float          # OLS slope: y = a + beta*x
    alpha_yx: float
    r_squared: float
    # Tail analysis
    bear_corr: float        # corr when x < median(x)
    bull_corr: float        # corr when x > median(x)
    tail_ratio: float       # bear_corr / bull_corr  (>1 = higher downside co-movement)


def compute_bivariate_stats(x: pd.Series, y: pd.Series) -> Optional[BivariateStats]:
    from scipy import stats as sp
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if len(df) < 8:
        return None
    xv, yv = df["x"].values, df["y"].values

    pr, pp   = sp.pearsonr(xv, yv)
    sr, sp_  = sp.spearmanr(xv, yv)
    kt, kp   = sp.kendalltau(xv, yv)
    cov      = float(np.cov(xv, yv)[0, 1])
    slope, intercept, _, _, _ = sp.linregress(xv, yv)

    # Tail split on median of x
    med = np.median(xv)
    bear = df[df["x"] <= med]
    bull = df[df["x"] >  med]
    bc = float(bear["x"].corr(bear["y"])) if len(bear) > 4 else float("nan")
    uc = float(bull["x"].corr(bull["y"])) if len(bull) > 4 else float("nan")
    tr = bc / uc if (uc and not np.isnan(uc) and uc != 0) else float("nan")

    y_hat = intercept + slope * xv
    ss_res = np.sum((yv - y_hat) ** 2)
    ss_tot = np.sum((yv - yv.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return BivariateStats(
        n_obs=len(df), pearson_r=float(pr), pearson_p=float(pp),
        spearman_r=float(sr), spearman_p=float(sp_),
        kendall_tau=float(kt), kendall_p=float(kp),
        covariance=cov,
        beta_yx=float(slope), alpha_yx=float(intercept), r_squared=float(r2),
        bear_corr=bc, bull_corr=uc, tail_ratio=tr,
    )


# Chi-squared quantiles for 2 DOF (for confidence ellipses)
_CHI2_2DF = {70: 2.408, 80: 3.219, 90: 4.605, 95: 5.991}


def _ellipse_points(xv: np.ndarray, yv: np.ndarray, confidence: int = 80, n_pts: int = 120):
    """
    Compute confidence ellipse boundary points for a 2-D scatter.
    Based on eigen-decomposition of the sample covariance matrix.
    confidence: integer percent level (70, 80, 90, 95).
    """
    n = len(xv)
    if n < 4:
        return None, None
    mx, my = xv.mean(), yv.mean()
    cov = np.cov(xv, yv, ddof=1)            # 2×2 covariance matrix
    eigvals, eigvecs = np.linalg.eigh(cov)   # sorted ascending
    # Largest eigenvalue → major axis
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    if np.any(eigvals <= 0):
        return None, None
    chi2 = _CHI2_2DF.get(confidence, 3.219)
    angle = np.linspace(0, 2 * np.pi, n_pts)
    unit = np.column_stack([np.cos(angle), np.sin(angle)])
    # Scale by sqrt(eigenvalue * chi2_quantile)
    axes = np.sqrt(eigvals * chi2)
    pts = unit * axes                        # (n_pts × 2) in eigen-space
    rotated = pts @ eigvecs.T               # back to data space
    return rotated[:, 0] + mx, rotated[:, 1] + my


def scatter_chart(x: pd.Series, y: pd.Series, xname: str, yname: str):
    import plotly.graph_objects as go
    from scipy import stats as sp
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    slope, intercept, r, p, se = sp.linregress(df["x"], df["y"])
    x_fit = np.linspace(df["x"].min(), df["x"].max(), 100)
    y_fit = intercept + slope * x_fit
    n = len(df)
    t_crit = sp.t.ppf(0.975, df=n - 2)
    x_mean = df["x"].mean()
    se_fit = se * np.sqrt(1/n + (x_fit - x_mean)**2 / np.sum((df["x"] - x_mean)**2))
    y_upper = y_fit + t_crit * se_fit
    y_lower = y_fit - t_crit * se_fit

    fig = go.Figure()

    # OLS confidence band
    fig.add_trace(go.Scatter(
        x=x_fit, y=y_upper, mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=x_fit, y=y_lower, mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor="rgba(102,8,116,0.10)",
        showlegend=False, hoverinfo="skip",
    ))

    # Confidence ellipses (80% and 70%)
    xv, yv = df["x"].values, df["y"].values
    for conf, color, dash in [(80, "rgba(180,100,0,0.70)", "dot"),
                               (70, "rgba(180,100,0,0.40)", "dot")]:
        ex, ey = _ellipse_points(xv, yv, confidence=conf)
        if ex is not None:
            fig.add_trace(go.Scatter(
                x=np.append(ex, ex[0]), y=np.append(ey, ey[0]),
                mode="lines", line=dict(color=color, dash=dash, width=1.2),
                name=f"{conf}% ellipse", hoverinfo="skip",
            ))

    # OLS fit line
    fig.add_trace(go.Scatter(
        x=x_fit, y=y_fit, mode="lines",
        line=dict(color="#660874", dash="dash", width=1.5),
        name=f"OLS fit  β={slope:.3f}  R²={r**2:.3f}",
    ))
    # Data points
    fig.add_trace(go.Scatter(
        x=df["x"], y=df["y"], mode="markers",
        marker=dict(color="#660874", opacity=0.65, size=7),
        text=df.index.strftime("%Y-%m"),
        hovertemplate="%{text}<br>x=%{x:.4f}  y=%{y:.4f}",
        name="Monthly obs",
    ))
    fig.update_layout(
        title=f"Scatter: {yname} vs {xname}   ρ={r:.3f}  p={p:.3f}",
        xaxis_title=xname, yaxis_title=yname,
        paper_bgcolor="#fff", plot_bgcolor="#fafafa",
        height=420, margin=dict(l=55, r=20, t=50, b=45),
        legend=dict(font=dict(size=10), x=0.01, y=0.99),
    )
    return fig


def rolling_corr_chart(x: pd.Series, y: pd.Series, xname: str, yname: str, window: int = 12):
    """
    Rolling correlation chart with continuous colored fill areas.
    Uses clip() to avoid gaps at zero-crossings (Bug fix: split traces left gaps).
    """
    import plotly.graph_objects as go
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    rc = df["x"].rolling(window).corr(df["y"]).dropna()
    overall = df["x"].corr(df["y"])

    fig = go.Figure()
    fig.add_hline(y=0,       line_dash="dot", line_color="#cccccc", line_width=1)
    fig.add_hline(y=overall, line_dash="dash", line_color="#b35c00", line_width=1,
                  annotation_text=f"Full-period ρ={overall:.3f}",
                  annotation_position="top right")

    # Continuous line — no gaps at zero-crossings
    fig.add_trace(go.Scatter(
        x=rc.index, y=rc.values, mode="lines",
        line=dict(color="#660874", width=1.5),
        name=f"{window}M rolling ρ",
    ))
    # Green fill above zero, red fill below zero using clip (continuous)
    fig.add_trace(go.Scatter(
        x=rc.index, y=rc.clip(lower=0).values, mode="none",
        fill="tozeroy", fillcolor="rgba(0,176,80,0.18)",
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=rc.index, y=rc.clip(upper=0).values, mode="none",
        fill="tozeroy", fillcolor="rgba(224,48,48,0.18)",
        showlegend=False, hoverinfo="skip",
    ))

    fig.update_layout(
        title=f"Rolling {window}M correlation: {xname} & {yname}",
        xaxis_title="Date", yaxis_title="Correlation",
        paper_bgcolor="#fff", plot_bgcolor="#fafafa",
        height=340, margin=dict(l=55, r=20, t=50, b=40),
        yaxis=dict(range=[-1.05, 1.05]),
    )
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 0.10) -> str:
    """Convert '#RRGGBB' to 'rgba(R,G,B,alpha)' (Bug fix: str.replace produced invalid CSS)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def distribution_chart(x: pd.Series, y: pd.Series, xname: str, yname: str):
    import plotly.graph_objects as go
    from scipy.stats import gaussian_kde
    fig = go.Figure()
    for series, name, color in [(x, xname, "#660874"), (y, yname, "#00b050")]:
        s = series.dropna()
        grid = np.linspace(s.min() - s.std(), s.max() + s.std(), 200)
        kde  = gaussian_kde(s)(grid)
        fig.add_trace(go.Scatter(
            x=grid, y=kde, mode="lines", name=name,
            line=dict(color=color, width=2),
        ))
        fig.add_trace(go.Scatter(
            x=grid, y=kde, mode="none", fill="tozeroy",
            fillcolor=_hex_to_rgba(color, 0.12),
            showlegend=False, hoverinfo="skip",
        ))
    fig.update_layout(
        title="Return distributions (KDE)",
        xaxis_title="Monthly excess return", yaxis_title="Density",
        paper_bgcolor="#fff", plot_bgcolor="#fafafa",
        height=320, margin=dict(l=55, r=20, t=50, b=40),
    )
    return fig


def tail_analysis_chart(x: pd.Series, y: pd.Series, xname: str, yname: str,
                         quantiles: int = 10):
    """Scatter of conditional correlation by x-quantile bucket."""
    import plotly.graph_objects as go
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    df["q"] = pd.qcut(df["x"], quantiles, labels=False, duplicates="drop")
    rows = []
    for q, grp in df.groupby("q"):
        if len(grp) >= 4:
            rows.append({"quantile": int(q) + 1,
                         "x_mid": grp["x"].mean(),
                         "corr":  grp["x"].corr(grp["y"]),
                         "n":     len(grp)})
    if not rows:
        return None

def conditional_stats_chart(x: pd.Series, y: pd.Series, xname: str, yname: str,
                              n_quantiles: int = 5):
    """
    Box plots of X distribution conditional on Y quintile.
    Mirrors the 'X conditional on Y' section of the reference bivariate profiler.
    Shows how the distribution of x changes as y moves from low to high.
    """
    import plotly.graph_objects as go
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if len(df) < n_quantiles * 4:
        return None

    try:
        df["q"] = pd.qcut(df["y"], n_quantiles, duplicates="drop")
    except ValueError:
        return None

    quantile_labels = {i: str(cat) for i, cat in enumerate(df["q"].cat.categories)}
    df["q_idx"] = df["q"].cat.codes

    traces = []
    colors = ["#e03030", "#e07030", "#888888", "#30a050", "#1060c0"]
    for idx in sorted(df["q_idx"].unique()):
        grp = df[df["q_idx"] == idx]["x"].values
        label = quantile_labels.get(idx, str(idx))
        color = colors[min(idx, len(colors) - 1)]
        traces.append(go.Box(
            y=grp,
            name=label,
            marker_color=color,
            line_color=color,
            fillcolor=color.replace("rgb", "rgba").replace(")", ", 0.25)") if "rgb" in color
                       else _hex_to_rgba(color, 0.25),
            boxpoints="outliers",
            jitter=0.3,
            pointpos=0,
            marker=dict(size=4, opacity=0.5),
            hovertemplate=f"<b>{label}</b><br>%{{y:.4f}}<extra></extra>",
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        title=f"{xname} distribution by {yname} quintile",
        xaxis_title=f"{yname} quintile (low → high)",
        yaxis_title=f"{xname} (excess return)",
        paper_bgcolor="#fff", plot_bgcolor="#fafafa",
        height=360, margin=dict(l=55, r=20, t=50, b=60),
        showlegend=False,
    )
    return fig
