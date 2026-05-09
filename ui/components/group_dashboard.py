"""
ui/components/group_dashboard.py — Card-based group dashboard.
Fix 1: all HTML triple-quoted, no f-string quote collisions.
Fix 4: group name header in portfolio tab.
Fix 8: card redesign per spec (shadow, light purple header, metric rows).
Fix 9: empty state, spacing, 2-col grid.
"""

import math
from typing import Optional, TYPE_CHECKING

import streamlit as st

from stock_engine.backtest.base import BacktestResult
from stock_engine.data.yfinance_provider import YFinanceProvider
from stock_engine.portfolio.models import PortfolioGroup, TickerAllocation
from stock_engine.portfolio.rebalancer import RebalanceConfig
from stock_engine.ui.components.holdings import allocation_table, holdings_table
from stock_engine.ui.components.rebalance_panel import rebalance_panel
from stock_engine.ui.components.ticker_search import ticker_search_widget
from stock_engine.ui.theme import COLOR_GAIN, COLOR_LOSS, SECTION_HEADER


def _fetch_start_price(ticker: str, start_date: str, config) -> float:
    """Delegate to YFinanceProvider.fetch_price_at — consolidated price fetch."""
    return YFinanceProvider(config).fetch_price_at(
        ticker, start_date, config.price_field
    ) or 0.0


def group_dashboard(
    groups: list[PortfolioGroup],
    group_results: dict[str, BacktestResult],
    config,
) -> tuple[list[PortfolioGroup], Optional[str], Optional[RebalanceConfig]]:
    """
    Returns (updated_groups, group_name_to_run_or_None, rb_cfg_or_None).
    Fix 9: empty state, 2-col grid, 8px spacing after summary bar.
    """
    # ── Empty state (Fix 9) ────────────────────────────────────────────────────
    if not groups:
        st.markdown("""
<div class="empty-state">
<h3>🏦 No portfolios yet</h3>
<p>Create a group to start comparing portfolios side by side</p>
</div>
""", unsafe_allow_html=True)
        if st.button("＋ Create First Group", type="primary"):
            return [_new_group(config)], None, None
        return [], None, None

    # ── New Group button ───────────────────────────────────────────────────────
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("＋ New Group"):
            groups.append(_new_group(config))

    st.write("")  # 8px spacing (Fix 9)
    st.divider()

    group_to_run: Optional[str] = None
    rb_cfg_to_run: Optional[RebalanceConfig] = None
    groups_to_delete: set[int] = set()

    # ── 2-column grid (Fix 9) ─────────────────────────────────────────────────
    for row_start in range(0, len(groups), 2):
        cols = st.columns(2)
        for col_i, gi in enumerate(range(row_start, min(row_start + 2, len(groups)))):
            group = groups[gi]
            result = group_results.get(group.name)
            with cols[col_i]:
                run_name, should_delete, rb_cfg = _render_card(group, result, config, gi)
                if run_name:
                    group_to_run = run_name
                    rb_cfg_to_run = rb_cfg
                if should_delete:
                    groups_to_delete.add(gi)

    final_groups = [g for i, g in enumerate(groups) if i not in groups_to_delete]
    return final_groups, group_to_run, rb_cfg_to_run


def _new_group(config) -> PortfolioGroup:
    idx = len(st.session_state.get("groups", [])) + 1
    return PortfolioGroup(name=f"Group {idx}", starting_capital=config.initial_capital)


