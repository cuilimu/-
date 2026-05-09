"""
ui/components/ticker_search.py — Floating search widget (Yahoo Finance style).

The suggestion list uses position:fixed (z-index:9999) so it is fully detached
from document flow — it never pushes any other element or affects page height.

State machine:
  showDropdown (open_key) = True ONLY when input focused AND query != ""
  query        (shadow_key): cleared synchronously on "+" click

Transitions
-----------
  "+" click         → shadow_key="" + open_key=False + clear_key=True → rerun
                      After rerun: clear_key fires, returns ticker, resets all state.
                      query="" guarantees onFocus cannot reopen the dropdown.
  Escape / ✕ close → open_key=False → rerun
  Bucket/delete btn → caller calls _dismiss_search() (sets open_key=False) then rerun
  onFocus (JS)      → show dropdown if query != ""
  onBlur  (JS)      → 150ms delay, then hide dropdown visually if focus left wrap
  Nothing else may modify open_key.
"""

from typing import Optional
import streamlit as st
import streamlit.components.v1 as _components

from stock_engine.data.search import search_tickers
from stock_engine.ui.styles import inject as _inject_css

# ── Asset type → (label, bg, fg) ─────────────────────────────────────────────
_TYPE_LABEL = {
    "EQUITY":     ("EQ",  "#e8f0fe", "#1a56db"),
    "ETF":        ("ETF", "#fef3c7", "#d97706"),
    "MUTUALFUND": ("MF",  "#f0fdf4", "#16a34a"),
    "INDEX":      ("IDX", "#f5f3ff", "#7c3aed"),
    "CURRENCY":   ("FX",  "#fff7ed", "#c2410c"),
    "FUTURE":     ("FUT", "#fdf2f8", "#9d174d"),
}

# JS injected via components.html(height=0).
# Runs inside an iframe; accesses window.parent.document.
# - Positions .ts-wrap as fixed, precisely below the search input.
# - Wires focus/blur handlers (150ms blur delay) for clean UX.
# - Silently no-ops if CSP blocks cross-frame access (cloud deployments).
_JS_POSITION = """
<script>
(function positionDropdown() {
  try {
    var pDoc = window.parent.document;

    // Locate the search input by its unique placeholder text
    var inputs = pDoc.querySelectorAll(
      'input[placeholder="Symbol or company name…"]'
    );
    if (!inputs.length) return;
    var inp = inputs[0];

    var wrap = pDoc.querySelector('.ts-wrap');
    if (!wrap) return;

    function reposition() {
      var rect = inp.getBoundingClientRect();
      if (rect.width === 0) return;
      wrap.style.top   = (rect.bottom + 3) + 'px';
      wrap.style.left  = rect.left + 'px';
      wrap.style.width = rect.width + 'px';
    }
    reposition();

    // Stay aligned on scroll / resize
    window.parent.addEventListener('scroll', reposition, {passive: true});
    window.parent.addEventListener('resize', reposition, {passive: true});

    // Attach focus/blur only once per input element
    if (!inp._tsHandlersAdded) {
      inp._tsHandlersAdded = true;

      // onFocus: show dropdown if there is already a query
      inp.addEventListener('focus', function() {
        if (inp.value && inp.value.trim().length > 0) {
          reposition();
          wrap.style.display = '';
        }
      });

      // onBlur: 150ms delay so "+" click registers before hide fires
      inp.addEventListener('blur', function() {
        setTimeout(function() {
          var focused = pDoc.activeElement;
          if (wrap && !wrap.contains(focused)) {
            wrap.style.display = 'none';
          }
        }, 150);
      });

      // Escape: hide immediately
      inp.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
          if (wrap) wrap.style.display = 'none';
        }
      });
    }
  } catch (e) { /* CSP / cross-origin — silently ignore */ }
})();
</script>
"""


