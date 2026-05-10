---
name: UI hard rules — no hex literals, no style blocks
description: Enforced rules for all .py files under ui/components and ui/app.py
type: feedback
---

No `<style>` blocks in .py files. No hex color literals (#RRGGBB or #RGB) in .py files.

**Why:** A 2026-05-07 refactor extracted ~84 KB of CSS and 2507 lines of duplicate styling from Python files. Re-introducing hex literals or inline styles undoes that work. Changing the brand purple used to require editing ~62 hardcoded strings across 17 files.

**How to apply:**
- Colors for Plotly traces come from `ARX_LIGHT_THEME` attributes (color_portfolio, color_gain, color_loss, color_neutral, color_cash) imported from `stock_engine.viz.theme`.
- Additional tokens (CHART_SERIES_PALETTE, CORR_COLORSCALE, etc.) come from `stock_engine.ui.theme`.
- CSS lives in `ui/styles/<name>.css`, loaded via `_inject_css("<name>")`.
- Before declaring any UI change done, run:
  `rg -n '#[0-9a-fA-F]{6}' ui/components ui/app.py` — must return no matches.
  `rg -l '<style>' ui/components ui/app.py` — must return no matches.
