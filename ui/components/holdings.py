"""
ui/components/holdings.py -- Per-ticker allocation input and post-backtest holdings table.
Fix 1: all HTML triple-quoted, no f-string quote collisions.
Fix 2: P&L = (end_price - cost_basis) * shares -- two different dates.
"""

import math
from typing import Optional

import pandas as pd
import streamlit as st

from stock_engine.portfolio.models import PortfolioSnapshot, TickerAllocation
from stock_engine.portfolio.transaction import ClosedPosition
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.ui.theme import (
    COLOR_GAIN, COLOR_LOSS, COLOR_NEUTRAL,
    CARD_BG, CARD_BORDER, MAIN_TEXT, MAIN_TEXT_SECONDARY,
)

LOT_SIZE = 100


def allocation_table(
    allocations: list[TickerAllocation],
    price_field: str,
    start_prices: dict[str, float],
    total_capital: float,
    key_prefix: str,
) -> tuple[list[TickerAllocation], list[str]]:
    """
    Bloomberg-style position entry grid.
    Columns: #  |  SECURITY  |  ALLOCATION ($)  |  PRICE  |  SHARES  |  MKT VALUE  |  WEIGHT  |  RM
    """
    _inject_css("holdings")

    to_remove: list[str] = []
    updated:   list[TickerAllocation] = []

    # Header — original bbg-wrap structure; grid-template-columns now use fr units
    # (matching the st.columns ratios below) instead of fixed pixels.
    group_html = (
        '<div class="bbg-wrap">'
        '<div class="bbg-thead-grp">'
        '<span class="bbg-th">&nbsp;</span>'
        '<span class="bbg-th">&nbsp;</span>'
        '<span class="bbg-th">PLANNED ALLOCATION</span>'
        '<span class="bbg-th r">MARKET PRICE</span>'
        '<span class="bbg-th r">SHARES</span>'
        '<span class="bbg-th r">MKT VALUE</span>'
        '<span class="bbg-th r">WEIGHT</span>'
        '<span class="bbg-th">&nbsp;</span>'
        '</div>'
        '<div class="bbg-thead">'
        '<span class="bbg-th">#</span>'
        '<span class="bbg-th">SECURITY</span>'
        '<span class="bbg-th">ALLOCATION (USD)</span>'
        '<span class="bbg-th r">PRICE</span>'
        '<span class="bbg-th r">SHARES</span>'
        '<span class="bbg-th r">MKT VALUE</span>'
        '<span class="bbg-th r">WEIGHT %</span>'
        '<span class="bbg-th"></span>'
        '</div>'
    )
    st.markdown(group_html, unsafe_allow_html=True)

    # Per-ticker rows
    total_allocated = sum(a.allocated_dollars for a in allocations)
    total_mkt_val   = 0.0
    total_deployed  = 0.0

    for idx, alloc in enumerate(allocations, 1):
        price = start_prices.get(alloc.ticker, 0.0)

        c_num, c_tick, c_input, c_price, c_sh, c_mv, c_wt, c_rm = st.columns(
            [0.4, 1.1, 2.0, 1.0, 1.0, 1.2, 0.8, 0.35],
            vertical_alignment="center",
        )

        with c_num:
            st.markdown(f'<div class="bbg-num">{idx})</div>', unsafe_allow_html=True)

        with c_tick:
            st.markdown(
                f'<div class="bbg-ticker">{alloc.ticker}</div>'
                f'<div class="bbg-sub">{price_field}</div>',
                unsafe_allow_html=True,
            )

        with c_input:
            new_dollars = st.number_input(
                "",
                min_value=0.0,
                value=float(alloc.allocated_dollars),
                step=1000.0,
                format="%.0f",
                key=f"{key_prefix}_dollars_{alloc.ticker}",
                label_visibility="collapsed",
            )
            alloc.allocated_dollars = new_dollars

        with c_price:
            if price > 0:
                st.markdown(
                    f'<div class="bbg-val">&#36;{price:,.2f}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('<div class="bbg-warn">N/A</div>', unsafe_allow_html=True)

        with c_sh:
            if price > 0 and new_dollars > 0:
                shares = math.floor(new_dollars / price)
                deployed = shares * price
                total_deployed += deployed
                total_mkt_val  += deployed
                returned = new_dollars - deployed
                weight = new_dollars / total_capital * 100 if total_capital > 0 else 0.0
                st.markdown(
                    f'<div class="bbg-val">{shares:,}</div>'
                    + (f'<div class="bbg-warn">+&#36;{returned:,.0f} returned</div>'
                       if returned > 0.5 else ''),
                    unsafe_allow_html=True,
                )
            else:
                shares, deployed, returned = 0, 0.0, 0.0
                weight = 0.0
                st.markdown('<div class="bbg-val">—</div>', unsafe_allow_html=True)

        with c_mv:
            mkt = shares * price if price > 0 else 0.0
            st.markdown(
                f'<div class="bbg-val">&#36;{mkt:,.0f}</div>' if mkt > 0
                else '<div class="bbg-val">—</div>',
                unsafe_allow_html=True,
            )

        with c_wt:
            w = new_dollars / total_capital * 100 if total_capital > 0 else 0.0
            st.markdown(
                f'<div class="bbg-wt">{w:.1f}%</div>',
                unsafe_allow_html=True,
            )

        with c_rm:
            if st.button("✕", key=f"{key_prefix}_rm_{alloc.ticker}",
                         help=f"Remove {alloc.ticker}"):
                to_remove.append(alloc.ticker)
                continue

        updated.append(alloc)

    # Totals row
    total_allocated_updated = sum(a.allocated_dollars for a in updated)
    total_returned = total_allocated_updated - total_deployed
    cash_balance   = total_capital - total_deployed
    rem_color = "#00b050" if cash_balance >= 0 else "#cc0000"

    tot_c1, tot_c2, tot_c3, tot_c4 = st.columns([0.4+1.1, 2.0, 1.0+1.0+1.2+0.8+0.35, 0.01])
    with tot_c1:
        st.markdown(
            '<div style="font-size:11px;font-weight:700;color:#660874;padding:6px 4px">TOTALS</div>',
            unsafe_allow_html=True,
        )
    with tot_c2:
        st.markdown(
            f'<div style="font-size:12px;font-weight:700;color:#1a1a1a;padding:4px 2px">'
            f'&#36;{total_allocated_updated:,.0f}</div>'
            f'<div style="font-size:10px;color:#888">of &#36;{total_capital:,.0f} capital</div>',
            unsafe_allow_html=True,
        )
    with tot_c3:
        st.markdown(
            f'<div style="font-size:11px;line-height:1.8">'
            f'<span style="color:#888">Deployed: </span>'
            f'<span style="font-weight:700">&#36;{total_deployed:,.0f}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:#888">Returned: </span>'
            f'<span style="font-weight:600;color:#888">&#36;{total_returned:,.2f}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:#888">Cash: </span>'
            f'<span style="font-weight:700;color:{rem_color}">&#36;{cash_balance:,.0f}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)
    return updated, to_remove


def holdings_table(
    snapshot: PortfolioSnapshot,
    end_prices: dict[str, float],
    price_field: str,
    key_prefix: str = "holdings",
    closed_positions: Optional[list] = None,
    initial_capital: float = 0.0,
) -> None:
    """
    Section 1: Open positions (unrealized P&L).
    Section 2: Closed positions from FIFO matching (realized P&L) -- Multi-Date only.
    Summary row: open P&L + realized P&L = total P&L.
    """
    closed_positions = closed_positions or []
    has_open   = bool(snapshot and snapshot.positions)
    has_closed = bool(closed_positions)

    if not has_open and not has_closed:
        st.info("Run backtest to see holdings.")
        return

    # Section 1: Open Positions
    open_pnl_abs = 0.0
    open_cost    = 0.0

    if has_open:
        st.markdown(
            '<div class="section-header">Open Positions</div>',
            unsafe_allow_html=True,
        )
        rows_html = ""
        for ticker, pos in snapshot.positions.items():
            current_price = end_prices.get(ticker, pos.cost_basis)
            market_value  = pos.quantity * current_price
            cost_value    = pos.quantity * pos.cost_basis

            pnl_abs   = market_value - cost_value
            pnl_pct   = (pnl_abs / cost_value * 100) if cost_value > 0 else 0.0
            open_pnl_abs += pnl_abs
            open_cost    += cost_value

            lots      = int(pos.quantity) // LOT_SIZE
            pnl_color = COLOR_GAIN if pnl_abs >= 0 else COLOR_LOSS
            sign      = "+" if pnl_abs >= 0 else ""

            rows_html += (
                "<tr>"
                "<td>"
                '<div class="holdings-ticker">' + ticker + "</div>"
                '<div class="holdings-sub">$' + f"{market_value:,.2f}" + "</div>"
                "</td>"
                "<td>"
                '<div style="color:' + pnl_color + ';font-weight:600">'
                + sign + "$" + f"{pnl_abs:,.2f}" + "</div>"
                '<div style="color:' + pnl_color + ';font-size:12px">'
                + sign + f"{pnl_pct:.1f}" + "%</div>"
                "</td>"
                "<td>"
                "<div>" + f"{int(pos.quantity):,}" + " shares</div>"
                '<div class="holdings-sub">(' + str(lots) + " lot" + ("s" if lots != 1 else "") + ")</div>"
                "</td>"
                "<td>"
                "<div>$" + f"{current_price:,.2f}"
                + ' <span class="holdings-sub">(' + price_field + ")</span></div>"
                '<div class="holdings-sub">cost $'
                + f"{pos.cost_basis:,.2f}"
                + " (" + price_field + ")</div>"
                "</td>"
                "<td><span style='color:#888'>--</span></td>"
                "</tr>"
            )

        table_html = (
            '<table class="holdings-table">'
            "<thead><tr>"
            "<th>Name / Market Value</th>"
            "<th>Unrealized P&amp;L</th>"
            "<th>Shares Held</th>"
            "<th>Price / Cost</th>"
            "<th>Realized P&amp;L</th>"
            "</tr></thead>"
            "<tbody>" + rows_html + "</tbody>"
            "</table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)

    # Section 2: Closed Positions
    realized_pnl_total = 0.0

    if has_closed:
        st.markdown(
            '<div class="section-header" style="margin-top:18px">Closed Positions</div>',
            unsafe_allow_html=True,
        )
        rows_html = ""
        for cp in closed_positions:
            realized_pnl_total += cp.realized_pnl
            pnl_color = COLOR_GAIN if cp.realized_pnl >= 0 else COLOR_LOSS
            pnl_sign  = "+" if cp.realized_pnl >= 0 else ""
            pct_sign  = "+" if cp.realized_pnl_pct >= 0 else ""

            rows_html += (
                "<tr>"
                "<td><div class='holdings-ticker'>" + cp.ticker + "</div></td>"
                "<td><div class='holdings-sub'>" + cp.buy_date + "</div></td>"
                "<td><div class='holdings-sub'>" + cp.sell_date + "</div></td>"
                "<td><div>" + f"{cp.shares:,}" + "</div></td>"
                "<td><div>$" + f"{cp.buy_price:,.2f}" + "</div></td>"
                "<td><div>$" + f"{cp.sell_price:,.2f}" + "</div></td>"
                "<td>"
                '<div style="color:' + pnl_color + ';font-weight:600">'
                + pnl_sign + "$" + f"{cp.realized_pnl:,.2f}" + "</div>"
                "</td>"
                "<td>"
                '<div style="color:' + pnl_color + '">'
                + pct_sign + f"{cp.realized_pnl_pct * 100:.2f}" + "%</div>"
                "</td>"
                "<td><div class='holdings-sub'>" + f"{cp.holding_days}" + "d</div></td>"
                "</tr>"
            )

        table_html = (
            '<table class="holdings-table">'
            "<thead><tr>"
            "<th>Name</th>"
            "<th>Buy Date</th>"
            "<th>Sell Date</th>"
            "<th>Shares</th>"
            "<th>Buy Price</th>"
            "<th>Sell Price</th>"
            "<th>Realized P&amp;L</th>"
            "<th>Return %</th>"
            "<th>Held</th>"
            "</tr></thead>"
            "<tbody>" + rows_html + "</tbody>"
            "</table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)

    # Summary row
    if has_open or has_closed:
        total_pnl     = open_pnl_abs + realized_pnl_total
        total_cost    = open_cost + (initial_capital - open_cost) if initial_capital > 0 else open_cost or 1
        base          = initial_capital if initial_capital > 0 else (open_cost or 1.0)
        total_pct     = total_pnl / base * 100

        open_sign     = "+" if open_pnl_abs >= 0 else ""
        open_color    = COLOR_GAIN if open_pnl_abs >= 0 else COLOR_LOSS
        real_sign     = "+" if realized_pnl_total >= 0 else ""
        real_color    = COLOR_GAIN if realized_pnl_total >= 0 else COLOR_LOSS
        total_sign    = "+" if total_pnl >= 0 else ""
        total_color   = COLOR_GAIN if total_pnl >= 0 else COLOR_LOSS
        open_pct      = (open_pnl_abs / open_cost * 100) if open_cost > 0 else 0.0

        if has_open and has_closed:
            summary_html = (
                '<div style="margin-top:14px;font-size:13px;'
                'border-top:1px solid #e0e0e0;padding-top:10px">'
                '<div style="color:#666;margin-bottom:2px">'
                "<strong>Open P&amp;L:</strong> "
                '<span style="color:' + open_color + ';font-weight:700">'
                + open_sign + "$" + f"{open_pnl_abs:,.2f}"
                + " (" + open_sign + f"{open_pct:.1f}%)" + "</span>"
                "</div>"
                '<div style="color:#666;margin-bottom:2px">'
                "<strong>Realized P&amp;L:</strong> "
                '<span style="color:' + real_color + ';font-weight:700">'
                + real_sign + "$" + f"{realized_pnl_total:,.2f}" + "</span>"
                "</div>"
                '<div style="border-top:1px solid #e0e0e0;padding-top:6px;margin-top:4px">'
                '<span style="color:#660874;font-weight:700">Total P&amp;L:</span> '
                '<span style="color:' + total_color + ';font-weight:700">'
                + total_sign + "$" + f"{total_pnl:,.2f}"
                + " (" + total_sign + f"{total_pct:.1f}%)" + "</span>"
                "</div>"
                "</div>"
            )
        elif has_closed:
            summary_html = (
                '<div style="margin-top:14px;font-size:13px;'
                'border-top:1px solid #e0e0e0;padding-top:10px">'
                '<span style="color:#660874;font-weight:700">Total Realized P&amp;L:</span> '
                '<span style="color:' + total_color + ';font-weight:700">'
                + total_sign + "$" + f"{realized_pnl_total:,.2f}"
                + " (" + total_sign + f"{total_pct:.1f}%)" + "</span>"
                "</div>"
            )
        else:
            summary_html = (
                '<div style="margin-top:14px;font-size:13px;'
                'border-top:1px solid #e0e0e0;padding-top:10px">'
                '<span style="color:#660874;font-weight:700">Open P&amp;L:</span> '
                '<span style="color:' + open_color + ';font-weight:700">'
                + open_sign + "$" + f"{open_pnl_abs:,.2f}"
                + " (" + open_sign + f"{open_pct:.1f}%)" + "</span>"
                "</div>"
            )

        st.markdown(summary_html, unsafe_allow_html=True)
