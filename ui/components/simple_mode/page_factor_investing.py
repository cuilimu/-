"""
ui/components/simple_mode/page_factor_investing.py — Factor Investing Workbench tab.

Layout: 260px left config pane | main display with 4 sub-tabs.
  Config: data source toggle, factor multi-select, date range, Run Analysis.
  Overview: factor stats table with significance chips.
  QSpread Returns: cumulative long-short factor return charts.
  Correlations: cross-factor correlation heatmap.
  Score My Portfolio: rank session tickers on live factor proxies via yfinance.

Data sources:
  Live (default): Fama-French Data Library via pandas_datareader.
  Custom File: user-supplied CapitalIQ CSV + Factor_SP500 XLSX paths.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stock_engine.analytics.factor_investing import (
    CORE_FACTORS,
    FACTOR_FF_LABEL,
    FactorInvestingEngine,
    FactorInvestingResult,
    FactorStats,
    ValidationResult,
    cross_validate,
)
from stock_engine.analytics.factor_investing.loader import load_qspread_series
from stock_engine.analytics.factor_investing.theory import (
    FACTOR_THEORY,
    PORTFOLIO_CONSTRUCTION,
    FactorEntry,
)
from stock_engine.config import Config
from stock_engine.ui.components.simple_mode.session import get_session, save_session, set_step
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.ui.theme import CHART_SERIES_PALETTE, CORR_COLORSCALE
from stock_engine.viz.theme import ARX_LIGHT_THEME

# Session-state keys
_K_RESULT     = "fi_result"
_K_SOURCE     = "fi_data_source"   # "live" | "custom"
_K_SCORES     = "fi_portfolio_scores"
_K_TILT_ON    = "fi_tilt_active"
_K_VALIDATION = "fi_validation"    # list[ValidationResult] | None

# Default reference path for cross-validation (user's own CapitalIQ compute).
# Only used as a VALIDATION cross-check, never as the primary data source.
_VALIDATION_CAPITALIQ_DEFAULT = (
    r"C:\Users\Limu\Documents\2026 Spring"
    r"\RSM 6308 Advanced Investments\Project 1 data"
    r"\CapitalIQ_extend.csv"
)


# ── Session state ──────────────────────────────────────────────────────────────

def _init_state() -> None:
    st.session_state.setdefault(_K_RESULT,     None)
    st.session_state.setdefault(_K_SOURCE,     "live")
    st.session_state.setdefault(_K_SCORES,     None)
    st.session_state.setdefault(_K_VALIDATION, None)
    st.session_state.setdefault("fi_chart_factor", CORE_FACTORS[0])


# ── Plotly layout helpers ──────────────────────────────────────────────────────

def _tlayout(title: str, height: int) -> dict:
    t = ARX_LIGHT_THEME
    return dict(
        title=dict(text=title, font=dict(color=t.font_color, size=12)),
        paper_bgcolor=t.bg_paper,
        plot_bgcolor=t.bg_plot,
        font=dict(family=t.font_family, size=t.font_size_base, color=t.font_color),
        margin=dict(l=40, r=16, t=36, b=36),
        height=height,
        hovermode="x unified",
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=t.font_color, size=10),
            orientation="h", y=1.02, x=0,
        ),
    )


def _tax() -> dict:
    t = ARX_LIGHT_THEME
    return dict(
        gridcolor=t.grid_color, showgrid=True, zeroline=False,
        tickfont=dict(color=t.font_color, size=10),
    )


# ── HTML table builders ────────────────────────────────────────────────────────

def _sig_chip_html(p_value: float) -> str:
    if math.isnan(p_value):
        return ""
    if p_value < 0.01:
        return '<span class="fi-sig-chip fi-sig-strong">***</span>'
    if p_value < 0.05:
        return '<span class="fi-sig-chip fi-sig-med">**</span>'
    if p_value < 0.10:
        return '<span class="fi-sig-chip fi-sig-weak">*</span>'
    return ""


def _fmt(value: float, pct: bool = False, decimals: int = 2) -> str:
    if value is None or math.isnan(value):
        return "—"
    if pct:
        return f"{value * 100:.1f}%"
    return f"{value:.{decimals}f}"


def _build_stats_table_html(stats_list: list[FactorStats]) -> str:
    rows = []
    for s in stats_list:
        if s.sharpe > 0.4:
            sharpe_cls = "fi-sharpe-good"
        elif s.sharpe > 0.2:
            sharpe_cls = "fi-sharpe-mid"
        else:
            sharpe_cls = "fi-sharpe-low"
        sig_html = _sig_chip_html(s.p_value)
        label = FACTOR_FF_LABEL.get(s.factor_name, s.factor_name)
        rows.append(
            f"<tr>"
            f'<td title="{s.factor_name}">{label}</td>'
            f"<td>{s.n_months}</td>"
            f"<td>{_fmt(s.mean_ann, pct=True)}</td>"
            f"<td>{_fmt(s.std_ann, pct=True)}</td>"
            f'<td class="{sharpe_cls}">{_fmt(s.sharpe)}</td>'
            f"<td>{_fmt(s.skewness)}</td>"
            f"<td>{_fmt(s.kurtosis)}</td>"
            f'<td class="col-sig">{sig_html}</td>'
            f"</tr>"
        )
    body = "".join(rows)
    return (
        '<table class="fi-stats-table">'
        "<thead><tr>"
        "<th>Factor  ←  FF Proxy</th>"
        '<th class="col-n">N</th>'
        "<th>Mean Ann</th>"
        "<th>STD Ann</th>"
        "<th>Sharpe</th>"
        "<th>Skewness</th>"
        "<th>Kurtosis</th>"
        '<th class="col-sig">Sig</th>'
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _build_acf_table_html(stats_list: list[FactorStats]) -> str:
    rows = []
    for s in stats_list:
        rows.append(
            f"<tr>"
            f"<td>{FACTOR_FF_LABEL.get(s.factor_name, s.factor_name)}</td>"
            f"<td>{_fmt(s.acf_lag1, decimals=3)}</td>"
            f"<td>{_fmt(s.acf_lag12, decimals=3)}</td>"
            f"<td>{_fmt(s.acf_lag24, decimals=3)}</td>"
            f"<td>—</td>"
            f"<td>{_fmt(s.t_stat)}</td>"
            f"<td>{_fmt(s.p_value, decimals=4)}</td>"
            f"</tr>"
        )
    body = "".join(rows)
    return (
        '<table class="fi-stats-table">'
        "<thead><tr>"
        "<th>Factor</th>"
        "<th>ACF(1)</th>"
        "<th>ACF(12)</th>"
        "<th>ACF(24)</th>"
        "<th>Avg Turn.</th>"
        "<th>t-stat</th>"
        "<th>p-value</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


# ── Chart builders ─────────────────────────────────────────────────────────────

def _qspread_chart(result: FactorInvestingResult, factor_name: str) -> go.Figure:
    t = ARX_LIGHT_THEME
    palette = [
        t.color_portfolio, t.color_gain, t.color_loss, t.color_neutral,
        t.color_cash, CHART_SERIES_PALETTE[3], CHART_SERIES_PALETTE[7],
    ]

    # Quintile fan chart — only available when source="precomputed" with XLSX file
    qr_map = {q.factor_name: q for q in result.quintile_returns}
    if factor_name in qr_map:
        qr = qr_map[factor_name]
        fig = go.Figure()
        q_series = [
            ("Q1", qr.q1), ("Q2", qr.q2), ("Q3", qr.q3),
            ("Q4", qr.q4), ("Q5", qr.q5), ("QSpread", qr.qspread),
        ]
        for i, (label, s) in enumerate(q_series):
            clean = s.dropna()
            if clean.empty:
                continue
            cum = (1 + clean).cumprod() - 1
            width = 2.0 if label == "QSpread" else 1.2
            dash = "solid" if label != "QSpread" else "dash"
            fig.add_trace(go.Scatter(
                x=cum.index, y=cum.values, mode="lines",
                name=label,
                line=dict(color=palette[i % len(palette)], width=width, dash=dash),
            ))
        fig.update_layout(**_tlayout(
            f"{factor_name} — Quintile Cumulative Returns", 420,
        ))
        fig.update_xaxes(_tax())
        fig.update_yaxes(_tax(), tickformat=".0%")
        return fig

    # QSpread-only (live Fama-French path or missing XLSX)
    series = result.qspread_series.get(factor_name)
    if series is None or series.empty:
        return go.Figure()

    cum = (1 + series).cumprod() - 1
    label = FACTOR_FF_LABEL.get(factor_name, factor_name)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cum.index, y=cum.values, mode="lines",
        name="QSpread (L/S)",
        line=dict(color=t.color_portfolio, width=2.0),
        fill="tozeroy",
        fillcolor="rgba(102,8,116,0.08)",
    ))
    fig.update_layout(**_tlayout(f"{label} — Long/Short Cumulative Return", 380))
    fig.update_xaxes(_tax())
    fig.update_yaxes(_tax(), tickformat=".0%")
    return fig


def _corr_heatmap(result: FactorInvestingResult) -> go.Figure:
    t = ARX_LIGHT_THEME
    corr = result.correlation
    if corr.matrix.empty:
        return go.Figure()

    labels = [FACTOR_FF_LABEL.get(lbl, lbl).split("  ←  ")[0] for lbl in corr.labels]
    z = corr.matrix.values.tolist()

    fig = go.Figure(go.Heatmap(
        z=z, x=labels, y=labels,
        colorscale=CORR_COLORSCALE,
        zmid=0, zmin=-1, zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in z],
        texttemplate="%{text}",
        showscale=True,
        colorbar=dict(thickness=12, len=0.9,
                      tickfont=dict(color=t.font_color, size=9)),
    ))
    n = len(labels)
    fig.update_layout(**_tlayout("Factor QSpread Correlations", max(320, n * 60 + 80)))
    fig.update_xaxes(
        gridcolor=t.grid_color, showgrid=False, zeroline=False,
        tickangle=-30, side="bottom",
        tickfont=dict(color=t.font_color, size=9),
    )
    fig.update_yaxes(
        gridcolor=t.grid_color, showgrid=False, zeroline=False,
        tickfont=dict(color=t.font_color, size=9),
        autorange="reversed",
    )
    return fig


# ── Score My Portfolio helpers ─────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_portfolio_scores(tickers: tuple[str, ...]) -> Optional[pd.DataFrame]:
    """Compute MOM, AnnVol, Beta z-scores for a tuple of tickers via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    end = pd.Timestamp.now()
    start = end - pd.DateOffset(months=14)
    all_tickers = list(tickers) + ["SPY"]
    try:
        raw = yf.download(
            all_tickers, start=start, end=end,
            auto_adjust=True, progress=False, threads=True,
        )
    except Exception:
        return None

    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw.iloc[:, 0]
    else:
        close = raw

    close = close.dropna(how="all")
    if close.empty:
        return None

    daily_ret = close.pct_change().dropna(how="all")
    monthly = close.resample("ME").last().pct_change()

    records = {}
    for ticker in tickers:
        if ticker not in close.columns:
            continue
        try:
            daily = daily_ret[ticker].dropna()
            mon   = monthly[ticker].dropna() if ticker in monthly.columns else pd.Series(dtype=float)

            mom = float(mon.iloc[-12:-1].mean()) if len(mon) >= 12 else float("nan")
            recent_daily = daily.last("365D") if len(daily) > 30 else daily
            ann_vol = float(recent_daily.std() * (252 ** 0.5))

            spy_ret = daily_ret["SPY"].dropna() if "SPY" in daily_ret.columns else pd.Series(dtype=float)
            aligned = pd.concat([daily.rename("t"), spy_ret.rename("s")], axis=1).dropna()
            if len(aligned) >= 20:
                cov = float(aligned["t"].cov(aligned["s"]))
                var_spy = float(aligned["s"].var())
                beta = cov / var_spy if var_spy > 0 else float("nan")
            else:
                beta = float("nan")

            records[ticker] = {"MOM": mom, "AnnVol12M": ann_vol, "Beta": beta}
        except Exception:
            continue

    if not records:
        return None

    df = pd.DataFrame(records).T.astype(float)
    for col in df.columns:
        vals = df[col].dropna()
        if len(vals) >= 2:
            df[f"z_{col}"] = (df[col] - vals.mean()) / vals.std()
        else:
            df[f"z_{col}"] = float("nan")

    z_cols = {"z_MOM": 1.0, "z_AnnVol12M": -1.0, "z_Beta": -1.0}
    avail = [c for c in z_cols if c in df.columns]
    if avail:
        df["Composite"] = sum(df[c] * z_cols[c] for c in avail) / len(avail)
    else:
        df["Composite"] = float("nan")

    df["Rank"] = df["Composite"].rank(ascending=False, method="min").astype(int)
    n = len(df["Composite"].dropna())
    if n >= 3:
        df["Decile"] = pd.qcut(
            df["Composite"].rank(ascending=True, method="first"),
            min(n, 10), labels=False,
        ).fillna(0).astype(int) + 1
    else:
        df["Decile"] = 1

    return df.sort_values("Rank")


