"""
ui/components/transaction_panel.py — Multi-Date transaction panel.
Fix 1: ticker stored in pending_tx_ticker session key, never None in log.
Fix 2: preview_price/shares fetched at add time, shown in grey before backtest.
Fix 3: sell validation uses compute_holdings_at_date() from transaction log.
Fix 4: log rendered as st.columns() rows with inline delete button.
Fix 5: validate_transactions() gate before Run Backtest.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import streamlit as st

from stock_engine.config import Config
from stock_engine.data.yfinance_provider import YFinanceProvider
from stock_engine.data.event_provider import get_events_cached
from stock_engine.portfolio.models import ScheduledTransaction
from stock_engine.portfolio.transaction import compute_cash_at_date
from stock_engine.ui.components.ticker_search import ticker_search_widget
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.ui.theme import COLOR_GAIN, COLOR_LOSS, SECTION_HEADER

_TXN_COUNTER = "txn_id_counter"

# ── Fix 3: holdings computation from transaction log ───────────────────────────

def compute_holdings_at_date(
    txns: list[ScheduledTransaction],
    ticker: str,
    as_of_date: str,
) -> int:
    """
    Compute shares held as of as_of_date from the transaction log.
    Uses preview_shares for BUYs (pre-backtest) and shares for SELLs.
    """
    held = 0
    for t in sorted(txns, key=lambda x: x.date):
        if t.date > as_of_date:
            break
        if t.ticker != ticker:
            continue
        if t.is_buy():
            held += t.preview_shares or t.executed_shares or 0
        else:
            held -= t.shares or t.executed_shares or 0
    return max(0, held)


# ── Fix 5: validation gate ─────────────────────────────────────────────────────

def validate_transactions(txns: list[ScheduledTransaction]) -> list[str]:
    errors: list[str] = []
    if not txns:
        errors.append("No transactions added.")
        return errors
    for i, t in enumerate(txns):
        if not t.ticker:
            errors.append(f"Transaction #{i+1}: ticker is missing.")
        if t.is_buy() and (not t.amount_usd or t.amount_usd <= 0):
            errors.append(f"Transaction #{i+1}: invalid amount.")
        if t.is_buy() and t.preview_price is None:
            errors.append(f"Transaction #{i+1}: could not fetch price for {t.date}.")
    return errors


# ── Public API ─────────────────────────────────────────────────────────────────

def mode_toggle(key: str = "buy_mode") -> str:
    """Returns 'same_day' or 'multi_date'."""
    st.markdown("**Buy Mode**")
    mode = st.radio(
        "",
        ["Same Day", "Multi-Date"],
        horizontal=True,
        key=key,
        label_visibility="collapsed",
    )
    return "multi_date" if "Multi" in mode else "same_day"


def render_transaction_panel(
    session_key: str,
    config: Config,
    start_date: str,
    end_date: str,
    initial_capital: float,
) -> list[ScheduledTransaction]:
    """
    Renders the full multi-date transaction panel.
    Returns current list of ScheduledTransactions.
    """
    _inject_css("transaction_panel")

    if _TXN_COUNTER not in st.session_state:
        st.session_state[_TXN_COUNTER] = 0
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    # Fix 1: pending ticker state key
    pending_key = f"{session_key}_pending_ticker"
    if pending_key not in st.session_state:
        st.session_state[pending_key] = None

    txns: list[ScheduledTransaction] = st.session_state[session_key]

    # ── Header row ─────────────────────────────────────────────────────────────
    h1, h2 = st.columns([3, 1])
    h1.markdown(
        '<div class="section-header">Transaction Log</div>',
        unsafe_allow_html=True,
    )
    add_open_key = f"{session_key}_add_open"
    if add_open_key not in st.session_state:
        st.session_state[add_open_key] = False
    with h2:
        if st.button("＋ Add Transaction", key=f"{session_key}_add_btn"):
            st.session_state[add_open_key] = True
            st.session_state[pending_key] = None

    # ── Add form ───────────────────────────────────────────────────────────────
    if st.session_state.get(add_open_key):
        new_txn = _render_add_form(
            session_key=session_key,
            pending_key=pending_key,
            config=config,
            start_date=start_date,
            end_date=end_date,
            existing_txns=txns,
            initial_capital=initial_capital,
        )
        if new_txn is not None:
            # Fix 1: assert ticker is set
            if not new_txn.ticker:
                st.error("Cannot add transaction — ticker is missing.")
            else:
                txns.append(new_txn)
                txns.sort(key=lambda t: t.date)
                st.session_state[session_key] = txns
                st.session_state[add_open_key] = False
                st.session_state[pending_key] = None  # Fix 1: clear pending
                st.rerun()

    # ── Transaction log table (Fix 4: st.columns rows) ────────────────────────
    if not txns:
        st.info("No transactions yet. Click **＋ Add Transaction** to begin.")
    else:
        # Change 6: sequencing note
        st.markdown(
            '<span style="color:#888;font-size:12px">'
            "ℹ️ Transactions are locked in chronological order. "
            "New entries must follow the latest date.</span>",
            unsafe_allow_html=True,
        )
        _render_txn_table(txns, session_key, start_date, end_date)

    # ── Cash tracker ───────────────────────────────────────────────────────────
    _render_cash_tracker(txns, initial_capital)

    # ── Fix 5: validation status ───────────────────────────────────────────────
    errors = validate_transactions(txns)
    if errors:
        for e in errors:
            st.markdown(
                f'<span class="val-err">⚠ {e}</span>',
                unsafe_allow_html=True,
            )
    elif txns:
        st.markdown(
            f'<span class="val-ok">✓ {len(txns)} transaction(s) ready</span>',
            unsafe_allow_html=True,
        )

    return st.session_state[session_key]


# ── Add Transaction form ───────────────────────────────────────────────────────

def _render_add_form(
    session_key: str,
    pending_key: str,
    config: Config,
    start_date: str,
    end_date: str,
    existing_txns: list[ScheduledTransaction],
    initial_capital: float,
) -> Optional[ScheduledTransaction]:

    with st.container(border=True):
        st.markdown("**Add Transaction**")

        c_action, c_ticker = st.columns([1, 2])
        with c_action:
            action = st.radio(
                "Action",
                ["🟢 Buy", "🔴 Sell"],
                key=f"{session_key}_f_action",
                horizontal=True,
            )
            is_buy = action.startswith("🟢")

        with c_ticker:
            # Fix 1: use ticker_search_widget, store result in pending_key
            selected = ticker_search_widget(
                key=f"{session_key}_f_ticker",
                existing_tickers=[],
                label="Ticker",
            )
            if selected:
                st.session_state[pending_key] = selected

            # Fallback direct entry
            direct = st.text_input(
                "Or enter symbol directly",
                key=f"{session_key}_f_direct",
                placeholder="e.g. AAPL",
            ).upper().strip()
            if direct and not st.session_state.get(pending_key):
                st.session_state[pending_key] = direct

            ticker = st.session_state.get(pending_key)
            if ticker:
                st.markdown(
                    f'<span style="color:#660874;font-weight:700">Selected: {ticker}</span>',
                    unsafe_allow_html=True,
                )

        # ── Event timeline (shown after ticker is selected) ───────────────
        if ticker:
            _render_event_timeline(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                date_state_key=f"{session_key}_f_date",
                context_key=session_key,
            )

        # Date — Change 6: min_value clamped to latest existing txn date for this ticker
        start_ts = pd.Timestamp(start_date).date()
        end_ts   = pd.Timestamp(end_date).date()

        # Compute sequencing floor: max date of existing transactions for this ticker
        if ticker:
            ticker_dates = [
                pd.Timestamp(t.date).date()
                for t in existing_txns
                if t.ticker == ticker and t.date
            ]
            seq_floor = max(ticker_dates, default=start_ts)
        else:
            seq_floor = start_ts

        effective_min = max(start_ts, seq_floor)

        # Show sequencing note if floor is later than backtest start
        if seq_floor > start_ts and ticker:
            st.markdown(
                f'<span style="color:#888;font-size:12px">'
                f"ℹ️ Transactions are chronological — new entry must be ≥ {seq_floor}</span>",
                unsafe_allow_html=True,
            )

        txn_date_val = st.date_input(
            "Date",
            value=max(effective_min, start_ts),
            min_value=effective_min,
            max_value=end_ts,
            key=f"{session_key}_f_date",
        )
        txn_date = str(txn_date_val)

        # Inline sequencing error if user somehow enters earlier date
        if txn_date_val < seq_floor and ticker:
            st.markdown(
                f'<span style="color:#e03030;font-size:12px">'
                f"⚠️ Cannot add transaction before {seq_floor} — transactions are chronological</span>",
                unsafe_allow_html=True,
            )

        # Fix 2: live available cash display
        avail_cash = compute_cash_at_date(existing_txns, txn_date, initial_capital)
        avail_color = COLOR_GAIN if avail_cash >= 0 else COLOR_LOSS
        st.markdown(
            f'<span style="color:#888;font-size:12px">'
            f"Available cash as of {txn_date}: "
            f'<strong style="color:{avail_color}">${avail_cash:,.2f}</strong>'
            f"</span>",
            unsafe_allow_html=True,
        )

        # Fix 1+2: fetch preview price at add time via consolidated method
        preview_price = 0.0
        preview_shares = None
        if ticker:
            preview_price = YFinanceProvider(config).fetch_price_at(
                ticker, txn_date, config.price_field
            ) or 0.0

        errors: list[str] = []
        amount_usd  = None
        shares_sell = None

        if is_buy:
            amount_usd = st.number_input(
                "Amount ($)",
                min_value=0.0,
                value=10_000.0,
                step=1_000.0,
                format="%.0f",
                key=f"{session_key}_f_amount",
            )
            if preview_price > 0:
                preview_shares = math.floor(amount_usd / preview_price)
                returned = amount_usd - preview_shares * preview_price
                st.markdown(
                    f'<span style="color:#888;font-size:12px">'
                    f"@ ${preview_price:,.2f} ({config.price_field}) "
                    f"= {preview_shares} shares | returned: ${returned:,.2f}"
                    f"</span>",
                    unsafe_allow_html=True,
                )
                if preview_shares < 1:
                    errors.append(
                        f"Insufficient amount — min 1 share = ${preview_price:,.2f}"
                    )
                elif amount_usd > avail_cash + 1e-6:
                    errors.append(
                        f"Insufficient cash — need ${amount_usd:,.0f}, "
                        f"available ${avail_cash:,.2f} as of {txn_date}"
                    )
            elif ticker:
                errors.append(f"Could not fetch price for {txn_date}")
        else:
            # Fix 3: compute holdings from transaction log
            held = compute_holdings_at_date(existing_txns, ticker or "", txn_date)
            st.markdown(
                f'<span style="color:#888;font-size:12px">'
                f"Holdings as of {txn_date}: **{held} shares**"
                f" (from transaction log)"
                f"</span>",
                unsafe_allow_html=True,
            )
            shares_sell = st.number_input(
                "Shares to sell",
                min_value=0,
                max_value=max(held, 1),
                value=min(held, 1) if held > 0 else 0,
                step=1,
                key=f"{session_key}_f_shares",
            )
            if preview_price > 0 and shares_sell > 0:
                st.markdown(
                    f'<span style="color:#888;font-size:12px">'
                    f"Proceeds ≈ ${shares_sell * preview_price:,.2f}"
                    f"</span>",
                    unsafe_allow_html=True,
                )
            if shares_sell > held:
                errors.append(
                    f"Only {held} shares held as of {txn_date} based on transaction log"
                )

        if not ticker:
            errors.append("Select a ticker.")
        if txn_date < start_date or txn_date > end_date:
            errors.append(f"Date must be between {start_date} and {end_date}")

        for e in errors:
            st.markdown(
                f'<span style="color:{COLOR_LOSS};font-size:12px">⚠️ {e}</span>',
                unsafe_allow_html=True,
            )

        c_cancel, c_confirm = st.columns([1, 1])
        with c_cancel:
            if st.button("Cancel", key=f"{session_key}_f_cancel"):
                st.session_state[f"{session_key}_add_open"] = False
                st.session_state[pending_key] = None
                st.rerun()
        with c_confirm:
            disabled = bool(errors) or not ticker
            if st.button(
                "✓ Confirm Add",
                type="primary",
                key=f"{session_key}_f_confirm",
                disabled=disabled,
            ):
                st.session_state[_TXN_COUNTER] += 1
                return ScheduledTransaction(
                    ticker=ticker,
                    action="BUY" if is_buy else "SELL",
                    date=txn_date,
                    amount_usd=amount_usd if is_buy else None,
                    shares=int(shares_sell) if not is_buy else None,
                    price_field=config.price_field,
                    preview_price=preview_price if preview_price > 0 else None,
                    preview_shares=preview_shares,
                    txn_id=st.session_state[_TXN_COUNTER],
                )
    return None

# ── Event timeline (in add form) ───────────────────────────────────────────────

EVENTS_PER_PAGE = 5


def _render_event_timeline(
    ticker: str,
    start_date: str,
    end_date: str,
    date_state_key: str,
    context_key: str = "default",
) -> None:
    """
    Shows corporate events for ticker within backtest period.
    Paginated: 10 events per page. No pagination controls when ≤ 10 events.
    → Use button fills the date picker state key.
    context_key must be unique per panel to avoid page-state collision.
    """
    with st.spinner(f"Loading events for {ticker}…"):
        events = get_events_cached(ticker, start_date, end_date)

    with st.expander(
        f"📅 Key Events — {ticker} ({len(events)} total)",
        expanded=False,
    ):
        if not events:
            st.markdown(
                '<span style="color:#999;font-size:12px;font-style:italic">'
                "No earnings, dividend, or split events found in this period.</span>",
                unsafe_allow_html=True,
            )
            return

        # Reset page when expander is opened (page_key scoped per ticker+context)
        page_key = f"event_page_{ticker}_{context_key}"
        if page_key not in st.session_state:
            st.session_state[page_key] = 0

        total_pages = math.ceil(len(events) / EVENTS_PER_PAGE)
        st.session_state[page_key] = min(st.session_state[page_key], total_pages - 1)
        current_page = st.session_state[page_key]

        page_events = events[
            current_page * EVENTS_PER_PAGE : (current_page + 1) * EVENTS_PER_PAGE
        ]

        for ev in page_events:
            col_date, col_icon, col_label, col_use = st.columns([1.2, 0.4, 3, 0.7])
            col_date.markdown(
                f'<span style="color:#444;font-family:monospace;font-size:12px">{ev.date}</span>',
                unsafe_allow_html=True,
            )
            col_icon.markdown(ev.icon())
            label_text = ev.label + (f" {ev.detail}" if ev.detail else "")
            col_label.markdown(
                f'<span style="color:#666;font-size:13px">{label_text}</span>',
                unsafe_allow_html=True,
            )
            if col_use.button(
                "→ Use",
                key=f"use_event_{ticker}_{ev.date}_{ev.event_type}_{context_key}",
            ):
                import datetime
                st.session_state[date_state_key] = datetime.date.fromisoformat(ev.date)
                st.rerun()

        # Pagination controls — only if more than one page
        if total_pages > 1:
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                if current_page > 0:
                    if st.button("← Prev", key=f"prev_{page_key}"):
                        st.session_state[page_key] -= 1
                        st.rerun()
            with c2:
                st.caption(f"{current_page + 1} / {total_pages} ({len(events)} events)")
            with c3:
                if current_page < total_pages - 1:
                    if st.button("Next →", key=f"next_{page_key}"):
                        st.session_state[page_key] += 1
                        st.rerun()


# ── Fix 4: transaction log as st.columns rows ──────────────────────────────────

def _render_txn_table(
    txns: list[ScheduledTransaction],
    session_key: str,
    start_date: str = "",
    end_date: str = "",
) -> None:
    # Column widths: #, ACTION, TICKER, DATE, AMOUNT, SHARES, PRICE, DEL
    COLS = [0.4, 1.2, 1.2, 1.8, 1.8, 1.4, 1.4, 0.5]

    # Fix 1: events shown only inside the add-form modal, never in the log table.

    # Header
    hcols = st.columns(COLS)
    for header, col in zip(
        ["#", "ACTION", "TICKER", "DATE", "AMOUNT", "SHARES", "PRICE", ""],
        hcols,
    ):
        col.markdown(
            f'<span style="color:#666;font-size:11px;text-transform:uppercase;'
            f'font-weight:600">{header}</span>',
            unsafe_allow_html=True,
        )

    st.markdown('<hr style="margin:2px 0 6px;border-color:#e0e0e0">', unsafe_allow_html=True)

    # Data rows (Fix 4: inline delete button)
    to_delete = None
    for i, txn in enumerate(txns):
        if not txn.ticker:
            st.markdown(
                f'<span style="color:{COLOR_LOSS}">⚠️ Transaction #{i+1}: ticker missing — please delete and re-add.</span>',
                unsafe_allow_html=True,
            )
            continue

        row_border = "#00b050" if txn.is_buy() else "#e03030"
        if txn.error:
            row_border = "#ffaa00"

        dcols = st.columns(COLS)

        # # column with left border indicator
        dcols[0].markdown(
            f'<div style="border-left:3px solid {row_border};padding-left:6px">'
            f'{i+1}</div>',
            unsafe_allow_html=True,
        )

        # Action badge
        badge = (
            '<span class="badge-buy">🟢 BUY</span>'
            if txn.is_buy()
            else '<span class="badge-sell">🔴 SELL</span>'
        )
        dcols[1].markdown(badge, unsafe_allow_html=True)

        dcols[2].markdown(f"**{txn.ticker}**")
        dcols[3].write(txn.display_date() + (" ⚠️" if txn.date_adjusted else ""))

        # Amount
        if txn.is_buy():
            dcols[4].write(f"${txn.amount_usd:,.0f}" if txn.amount_usd else "—")
        else:
            dcols[4].write("—")

        # Fix 2: shares — preview (grey) vs executed (bold black)
        if txn.is_executed and txn.executed_shares is not None:
            dcols[5].markdown(
                f'<span class="executed-val">{txn.executed_shares:,} ✓</span>',
                unsafe_allow_html=True,
            )
        elif txn.preview_shares is not None:
            dcols[5].markdown(
                f'<span class="preview-val">{txn.preview_shares:,}</span>',
                unsafe_allow_html=True,
            )
        elif txn.shares is not None:
            dcols[5].write(str(txn.shares))
        else:
            dcols[5].write("—")

        # Fix 2: price — preview (grey) vs executed (bold black)
        if txn.is_executed and txn.executed_price is not None:
            dcols[6].markdown(
                f'<span class="executed-val">${txn.executed_price:,.2f} ✓</span>',
                unsafe_allow_html=True,
            )
        elif txn.preview_price is not None:
            dcols[6].markdown(
                f'<span class="preview-val">${txn.preview_price:,.2f}</span>',
                unsafe_allow_html=True,
            )
        else:
            dcols[6].write("—")

        # Fix 4: inline delete button
        if dcols[7].button("✕", key=f"{session_key}_del_{txn.txn_id}"):
            to_delete = txn.txn_id

        # Error note
        if txn.error:
            st.markdown(
                f'<span style="color:#ffaa00;font-size:11px;margin-left:20px">'
                f"⚠️ {txn.error}</span>",
                unsafe_allow_html=True,
            )

    if to_delete is not None:
        st.session_state[session_key] = [
            t for t in txns if t.txn_id != to_delete
        ]
        st.rerun()


# ── Cash tracker ───────────────────────────────────────────────────────────────

def _render_cash_tracker(
    txns: list[ScheduledTransaction],
    initial_capital: float,
) -> None:
    """
    Fix 2: chronological cash ledger.
    Each transaction row shows delta + running balance.
    Red = outflow (buy), green = inflow (sell).
    """
    if not txns:
        return

    rows_html = []
    balance = initial_capital

    for t in sorted(txns, key=lambda x: x.date):
        if t.error:
            continue
        if t.is_buy():
            if t.is_executed:
                delta = -(t.executed_value or 0.0)
                delta += (t.returned_cash or 0.0)
            else:
                delta = -((t.preview_shares or 0) * (t.preview_price or 0.0))
            color = COLOR_LOSS
            sign  = "-"
        else:
            if t.is_executed:
                delta = (t.executed_value or 0.0)
            else:
                delta = (t.shares or 0) * (t.preview_price or 0.0)
            color = COLOR_GAIN
            sign  = "+"

        balance += delta
        preview_note = "" if t.is_executed else " <em style='color:#aaa'>(est.)</em>"
        rows_html.append(
            f'<div style="font-family:monospace;font-size:11px;color:#555;'
            f'padding:2px 0;display:flex;gap:12px">'
            f'<span style="min-width:90px">{t.date}</span>'
            f'<span style="min-width:52px;color:{color};font-weight:600">'
            f'{t.action}</span>'
            f'<span style="min-width:60px;font-weight:600">{t.ticker}</span>'
            f'<span style="min-width:110px;color:{color}">'
            f'{sign}${abs(delta):,.2f}{preview_note}</span>'
            f'<span style="color:#333">bal: <strong>${balance:,.2f}</strong></span>'
            f"</div>"
        )

    avail_color = COLOR_GAIN if balance >= 0 else COLOR_LOSS
    rows_joined = "\n".join(rows_html)
    html = (
        '<div class="cash-tracker" style="flex-direction:column;gap:4px">'
        f'<div style="font-size:12px;font-weight:600;color:#660874;'
        f'margin-bottom:4px">Cash Ledger</div>'
        f'<div style="font-family:monospace;font-size:11px;color:#555;'
        f'padding:2px 0;display:flex;gap:12px">'
        f'<span style="min-width:90px">Start</span>'
        f'<span style="min-width:222px"></span>'
        f'<span style="color:#333">bal: <strong>${initial_capital:,.2f}</strong></span>'
        f"</div>"
        f"{rows_joined}"
        f'<div style="margin-top:4px;font-size:12px">'
        f"<strong>Available:</strong> "
        f'<span style="color:{avail_color};font-weight:600">${balance:,.2f}</span>'
        f"</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Holdings sub-rows (post-backtest) ─────────────────────────────────────────

def render_txn_subrows(
    ticker: str,
    txns: list[ScheduledTransaction],
) -> None:
    ticker_txns = [t for t in txns if t.ticker == ticker and not t.error]
    if not ticker_txns:
        return

    with st.expander(f"📋 {ticker} — {len(ticker_txns)} transaction(s)", expanded=False):
        for t in ticker_txns:
            price = t.executed_price or t.preview_price or 0
            shares = t.executed_shares or t.preview_shares or t.shares or 0
            value  = t.executed_value or (shares * price)

            if t.is_buy():
                value_html = (
                    f'<span style="color:{COLOR_LOSS}">(${value:,.2f})</span>'
                )
            else:
                value_html = (
                    f'<span style="color:{COLOR_GAIN}">+${value:,.2f}</span>'
                )

            executed_note = "✓" if t.is_executed else "(preview)"
            action_color = "#00b050" if t.is_buy() else "#e03030"
            st.markdown(
                f'<div style="font-size:12px;color:#888;padding:3px 0">'
                f"└─ {t.display_date()} &nbsp;"
                f'<strong style="color:{action_color}">'
                f"{t.action}</strong> &nbsp;"
                f"{shares} shares @ ${price:,.2f} {executed_note}"
                f" &nbsp;{value_html}"
                f"</div>",
                unsafe_allow_html=True,
            )
