"""
ui/components/summary_bar.py — Aggregate summary bar (Fix 9: light purple bg, purple border).
Fix 1: HTML built without f-string quote collisions.
"""

import numpy as np
import streamlit as st
from stock_engine.analytics import AnalyticsEngine
from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.ui.theme import COLOR_GAIN, COLOR_LOSS, fmt_ratio


def summary_bar(group_results: dict[str, BacktestResult]) -> None:
    if not group_results:
        return

    total_deployed = 0.0
    total_current = 0.0
    calmar_values: list[float] = []
    _engine = AnalyticsEngine(Config())

    for result in group_results.values():
        total_deployed += result.initial_capital
        if result.snapshots:
            total_current += result.snapshots[-1].nav
        # Compute Calmar from cached summary if available, else derive
        if result.summary and "calmar" in result.summary:
            raw = result.summary["calmar"]
            if raw not in ("N/A", "∞"):
                try:
                    calmar_values.append(float(raw))
                except ValueError:
                    pass
            elif raw == "∞":
                calmar_values.append(float("inf"))
        elif len(result.snapshots) >= 2:
            try:
                m = _engine.compute(result)
                if m.calmar_ratio is not None and not np.isnan(m.calmar_ratio):
                    calmar_values.append(m.calmar_ratio)
            except Exception:
                pass

    pnl = total_current - total_deployed
    pnl_pct = (pnl / total_deployed * 100) if total_deployed > 0 else 0.0
    pnl_color = COLOR_GAIN if pnl >= 0 else COLOR_LOSS
    sign = "+" if pnl >= 0 else ""

    finite_calmars = [v for v in calmar_values if not np.isinf(v)]
    if calmar_values and all(np.isinf(v) for v in calmar_values):
        calmar_avg: float | None = float("inf")
    elif finite_calmars:
        calmar_avg = float(np.mean(finite_calmars))
    else:
        calmar_avg = None
    calmar_text, calmar_color = fmt_ratio(calmar_avg)

    # Fix 1: build HTML string without mixing quote styles inside f-string
    pnl_html = (
        '<span style="color:' + pnl_color + ';font-weight:600">'
        + sign + "$" + f"{pnl:,.0f}"
        + " (" + sign + f"{pnl_pct:.1f}" + "%)"
        + "</span>"
    )
    calmar_html = '<span style="color:' + calmar_color + ';font-weight:600">' + calmar_text + "</span>"
    html = (
        '<div class="summary-bar">'
        "<span><strong>Total Deployed:</strong> $" + f"{total_deployed:,.0f}" + "</span>"
        "<span><strong>Total Value:</strong> $" + f"{total_current:,.0f}" + "</span>"
        "<span><strong>Overall P&amp;L:</strong> " + pnl_html + "</span>"
        '<span title="Annualised Return / Max Drawdown"><strong>Calmar:</strong> ' + calmar_html + "</span>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


