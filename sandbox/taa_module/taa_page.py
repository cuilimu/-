"""
taa_page.py — Streamlit renderer for the TAA step.

Layout:
  ┌──────────────────────────────────────────────────────────┐
  │ STRATEGY  ( ) Passthrough  (•) Factor MVO  ( ) [coming]  │
  ├──────────────────────────────────────────────────────────┤
  │ rf [0.04]   pick [Max Sharpe ▼]   target_return [—]      │
  ├──────────────────────────────────────────────────────────┤
  │ [▶ Run MVO]   status: up-to-date / params changed        │
  ├──────────────────────────────────────────────────────────┤
  │ ↓↓  Single matplotlib overview report (5 rows)  ↓↓       │
  ├──────────────────────────────────────────────────────────┤
  │ SAVED RUNS  [label input]  [💾 Save]                      │
  │   Run 1 ✓ (active) · Base case  [Load] [✕]               │
  │   Run 2 · Aggressive            [Load] [✕]               │
  └──────────────────────────────────────────────────────────┘

Compute is triggered ONLY by the "▶ Run MVO" button — parameter changes
alone no longer auto-start the simulation. Named runs can be saved to
session state and restored via "Load".
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from stock_engine.sandbox.taa_module.factor_mvo import (
    Pick, TAAResult, compute_factor_mvo, passthrough_result,
)
from stock_engine.sandbox.taa_module.overview_chart import render_taa_overview
from stock_engine.sandbox.taa_module.strategies import REGISTRY, get_strategy
from stock_engine.sandbox.taa_module.types import FactorBucket, MiniUniverse

_PICK_LABELS = {
    "max_sharpe": "Max Sharpe",
    "gmv":        "Min Variance",
    "target":     "Target Return",
}

# ── Session-state keys ────────────────────────────────────────────────────────
_K_STRATEGY  = "_taa_strategy"
_K_RF        = "_taa_rf"
_K_PICK      = "_taa_pick"
_K_TARGET    = "_taa_target_return"
_K_MIN_W     = "_taa_min_w"
_K_MAX_W     = "_taa_max_w"
_K_CACHE     = "_taa_cache"
_K_CACHE_KEY = "_taa_cache_key"
_K_DIRTY     = "_taa_dirty"       # True when params changed since last run
_K_SAVED     = "_taa_saved_runs"  # list[dict] — named save slots
_K_PEND_LOAD = "_taa_pending_load"  # pending param/result restore from Load


# ── Public entry ───────────────────────────────────────────────────────────────

def render_taa_page(
    universe: MiniUniverse,
    provider,
) -> Optional[TAAResult]:
    """Render the TAA controls + overview report. Returns the active TAAResult
    or None if the universe is empty / no run has been executed yet."""
    if not universe.tickers:
        st.info("Universe is empty — assign at least one ticker to a bucket "
                "in the previous step.")
        return None

    # Apply a pending param/result restore from "Load" BEFORE any widgets
    # render so they pick up the restored values immediately.
    _apply_pending_load()

    # ── Defaults (only sets if key absent — does not overwrite loaded values) ──
    st.session_state.setdefault(_K_STRATEGY, "factor_mvo")
    st.session_state.setdefault(_K_RF,       0.04)
    st.session_state.setdefault(_K_PICK,     "max_sharpe")
    st.session_state.setdefault(_K_TARGET,   None)
    st.session_state.setdefault(_K_MIN_W,    5.0)
    st.session_state.setdefault(_K_MAX_W,    80.0)
    st.session_state.setdefault(_K_DIRTY,    True)
    st.session_state.setdefault(_K_SAVED,    [])

    # ── Strategy selector ──────────────────────────────────────────────
    st.markdown("##### STRATEGY")
    avail_pairs = [(s.id, s.label) for s in REGISTRY if s.available]
    cur_id  = st.session_state[_K_STRATEGY]
    cur_idx = ([p[0] for p in avail_pairs].index(cur_id)
               if cur_id in [p[0] for p in avail_pairs] else 0)
    picked_id = st.radio(
        "TAA strategy",
        options=[p[0] for p in avail_pairs],
        format_func=lambda i: dict(avail_pairs)[i],
        index=cur_idx, key=_K_STRATEGY,
        horizontal=True, label_visibility="collapsed",
    )
    for s in REGISTRY:
        if not s.available:
            st.caption(f"○ {s.label} — *{s.description}*")

    strat = get_strategy(picked_id)
    if strat:
        st.caption(strat.description)

    # ── Sub-controls only visible for factor_mvo ──────────────────────
    if picked_id == "factor_mvo":
        c1, c2, c3 = st.columns([1, 1.2, 1.6])
        with c1:
            st.number_input(
                "Risk-free rate (annual)",
                min_value=0.0, max_value=0.20, step=0.005,
                format="%.3f", key=_K_RF,
            )
        with c2:
            pick_opts = ["max_sharpe", "gmv", "target"]
            st.selectbox(
                "Pick from frontier",
                options=pick_opts,
                format_func=lambda v: _PICK_LABELS[v],
                index=pick_opts.index(st.session_state[_K_PICK]),
                key=_K_PICK,
            )
        with c3:
            if st.session_state[_K_PICK] == "target":
                tgt_in = st.number_input(
                    "Target return (annual; blank = median μ per bucket)",
                    min_value=0.0, max_value=1.0, step=0.01, format="%.3f",
                    value=(st.session_state[_K_TARGET]
                           if st.session_state[_K_TARGET] is not None else 0.0),
                    key=_K_TARGET + "_input",
                )
                st.session_state[_K_TARGET] = (tgt_in if tgt_in > 0 else None)
            else:
                st.caption("Target return only used when pick = Target Return.")

        if st.session_state.get("_taa_global_bounds_set"):
            min_w = float(st.session_state.get(_K_MIN_W, 5.0))
            max_w = float(st.session_state.get(_K_MAX_W, 80.0))
            st.caption(
                f"Weight bounds: **{min_w:.0f}% – {max_w:.0f}%** per asset "
                f"(set globally in the sidebar)"
            )
        else:
            c4, c5, _ = st.columns([1, 1, 1.8])
            with c4:
                st.number_input(
                    "Min weight / asset (%)",
                    min_value=0.0, max_value=50.0, step=1.0, format="%.0f",
                    key=_K_MIN_W,
                    help="Lower bound per asset. Prevents the optimizer from "
                         "zeroing out positions. Auto-clamped if n × min > 100%.",
                )
            with c5:
                st.number_input(
                    "Max weight / asset (%)",
                    min_value=10.0, max_value=100.0, step=5.0, format="%.0f",
                    key=_K_MAX_W,
                    help="Upper bound per asset. Limits concentration within a bucket.",
                )

    st.markdown("---")

    # ── Passthrough shortcut (no compute needed) ──────────────────────
    if picked_id == "passthrough":
        taa = passthrough_result(universe, rf=float(st.session_state[_K_RF]))
        _render_passthrough_summary(universe)
        return taa

    # ── Detect param drift ────────────────────────────────────────────
    cache_key = _build_cache_key(
        universe,
        rf=float(st.session_state[_K_RF]),
        pick=st.session_state[_K_PICK],
        target=st.session_state[_K_TARGET],
        min_w=float(st.session_state[_K_MIN_W]),
        max_w=float(st.session_state[_K_MAX_W]),
    )
    if st.session_state.get(_K_CACHE_KEY) != cache_key:
        st.session_state[_K_DIRTY] = True

    has_result = st.session_state.get(_K_CACHE) is not None
    dirty      = bool(st.session_state.get(_K_DIRTY, True))

    # ── Run button + status row ───────────────────────────────────────
    c_btn, c_status = st.columns([1, 3])
    with c_btn:
        run_clicked = st.button(
            "▶ Run MVO",
            type="primary",
            use_container_width=True,
            help=(
                "Run Monte-Carlo + efficient-frontier scan for all 4 factor "
                "buckets. Results are cached — clicking again with the same "
                "parameters is instant."
            ),
        )
    with c_status:
        if not has_result:
            st.info("Set parameters above, then click **▶ Run MVO** to compute.")
        elif dirty:
            st.warning("Parameters changed since last run — click **▶ Run MVO** to update.")
        else:
            st.success("Results are up to date.")

    # ── Compute only when button is explicitly clicked ────────────────
    if run_clicked:
        with st.spinner(
            "Computing factor MVO + Monte-Carlo + frontier scans "
            "for all 4 buckets…"
        ):
            taa = compute_factor_mvo(
                universe, provider,
                rf=float(st.session_state[_K_RF]),
                pick=st.session_state[_K_PICK],
                target_return=st.session_state[_K_TARGET],
                with_diagnostics_for_all_buckets=True,
                compute_factor_exposures=True,
                min_weight=float(st.session_state[_K_MIN_W]) / 100.0,
                max_weight=float(st.session_state[_K_MAX_W]) / 100.0,
            )
        st.session_state[_K_CACHE]     = taa
        st.session_state[_K_CACHE_KEY] = cache_key
        st.session_state[_K_DIRTY]     = False

    taa: Optional[TAAResult] = st.session_state.get(_K_CACHE)
    if taa is None:
        # No run yet — nothing to show below.
        _render_save_panel(cache_key, taa=None)
        return None

    # ── Render overview + footer notes ────────────────────────────────
    render_taa_overview(universe, taa)
    _render_footer_notes(taa)

    # ── Save / load panel ─────────────────────────────────────────────
    _render_save_panel(cache_key, taa=taa)

    return taa


# ── Save / load panel ─────────────────────────────────────────────────────────

def _render_save_panel(cache_key: str, taa: Optional[TAAResult]) -> None:
    """Controls for saving the current run and browsing past saved runs."""
    st.markdown("---")
    saved: list[dict] = st.session_state.setdefault(_K_SAVED, [])

    st.markdown("##### SAVED RUNS")

    # ── Save current run ──────────────────────────────────────────────
    already_saved = taa is not None and any(
        r["cache_key"] == cache_key for r in saved
    )
    c_lbl, c_save = st.columns([3, 1])
    with c_lbl:
        label = st.text_input(
            "Run label",
            placeholder="e.g. Base case — Q2 2026",
            key="_taa_save_label_input",
            label_visibility="collapsed",
            disabled=taa is None,
        )
    with c_save:
        save_help = (
            "No results to save yet — run the MVO first." if taa is None
            else "Already saved." if already_saved
            else "Save the current results as a named snapshot."
        )
        if st.button(
            "💾 Save",
            disabled=(taa is None or already_saved),
            use_container_width=True,
            help=save_help,
        ):
            entry = {
                "label":     label.strip() or f"Run {len(saved) + 1}",
                "cache_key": cache_key,
                "taa":       taa,
                "saved_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
                "params":    _extract_params(),
            }
            saved.append(entry)
            st.session_state[_K_SAVED] = saved
            st.toast(f"Saved: \"{entry['label']}\"")

    # ── Saved runs list ───────────────────────────────────────────────
    if not saved:
        st.caption(
            "No saved runs yet. Run the MVO and click **💾 Save** to keep a "
            "named snapshot you can return to later."
        )
        return

    for i, r in enumerate(saved):
        p          = r["params"]
        is_active  = (r["cache_key"] == cache_key)
        badge      = " · ✓ **active**" if is_active else ""
        pick_label = _PICK_LABELS.get(p["pick"], p["pick"])

        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.markdown(
                    f"**{r['label']}**{badge}  \n"
                    f"<small style='color:#888'>"
                    f"{r['saved_at']} &nbsp;·&nbsp; "
                    f"rf = {p['rf']:.3f} &nbsp;·&nbsp; "
                    f"{pick_label} &nbsp;·&nbsp; "
                    f"bounds {p['min_w']:.0f}% – {p['max_w']:.0f}%"
                    f"</small>",
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button(
                    "Load",
                    key=f"_taa_load_{i}",
                    use_container_width=True,
                    disabled=is_active,
                    help="Restore these parameters and results.",
                ):
                    # Store the full entry as pending; it will be applied at
                    # the top of the next render call before widgets render.
                    st.session_state[_K_PEND_LOAD] = r
                    st.rerun()
            with c3:
                if st.button(
                    "✕",
                    key=f"_taa_del_{i}",
                    use_container_width=True,
                    help="Delete this saved run.",
                ):
                    saved.pop(i)
                    st.session_state[_K_SAVED] = saved
                    st.rerun()


def _apply_pending_load() -> None:
    """Apply a pending saved-run restore.

    Called at the very top of render_taa_page — before any widgets render —
    so that widget keys read the restored values on this rerun.
    """
    pending = st.session_state.pop(_K_PEND_LOAD, None)
    if pending is None:
        return
    p = pending["params"]
    st.session_state[_K_RF]        = p["rf"]
    st.session_state[_K_PICK]      = p["pick"]
    st.session_state[_K_TARGET]    = p.get("target")
    st.session_state[_K_MIN_W]     = p["min_w"]
    st.session_state[_K_MAX_W]     = p["max_w"]
    st.session_state[_K_CACHE]     = pending["taa"]
    st.session_state[_K_CACHE_KEY] = pending["cache_key"]
    st.session_state[_K_DIRTY]     = False


def _extract_params() -> dict:
    """Snapshot the current MVO parameter values for storage in a saved entry."""
    return {
        "rf":     float(st.session_state.get(_K_RF, 0.04)),
        "pick":   str(st.session_state.get(_K_PICK, "max_sharpe")),
        "target": st.session_state.get(_K_TARGET),
        "min_w":  float(st.session_state.get(_K_MIN_W, 5.0)),
        "max_w":  float(st.session_state.get(_K_MAX_W, 80.0)),
    }


# ── Existing helpers (unchanged) ──────────────────────────────────────────────

def _build_cache_key(universe: MiniUniverse, rf: float,
                     pick: str, target: Optional[float],
                     min_w: float = 0.0, max_w: float = 100.0) -> str:
    parts = ",".join(f"{a.ticker}:{a.bucket.value}"
                     for a in universe.assignments)
    return f"{parts}|{rf:.4f}|{pick}|{target}|{min_w:.1f}|{max_w:.1f}"


def _render_passthrough_summary(universe: MiniUniverse) -> None:
    n  = len(universe.tickers)
    eq = 100.0 / n if n else 0.0
    st.markdown(
        f"**Passthrough mode** — TAA does not change anything. "
        f"Equal-weight on Allocation page = **{eq:.2f}%** per ticker "
        f"({n} ticker{'s' if n != 1 else ''})."
    )
    rows = "".join(
        f'<tr><td style="padding:3px 8px;font-family:monospace">{t}</td>'
        f'<td style="padding:3px 8px;text-align:right">{eq:.2f}%</td></tr>'
        for t in universe.tickers
    )
    st.markdown(
        f'<table style="width:100%;font-size:11px;border-collapse:collapse">'
        f'<thead><tr style="border-bottom:1px solid #ddd">'
        f'<th style="text-align:left;padding:4px 8px">Ticker</th>'
        f'<th style="text-align:right;padding:4px 8px">EW weight</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>',
        unsafe_allow_html=True,
    )


def _render_footer_notes(taa: TAAResult) -> None:
    st.markdown("---")
    notes = []
    for bucket, sol in taa.bucket_solutions.items():
        if sol.note:
            notes.append(f"**{bucket.value}**: {sol.note}")
        for w in sol.mvo_result.warnings:
            notes.append(f"**{bucket.value}**: {w}")
    if taa.ignored_tickers:
        notes.append("UNASSIGNED tickers excluded from factor MVO: "
                     + ", ".join(taa.ignored_tickers))
    if notes:
        for n in notes:
            st.caption(f"⚠ {n}")
