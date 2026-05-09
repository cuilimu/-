"""
ui/components/simple_mode/page1_universe.py — Step 1: Stock Selection.

Design: Bloomberg Terminal — white bg, purple accent, squared, no decoration.

Layout (all heights hardcoded, nothing may expand the page):
  col_left  (2.1):  UNIVERSE panel
                      search input   (48px, floating dropdown via position:fixed)
                      ticker header  (20px)
                      ticker list    (360px = 10 rows × 36px, overflow-y:auto)
                      corr heatmap   (340px, approx square)
  col_right (3.7):  FACTOR BUCKETS  (180px fixed)
                    ALL-WEATHER MAP  (430px)
  Bottom bar: stats · Back / Next: Allocation
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from stock_engine.config import Config
from stock_engine.data.yfinance_provider import YFinanceProvider
from stock_engine.portfolio.models import FactorBucket
from stock_engine.ui.components.ticker_search import ticker_search_widget
from stock_engine.ui.components.simple_mode.session import (
    get_session, save_session, add_ticker, remove_ticker, set_bucket, next_step,
)
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.ui.theme import (
    CHART_BG, CHART_GRID, CHART_TEXT, CHART_AXIS, CHART_DIVIDER, CHART_AXIS_LABEL,
    MAIN_BG, MAIN_TEXT, SECTION_HEADER,
    FACTOR_GROWTH, FACTOR_FIN_COND, FACTOR_INFLATION,
    FACTOR_DIVERSIFIER, FACTOR_UNASSIGNED,
    TERMINAL_BG, TERMINAL_ROW_SEP,
    CORR_COLORSCALE as _CORR_COLORSCALE,
)

# ── Factor bucket colors (from theme — light variants visible on dark charts) ──
BUCKET_COLOR = {
    FactorBucket.GROWTH:      FACTOR_GROWTH,
    FactorBucket.FIN_COND:    FACTOR_FIN_COND,
    FactorBucket.INFLATION:   FACTOR_INFLATION,
    FactorBucket.DIVERSIFIER: FACTOR_DIVERSIFIER,
    FactorBucket.UNASSIGNED:  FACTOR_UNASSIGNED,
}
BUCKET_BG = {
    k: f"rgba({int(v[1:3],16)},{int(v[3:5],16)},{int(v[5:7],16)},0.07)"
    for k, v in BUCKET_COLOR.items()
}
BUCKET_LABEL = {
    FactorBucket.GROWTH:      "GROWTH",
    FactorBucket.FIN_COND:    "FIN. CONDITIONS",
    FactorBucket.INFLATION:   "INFLATION",
    FactorBucket.DIVERSIFIER: "DIVERSIFIER",
    FactorBucket.UNASSIGNED:  "UNASSIGNED",
}
BUCKET_SHORT = {
    FactorBucket.GROWTH:      "GROWTH",
    FactorBucket.FIN_COND:    "FIN.COND",
    FactorBucket.INFLATION:   "INFL",
    FactorBucket.DIVERSIFIER: "DIVERS",
    FactorBucket.UNASSIGNED:  "UNASGN",
}

_NAMES: dict[str, str] = {
    # ── ETFs — broad market ───────────────────────────────────────────────────
    "SPY":  "S&P 500 ETF",       "QQQ":  "Nasdaq 100 ETF",    "VTI":  "Total Mkt ETF",
    "IWM":  "Russell 2000 ETF",  "DIA":  "Dow Jones ETF",     "VOO":  "Vanguard S&P 500",
    # ── ETFs — international ─────────────────────────────────────────────────
    "EFA":  "MSCI EAFE ETF",     "EEM":  "MSCI EM ETF",       "VEA":  "Dev. Markets ETF",
    "VWO":  "EM ETF",            "IEMG": "Core MSCI EM ETF",  "ACWI": "MSCI ACWI ETF",
    # ── ETFs — fixed income ──────────────────────────────────────────────────
    "TLT":  "20Y Treasury ETF",  "IEF":  "7-10Y Treasury",    "BND":  "Total Bond ETF",
    "LQD":  "IG Corp Bond ETF",  "AGG":  "Agg Bond ETF",      "SHY":  "1-3Y Treasury",
    "GOVT": "US Treasury ETF",   "HYG":  "HY Bond ETF",       "JNK":  "SPDR HY Bond",
    "EMB":  "EM Bond ETF",       "MBB":  "MBS ETF",           "BNDX": "Intl Bond ETF",
    "VCIT": "Vanguard Corp Bond", "VCSH": "Short Corp Bond",
    # ── ETFs — inflation / TIPS ──────────────────────────────────────────────
    "TIPS": "TIPS ETF",          "SCHP": "Schwab TIPS ETF",   "VTIP": "Vanguard TIPS",
    # ── ETFs — commodities / gold ────────────────────────────────────────────
    "GLD":  "SPDR Gold ETF",     "IAU":  "iShares Gold ETF",  "GDX":  "Gold Miners ETF",
    "SLV":  "iShares Silver",    "USO":  "Oil Fund ETF",      "DBO":  "DB Oil ETF",
    "XLE":  "Energy ETF",        "PDBC": "Inv. Comm. ETF",    "DJP":  "Commodity Index",
    # ── ETFs — sector ────────────────────────────────────────────────────────
    "XLF":  "Financials ETF",    "XLP":  "Staples ETF",       "XLV":  "Health ETF",
    "XLK":  "Technology ETF",    "XLI":  "Industrials ETF",   "XLB":  "Materials ETF",
    "XLU":  "Utilities ETF",     "XLRE": "Real Estate ETF",   "XLC":  "Comm. Svcs ETF",
    "SOXX": "Semis ETF",
    # ── ETFs — real estate ───────────────────────────────────────────────────
    "VNQ":  "REIT ETF",          "IYR":  "Real Estate ETF",   "KBE":  "Bank ETF",
    "VFH":  "Fin. ETF",
    # ── Large-cap US equities ────────────────────────────────────────────────
    "AAPL": "Apple",             "MSFT": "Microsoft",         "NVDA": "NVIDIA",
    "AMZN": "Amazon",            "GOOGL": "Alphabet",         "META": "Meta Platforms",
    "TSLA": "Tesla",             "AVGO": "Broadcom",          "TSM":  "Taiwan Semi.",
    "AMD":  "AMD",               "INTC": "Intel",             "QCOM": "Qualcomm",
    "MU":   "Micron Technology", "ASML": "ASML Holding",
    "ADBE": "Adobe",             "CRM":  "Salesforce",        "ORCL": "Oracle",
    "IBM":  "IBM",               "NFLX": "Netflix",           "DIS":  "Walt Disney",
    "JPM":  "JPMorgan Chase",    "BAC":  "Bank of America",   "GS":   "Goldman Sachs",
    "MS":   "Morgan Stanley",    "C":    "Citigroup",         "WFC":  "Wells Fargo",
    "V":    "Visa",              "MA":   "Mastercard",        "AXP":  "American Express",
    "UNH":  "UnitedHealth",      "LLY":  "Eli Lilly",         "JNJ":  "Johnson & Johnson",
    "PFE":  "Pfizer",            "ABBV": "AbbVie",            "MRK":  "Merck",
    "XOM":  "ExxonMobil",        "CVX":  "Chevron",           "COP":  "ConocoPhillips",
    "KO":   "Coca-Cola",         "PG":   "Procter & Gamble",  "WMT":  "Walmart",
    "COST": "Costco",            "TGT":  "Target",            "HD":   "Home Depot",
    "MCD":  "McDonald's",        "SBUX": "Starbucks",         "NKE":  "Nike",
    "CAT":  "Caterpillar",       "DE":   "Deere & Co.",       "BA":   "Boeing",
    "LMT":  "Lockheed Martin",   "RTX":  "Raytheon Tech.",    "GE":   "GE",
    "HON":  "Honeywell",         "MMM":  "3M",                "AA":   "Alcoa",
    "T":    "AT&T",              "VZ":   "Verizon",           "CMCSA": "Comcast",
    "NEE":  "NextEra Energy",    "DUK":  "Duke Energy",       "SO":   "Southern Company",
    "AMT":  "American Tower",    "PLD":  "Prologis",          "O":    "Realty Income",
    "F":    "Ford Motor",        "GM":   "General Motors",
}

# _AW removed — betas now computed live via analytics/aw_beta.py
# Fallback hardcoded values live in aw_beta._FALLBACK

_BUCKET_ORDER = [
    FactorBucket.GROWTH, FactorBucket.FIN_COND,
    FactorBucket.INFLATION, FactorBucket.DIVERSIFIER,
]

# ── Layout constants — hardcoded, never change ─────────────────────────────────
_ROW_H    = 36    # px per ticker row
_N_ROWS   = 10    # always exactly 10 rows rendered
_LIST_H   = _N_ROWS * _ROW_H   # 360px fixed
_CORR_H   = 400   # correlation heatmap height (sized so module bottom aligns with AW map)
_MAP_H    = 430   # All-Weather Map height
# _BUCKET_H is sized so that the bottom of the All-Weather Map aligns with the
# bottom of the Correlation Heatmap.  Left-column total ≈ 914px; right-column
# overhead (spacer 8 + AW-header 26 + chart 430 + gaps 16) = 480px, so the
# bucket panel must fill the remaining 914 - 480 = 434px → rounded to 440px.
_BUCKET_H = 440   # factor buckets panel (fills space above All-Weather Map)

_BBG_WARN = "rgba(217,119,6,0.75)"   # warning annotation (amber)

# Per-quadrant palette — light variants at 0.25 opacity, legible on dark chart bg.
# Same colors echo the factor bucket assignment for visual consistency.
# (fill_rgba, label_color from theme)
_QUAD_PALETTE = {
    FactorBucket.GROWTH:      ("rgba(74,222,128,0.08)",  FACTOR_GROWTH),
    FactorBucket.FIN_COND:    ("rgba(55,138,221,0.08)",  FACTOR_FIN_COND),
    FactorBucket.INFLATION:   ("rgba(251,146,60,0.08)",  FACTOR_INFLATION),
    FactorBucket.DIVERSIFIER: ("rgba(192,132,252,0.08)", FACTOR_DIVERSIFIER),
}
_AW_QUAD_PALETTE = {
    "STAGFLATION": ("rgba(251,146,60,0.08)",  FACTOR_INFLATION),
    "GOLDILOCKS":  ("rgba(74,222,128,0.08)",  FACTOR_GROWTH),
    "RECESSION":   ("rgba(55,138,221,0.08)",  FACTOR_FIN_COND),
    "EXPANSION":   ("rgba(192,132,252,0.08)", FACTOR_DIVERSIFIER),
}
# _CORR_COLORSCALE imported from ui/theme.py

# ── Search widget key ──────────────────────────────────────────────────────────
_SEARCH_KEY = "p1_search"


def _dismiss_search() -> None:
    """Close search dropdown without clearing query. Call before any non-search rerun."""
    st.session_state[f"{_SEARCH_KEY}_open"] = False


def _hex_alpha(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Global CSS ─────────────────────────────────────────────────────────────────


# ── Page entry ─────────────────────────────────────────────────────────────────

def render_page1(config: Config) -> None:
    _inject_css("page1_universe")
    sess = get_session()

    tab_universe, tab_news = st.tabs(["Universe", "News"])

    with tab_universe:
        col_left, col_right = st.columns([2.1, 3.7], gap="medium")

        with col_left:
            _render_universe_panel(sess)
            st.markdown('<div class="p1-spacer-sm"></div>', unsafe_allow_html=True)
            _render_corr_heatmap(sess, config)

        with col_right:
            _render_factor_buckets(sess)
            st.markdown('<div class="p1-spacer-sm"></div>', unsafe_allow_html=True)
            _render_allweather_map(sess, config)

    with tab_news:
        from stock_engine.ui.components.simple_mode.page1_news import render_news_tab
        render_news_tab()

    st.markdown(
        '<div style="height:1px;background:var(--border);margin:8px 0"></div>',
        unsafe_allow_html=True,
    )
    _render_bottom_bar(sess)


# ── Universe panel ─────────────────────────────────────────────────────────────

def _render_universe_panel(sess) -> None:
    n = len(sess.universe.tickers)
    st.markdown(
        f'<div class="p1-sec">'
        f'<span>UNIVERSE</span>'
        f'<span style="color:var(--theme-purple);font-size:10px;letter-spacing:0">'
        f'{n} / {_N_ROWS}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Floating search — dropdown never affects layout (position:fixed)
    selected = ticker_search_widget(
        key=_SEARCH_KEY,
        existing_tickers=sess.universe.tickers,
        label="Add ticker…",
    )
    if selected:
        add_ticker(sess, selected)
        st.rerun()

    # Column header — 5-col: # 28px | ticker 80px | name flex | bucket 160px | del 40px
    st.markdown(
        '<div class="p1-th">'
        '<span>#</span>'
        '<span>TICKER</span>'
        '<span>NAME</span>'
        '<span>BUCKET</span>'
        '<span></span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Fixed 360px container — always 10 rows, never expands ────────────────
    n_tickers = len(sess.universe.tickers)
    n_empty   = max(0, _N_ROWS - n_tickers)

    with st.container(height=_LIST_H, border=False, key="p1_ticker_list"):
        for i, ticker in enumerate(list(sess.universe.tickers), 1):
            _render_ticker_row(sess, ticker, i)

        # Blank placeholder rows — same height as real rows, dark bg
        if n_empty > 0:
            placeholder_html = '<div class="p1-empty-row"></div>' * n_empty
            st.markdown(placeholder_html, unsafe_allow_html=True)


def _render_ticker_row(sess, ticker: str, row_num: int = 0) -> None:
    """5-column row: #(28px) | ticker(80px) | name(flex) | bucket(160px) | delete(40px).
    st.columns ratios are neutral placeholders — CSS nth-child enforces px widths.
    """
    meta   = sess.universe.assets.get(ticker)
    bucket = meta.factor_bucket if meta else FactorBucket.UNASSIGNED
    color  = BUCKET_COLOR[bucket]
    name   = _NAMES.get(ticker, "")

    c_num, c_sym, c_name, c_bucket, c_del = st.columns([1, 1, 1, 1, 1], gap="small")

    with c_num:
        st.markdown(
            f'<div class="p1-row-num">{row_num}</div>',
            unsafe_allow_html=True,
        )

    with c_sym:
        st.markdown(
            f'<div class="p1-row-sym-wrap">'
            f'<div style="width:5px;height:5px;flex-shrink:0;border-radius:1px;'
            f'background:{color}"></div>'
            f'<span class="p1-row-sym">{ticker}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c_name:
        title_attr = f'title="{name}"' if name else ""
        display = name if name else '<span class="p1-row-empty-name">—</span>'
        st.markdown(
            f'<div {title_attr} class="p1-row-name">{display}</div>',
            unsafe_allow_html=True,
        )
    with c_bucket:
        opts    = list(FactorBucket)
        idx     = opts.index(bucket)
        new_idx = st.selectbox(
            "", range(len(opts)), index=idx,
            format_func=lambda i: BUCKET_SHORT[opts[i]],
            key=f"p1_bkt_{ticker}",
            label_visibility="collapsed",
        )
        if opts[new_idx] != bucket:
            _dismiss_search()
            set_bucket(sess, ticker, opts[new_idx])
            st.rerun()
    with c_del:
        if st.button("×", key=f"p1_del_{ticker}", help=f"Remove {ticker}"):
            _dismiss_search()
            remove_ticker(sess, ticker)
            st.rerun()


# ── Factor Buckets — quadrant Plotly chart ────────────────────────────────────

# Quadrant grid: (col, row) in a 2 × 2 space.
# col=0 → left, col=1 → right; row=0 → bottom, row=1 → top.
_QUAD_POS = {
    FactorBucket.GROWTH:      (0, 1),   # top-left
    FactorBucket.FIN_COND:    (1, 1),   # top-right
    FactorBucket.INFLATION:   (0, 0),   # bottom-left
    FactorBucket.DIVERSIFIER: (1, 0),   # bottom-right
}
_MAX_PER_ROW = 3   # max ticker chips per row inside a quadrant cell


def _render_factor_buckets(sess) -> None:
    """2 × 2 quadrant Plotly chart, one cell per factor bucket.
    Chart height = _BUCKET_H − 30px (section header overhead) so the total
    section height matches _BUCKET_H and bottom-aligns with the Corr Heatmap.
    """
    st.markdown('<div class="p1-sec"><span>FACTOR BUCKETS</span></div>',
                unsafe_allow_html=True)

    universe = sess.universe
    fig      = go.Figure()

    # ── Quadrant backgrounds ───────────────────────────────────────────────
    for bucket, (cx, cy) in _QUAD_POS.items():
        q_fill, q_color = _QUAD_PALETTE[bucket]
        fig.add_shape(
            type="rect",
            x0=cx, x1=cx + 1, y0=cy, y1=cy + 1,
            fillcolor=q_fill,
            line=dict(width=0),
            layer="below",
        )
        assets = universe.by_bucket(bucket)
        count = len(assets)
        fig.add_annotation(
            x=cx + 0.05, y=cy + 0.96,
            text=f"{BUCKET_SHORT[bucket]}  ·  {count}",
            showarrow=False,
            xanchor="left", yanchor="top",
            font=dict(size=9, color=q_color, family="monospace"),
        )

    # ── Solid divider lines ────────────────────────────────────────────────
    for kwargs in [
        dict(x0=0, x1=2, y0=1, y1=1),   # horizontal
        dict(x0=1, x1=1, y0=0, y1=2),   # vertical
    ]:
        fig.add_shape(type="line", **kwargs,
                      line=dict(color=CHART_DIVIDER, width=1))

    # ── Ticker markers ─────────────────────────────────────────────────────
    for bucket, (cx, cy) in _QUAD_POS.items():
        assets   = universe.by_bucket(bucket)
        _, q_color = _QUAD_PALETTE[bucket]

        if not assets:
            fig.add_annotation(
                x=cx + 0.5, y=cy + 0.50,
                text="NO DATA",
                showarrow=False,
                xanchor="center", yanchor="middle",
                font=dict(size=9, color=CHART_AXIS, family="monospace"),
            )
            continue

        n      = len(assets)
        n_cols = min(n, _MAX_PER_ROW)
        n_rows = (n + _MAX_PER_ROW - 1) // _MAX_PER_ROW

        # Content area: leave top 22 % for the label, 4 % bottom padding
        pad_top  = 0.24
        pad_side = 0.08
        cell_w   = (1.0 - 2 * pad_side) / n_cols
        cell_h   = (1.0 - pad_top - 0.04) / n_rows

        for i, ticker in enumerate(assets):
            row = i // _MAX_PER_ROW
            col = i %  _MAX_PER_ROW
            tx  = cx + pad_side + (col + 0.5) * cell_w
            ty  = cy + (1 - pad_top) - (row + 0.5) * cell_h

            fig.add_trace(go.Scatter(
                x=[tx], y=[ty],
                mode="markers+text",
                text=[ticker],
                textposition="middle center",
                textfont=dict(size=10, color=CHART_TEXT, family="monospace"),
                marker=dict(
                    size=20,
                    color=CHART_BG,
                    line=dict(width=1.8, color=q_color),
                    symbol="circle",
                ),
                hovertemplate=(
                    f"<b>{ticker}</b><br>"
                    f"{BUCKET_LABEL[bucket]}<extra></extra>"
                ),
                showlegend=False,
            ))

    chart_h = _BUCKET_H - 30   # section header (~30px) already rendered above

    fig.update_layout(
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin=dict(l=8, r=8, t=8, b=8),
        height=chart_h,
        xaxis=dict(range=[-0.08, 2.08], visible=False,
                   showgrid=False, fixedrange=True),
        yaxis=dict(range=[-0.08, 2.08], visible=False,
                   showgrid=False, fixedrange=True),
        showlegend=False,
        dragmode=False,
    )

    st.markdown('<div class="p1-chart">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, key="p1_buckets",
                    config=dict(displayModeBar=False))
    st.markdown('</div>', unsafe_allow_html=True)


# ── Correlation Heatmap ────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_corr(
    tickers: tuple[str, ...],
    start: str,
    end: str,
    price_field: str,
    _cache_key: str,
) -> Optional[pd.DataFrame]:
    try:
        from stock_engine.config import Config as _C
        cfg = _C()
        cfg.price_field = price_field
        provider = YFinanceProvider(cfg)
        price_data: dict = {}
        for t in tickers:
            try:
                df  = provider.fetch_historical(t, start, end, "1d")
                col = price_field.lower()
                if col not in df.columns:
                    col = "close"
                price_data[t] = df[col].dropna()
            except Exception:
                pass
        if len(price_data) < 2:
            return None
        prices = pd.DataFrame(price_data).dropna()
        return prices.pct_change().dropna().corr()
    except Exception:
        return None


def _corr_placeholder_html(h: int) -> str:
    """STATA-styled empty state for the correlation heatmap.

    Two-pane layout: monospaced 'Results' log (left) + 'Properties' panel (right).
    Caller substitutes the {msg} field via str.format(msg=...).
    All styling lives in page1_universe.css (.p1-corr-ph-* classes).
    """
    return (
        f'<div class="p1-chart p1-corr-ph" style="height:{h}px">'
        f'<div class="p1-corr-ph-bar">'
        f'<span>Results</span>'
        f'<span class="p1-corr-ph-bar-idle">— idle —</span>'
        f'</div>'
        f'<div class="p1-corr-ph-body">'
        f'<div class="p1-corr-ph-log">'
        f'<span class="p1-corr-ph-log-prompt">.</span> correlate '
        f'<span class="p1-corr-ph-log-pending">&lt;pending&gt;</span>'
        f'<div class="p1-corr-ph-log-gap"></div>'
        f'<div><span class="p1-corr-ph-log-key">status   : </span>'
        f'<span class="p1-corr-ph-log-val">{{msg}}</span></div>'
        f'<div><span class="p1-corr-ph-log-key">required : </span>&ge; 2 tickers</div>'
        f'<div><span class="p1-corr-ph-log-key">window   : </span>6 months (default)</div>'
        f'<div><span class="p1-corr-ph-log-key">method   : </span>Pearson, daily returns</div>'
        f'<div><span class="p1-corr-ph-log-key">range    : </span>[-1.00, +1.00]</div>'
        f'<div class="p1-corr-ph-log-gap"></div>'
        f'<span class="p1-corr-ph-log-prompt">.</span> '
        f'<span class="p1-corr-ph-log-key">_</span>'
        f'</div>'
        f'<div class="p1-corr-ph-props">'
        f'<div class="p1-corr-ph-props-hdr">Properties</div>'
        f'<div class="p1-corr-ph-props-body">'
        f'<div><div class="p1-corr-ph-prop-key">name</div>'
        f'<div class="p1-corr-ph-prop-val">corr_matrix</div></div>'
        f'<div><div class="p1-corr-ph-prop-key">type</div>'
        f'<div>heatmap</div></div>'
        f'<div><div class="p1-corr-ph-prop-key">cells</div>'
        f'<div>&mdash; &times; &mdash;</div></div>'
        f'<div><div class="p1-corr-ph-prop-key">scale</div>'
        f'<div>navy &rarr; purple</div></div>'
        f'</div></div>'
        f'</div></div>'
    )


def _render_corr_heatmap(sess, config: Config) -> None:
    with st.container(key="p1_corr_mod", border=False):
        _render_corr_heatmap_body(sess, config)


def _render_corr_heatmap_body(sess, config: Config) -> None:
    st.markdown('<div class="p1-sec"><span>CORRELATION · PRE-PURCHASE</span></div>',
                unsafe_allow_html=True)

    tickers  = tuple(sess.universe.tickers)
    purchase = sess.universe.purchase_date
    bt_start = sess.universe.backtest_start

    _ph = _corr_placeholder_html(_CORR_H)

    if len(tickers) < 2:
        st.markdown(_ph.format(msg="Add ≥ 2 tickers to compute"),
                    unsafe_allow_html=True)
        return
    if not purchase or not bt_start:
        st.markdown(_ph.format(msg="Set dates in sidebar"), unsafe_allow_html=True)
        return

    lb_col, _ = st.columns([1.1, 2])
    with lb_col:
        st.markdown('<div class="p1-corr-lb-selector">', unsafe_allow_html=True)
        lookback = st.selectbox(
            "", ["3M", "6M", "12M"], index=1,
            key="p1_corr_lb", label_visibility="collapsed",
        )
        st.markdown('</div>', unsafe_allow_html=True)
    days_map = {"3M": 90, "6M": 180, "12M": 365}
    end_ts   = pd.Timestamp(purchase)
    start_ts = end_ts - pd.Timedelta(days=days_map[lookback])

    with st.spinner(""):
        corr = _fetch_corr(
            tickers,
            start_ts.strftime("%Y-%m-%d"),
            end_ts.strftime("%Y-%m-%d"),
            config.price_field,
            f"{start_ts.date()}:{end_ts.date()}",
        )

    if corr is None or corr.empty:
        st.markdown(_ph.format(msg="Not enough price history"),
                    unsafe_allow_html=True)
        return

    n         = len(corr)
    cell_font = max(7, min(10, 68 // n))

    fig = go.Figure(data=go.Heatmap(
        z=corr.values,
        x=list(corr.columns),
        y=list(corr.index),
        colorscale=_CORR_COLORSCALE,
        zmin=-1, zmax=1,
        opacity=0.8,
        text=[[f"{v:.2f}" for v in row] for row in corr.values],
        texttemplate="%{text}",
        textfont=dict(size=cell_font, color=MAIN_TEXT),
        hovertemplate="%{y} × %{x}<br>r = %{z:.3f}<extra></extra>",
        showscale=False,
    ))
    fig.update_layout(
        paper_bgcolor=MAIN_BG,
        plot_bgcolor=MAIN_BG,
        margin=dict(l=52, r=4, t=4, b=52),
        height=_CORR_H,
        xaxis=dict(
            tickfont=dict(color=CHART_AXIS, size=8.5, family="monospace"),
            showgrid=False, side="bottom",
            tickangle=-30 if n > 6 else 0,
        ),
        yaxis=dict(
            tickfont=dict(color=CHART_AXIS, size=8.5, family="monospace"),
            showgrid=False,
            scaleanchor="x",
            scaleratio=1,
            constrain="domain",
        ),
    )
    st.markdown('<div class="p1-chart">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, key="p1_corr",
                    config=dict(displayModeBar=False))
    st.markdown('</div>', unsafe_allow_html=True)


# ── All-Weather Map ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_aw_betas(
    tickers: tuple,
    fred_api_key: str,
    price_field: str,
    start: str,
    end: str,
) -> dict:
    from stock_engine.analytics.aw_beta import compute_aw_betas
    from stock_engine.config import Config as _C
    from stock_engine.data.yfinance_provider import YFinanceProvider
    cfg = _C()
    cfg.price_field = price_field
    provider = YFinanceProvider(cfg)
    return compute_aw_betas(list(tickers), fred_api_key or None, provider, start, end)


def _render_allweather_map(sess, config) -> None:
    fred_key_early = (st.session_state.get("fred_api_key", "")
                      or __import__("os").environ.get("FRED_API_KEY", ""))
    _aw_mode_lbl = "OLS-FRED" if fred_key_early else "Fallback"
    st.markdown(
        f'<div class="p1-sec">'
        f'<span>ALL-WEATHER MAP</span>'
        f'<span style="color:var(--text-mute);font-size:9px">{_aw_mode_lbl}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    universe = sess.universe
    tickers  = universe.tickers
    fig      = go.Figure()

    fred_key = st.session_state.get("fred_api_key", "") or ""
    bt_start = str(universe.backtest_start or "2015-01-01")
    bt_end   = str(universe.purchase_date  or "2024-12-31")
    betas: dict = {}
    if tickers:
        with st.spinner("Computing All-Weather betas..."):
            betas = _cached_aw_betas(
                tuple(tickers), fred_key,
                getattr(config, "price_field", "close"),
                bt_start, bt_end,
            )

    # betas is now (β_growth, β_inflation, r_squared) 3-tuple
    all_vals = list(betas.values())
    max_g = max((abs(v[0]) for v in all_vals), default=1.0) or 1.0
    max_i = max((abs(v[1]) for v in all_vals), default=1.0) or 1.0
    norm = {t: (v[0] / max_g, v[1] / max_i) for t, v in betas.items()}

    _QUADS = [
        (-1,  0,  0,  1, "STAGFLATION", -0.5,  0.5),
        ( 0,  1,  0,  1, "GOLDILOCKS",   0.5,  0.5),
        (-1,  0, -1,  0, "RECESSION",   -0.5, -0.5),
        ( 0,  1, -1,  0, "EXPANSION",    0.5, -0.5),
    ]
    for x0, x1, y0, y1, qname, cx, cy in _QUADS:
        q_fill, q_label = _AW_QUAD_PALETTE[qname]
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=q_fill, line=dict(width=0), layer="below")
        fig.add_annotation(
            x=cx * 1.44, y=cy * 1.60,
            text=qname,
            showarrow=False,
            font=dict(size=9, color=q_label, family="monospace"),
            xanchor="center", yanchor="middle",
        )

    qcounts = {q: 0 for q in ["STAGFLATION", "GOLDILOCKS", "RECESSION", "EXPANSION"]}
    for t in tickers:
        gx, gy = norm.get(t, (0.0, 0.0))
        if   gx < 0 and gy > 0: qcounts["STAGFLATION"] += 1
        elif gx > 0 and gy > 0: qcounts["GOLDILOCKS"]  += 1
        elif gx < 0 and gy < 0: qcounts["RECESSION"]   += 1
        else:                    qcounts["EXPANSION"]   += 1

    _WARN_XY = {
        "STAGFLATION": (-0.50,  0.52),
        "GOLDILOCKS":  ( 0.50,  0.52),
        "RECESSION":   (-0.50, -0.52),
        "EXPANSION":   ( 0.50, -0.52),
    }
    for qname, cnt in qcounts.items():
        if cnt == 0 and len(tickers) >= 3:
            wx, wy = _WARN_XY[qname]
            fig.add_annotation(
                x=wx, y=wy, text="NO DATA",
                showarrow=False, xanchor="center",
                font=dict(size=8, color=_BBG_WARN, family="monospace"),
            )

    # Inline constants — avoids sys.modules caching issues with aw_beta
    _R2_LOW   = 0.05
    _CIDX_MAP = {
        "HK": "^HSI",    "JP": "^N225",   "GB": "^FTSE",
        "CN": "CSI300",  "FR": "^FCHI",   "DE": "^GDAXI",
        "AU": "^AXJO",   "CA": "^GSPTSE", "KR": "^KS11",
        "IN": "^BSESN",  "TW": "^TWII",   "SG": "^STI",
    }
    _SFXMAP = {
        "HK":"HK","T":"JP","L":"GB","SS":"CN","SZ":"CN","PA":"FR",
        "DE":"DE","AX":"AU","TO":"CA","KS":"KR","BO":"IN","NS":"IN",
        "TW":"TW","TWO":"TW","SI":"SG",
    }

    def _ctry(t: str) -> str:
        if "." not in t:
            return "US"
        return _SFXMAP.get(t.rsplit(".", 1)[1].upper(), "US")

    for ticker in tickers:
        gx, gy              = norm.get(ticker, (0.0, 0.0))
        bg_raw, bi_raw, r2  = betas.get(ticker, (0.0, 0.0, 0.0))
        meta                = universe.assets.get(ticker)
        bucket              = meta.factor_bucket if meta else FactorBucket.UNASSIGNED
        lbl                 = BUCKET_SHORT[bucket]
        _, q_color          = _QUAD_PALETTE.get(bucket, ("", SECTION_HEADER))
        low_fit             = r2 < _R2_LOW and fred_key

        country = _ctry(ticker)
        if country == "US":
            method = "OLS-FRED" if fred_key else "Fallback"
        else:
            idx = _CIDX_MAP.get(country, country)
            method = ("OLS-" + idx) if fred_key else "Fallback"

        hover = (
            "<b>" + ticker + "</b>"
            + (" ⚠ low fit" if low_fit else "") + "<br>"
            + "β_growth: " + f"{bg_raw:+.3f}"
            + "  β_infl: " + f"{bi_raw:+.3f}"
            + "  R²: " + f"{r2:.2f}" + "<br>"
            + "Bucket: " + lbl + "  · " + method
            + "<extra></extra>"
        )

        # Low-fit ticker styling lives on `marker.opacity` and the "⚠" text suffix; Plotly markers do not support dashed outlines.
        fig.add_trace(go.Scatter(
            x=[gx], y=[gy],
            mode="markers+text",
            text=[ticker + ("⚠" if low_fit else "")],
            textposition="middle center",
            textfont=dict(
                size=8,
                color=CHART_TEXT,
                family="monospace",
            ),
            marker=dict(
                size=16,
                color=CHART_BG,
                line=dict(width=1.8, color=q_color),
                symbol="circle",
                opacity=0.6 if low_fit else 1.0,
            ),
            hovertemplate=hover,
            showlegend=False,
        ))

    _tick_cfg = dict(
        color=CHART_AXIS_LABEL, size=8, family="monospace",
    )
    _ax_title = dict(font=dict(size=9, color=CHART_AXIS_LABEL, family="monospace"))
    axis_cfg = dict(
        range=[-1.15, 1.15],
        zeroline=True, zerolinecolor=CHART_DIVIDER, zerolinewidth=1,
        showgrid=True, gridcolor=CHART_GRID, gridwidth=1,
        showticklabels=True, nticks=5, tickformat=".1f",
        tickfont=_tick_cfg, showline=False,
    )
    fig.update_layout(
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin=dict(l=48, r=16, t=8, b=40),
        height=_MAP_H,
        xaxis=dict(**axis_cfg,
                   title=dict(text="GROWTH BETA", **_ax_title)),
        yaxis=dict(**axis_cfg,
                   title=dict(text="INFLATION BETA", **_ax_title)),
        showlegend=False,
    )

    st.markdown('<div class="p1-chart">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, key="p1_aw_map",
                    config=dict(displayModeBar=False))
    st.markdown('</div>', unsafe_allow_html=True)


# ── Bottom bar ─────────────────────────────────────────────────────────────────

def _render_bottom_bar(sess) -> None:
    universe   = sess.universe
    n_total    = len(universe.tickers)
    n_assigned = sum(
        1 for t in universe.tickers
        if universe.assets.get(t) and
        universe.assets[t].factor_bucket != FactorBucket.UNASSIGNED
    )
    unassigned_list = [
        t for t in universe.tickers
        if universe.assets.get(t) and
        universe.assets[t].factor_bucket == FactorBucket.UNASSIGNED
    ]

    col_stats, col_nav = st.columns([5, 2])
    with col_stats:
        parts = [str(n_total) + " ticker" + ("s" if n_total != 1 else "")]
        if n_total:
            parts.append(str(n_assigned) + "/" + str(n_total) + " assigned")
        if unassigned_list:
            ua_str = ", ".join(unassigned_list[:6])
            if len(unassigned_list) > 6:
                ua_str += " +" + str(len(unassigned_list) - 6)
            parts.append("unassigned: " + ua_str)
        st.markdown(
            f'<div class="p1-summary-bar">{"  ·  ".join(parts)}</div>',
            unsafe_allow_html=True,
        )

    with col_nav:
        btn_col, _ = st.columns([3, 1])
        with btn_col:
            if st.button(
                "Next: Allocation ->",
                type="primary",
                disabled=(n_total == 0),
                use_container_width=True,
                key="p1_next",
            ):
                from stock_engine.ui.components.simple_mode.session import next_step
                next_step()
