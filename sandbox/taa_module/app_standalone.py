"""
app_standalone.py — independent Streamlit harness for the TAA prototype.

Run:
    streamlit run stock_engine/sandbox/taa_module/app_standalone.py

Three steps emulate the planned app flow:
  Step 1 — Universe (set tickers + bucket assignments; demo defaults wired)
  Step 2 — TAA      (passthrough / factor MVO + diagnostics)
  Step 3 — Allocation Preview (Equal-Weight under TAA + Manual untouched)

Uses MockReturnsProvider — no yfinance, no main-app session, no theme
imports. The output of Step 2 is a TAAResult that Step 3 consumes via
apply_equal_weights_v2().
"""
from __future__ import annotations

import streamlit as st

from stock_engine.sandbox.taa_module.equal_weight import (
    explain_equal_weight_rule,
)
from stock_engine.sandbox.taa_module.factor_mvo import TAAResult
from stock_engine.sandbox.taa_module.mock_data import MockReturnsProvider
from stock_engine.sandbox.taa_module.rebalance import rebalance_at
from stock_engine.sandbox.taa_module.taa_page import render_taa_page
from stock_engine.sandbox.taa_module.types import (
    BucketAssignment, FactorBucket, MiniUniverse,
)

# ── Demo universe ─────────────────────────────────────────────────────────────
_DEMO = [
    ("AAPL", FactorBucket.GROWTH),
    ("MSFT", FactorBucket.GROWTH),
    ("NVDA", FactorBucket.GROWTH),
    ("JPM",  FactorBucket.FIN_COND),
    ("GS",   FactorBucket.FIN_COND),
    ("GLD",  FactorBucket.INFLATION),
    ("XLE",  FactorBucket.INFLATION),
    ("TLT",  FactorBucket.DIVERSIFIER),
    ("IEF",  FactorBucket.DIVERSIFIER),
]

_BUCKET_OPTS = [
    FactorBucket.GROWTH, FactorBucket.FIN_COND,
    FactorBucket.INFLATION, FactorBucket.DIVERSIFIER,
    FactorBucket.UNASSIGNED,
]

_BUCKET_LABEL = {
    FactorBucket.GROWTH:      "GROWTH",
    FactorBucket.FIN_COND:    "FIN. COND",
    FactorBucket.INFLATION:   "INFLATION",
    FactorBucket.DIVERSIFIER: "DIVERSIFIER",
    FactorBucket.UNASSIGNED:  "UNASSIGNED",
}


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TAA Sandbox",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("TAA · Sandbox")
st.caption("Independent prototype — passthrough vs. factor mean-variance "
           "(mock data). When approved, lifts into ui/components/simple_mode "
           "as Step 3 between Stock Selection and Allocation.")


# ── Session ───────────────────────────────────────────────────────────────────
def _init_session():
    if "sb_step" not in st.session_state:
        st.session_state["sb_step"] = 1
    if "sb_universe" not in st.session_state:
        st.session_state["sb_universe"] = MiniUniverse(
            assignments=[BucketAssignment(t, b) for t, b in _DEMO]
        )
    if "sb_capital" not in st.session_state:
        st.session_state["sb_capital"] = 100_000.0


_init_session()
provider = MockReturnsProvider()


# ── Top stepper ───────────────────────────────────────────────────────────────
def _stepper():
    cols = st.columns([1, 1, 1, 4])
    for i, (n, label) in enumerate([(1, "Universe"), (2, "TAA"),
                                     (3, "Allocation Preview")]):
        with cols[i]:
            cur = st.session_state["sb_step"]
            kind = "primary" if n == cur else "secondary"
            if st.button(f"Step {n}: {label}", key=f"sb_step_{n}", type=kind,
                         use_container_width=True):
                st.session_state["sb_step"] = n
                st.rerun()


_stepper()
st.markdown("---")