def _build_score_table_html(df: pd.DataFrame) -> str:
    max_abs = df["Composite"].abs().max()
    if max_abs == 0 or math.isnan(max_abs):
        max_abs = 1.0

    rows = []
    for rank, (ticker, row) in enumerate(df.iterrows(), start=1):
        score = row.get("Composite", float("nan"))
        if math.isnan(score):
            pct, bar_cls = 2, "fi-score-bar-pos"
        else:
            pct = max(2, min(100, int(abs(score) / max_abs * 100)))
            bar_cls = "fi-score-bar-pos" if score >= 0 else "fi-score-bar-neg"

        score_cell = (
            f'<td><div class="fi-score-cell">'
            f'<span class="fi-score-num">{_fmt(score)}</span>'
            f'<div class="fi-score-bar-track">'
            f'<div class="fi-score-bar-fill {bar_cls}" style="width:{pct}%"></div>'
            f"</div></div></td>"
        )
        rows.append(
            f"<tr>"
            f"<td>{rank}</td>"
            f'<td class="col-ticker">{ticker}</td>'
            f"<td>{_fmt(row.get('z_MOM', float('nan')))}</td>"
            f"<td>{_fmt(row.get('z_AnnVol12M', float('nan')))}</td>"
            f"<td>{_fmt(row.get('z_Beta', float('nan')))}</td>"
            f"{score_cell}"
            f'<td><span class="fi-decile-badge">{int(row.get("Decile", 1))}</span></td>'
            f"</tr>"
        )

    body = "".join(rows)
    return (
        '<table class="fi-score-table">'
        "<thead><tr>"
        "<th>#</th>"
        '<th class="col-ticker">Ticker</th>'
        "<th>z-MOM</th>"
        "<th>z-Vol</th>"
        "<th>z-Beta</th>"
        "<th>Score</th>"
        "<th>Decile</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


# ── Run analysis ───────────────────────────────────────────────────────────────

def _run_analysis(
    factors: list[str],
    source: str,
    start: str,
    capitaliq_path: str,
    factor_sp500_path: str,
    validation_path: str,
) -> None:
    if not factors:
        st.warning("Select at least one factor.")
        return

    engine = FactorInvestingEngine(
        capitaliq_path=capitaliq_path or None,
        factor_sp500_path=factor_sp500_path or None,
    )

    if source == "compute":
        # Tier-2: show live progress during long computation
        status_box = st.empty()
        def _progress(msg: str) -> None:
            status_box.info(f"⏳ {msg}")

        result = engine.run_compute(factors=factors, start=start, progress_cb=_progress)
        status_box.empty()
    else:
        with st.spinner("Loading factor data…"):
            if source == "live":
                result = engine.run_live(factors=factors, start=start)
            else:
                result = engine.run_quick(factors=factors)

    st.session_state[_K_RESULT] = result
    st.session_state[_K_SCORES] = None
    st.session_state[_K_VALIDATION] = None

    # Cross-validation against static reference (live or computed modes)
    if source in ("live", "compute") and result.qspread_series:
        vpath = validation_path.strip() if validation_path else _VALIDATION_CAPITALIQ_DEFAULT
        try:
            static_dict = load_qspread_series(vpath, factors=factors)
            if static_dict:
                val_results = cross_validate(result.qspread_series, static_dict)
                st.session_state[_K_VALIDATION] = val_results
        except Exception:
            pass

    st.rerun()


# ── Config pane ────────────────────────────────────────────────────────────────

def _render_config_pane(config: Config) -> tuple[list[str], str, str, str, str, str]:
    """Render left config panel.

    Returns
    -------
    (selected_factors, source, start, capitaliq_path, sp500_path, validation_path)
    """

    # ── Data source ───────────────────────────────────────────────────────────
    st.markdown('<div class="fi-config-label">DATA SOURCE</div>', unsafe_allow_html=True)
    _SRC_LABELS = {
        "live":    "Live · Fama-French",
        "compute": "Compute · Daily data",
        "custom":  "Custom File",
    }
    source = st.radio(
        "Data source",
        list(_SRC_LABELS.keys()),
        index=0,
        key="fi_data_source",
        format_func=_SRC_LABELS.get,
        label_visibility="collapsed",
    )

    capitaliq_path = ""
    factor_sp500_path = ""

    if source == "live":
        st.caption("Downloads from Kenneth French's Data Library · Updated monthly")
    elif source == "compute":
        st.caption(
            "Downloads S&P 500 daily prices via yfinance, computes 5 price-based "
            "factors from scratch. BP/LTGC supplemented from Fama-French. "
            "First run: ~1-2 min · cached 24h."
        )
    else:
        st.caption("Point to your own CapitalIQ CSV + Factor XLSX files.")
        capitaliq_path = st.text_input(
            "CapitalIQ CSV path",
            key="fi_capitaliq_path",
            placeholder=r"C:\...\CapitalIQ_extend.csv",
            label_visibility="visible",
        )
        factor_sp500_path = st.text_input(
            "Factor_SP500 XLSX path",
            key="fi_factor_sp500_path",
            placeholder=r"C:\...\Factor_SP500.xlsx",
            label_visibility="visible",
        )

    # ── Date range ────────────────────────────────────────────────────────────
    st.markdown('<div class="fi-config-sep"></div>', unsafe_allow_html=True)
    st.markdown('<div class="fi-config-label">DATE RANGE</div>', unsafe_allow_html=True)
    start_str = config.default_start_date or "1990-01-01"
    st.caption(f"Start: {start_str}  ·  End: latest")

    # ── Factor selection ──────────────────────────────────────────────────────
    st.markdown('<div class="fi-config-sep"></div>', unsafe_allow_html=True)
    st.markdown('<div class="fi-config-label">FACTORS</div>', unsafe_allow_html=True)

    selected: list[str] = []
    for factor in CORE_FACTORS:
        label = FACTOR_FF_LABEL.get(factor, factor)
        if st.checkbox(label, value=True, key=f"fi_factor_{factor}"):
            selected.append(factor)

    # ── Methodology note ──────────────────────────────────────────────────────
    st.markdown('<div class="fi-config-sep"></div>', unsafe_allow_html=True)
    st.markdown('<div class="fi-config-label">METHODOLOGY</div>', unsafe_allow_html=True)
    if source == "live":
        st.caption(
            "Long-short factor return series from Fama-French. "
            "Not a raw quintile sort — see French Data Library documentation."
        )
    elif source == "compute":
        st.caption(
            "Quintile sort on S&P 500 · Equal-weight · 1M holding lag · "
            "Winsorized 1/99% · 252-day rolling windows for Beta and Vol."
        )
    else:
        st.caption("Quintile sort · Equal-weight · 1M holding lag · Winsorized 1/99%")

    # ── Validation reference ──────────────────────────────────────────────────
    st.markdown('<div class="fi-config-sep"></div>', unsafe_allow_html=True)
    st.markdown('<div class="fi-config-label">VALIDATION REF.</div>', unsafe_allow_html=True)
    st.caption("CapitalIQ Q-spread CSV used as cross-check against live data.")
    validation_path = st.text_input(
        "CapitalIQ ref. path (optional)",
        value=_VALIDATION_CAPITALIQ_DEFAULT,
        key="fi_validation_path",
        label_visibility="collapsed",
        help="Leave blank or point to your CapitalIQ_extend.csv. "
             "Auto-compared with live data in the Validation tab.",
    )
    val_results = st.session_state.get(_K_VALIDATION)
    if val_results:
        n_ok = sum(1 for v in val_results if v.validated)
        n_total = len(val_results)
        tag = ":green[Validated]" if n_ok == n_total else ":orange[Partial]"
        st.caption(f"{tag} — {n_ok}/{n_total} factors r ≥ 0.80")

    # ── Run button ────────────────────────────────────────────────────────────
    with st.container(key="fi_run_btn"):
        if st.button("Run Analysis", key="fi_run",
                     use_container_width=True, type="primary"):
            _run_analysis(
                selected, source, start_str,
                capitaliq_path, factor_sp500_path, validation_path,
            )

    result: Optional[FactorInvestingResult] = st.session_state.get(_K_RESULT)
    if result is not None:
        _SRC_MAP = {"live": "Fama-French (live)", "computed": "S&P 500 daily compute", "precomputed": "CapitalIQ static"}
    src_label = _SRC_MAP.get(result.source, result.source)
        st.caption(
            f"Source: {src_label}  ·  "
            f"As of: {result.as_of_date.strftime('%b %Y')}"
        )

    if st.session_state.get(_K_TILT_ON):
        st.markdown(
            '<span class="fi-active-badge">Factor tilt active</span>',
            unsafe_allow_html=True,
        )

    return selected, source, start_str, capitaliq_path, factor_sp500_path, validation_path


# ── Tab renderers ──────────────────────────────────────────────────────────────

def _render_overview(result: FactorInvestingResult) -> None:
    _SRC_MAP = {"live": "Fama-French (live)", "computed": "S&P 500 daily compute", "precomputed": "CapitalIQ static"}
    src_label = _SRC_MAP.get(result.source, result.source)
    n = len(result.factor_stats)
    st.markdown(
        f'<div class="fi-results-bar">'
        f"FACTOR STATISTICS — LONG/SHORT SPREAD"
        f'<span class="fi-results-count">{n} factors · {src_label} · monthly</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(_build_stats_table_html(result.factor_stats), unsafe_allow_html=True)

    with st.expander("ACF & Hypothesis Tests"):
        st.markdown(_build_acf_table_html(result.factor_stats), unsafe_allow_html=True)
        st.caption(
            "ACF: autocorrelation at lags 1, 12, 24 months. "
            "t-stat: 1-sample t-test, H₁: mean L/S return > 0. "
            "*** p<0.01  ** p<0.05  * p<0.10."
        )


def _render_qspread_returns(result: FactorInvestingResult) -> None:
    factors_available = [s.factor_name for s in result.factor_stats
                         if not result.qspread_series.get(s.factor_name, pd.Series()).empty
                         or any(q.factor_name == s.factor_name for q in result.quintile_returns)]
    if not factors_available:
        st.info("No return series available. Run the analysis first.")
        return

    selected = st.selectbox(
        "Factor", factors_available,
        index=0, key="fi_chart_factor",
        format_func=lambda f: FACTOR_FF_LABEL.get(f, f).split("  ←  ")[0],
    )
    fig = _qspread_chart(result, selected)
    st.plotly_chart(fig, use_container_width=True)

    if result.source == "live":
        st.caption(
            "Cumulative return of the long-short (Q5 − Q1 equivalent) factor portfolio "
            "sourced from Kenneth French's Data Library. "
            "Positive → the factor premium was positive over the period."
        )
    else:
        st.caption(
            "Cumulative return of each quintile portfolio and the long-short spread (QSpread = Q5 − Q1). "
            "Q5 = top-quintile stocks, Q1 = bottom-quintile stocks. Equal-weighted, 1-month holding lag."
        )


def _render_correlations(result: FactorInvestingResult) -> None:
    with st.container(key="fi_corr_heatmap"):
        fig = _corr_heatmap(result)
        if fig.data:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need at least 2 factors to show correlations.")
    st.caption(
        "Pearson correlation of monthly long-short factor returns, aligned on the common date index. "
        "Low correlation → diversification benefit when combining factors."
    )


def _render_score_portfolio(result: FactorInvestingResult) -> None:
    sess = get_session()
    tickers = sess.universe.tickers

    if not tickers:
        st.markdown(
            '<div class="fi-empty">'
            "<h3>No portfolio tickers yet</h3>"
            "<p>Add stocks in Step 2 (Stock Selection) first, "
            "then return here to score them on live factor data.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div class="fi-results-bar">'
        f"FACTOR SCORES — CURRENT PORTFOLIO"
        f'<span class="fi-results-count">{len(tickers)} tickers · live via yfinance</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Live factor proxies from 12M yfinance data: "
        "MOM (avg monthly return t-12:t-2), AnnVol (annualized daily vol), "
        "Beta (CAPM vs SPY). Z-scored cross-sectionally. "
        "Composite = equal-weighted (z_MOM − z_Vol − z_Beta)."
    )

    if st.button("Compute Factor Scores", key="fi_score_btn"):
        st.session_state[_K_SCORES] = None
        with st.spinner("Fetching market data…"):
            scores = _fetch_portfolio_scores(tuple(sorted(tickers)))
            st.session_state[_K_SCORES] = scores

    scores: Optional[pd.DataFrame] = st.session_state.get(_K_SCORES)

    if scores is None:
        st.info("Click **Compute Factor Scores** to score your portfolio tickers.")
        return
    if scores.empty:
        st.warning("Could not fetch data for the selected tickers.")
        return

    st.markdown(_build_score_table_html(scores), unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        with st.container(key="fi_push_step2"):
            if st.button("Apply to Stock Selection", key="fi_push_step2_btn",
                         use_container_width=True):
                _apply_to_selection(scores, sess)
    with c2:
        with st.container(key="fi_push_tilt"):
            if st.button("Apply Tilt to Allocation", key="fi_push_tilt_btn",
                         use_container_width=True):
                _apply_tilt(scores)


def _render_theory(selected_factors: list[str]) -> None:
    """Render theoretical background, LaTeX formulas, and portfolio construction logic."""

    # ── Portfolio construction ─────────────────────────────────────────────────
    pc = PORTFOLIO_CONSTRUCTION
    with st.expander("Portfolio Construction Methodology", expanded=True):
        st.markdown(
            "**Universe:** " + pc["universe"],
            unsafe_allow_html=False,
        )
        st.markdown("**Step-by-step procedure:**")
        for i, (step_name, step_desc) in enumerate(pc["steps"], start=1):
            st.markdown(f"**{i}. {step_name}** — {step_desc}")

        st.markdown("**Winsorized characteristic sort:**")
        st.latex(pc["sort_formula_tex"])
        st.markdown("**Equal-weight within quintile:**")
        st.latex(pc["equal_weight_formula_tex"])
        st.markdown("**Q-spread (long Q5, short Q1):**")
        st.latex(pc["qspread_formula_tex"])
        st.markdown("**Annualized Sharpe ratio:**")
        st.latex(pc["annualized_sharpe_tex"])
        st.markdown("**t-statistic (H₀: mean Q-spread = 0):**")
        st.latex(pc["t_stat_tex"])

    st.markdown('<div class="fi-config-sep" style="margin:12px 0"></div>',
                unsafe_allow_html=True)

    # ── Per-factor cards ───────────────────────────────────────────────────────
    st.markdown(
        '<div class="fi-results-bar">'
        "FACTOR REFERENCE"
        '<span class="fi-results-count">academic foundation + formulas</span>'
        "</div>",
        unsafe_allow_html=True,
    )

    factors_to_show = selected_factors if selected_factors else list(FACTOR_THEORY.keys())
    for factor_key in factors_to_show:
        entry: FactorEntry | None = FACTOR_THEORY.get(factor_key)
        if entry is None:
            continue

        with st.expander(f"{entry.name}  ·  {entry.category}", expanded=False):
            # Intuition banner
            st.markdown(
                f'<div class="fi-results-bar" style="margin-bottom:8px">'
                f'<em>{entry.intuition}</em>'
                f"</div>",
                unsafe_allow_html=True,
            )

            # Theory text
            for para in entry.description.split("\n\n"):
                st.markdown(para)

            # Formulas
            st.markdown("**Factor characteristic:**")
            st.latex(entry.formula_tex)
            st.markdown("**Q-spread (long-short) return:**")
            st.latex(entry.qspread_tex)

            # References
            st.markdown("**Key references:**")
            for ref in entry.references:
                st.caption(f"• {ref}")


def _render_validation(val_results: list[ValidationResult]) -> None:
    """Render the factor reliability / cross-validation table."""
    if not val_results:
        st.info(
            "No validation data available. "
            "Provide a CapitalIQ reference path in the config pane and re-run analysis."
        )
        return

    n_ok = sum(1 for v in val_results if v.validated)
    n_total = len(val_results)
    status_label = "All factors validated" if n_ok == n_total else f"{n_ok}/{n_total} factors validated"
    st.markdown(
        f'<div class="fi-results-bar">'
        f"FACTOR RELIABILITY — LIVE vs STATIC CROSS-CHECK"
        f'<span class="fi-results-count">{status_label} · threshold r ≥ 0.80</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Compares Fama-French long-short returns (live) with CapitalIQ Q-spread returns (static reference) "
        "over their overlapping date range. High Pearson r confirms that the live data is a reliable proxy "
        "for the custom quintile-sort methodology."
    )

    rows = []
    for v in val_results:
        r_pct  = f"{v.pearson_r * 100:.1f}%"
        r2_pct = f"{v.r_squared * 100:.1f}%"
        beta_s = _fmt(v.beta)
        period = f"{v.period_start.strftime('%Y-%m')} – {v.period_end.strftime('%Y-%m')}"

        if v.validated:
            badge = '<span class="fi-sig-chip fi-sig-strong">Validated</span>'
        elif v.pearson_r >= 0.60:
            badge = '<span class="fi-sig-chip fi-sig-med">Moderate</span>'
        else:
            badge = '<span class="fi-sig-chip fi-sig-weak">Weak</span>'

        rows.append(
            f"<tr>"
            f"<td>{v.factor_name}</td>"
            f"<td>{v.ff_proxy}</td>"
            f"<td>{period}</td>"
            f"<td>{v.n_overlap}</td>"
            f"<td><strong>{r_pct}</strong></td>"
            f"<td>{r2_pct}</td>"
            f"<td>{beta_s}</td>"
            f"<td>{badge}</td>"
            f"</tr>"
        )
    body = "".join(rows)
    html = (
        '<table class="fi-stats-table">'
        "<thead><tr>"
        "<th>Factor</th>"
        "<th>FF Proxy</th>"
        "<th>Overlap Period</th>"
        '<th class="col-n">N</th>'
        "<th>Pearson r</th>"
        "<th>R&sup2;</th>"
        "<th>Beta</th>"
        "<th>Status</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )
    st.markdown(html, unsafe_allow_html=True)

    with st.expander("Interpretation"):
        st.markdown(
            "**Pearson r** measures the linear correlation between the two monthly return series "
            "over overlapping periods. r ≥ 0.80 is treated as validated — the live Fama-French "
            "proxy and the CapitalIQ quintile sort move together closely enough for research use.\n\n"
            "**Beta** is the OLS slope of `live ~ static`. Beta ≈ 1.0 indicates equal magnitude; "
            "beta > 1 means the live series is more volatile than the CapitalIQ reference.\n\n"
            "**Note:** Perfect correlation is not expected — French data uses all NYSE/AMEX/NASDAQ "
            "stocks while CapitalIQ focuses on S&P 500. Differences in universe and weighting "
            "produce structural gaps, especially for smaller-cap factors (SMB proxy)."
        )


def _apply_to_selection(scores: pd.DataFrame, sess) -> None:
    top_n = min(10, len(scores))
    top_tickers = list(scores.head(top_n).index)
    sess.universe.tickers = top_tickers
    save_session(sess)
    st.toast(f"Stock selection updated: top {top_n} tickers by composite score.")


def _apply_tilt(scores: pd.DataFrame) -> None:
    valid = scores["Composite"].dropna()
    if valid.empty:
        st.warning("No valid composite scores to apply.")
        return
    shifted = valid - valid.min()
    total = shifted.sum()
    tilt = (shifted / total).to_dict() if total > 0 else {}
    st.session_state["fi_tilt_vector"] = tilt
    st.session_state[_K_TILT_ON] = True
    st.toast("Factor tilt applied — visible in Allocation step.")


# ── Main entry point ───────────────────────────────────────────────────────────

def render_page_factor_investing(config: Config) -> None:
    _inject_css("factor_investing")
    _init_state()

    st.markdown(
        '<span class="fi-page-marker" style="display:none"></span>',
        unsafe_allow_html=True,
    )

    with st.container(key="fi_main_grid"):
        cols = st.columns([1, 3], gap="small")

        with cols[0]:
            with st.container(key="fi_config_pane", border=False):
                _render_config_pane(config)

        with cols[1]:
            result: Optional[FactorInvestingResult] = st.session_state.get(_K_RESULT)

            if result is None:
                st.markdown(
                    '<div class="fi-empty">'
                    "<h3>Factor Investing Analysis</h3>"
                    "<p>Select factors in the left panel and click "
                    "<strong>Run Analysis</strong>. "
                    "Data is pulled live from Kenneth French's "
                    "Data Library — no local files required. "
                    "A cross-validation against your CapitalIQ reference "
                    "runs automatically in the background.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                return

            val_results: Optional[list] = st.session_state.get(_K_VALIDATION)

            selected_factors: list[str] = [
                f for f in CORE_FACTORS
                if st.session_state.get(f"fi_factor_{f}", True)
            ]

            with st.container(key="fi_subtabs"):
                tab_labels = ["Overview", "L/S Returns", "Correlations",
                              "Score My Portfolio", "Theory", "Validation"]
                tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tab_labels)

            with tab1:
                _render_overview(result)
            with tab2:
                _render_qspread_returns(result)
            with tab3:
                _render_correlations(result)
            with tab4:
                _render_score_portfolio(result)
            with tab5:
                _render_theory(selected_factors)
            with tab6:
                _render_validation(val_results or [])
