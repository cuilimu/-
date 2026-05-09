---
name: Page 1 Universe — Design Decisions & Locked Patterns
description: Screen-specific layout decisions, token usage, locked patterns, and rigor-upgrade decisions for the Stock Selection page (Step 1 of Simple Mode).
type: project
---

Page 1 is the Stock Selection & Universe Definition screen (Simple Mode Step 1). It has two columns: left (2.1 ratio) holds ticker list + correlation heatmap; right (3.7 ratio) holds factor buckets + All-Weather Map. A bottom bar holds stats and the Next nav button.

**Locked layout constants (do not change without explicit user direction):**
- Ticker row height: 36px (10 rows fixed, 360px total list height)
- Correlation heatmap height: 400px (left column, aligns with right column bottom)
- All-Weather Map height: 430px
- Factor Buckets panel: 440px (fills gap above AW Map so columns bottom-align)
- Column ratios: left 2.1 / right 3.7, gap="medium"
- Ticker list column widths: # 28px | ticker 80px | name flex | bucket 160px | del 40px

**Terminal zone:** Ticker list uses dark terminal bg (theme.TERMINAL_BG) with row sep (theme.TERMINAL_ROW_SEP).

**Factor color mapping (locked):**
- Growth → FACTOR_GROWTH (#4ade80)
- Fin. Conditions → FACTOR_FIN_COND (#378add)
- Inflation → FACTOR_INFLATION (#fb923c)
- Diversifier → FACTOR_DIVERSIFIER (#c084fc)
- Unassigned → FACTOR_UNASSIGNED (#94a3b8)

**Chart backgrounds:**
- Factor Buckets chart: dark CHART_BG (#111111)
- All-Weather Map: dark CHART_BG (#111111)
- Correlation heatmap: white MAIN_BG (#FFFFFF) — intentionally light for label legibility

**CSS file:** ui/styles/page1_universe.css. Loaded via _inject_css("page1_universe").

**Rigor-upgrade decisions (2026-05-09, "Bloomberg terminal grade" spec):**

Ticker List:
- Header bar (.p1-th): padding 0 4px 0 6px, height 24px, line-height 24px, font-family monospace, color var(--terminal-text). Removed raw rgba(255,255,255,0.88).
- Bucket indicator: changed from 5×5px inline-style dot to 2×16px vertical bar (.p1-bucket-dot class with data-bucket attribute). Eliminates inline style hex violation.
- BUCKET_SHORT values: all uppercase — "GROWTH", "FIN.COND", "INFL", "DIVERS", "–".
- Name column color: var(--text-secondary) → var(--terminal-name-dim). New token TERMINAL_NAME_DIM = "#2e2540".
- Delete button: font-size 11px, font-weight 400, width 24px (was 16px/300/28px).

Factor Bucket Chart:
- Quadrant labels: no <b> tags, size=9 monospace, pipe separator for count (e.g. "GROWTH | 3").
- Divider lines: solid (no dash), color=CHART_DIVIDER (#383838) — eliminates raw rgba string in .py.
- Quadrant fill opacity: 0.08 via _hex_alpha() helper (was 0.25 literal rgba).
- Markers: size=20 (was 26), color=CHART_BG dark fill (was MAIN_BG white), textfont size=10 color=CHART_TEXT (was bucket accent color at size=11).
- Empty indicator: "EMPTY" at size=9 monospace (was "—" at size=18).
- Margins: l=8, r=8, t=8, b=8 (was l=6, r=6, t=6, b=10 — off-grid).
- Axis range tightened to [-0.08, 2.08] (was [-0.15, 2.15]).

All-Weather Map:
- Axis labels: removed add_annotation "Growth ->" and "Inflation ^" ASCII arrows. Replaced with native Plotly axis titles "GROWTH BETA" / "INFLATION BETA" at size=9 monospace CHART_AXIS_LABEL color.
- Tick labels: showticklabels=True (was False), tickvals=[-1.0,-0.5,0.0,0.5,1.0], size=8 monospace.
- Zeroline: zeroline=True, zerolinecolor=CHART_DIVIDER, zerolinewidth=1. Removed redundant manual add_shape divider lines (which contained raw rgba strings).
- Markers: size=16 (was 20), color=CHART_BG dark fill (was MAIN_BG white), textposition="middle center" (was "top center"), textfont size=8 color=CHART_TEXT.
- Quadrant labels: no <b> tags, size=9, positions at cx*1.44 / cy*1.60 corners (was cx*0.78/cy*0.84 — too close to center).
- Empty warning: "NO DATA" at size=8 monospace (was "empty" at size=9), positions at ±0.75 corners (was ±0.50).
- Margins: l=48, r=16, t=8, b=40 (was l=6, r=6, t=6, b=24 — off-grid and no room for axis titles/ticks).

New tokens added (2026-05-09 rigor upgrade):
- TERMINAL_NAME_DIM = "#2e2540" — name column text on dark terminal bg. Slots between TERMINAL_DIM and TERMINAL_TEXT. Add to theme.py terminal block and --terminal-name-dim CSS var.
- CHART_AXIS_LABEL = "#888888" — axis title text on dark charts, subordinate to CHART_AXIS (#aaaaaa). Add to theme.py chart block and --chart-axis-label CSS var.
- CHART_DIVIDER = "#383838" — structural divider lines on dark chart bg (solid, no rgba). Replaces raw rgba() strings in Plotly add_shape calls.

Factor CSS vars needed in :root (theme.py CUSTOM_CSS):
- --factor-growth (#4ade80), --factor-fin-cond (#378add), --factor-inflation (#fb923c), --factor-diversifier (#c084fc), --factor-unassigned (#94a3b8)
- --terminal-name-dim (#2e2540)
- --chart-axis-label (#888888)

**Violations found in pre-rigor code:**
- .p1-th used raw rgba(255,255,255,0.88) in CSS — replaced with var(--terminal-text).
- _render_ticker_row injected inline style="background:{color}" hex on bucket dot — eliminated via data-bucket CSS rules.
- _QUAD_PALETTE and _AW_QUAD_PALETTE used literal rgba strings — replaced with _hex_alpha() helper calls.
- add_shape divider lines used raw "rgba(255,255,255,0.2)" strings in .py — eliminated by switching to CHART_DIVIDER token.
- All-Weather Map margin l=6 was off the 8px grid.
- Factor Bucket chart margin b=10 was off the 8px grid.

**Deferred violations (out of scope for this spec):**
- _BBG_WARN = "rgba(217,119,6,0.75)" at line 140 — raw rgba in .py. Future token: CHART_WARN = "#d97706".

**Why:** Identified in the 2026-05-09 Bloomberg-terminal-grade rigor redesign.
**How to apply:** All future work on this page must maintain: uppercase BUCKET_SHORT convention; dark marker fill (CHART_BG not MAIN_BG); native axis titles (not add_annotation); 8px margin grid; _hex_alpha() for Plotly rgba fills derived from theme constants; data-bucket attribute for bucket color indicators (not inline style).