# ── Step 1: Universe ─────────────────────────────────────────────────────────
def _render_step1():
    st.markdown("#### Step 1 · Universe & bucket assignments")
    st.caption("Edit the table inline. Row delete: clear ticker cell. "
               "Bucket dropdown drives where each ticker goes in TAA.")

    universe: MiniUniverse = st.session_state["sb_universe"]

    # Editable table via st.data_editor (Streamlit ≥ 1.23)
    data = [
        {"ticker": a.ticker, "bucket": _BUCKET_LABEL[a.bucket]}
        for a in universe.assignments
    ]
    edited = st.data_editor(
        data,
        num_rows="dynamic",
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", required=True),
            "bucket": st.column_config.SelectboxColumn(
                "Bucket",
                options=[_BUCKET_LABEL[b] for b in _BUCKET_OPTS],
                required=True,
            ),
        },
        key="sb_universe_editor",
        use_container_width=True,
        hide_index=True,
    )

    # Reverse map for label → enum
    inv = {v: k for k, v in _BUCKET_LABEL.items()}
    new_assignments = []
    for row in edited:
        t = (row.get("ticker") or "").strip().upper()
        b_label = (row.get("bucket") or _BUCKET_LABEL[FactorBucket.UNASSIGNED])
        bucket = inv.get(b_label, FactorBucket.UNASSIGNED)
        if t:
            new_assignments.append(BucketAssignment(t, bucket))
    st.session_state["sb_universe"] = MiniUniverse(assignments=new_assignments)

    st.session_state["sb_capital"] = st.number_input(
        "Capital (USD)", min_value=1_000.0, max_value=1e9,
        step=1_000.0, format="%.0f",
        value=float(st.session_state["sb_capital"]),
        key="sb_capital_input",
    )

    cols = st.columns([4, 1])
    with cols[1]:
        if st.button("Next → TAA", type="primary", use_container_width=True,
                     disabled=not st.session_state["sb_universe"].tickers):
            st.session_state["sb_step"] = 2
            st.rerun()


# ── Step 2: TAA ───────────────────────────────────────────────────────────────
def _render_step2():
    st.markdown("#### Step 2 · TAA")
    universe: MiniUniverse = st.session_state["sb_universe"]
    taa = render_taa_page(universe, provider)
    st.session_state["sb_taa"] = taa

    st.markdown("---")
    cols = st.columns([1, 4, 1])
    with cols[0]:
        if st.button("← Back", use_container_width=True):
            st.session_state["sb_step"] = 1
            st.rerun()
    with cols[2]:
        if st.button("Next → Allocation", type="primary",
                     use_container_width=True, disabled=(taa is None)):
            st.session_state["sb_step"] = 3
            st.rerun()


# ── Step 3: Allocation Preview ────────────────────────────────────────────────
def _render_step3():
    st.markdown("#### Step 3 · Allocation preview (after rebalance)")
    universe: MiniUniverse = st.session_state["sb_universe"]
    taa_prior: TAAResult = st.session_state.get("sb_taa")
    capital = float(st.session_state["sb_capital"])

    if taa_prior is None:
        st.warning("Go back to Step 2 and run TAA first.")
        return

    # Show the rebalance-order rule prominently
    st.info(
        "**Rebalance order (locked):**  on every rebalance date the "
        "factor-internal MVO weights are recomputed first (using returns "
        "≤ that date), then the bucket-equal allocation is rebuilt on top "
        "of those fresh intra-bucket weights.  Manual allocations skip "
        "TAA entirely.",
        icon="🔁",
    )

    sub = st.radio(
        "Allocation method",
        options=["Equal Weight (TAA-aware)", "Manual (TAA-independent)"],
        horizontal=True,
        key="sb_alloc_method",
    )

    # Faux rebalance date input — purely cosmetic in the sandbox because
    # the mock provider ignores `as_of`.  The wiring is real, so the
    # provider implementation can later honour the date.
    reb_date = st.text_input(
        "Rebalance as-of date (mock data ignores this)",
        value="2026-05-07", key="sb_reb_date",
    )

    # Pull the current strategy + params from session (set in Step 2)
    rf     = float(st.session_state.get("_taa_rf", 0.04))
    pick   = st.session_state.get("_taa_pick", "max_sharpe")
    target = st.session_state.get("_taa_target_return")
    mode   = ("passthrough" if st.session_state.get("_taa_strategy") == "passthrough"
              else "factor")

    if sub.startswith("Equal"):
        with st.spinner("Rebalance: recomputing factor MVO, then EW…"):
            weights, taa_fresh = rebalance_at(
                as_of=reb_date,
                universe=universe,
                provider=provider,
                taa_mode=mode,
                rf=rf, pick=pick, target_return=target,
                min_weight=float(st.session_state.get("_taa_min_w", 0.0)) / 100.0,
                max_weight=float(st.session_state.get("_taa_max_w", 100.0)) / 100.0,
            )
        st.caption(explain_equal_weight_rule(taa_fresh, universe))
        _render_weight_table(weights, capital)
        _render_bucket_breakdown(weights, universe)
    else:
        st.caption("Manual allocation is **never** affected by TAA. "
                   "(In the integrated app this opens the existing manual sub-page; "
                   "here we just echo a flat 0% template so you can verify the "
                   "decoupling.)")
        weights = {t: 0.0 for t in universe.tickers}
        _render_weight_table(weights, capital, allow_zeros=True)

    st.markdown("---")
    cols = st.columns([1, 5])
    with cols[0]:
        if st.button("← Back", use_container_width=True):
            st.session_state["sb_step"] = 2
            st.rerun()


