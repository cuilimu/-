---
name: Econometrics Console — Design Spec Decisions
description: Design decisions for LR/ARIMAX co-location question. Proposal A (merge into one step) was WITHDRAWN 2026-05-09 after taxonomy correction.
type: project
---

**PROPOSAL A (Unified Econometrics Console) — WITHDRAWN 2026-05-09.**

Reason: After taxonomy correction, Regression Analysis (factor_workspace_tab) is a portfolio attribution instrument, not a free-standing econometrics tool. It is architecturally tied to BacktestResult: workspace is initialized from BacktestResult.snapshots, FF5 auto-regression runs against the specific portfolio composition. Moving LR to a shared Econometrics Console with ARIMAX severs the interpretive link between regression output and the backtest that produced it.

**Locked decision: LR stays in Step 5 (Performance Eval). ARIMAX stays at Step 8.**

**Cross-reference bridge (approved alternative):**
Instead of co-location, implement two targeted changes:
1. A terminal-style link chip in the Regression Analysis sub-tab header: "ARIMAX → STEP 8" in theme.MAIN_TEXT_SECONDARY, 10px monospace, calls set_step(8) on click.
2. Optional workspace variable carry-over: residuals/fitted values from LR workspace could be surfaced as supplemental MEV options in ARIMAX — a data bridge, not a UI merge.

**Why Proposal A was wrong:** The Factor Decomposition Results table (cross-ticker regression summary in _render_decomposition_table) is a portfolio-evaluation artifact. It summarizes factor attribution per constituent from a specific backtest. It belongs in Performance, not in an isolated econometrics step. The analyst who sees alpha=0.08 on mktrf needs the backtest context to interpret it.

**Session scoping (still valid for cross-reference bridge):**
If the bridge is implemented, prefix all ARIMAX session state keys arx_, linear regression keys lr_. No shared mutable widget state. Shared read-only context (dates, tickers, capital) read from ResearchSession.universe.

**How to apply:** When the cross-reference bridge is implemented, the chip lives in factor_workspace_tab.py's _render_regression_tab, just below the Regression Analysis sub-tab header, before the workspace DataFrame expander.
