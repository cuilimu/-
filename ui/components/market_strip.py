"""
ui/components/market_strip.py — Bloomberg-style market ticker strip.

Relocated from home.py during the home redesign so the ticker bar can be
mounted on research/simulation pages where intraday context informs
decisions, instead of on the entry page where it was decorative noise.

Public API:
    render_market_strip()  — renders a 4-card horizontal flex row
                             (auto-injects ui/styles/market_strip.css)
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from stock_engine.ui.styles import inject as _inject_css


# ── Tickers ───────────────────────────────────────────────────────────────────
# ^IRX is the closest free Yahoo proxy for short-end "GT2 Govt"
# (yfinance has no clean 2y series). ^TNX = 10Y Treasury yield.
_MARKET_TICKERS: list[tuple[str, str, str]] = [
    ("^GSPC", "SPX",  "S&P 500"),
    ("^VIX",  "VIX",  "VIX Index"),
    ("^IRX",  "GT2",  "GT2 Govt"),
    ("^TNX",  "GT10", "GT10 Govt"),
]


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_market_snapshot() -> dict[str, dict]:
    """Two-call fetch per ticker: intraday 1-min bars (sparkline + latest tick)
    plus 5-day daily bars (prior close as honest day-change baseline). Falls
    back to 5-min × 5-day if 1-min frame is empty (weekends, off-hours).
    Cached 10 min."""
    import yfinance as yf
    out: dict[str, dict] = {}
    for tk, _label, _name in _MARKET_TICKERS:
        try:
            t = yf.Ticker(tk)
            intra = t.history(period="1d", interval="1m")
            if intra.empty:
                intra = t.history(period="5d", interval="5m")
            daily = t.history(period="5d", interval="1d")

            spark_vals:  list[float] = []
            spark_times: list        = []
            prior: float | None      = None

            if not intra.empty:
                clean       = intra["Close"].dropna()
                spark_vals  = clean.tolist()
                spark_times = list(clean.index)
            if not daily.empty:
                d_clean = daily["Close"].dropna().tolist()
                if not spark_vals and d_clean:
                    spark_vals  = d_clean
                    spark_times = list(daily["Close"].dropna().index)
                if len(d_clean) >= 2:
                    prior = d_clean[-2]
            if not spark_vals:
                out[tk] = {"error": "no data"}
                continue

            current = spark_vals[-1]
            if prior is None:
                prior = spark_vals[0]
            change = current - prior
            pct    = (change / prior * 100.0) if prior else 0.0

            out[tk] = {
                "current":     current,
                "change":      change,
                "pct":         pct,
                "spark":       spark_vals,
                "spark_times": spark_times,
            }
        except Exception as exc:
            out[tk] = {"error": str(exc)[:40]}
    return out


def _sparkline_block(values: list[float], times: list, color: str,
                     w: int = 160, h: int = 28) -> str:
    """Sparkline + axis labels. preserveAspectRatio=none stretches the line
    with card width; axis text sits in absolutely-positioned spans so font
    sizes don't distort with the SVG."""
    if not values or len(values) < 2:
        return '<div class="mt-spark-block"></div>'

    vmin, vmax = min(values), max(values)
    rng = (vmax - vmin) or 1.0
    pts = []
    n = len(values) - 1
    for i, v in enumerate(values):
        x = (i / n) * w
        y = h - ((v - vmin) / rng) * h
        pts.append(f"{x:.1f},{y:.1f}")
    svg = (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" class="mt-spark">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}"'
        f' stroke-width="1.4" vector-effect="non-scaling-stroke"/>'
        f'</svg>'
    )

    def _fmt(v: float) -> str:
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"

    t_start = t_end = ""
    if times:
        try:
            ts0, ts1 = pd.Timestamp(times[0]), pd.Timestamp(times[-1])
            if ts0.date() == ts1.date():
                t_start = ts0.strftime("%H:%M")
                t_end   = ts1.strftime("%H:%M")
            else:
                t_start = ts0.strftime("%m-%d")
                t_end   = ts1.strftime("%m-%d")
        except Exception:
            pass

    return (
        f'<div class="mt-spark-block">'
        f'<span class="mt-y-max">{_fmt(vmax)}</span>'
        f'<span class="mt-y-min">{_fmt(vmin)}</span>'
        f'{svg}'
        f'<div class="mt-x-axis"><span>{t_start}</span><span>{t_end}</span></div>'
        f'</div>'
    )


def _format_value(tk: str, v: float) -> str:
    if tk in ("^IRX", "^TNX", "^VIX"):
        return f"{v:.2f}"
    return f"{v:,.0f}"


def render_market_strip() -> None:
    """Horizontal 4-card ticker bar. Auto-injects ui/styles/market_strip.css."""
    _inject_css("market_strip")
    snapshot = _fetch_market_snapshot()
    cards: list[str] = []
    for tk, label, name in _MARKET_TICKERS:
        d = snapshot.get(tk, {})
        if "error" in d or "current" not in d:
            cards.append(
                f'<div class="mt-card">'
                f'  <div class="mt-row-top">'
                f'    <span class="mt-symbol">{label}</span>'
                f'    <span class="mt-value">—</span>'
                f'  </div>'
                f'  <div class="mt-row-mid">'
                f'    <span class="mt-name">{name}</span>'
                f'  </div>'
                f'  <div class="mt-error">data unavailable</div>'
                f'</div>'
            )
            continue
        up      = d["change"] >= 0
        cls     = "up" if up else "down"
        sign    = "+" if up else ""
        color   = "#00b050" if up else "#e03030"
        spark   = _sparkline_block(d["spark"], d.get("spark_times", []), color)
        suffix  = "%" if tk in ("^IRX", "^TNX") else ""
        cur_txt = _format_value(tk, d["current"]) + suffix
        chg_txt = f"{sign}{d['change']:.2f} ({sign}{d['pct']:.2f}%)"
        cards.append(
            f'<div class="mt-card">'
            f'  <div class="mt-row-top">'
            f'    <span class="mt-symbol">{label}</span>'
            f'    <span class="mt-value">{cur_txt}</span>'
            f'  </div>'
            f'  <div class="mt-row-mid">'
            f'    <span class="mt-name">{name}</span>'
            f'    <span class="mt-delta {cls}">{chg_txt}</span>'
            f'  </div>'
            f'  {spark}'
            f'</div>'
        )
    st.markdown(
        '<div class="market-ticker-bar">' + "".join(cards) + '</div>',
        unsafe_allow_html=True,
    )