# ── Shared display helpers ─────────────────────────────────────────────────────
def _render_weight_table(weights: dict, capital: float, allow_zeros: bool = False):
    if not weights:
        st.info("No weights to display.")
        return
    total = sum(weights.values())
    if total <= 0 and not allow_zeros:
        st.warning("Weights sum to zero.")
        return

    rows = "".join(
        f'<tr>'
        f'<td style="padding:4px 8px;font-family:monospace">{t}</td>'
        f'<td style="padding:4px 8px;text-align:right">{w*100:.2f}%</td>'
        f'<td style="padding:4px 8px;text-align:right">${w*capital:,.0f}</td>'
        f'</tr>'
        for t, w in sorted(weights.items(), key=lambda kv: -kv[1])
    )
    st.markdown(
        f'<table style="width:100%;font-size:12px;border-collapse:collapse">'
        f'<thead><tr style="border-bottom:1px solid #ddd">'
        f'<th style="text-align:left;padding:6px 8px">Ticker</th>'
        f'<th style="text-align:right;padding:6px 8px">Weight</th>'
        f'<th style="text-align:right;padding:6px 8px">USD</th></tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'<tfoot><tr style="border-top:1px solid #ddd;font-weight:600">'
        f'<td style="padding:6px 8px">TOTAL</td>'
        f'<td style="padding:6px 8px;text-align:right">{total*100:.2f}%</td>'
        f'<td style="padding:6px 8px;text-align:right">${total*capital:,.0f}</td>'
        f'</tr></tfoot></table>',
        unsafe_allow_html=True,
    )


def _render_bucket_breakdown(weights: dict, universe: MiniUniverse):
    """Stacked bucket-level summary so you can eyeball the (1/k) split."""
    bucket_w: dict = {}
    by_ticker_bucket = {a.ticker: a.bucket for a in universe.assignments}
    for t, w in weights.items():
        b = by_ticker_bucket.get(t, FactorBucket.UNASSIGNED)
        bucket_w[b] = bucket_w.get(b, 0.0) + w

    if not bucket_w:
        return

    label = {
        FactorBucket.GROWTH:      "GROWTH",
        FactorBucket.FIN_COND:    "FIN. COND",
        FactorBucket.INFLATION:   "INFLATION",
        FactorBucket.DIVERSIFIER: "DIVERSIFIER",
        FactorBucket.UNASSIGNED:  "UNASSIGNED",
    }
    st.markdown('<div style="margin-top:14px;font-size:11px;'
                'color:#666;letter-spacing:0.06em">BUCKET BREAKDOWN</div>',
                unsafe_allow_html=True)
    rows = "".join(
        f'<tr>'
        f'<td style="padding:3px 8px">{label[b]}</td>'
        f'<td style="padding:3px 8px;text-align:right">{w*100:.2f}%</td>'
        f'</tr>'
        for b, w in sorted(bucket_w.items(), key=lambda kv: -kv[1])
    )
    st.markdown(
        f'<table style="width:100%;font-size:11px;border-collapse:collapse">'
        f'<tbody>{rows}</tbody></table>',
        unsafe_allow_html=True,
    )


# ── Dispatch ──────────────────────────────────────────────────────────────────
step = st.session_state["sb_step"]
if step == 1:
    _render_step1()
elif step == 2:
    _render_step2()
elif step == 3:
    _render_step3()
