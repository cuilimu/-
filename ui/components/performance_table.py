"""
ui/components/performance_table.py — Multi-period return table renderer.
Positive = green bold, Negative = red bold, None = grey "—".
"""

import pandas as pd
import streamlit as st

from stock_engine.ui.theme import COLOR_GAIN, COLOR_LOSS, MAIN_TEXT_SECONDARY

# Columns that get sign+color treatment
_PCT_COLS   = {"%Chg", "WTD%", "MTD%", "1Mo%", "3Mo%", "YTD%", "12Mo%"}
_PLAIN_COLS = {"Last", "Chg"}   # no color, special formatting


def _fmt_pct(val) -> tuple[str, str]:
    """Returns (display_text, css_color)."""
    if val is None:
        return "—", MAIN_TEXT_SECONDARY
    color = COLOR_GAIN if val >= 0 else COLOR_LOSS
    sign  = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%", color


def _fmt_chg(val) -> str:
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}"


def _fmt_last(val) -> str:
    if val is None:
        return "—"
    return f"${val:.2f}"


def render_multi_period_table(df: pd.DataFrame) -> None:
    """
    Renders the multi-period return table as styled HTML.
    Alternating row bg: white / #fafafa.
    Header: uppercase grey 11px.
    Ticker: bold left-aligned.
    Numeric: right-aligned.
    """
    if df.empty:
        st.info("No data available.")
        return

    col_headers = list(df.columns)

    header_cells = "".join(
        f'<th style="text-align:{"left" if c == "Ticker" else "right"};'
        f'color:#666666;font-size:11px;text-transform:uppercase;'
        f'padding:6px 10px;border-bottom:2px solid #e0e0e0;'
        f'background:#f8f8f8;font-weight:500">{c}</th>'
        for c in col_headers
    )

    rows_html = ""
    for i, row in df.iterrows():
        bg = "#ffffff" if i % 2 == 0 else "#fafafa"
        cells = ""
        for col in col_headers:
            val = row[col]
            if col == "Ticker":
                cells += (
                    f'<td style="font-weight:700;padding:7px 10px;'
                    f'text-align:left;border-bottom:1px solid #f0f0f0">'
                    f'{val}</td>'
                )
            elif col == "Last":
                cells += (
                    f'<td style="padding:7px 10px;text-align:right;'
                    f'border-bottom:1px solid #f0f0f0">'
                    f'{_fmt_last(val)}</td>'
                )
            elif col == "Chg":
                text = _fmt_chg(val)
                color = COLOR_GAIN if (val and val >= 0) else (COLOR_LOSS if val and val < 0 else MAIN_TEXT_SECONDARY)
                cells += (
                    f'<td style="padding:7px 10px;text-align:right;'
                    f'color:{color};border-bottom:1px solid #f0f0f0">'
                    f'{text}</td>'
                )
            elif col in _PCT_COLS:
                text, color = _fmt_pct(val)
                weight = "600" if val is not None else "400"
                cells += (
                    f'<td style="padding:7px 10px;text-align:right;'
                    f'color:{color};font-weight:{weight};'
                    f'border-bottom:1px solid #f0f0f0">'
                    f'{text}</td>'
                )
            else:
                cells += f'<td style="padding:7px 10px">{val}</td>'

        rows_html += (
            f'<tr style="background:{bg}">{cells}</tr>'
        )

    table_html = (
        '<div style="overflow-x:auto">'
        '<table style="width:100%;border-collapse:collapse;font-size:13px">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)
