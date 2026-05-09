---
name: Workflow Taxonomy — Corrected Step Definitions
description: Locked step definitions and ordering for the 8-step Simple Mode workflow, corrected 2026-05-09 after prior session misread the taxonomy.
type: project
---

**Canonical 8-step order (LOCKED as of 2026-05-09):**

| Step | Nav Label | _STEP_FULL | What it does |
|------|-----------|------------|--------------|
| 1 | MACRO | MACRO OVERVIEW | Macro regime read-in, yield curve, credit spreads |
| 2 | UNIVERSE | STOCK SELECTION | Stock selection, factor bucket assignment |
| 3 | SAA | SAA — ALLOCATION | Cross-factor capital allocation (EW / Manual / Risk Parity / MVO across buckets) |
| 4 | TAA | TAA — INTRA-BUCKET | Factor-internal MVO — weights within each bucket |
| 5 | PERFORMANCE | PERFORMANCE EVAL | Backtest + Factor Decomposition (Regression Analysis sub-tab lives here) |
| 6 | RISK | RISK EVALUATION | Risk evaluation |
| 7 | TAA SCENARIOS | TAA SCENARIO TILTS | Macro scenario/regime tilts on the TAA layer (rate shocks, stagflation, etc.) |
| 8 | ARIMAX | ARIMAX FORECAST | SARIMAX(p,d,q) time-series forecast with FRED MEVs as regressors |

**Critical ordering rule:** SAA (Step 3) MUST precede TAA (Step 4). TAA is a child operation of SAA. MVO on intra-bucket weights (TAA) before cross-bucket allocations are set (SAA) is computationally incoherent. The sidebar weight bounds (min/max per asset) apply to TAA Step 4 only.

**Prior error (corrected 2026-05-09):** Live code in simple_aa.py had Steps 3 and 4 swapped (TAA at 3, SAA=labeled "Allocation" at 4). The prior session's flag "SAA at Step 7 is conceptually inverted" was based on misreading Step 7 as SAA — Step 7 is actually TAA Scenario Tilts.

**Regression Analysis location:** Lives in Step 5 Performance Eval, factor_workspace_tab.py, as sub-tab "Regression Analysis" under "Factor Decomposition". This is correct — LR is tied to the BacktestResult and belongs in the attribution/evaluation arc. It is NOT a free-standing econometrics tool.

**ARIMAX dependency chain:** Requires at least one computed portfolio (CandidateStatus.COMPUTED with backtest_result not None). Gate screen in page8_arimax.py shows dependency on Step 3 (SAA) and Step 4 (TAA) in sequence.

**Step 7 TAA Scenarios:** Stress tests the existing portfolio under macro regime changes. Answers "what happens to my TAA weights under a rate shock?" Comes before ARIMAX because it analyzes the existing portfolio; ARIMAX forecasts future returns from the portfolio's historical series.

**How to apply:** Any nav label change, step reorder, or new step proposal must respect SAA→TAA ordering. Do not merge Step 5 Regression Analysis with Step 8 ARIMAX (Proposal A — withdrawn).