def _render_card(
    group: PortfolioGroup,
    result: Optional[BacktestResult],
    config,
    gi: int,
) -> tuple[Optional[str], bool, Optional[RebalanceConfig]]:
    """Returns (group_name_to_run, should_delete, rb_cfg)."""
    expand_key = f"card_exp_{gi}"
    if expand_key not in st.session_state:
        st.session_state[expand_key] = False

    # ── Compute metrics ────────────────────────────────────────────────────────
    nav = result.snapshots[-1].nav if result and result.snapshots else group.starting_capital
    pnl = nav - group.starting_capital
    pnl_pct = (pnl / group.starting_capital * 100) if group.starting_capital > 0 else 0.0
    sign = "+" if pnl >= 0 else ""
    pnl_color = COLOR_GAIN if pnl >= 0 else COLOR_LOSS
    pnl_cls = "metric-value-gain" if pnl >= 0 else "metric-value-loss"

    arrow = "▲" if st.session_state[expand_key] else "▼"

    # ── Card header HTML (Fix 8) ───────────────────────────────────────────────
    header_html = (
        '<div class="engine-card-header">'
        '<span class="engine-card-title">📁 ' + group.name + "</span>"
        '<span style="color:#660874;font-size:18px">' + arrow + "</span>"
        "</div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    # Toggle expand on button click
    if st.button("▼", key=f"toggle_{gi}"):
        st.session_state[expand_key] = not st.session_state[expand_key]
        st.rerun()

    # ── Collapsed metric row (Fix 8) ───────────────────────────────────────────
    metrics_html = (
        '<div style="display:flex;gap:24px;padding:12px 16px;'
        'border:1px solid #e0e0e0;border-radius:0 0 12px 12px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.08);background:#fff;margin-bottom:12px">'

        "<div>"
        '<div class="metric-label">Capital</div>'
        '<div class="metric-value">$' + f"{group.starting_capital:,.0f}" + "</div>"
        "</div>"

        "<div>"
        '<div class="metric-label">P&amp;L</div>'
        '<div class="' + pnl_cls + '">' 
        + sign + "$" + f"{pnl:,.0f}"
        + " (" + sign + f"{pnl_pct:.1f}" + "%)"
        + "</div>"
        "</div>"

        "<div>"
        '<div class="metric-label">Total Value</div>'
        '<div class="metric-value">$' + f"{nav:,.0f}" + "</div>"
        "</div>"

        "</div>"
    )
    st.markdown(metrics_html, unsafe_allow_html=True)

    run_clicked = False
    should_delete = False
    rb_cfg: Optional[RebalanceConfig] = None

    # ── Expanded edit view ─────────────────────────────────────────────────────
    if st.session_state[expand_key]:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            group.name = c1.text_input("Group name", value=group.name, key=f"gname_{gi}")
            group.starting_capital = c2.number_input(
                "Capital ($)", value=group.starting_capital,
                min_value=1_000.0, step=1_000.0, format="%.0f", key=f"gcap_{gi}",
            )

            # Ticker search
            selected = ticker_search_widget(
                key=f"g{gi}_search",
                existing_tickers=group.tickers,
                label="Search ticker",
            )
            if selected and selected not in group.tickers:
                price = _fetch_start_price(selected, config.default_start_date, config)
                # New tickers default to $0 — manual-first allocation. Existing
                # positions are NOT touched. Use the "⚖ Equal Weight" button
                # below the search to redistribute capital equally.
                group.allocations.append(TickerAllocation(
                    ticker=selected,
                    allocated_dollars=0.0,
                    price_used=price,
                ))

            # Ensure all prices populated
            start_prices: dict[str, float] = {}
            for alloc in group.allocations:
                if alloc.price_used <= 0:
                    alloc.price_used = _fetch_start_price(
                        alloc.ticker, config.default_start_date, config
                    )
                start_prices[alloc.ticker] = alloc.price_used

            if group.allocations:
                # ── Equal Weight shortcut (top-right of the allocation table) ──
                # Splits group capital evenly across current tickers, floors
                # each to whole dollars (remainder shows up as cash in the
                # allocation table totals row). Overwrites every input but
                # does NOT trigger a backtest.
                _ew_l, _ew_r = st.columns([4, 1])
                with _ew_r:
                    if st.button(
                        "⚖ Equal Weight",
                        key=f"g{gi}_eq_weight",
                        help="Divide group capital equally across all tickers. "
                             "Remainder from rounding is held as cash.",
                        use_container_width=True,
                    ):
                        n = len(group.allocations)
                        if n > 0:
                            per = float(math.floor(group.starting_capital / n))
                            # WRITE the new value into both the model AND the
                            # widget's session_state slot before the rerun.
                            # st.number_input ignores `value=` once a key is
                            # registered; popping is unreliable, but assigning
                            # the same key is honoured on the next render.
                            # Key format must match allocation_table()'s
                            # number_input: f"{key_prefix}_dollars_{ticker}".
                            for alloc in group.allocations:
                                alloc.allocated_dollars = per
                                st.session_state[
                                    f"g{gi}_dollars_{alloc.ticker}"
                                ] = per
                            st.rerun()

                updated_allocs, to_remove = allocation_table(
                    allocations=group.allocations,
                    price_field=config.price_field,
                    start_prices=start_prices,
                    total_capital=group.starting_capital,
                    key_prefix=f"g{gi}",
                )
                group.allocations = [a for a in updated_allocs if a.ticker not in to_remove]

            # Holdings table (post-backtest, Fix 2+4)
            if result and result.snapshots:
                st.markdown(
                    '<div class="section-header">Holdings — ' + group.name + "</div>",
                    unsafe_allow_html=True,
                )
                last = result.snapshots[-1]
                end_prices: dict[str, float] = {}
                prov = YFinanceProvider(config)
                for t in last.positions:
                    try:
                        price = prov.fetch_price_at(t, result.end_date, config.price_field)
                        end_prices[t] = price if price and price > 0 else last.positions[t].cost_basis
                    except Exception:
                        end_prices[t] = last.positions[t].cost_basis

                holdings_table(last, end_prices, config.price_field, key_prefix=f"g{gi}_h",
                               closed_positions=result.closed_positions,
                               initial_capital=result.initial_capital)

            # Rebalance / transaction panel — mode-dependent
            buy_mode = st.session_state.get("buy_mode_home", "same_day")
            if buy_mode == "same_day":
                capital = (
                    result.snapshots[-1].nav if result and result.snapshots
                    else group.starting_capital
                )
                rb_cfg = rebalance_panel(
                    f"group_{group.name}",
                    config=config,
                    prior_result=result,
                    capital_hint=capital,
                )
            else:
                # Multi-date: render a per-group transaction log
                from stock_engine.ui.components.transaction_panel import (
                    render_transaction_panel, validate_transactions,
                )
                txn_key = f"txns_group_{group.name}"
                txns = render_transaction_panel(
                    session_key=txn_key,
                    config=config,
                    start_date=config.default_start_date,
                    end_date=config.effective_end_date(),
                    initial_capital=group.starting_capital,
                )
                # Disable the Run button if transactions are invalid
                _md_errs = validate_transactions(txns)
                if _md_errs:
                    for _e in _md_errs:
                        st.markdown(
                            f'<span style="color:#e03030;font-size:11px">⚠ {_e}</span>',
                            unsafe_allow_html=True,
                        )

            # Action buttons
            _buy_mode = st.session_state.get("buy_mode_home", "same_day")
            _run_disabled = False
            if _buy_mode == "multi_date":
                from stock_engine.ui.components.transaction_panel import validate_transactions as _vt
                _run_disabled = bool(_vt(st.session_state.get(f"txns_group_{group.name}", [])))
            b1, b2 = st.columns([1, 1])
            with b1:
                if st.button(
                    "▶ Run Backtest", type="primary",
                    key=f"run_{gi}", use_container_width=True,
                    disabled=_run_disabled,
                ):
                    run_clicked = True
            with b2:
                confirm_key = f"confirm_del_{gi}"
                if not st.session_state.get(confirm_key):
                    if st.button(
                        "🗑 Delete Group", key=f"del_{gi}",
                        use_container_width=True,
                    ):
                        st.session_state[confirm_key] = True
                        st.rerun()
                else:
                    st.warning("Confirm delete?")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("Yes, delete", key=f"del_yes_{gi}"):
                        st.session_state[confirm_key] = False
                        should_delete = True
                        st.rerun()
                    if cc2.button("Cancel", key=f"del_no_{gi}"):
                        st.session_state[confirm_key] = False
                        st.rerun()

    return (group.name if run_clicked else None), should_delete, rb_cfg