def ticker_search_widget(
    key: str,
    existing_tickers: list[str],
    label: str = "Search ticker",
) -> Optional[str]:
    """
    Floating ticker search widget.

    Session-state keys
    ------------------
    {key}_widget     — bound to st.text_input
    {key}_shadow     — mirrors widget value (never write to widget key directly)
    {key}_clear      — flag: rerun triggered by "+" click
    {key}_open       — bool: dropdown visible in Python state
    {key}_results    — list[TickerMatch]: current search hits
    {key}_selected   — str | None: chosen ticker, returned once then cleared
    {key}_prev_query — str: last query that triggered a search

    Returns the selected ticker on the rerun after a "+" click, else None.
    """
    _inject_css("ticker_search")

    widget_key     = f"{key}_widget"
    shadow_key     = f"{key}_shadow"
    clear_key      = f"{key}_clear"
    open_key       = f"{key}_open"
    results_key    = f"{key}_results"
    selected_key   = f"{key}_selected"
    prev_query_key = f"{key}_prev_query"

    for k, default in [
        (shadow_key,     ""),
        (clear_key,      False),
        (open_key,       False),
        (results_key,    []),
        (selected_key,   None),
        (prev_query_key, ""),
    ]:
        if k not in st.session_state:
            st.session_state[k] = default

    # ── Clear handler — fires on the rerun that follows a "+" click ───────────
    # Reset session state and capture the ticker to return, but DO NOT early-
    # return here. The earlier version returned before the text_input was
    # rendered, leaving the search input unmounted until the next rerun.
    # The user had to wiggle another widget (e.g. an allocation field) before
    # the search box reappeared. We now keep the input mounted on every
    # rerun and only deferred-return the ticker after rendering it.
    pending_ticker: Optional[str] = None
    if st.session_state[clear_key]:
        st.session_state[shadow_key]     = ""
        st.session_state[clear_key]      = False
        st.session_state[open_key]       = False
        st.session_state[results_key]    = []
        st.session_state[prev_query_key] = ""
        # Wipe the bound widget state BEFORE rendering so the text_input
        # visually clears (setting value= alone is ignored once a widget
        # key already exists in session_state).
        st.session_state[widget_key]     = ""
        pending_ticker = st.session_state[selected_key]
        st.session_state[selected_key]   = None

    st.markdown('<span class="ts-anchor"></span>', unsafe_allow_html=True)

    query = st.text_input(
        label,
        value=st.session_state[shadow_key],
        key=widget_key,
        placeholder="Symbol or company name…",
    )
    st.session_state[shadow_key] = query

    # If this rerun came from a "+" click, the input is now rendered (cleared
    # and ready for the next ticker). Return the captured selection — the
    # caller will append it to the group. Skip the search/dropdown branch
    # below: query was reset to "", open_key to False, so it would no-op
    # anyway, but returning here is cheaper and keeps the rerun focused.
    if pending_ticker is not None:
        return pending_ticker

    if query and len(query.strip()) >= 1:
        if (not st.session_state[open_key]
                or query.strip() != st.session_state[prev_query_key]):
            try:
                matches = search_tickers(query.strip(), max_results=6)
                st.session_state[results_key]    = matches
                st.session_state[open_key]       = True
                st.session_state[prev_query_key] = query.strip()
            except Exception:
                st.session_state[results_key] = []
    elif not query:
        st.session_state[open_key]    = False
        st.session_state[results_key] = []

    if not st.session_state[open_key] or not st.session_state[results_key]:
        return None

    results = st.session_state[results_key]
    n = len(results)

    st.markdown('<div class="ts-wrap ts-row-block">', unsafe_allow_html=True)

    for i, m in enumerate(results):
        already  = m.symbol in existing_tickers
        is_last  = (i == n - 1)
        type_raw = (m.type_ or "").upper()

        lbl, chip_bg, chip_fg = _TYPE_LABEL.get(type_raw, ("", "#f8f8f8", "#666"))
        type_chip = (
            f'<span class="ts-type" style="background:{chip_bg};color:{chip_fg}">{lbl}</span>'
        ) if lbl else ""
        exch_badge = (
            f'<span class="ts-exch">{m.exchange}</span>'
        ) if m.exchange else ""
        added_mark = '<span class="ts-added">✓ added</span>' if already else ""
        info_cls   = "ts-info" + (" ts-info-last" if is_last else "")

        c_info, c_btn = st.columns([9, 1], vertical_alignment="center")

        with c_info:
            st.markdown(
                f'<div class="{info_cls}">'
                f'<span class="ts-symbol">{m.symbol}</span>'
                f'<span class="ts-name">{m.name}</span>'
                f'{type_chip}{exch_badge}{added_mark}'
                f'</div>',
                unsafe_allow_html=True,
            )

        with c_btn:
            if already:
                st.markdown(
                    '<div style="text-align:center;font-size:13px;color:#16a34a;'
                    'font-weight:700;padding:4px 0">✓</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('<div class="ts-addbtn">', unsafe_allow_html=True)
                if st.button("＋", key=f"{key}_r_{i}_{m.symbol}"):
                    st.session_state[selected_key]   = m.symbol
                    st.session_state[clear_key]      = True
                    st.session_state[open_key]       = False
                    st.session_state[shadow_key]     = ""
                    st.session_state[prev_query_key] = ""
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    cl, _ = st.columns([1, 10])
    with cl:
        st.markdown('<div class="ts-close">', unsafe_allow_html=True)
        if st.button("✕ close", key=f"{key}_close"):
            st.session_state[open_key]    = False
            st.session_state[results_key] = []
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    _components.html(_JS_POSITION, height=0)

    return None
