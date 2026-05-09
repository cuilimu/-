---
name: ARIMAX page design decisions
description: Locked decisions for Step 8 ARIMAX Forecast page redesign — spec produced 2026-05-07
type: project
---

**Wizard abolition (locked):** The inner 7-step ARIMAX wizard is replaced by a single scrollable configuration panel inside one `st.expander("CONFIGURATION")`. Reason: wizard-inside-wizard creates two competing navigation models. Terminal UX shows all fields; analyst scans and edits rather than clicking Next.

**Command bar pattern (locked):** A `.summary-bar` strip at the top of `render_arimax_tab()` always shows: status pills (Target, MEVs, Model, Rules), observation count, Run button, Reset button. Run button is enabled when `arx_target_df` and `arx_mev_df` are both ready. This eliminates Step-7-only run trigger.

**Status pills:** `COLOR_GAIN` (#00b050) dot when ready, `COLOR_LOSS` (#e03030) dot when not ready, `COLOR_NEUTRAL` (#666666) for partial state (e.g. MEVs selected but not fetched).

**Results hierarchy (locked):** After run, Zone C renders in this order:
1. Results header bar (section-header style)
2. `forecast_with_ci_chart` for model rank 0 — full width, NO expander wrapper, height 560px
3. Model ranking table — `st.dataframe`, monospace 10px numerics
4. `st.tabs()` — one tab per top model (residuals) + Target Diagnostics + CV Forecasts + Download

Maximum ONE disclosure level (tabs). No expanders inside tabs. This is a hard rule.

**Config expander auto-collapse:** `arx_ran_once` session state flag. After successful run, expander defaults to `expanded=False`. Re-expanding preserves all values.

**Token violations fixed (in spec):**
- `arimax_tab.py` lines 487-490: hardcoded `#3b82f6`, `#94a3b8`, `#cbd5e1` → replace with `CHART_PORTFOLIO`, `MAIN_TEXT_SECONDARY`, `CHART_BENCHMARK` tokens.
- `arimax_charts.py` line 201: hardcoded `rgba(255,167,38,0.30)` → new token `CHART_CI_FILL_ALPHA` in `ui/theme.py`, new field `ci_fill_color` in `VizTheme`.

**New token added:** `CHART_CI_FILL_ALPHA = "rgba(255,167,38,0.30)"` — exception to hex-only rule because Plotly requires rgba string for semi-transparent fills. Single-sourced in `ui/theme.py`.

**Train/test bar:** Two contiguous `<div>` blocks, height 8px, CSS `width` proportional to `train_threshold`. Colors: `CHART_PORTFOLIO` (train) and `CHART_BENCHMARK` (test). Labels above at 10px monospace. Replaces the 14px oversized monospace glyph string.

**st.success() replaced:** All routine status confirmations in ARIMAX use inline HTML colored dot + text, not `st.success()` alert boxes (which have consumer-grade padding and radius).

**Step 7 review textarea height:** 160px (down from 260px). Analyst sets fields visually; textarea is copy-paste artifact only.

**`_render_step_indicator()` and `_render_nav()` functions:** Removed from render path. Session state key `arx_step` retained as internal completion-tracking variable for section header glyphs.

**Chart title font:** `size=12` in `_layout()` (reduced from 14) to match `FONT_SIZE_BASE` + 1 scale.

**Why:** The user asked for a design plan for Step 8. The spec concluded wizard-in-wizard is the primary UX failure; all other decisions follow from fixing that root cause.
**How to apply:** Do not re-introduce the step indicator or nav buttons in ARIMAX. Do not add new expander nesting inside results. These are locked.
