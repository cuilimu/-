# App Redesign Plan — Investment Research Platform

*Last updated: 2026-05-05 — UI design for all 6 pages finalized*

---

## 1. Design Principles

1. **All existing features are preserved.** Reorganisation only — no deletions.
2. **Simple mode is the primary research workflow.** Group mode and Multi-date mode remain independent and unchanged in scope.
3. **Universe-fixed assumption.** The new AA workflow operates on a locked asset universe. Dynamic rule-based rebalancing (factor investing, quarterly reconstitution) is explicitly out of scope for this redesign.
4. **Compute layer separated from UI layer.** Every calculation module must be callable independently of the UI, so ML backends can be swapped in later without touching frontend code.
5. **Session object is the single source of truth.** All pages within Simple mode read from and write to one shared ResearchSession. No page owns its own independent state.
6. **Bloomberg terminal aesthetic.** Dense layout, 9–11px fonts, monospace terminal output for factor results, dark chart areas (#111). Color system: Tsinghua Purple (#660874 / #8a0a9e), gain=#00b050, loss=#e03030, Growth=green #4ade80, Fin.Cond.=blue #378add, Inflation=orange #fb923c, Diversifier=purple #c084fc.

---

## 2. Mode Architecture (Top Level)

```
┌─────────────────────────────────────────────────────────────┐
│                        App Entry                            │
│   Row 1: Portfolio Scope  →  [ Simple Mode ] | Group Mode   │
│   Row 2: Execution Mode   →  [ One-day Buy ] | Multi-date   │
│                         "Start Simulation →"                │
└──────────────┬──────────────────────┬───────────────────────┘
               │                      │                      │
               ▼                      ▼                      ▼
   ┌───────────────────┐  ┌───────────────────┐  ┌──────────────────┐
   │   SIMPLE MODE     │  │   GROUP MODE      │  │ MULTI-DATE MODE  │
   │  (primary)        │  │  (unchanged)      │  │  (unchanged)     │
   │  6-page research  │  │                   │  │                  │
   │  workflow → SAA   │  │                   │  │                  │
   │  → TAA → Execute  │  │                   │  │                  │
   └───────────────────┘  └───────────────────┘  └──────────────────┘
          │
          ▼
   6-page workflow (§4)
```

Simple + One-day Buy = full 6-step AA pipeline unlocked.
Group mode and Multi-date mode are **not modified** by this redesign.

---

## 3. ResearchSession — Core Data Contract

```
ResearchSession
├── session_id          str
├── created_at          datetime
│
├── universe            Universe
│   ├── tickers         List[str]
│   ├── purchase_date   date                 # set in Page 1, locked downstream
│   ├── backtest_start  date                 # set in Page 1, locked downstream
│   ├── backtest_end    date                 # set in Page 1, locked downstream
│   └── assets          Dict[str, AssetMeta]
│                           ├── asset_class   Enum[equity|bond|commodity|cash|etf]
│                           ├── factor_bucket Enum[growth|fin_cond|inflation|diversifier|unassigned]
│                           ├── sector        str | None
│                           ├── region        str | None
│                           └── user_tags     List[str]
│
├── portfolios          List[PortfolioCandidate]
│   └── PortfolioCandidate
│       ├── candidate_id    str
│       ├── label           str          # "Equal Weight", "Manual", etc.
│       ├── method          Enum         # equal_weight | manual | mvo | risk_parity | ...
│       ├── weights         Dict[str, float]
│       ├── constraints     Dict
│       ├── backtest_result BacktestResult | None
│       ├── risk_result     RiskResult   | None
│       └── stale           bool
│
├── saa                 PortfolioCandidate | None
├── taa                 TAAScenario | None
│   ├── base_saa        ref → saa
│   ├── active_scenario str                  # e.g. "high_inflation", "recession", "custom"
│   ├── adjustments     Dict[str, float]     # ticker → delta from SAA weight (normalised)
│   ├── rationale       str
│   └── backtest_result BacktestResult | None
│
└── ml_extension        MLExtensionSlot | None   # reserved
```

**Staleness rule:** When a PortfolioCandidate's weights change, its `backtest_result` and `risk_result` are marked `stale=True`. UI shows a "Re-run" prompt. Results are never silently invalidated.

---

## 4. Six-Page Workflow (Simple Mode)

### Navigation Model

Left-side stepper. User can jump to any page freely — no forced linear gating. Downstream pages show a "⚠ results may be stale" banner if upstream input changed since last calculation.

```
[1] Stock Selection  →  [2] Allocation Research  →  [3] Performance  →  [4] Risk  →  [5] SAA  →  [6] TAA
                                                                                              ↓
                                                                                      [Execute / Same Day Buy]
```

---

### Page 1 — Stock Selection & Universe Definition

**Purpose:** Define asset universe, assign factor buckets, set backtest period.

**Layout:** Sidebar (130px) | Ticker list (148px) | Right panel (stacked top/bottom)

**Backtest period selector (new):**
- Purchase date picker + backtest start date → locked for all downstream steps
- Displayed as a locked tag on Pages 2–6

**Right panel — Top half: Factor Buckets 2×2 (manual drag)**
- 4 cells: Growth (green) | Fin. Conditions (blue) | Inflation (orange) | Diversifier (purple)
- Asset chips dragged into cells; unassigned pool bar below the grid
- Feeds risk-parity optimizer in Step 2

**Right panel — Bottom half: All-Weather Map (auto-assigned, read-only)**
- SVG coordinate chart: X = Growth↓↑, Y = Inflation↓↑
- 4 quadrants: Stagflation (top-left) | Goldilocks (top-right) | Recession (bottom-left) | Expansion (bottom-right)
- Assets plotted as colored circles by macro characteristic (lookup table)
- Unassigned shown as dashed grey circle at origin
- ⚠ warnings appear in sparse quadrants
- Validation layer only — does not affect optimization

**Correlation heatmap (new) — collapsible inline panel below asset list:**
- Activates when: ≥2 assets selected AND purchase date confirmed
- Data window: `[purchase_date − 6M, purchase_date)` — no look-ahead bias
- Lookback selector: 3M / 6M (default) / 12M / 1Y
- Purpose: identify redundant asset pairs and diversifiers before allocation

**Asset color coding in ticker list:** green = Growth, blue = Fin.Cond., orange = Inflation, purple = Diversifier, grey = unassigned

**Output to session:** `ResearchSession.universe` (tickers, factor_bucket tags, purchase_date, backtest dates)

---

### Page 2 — Allocation Research

**Purpose:** Build and compare portfolio weight strategies on the locked universe.

**Active methods:** Equal Weight | Manual
**Placeholder methods (greyed, future sub-pages):** Risk Parity | MVO | others

**Left config panel:**
- Global constraints (min/max weight per asset)
- Bucket-level bounds (e.g. Growth 30–60%)
- Rebalancing frequency + threshold
- Transaction cost assumptions: commission bps, bid-ask spread, market impact, slippage model; per-candidate override available

**Candidate cards:**
- Factor allocation stacked bar (bucket breakdown)
- Per-asset weight bars
- Status tags: computed (green) / not run (purple) / stale (orange)

**Output to session:** `ResearchSession.portfolios[]`

**ML extension point (future):** Expected return vector for MVO replaceable by ML predictor. Interface: `→ Dict[str, float]`.

---

### Page 3 — Performance Evaluation

**Purpose:** Comprehensive return-based assessment across all portfolio candidates.

**Tab structure:** Overview | BackTest | Portfolio | Factor Decomposition | Return Analysis

Backtest period shown as locked tag — cannot be changed here.

**BackTest tab:**
- Cumulative Return chart: all strategies + BM overlaid; click legend to isolate one strategy
- Drawdown chart: same multi-overlay + legend isolation
- Daily Return chart: single-strategy dropdown (too noisy multi-overlay)

**Portfolio tab:** per-candidate detail view (existing portfolio breakdown charts)

**Factor Decomposition tab** (≈ original app, minimal changes):
- Sub-tabs: Regression Analysis | Univariate Analysis | Bivariate Analysis
- Regression Analysis:
  - Full scrollable Data Table (Date + FF factors + rf + umd + each strategy + each stock); supports `gen` new columns (STATA-style)
  - "Run All Constituents" button: runs regression for all portfolios + all stocks at once
  - 8 STATA verbs: reg / corr / summ / scatter / rolling / gen / drop / ls
  - Command builder: Y variable = each configured strategy (EW, Manual, ...) + individual stocks; unconfigured strategies greyed (disabled)
  - STATA syntax preview bar + Run button + terminal-style output memo
  - Results: **two separate tables** with identical format (Ticker/Portfolio | Alpha monthly% | MKTRF | SMB | HML | RMW | CMA | N Obs, each row showing coef / (t-stat) / [p-value]):
    1. Portfolio Factor Decomposition (EW, Manual, ...) — purple left border on rows
    2. Individual Stocks Factor Decomposition

**Return Analysis tab:**
- Shared config section (cost assumptions, tax scenario, inflation rate, etc.)
- One summary card per strategy showing 2–3 key return metrics
- Click card → full existing profiler page (all profiler content preserved: Return Metrics, Timing & Attribution, Annualization Check, Flowchart, Arith vs Geo chart, TWR/MWR curve, Waterfall, Leverage Sensitivity)

**Existing components live here:**
`backtest/runner.py`, `analytics/metrics.py`, `analytics/engine.py`, `analytics/factor/`, `performance_table.py`, `profiler_tab.py`, `factor_workspace_tab.py`, `viz/charts.py`, `viz/univariate_charts.py`

**Output to session:** `BacktestResult` written into each `PortfolioCandidate`.

---

### Page 4 — Risk Evaluation

**Purpose:** Dedicated risk analysis. Extensible sub-page architecture.

**Extensibility pattern:**
- Current design = `Risk Management / Snapshot`
- Future additions = `Risk Management / New Function XX` (sibling sub-pages)
- Adding a new module requires no changes to existing Snapshot content

**Snapshot content:**
- KPI strip: MaxDD | VaR 95 (1D, parametric) | CVaR 95 (1D, historical) | Calmar Ratio
- VaR & CVaR panel: parametric + historical, rows per strategy + BM, tail distribution mini chart
- Drawdown panel: Top 5 events table (period / peak / trough / depth / recovery days) + MaxDD comparison bar chart across strategies
- Stress Testing (full width): crisis windows (2008 GFC / 2020 COVID / 2022 Rate Shock / 2000 Dot-com), per-asset simulated return, hedge effectiveness tag vs BM
- Correlation matrix: backtest period realized correlation with rolling window + regime comparison (Normal vs Crisis). **Note:** pre-purchase correlation lives in Page 1 (different purpose).
- Factor Exposure: FF5+UMD β bidirectional bar chart, R² fit, Tracking Error, Information Ratio; strategy tab switcher
- Rolling Risk panel: configurable window (60D/126D/252D) + metric selector (Vol/VaR/Beta/Sharpe), crisis periods highlighted

**Scope boundary:** Market risk only. Credit, liquidity, and counterparty risk are out of scope.

**ML extension point (future):** Stress scenario generation augmentable by ML-generated tail scenarios. Interface: `→ List[ScenarioResult]`.

**Output to session:** `RiskResult` written into each `PortfolioCandidate`.

---

### Page 5 — Strategic Asset Allocation (SAA)

**Purpose:** Select strategic baseline from evaluated candidates. Decision + documentation interface only — no new computation.

**Content:**
- Candidate scorecard: Performance group (CAGR / Sharpe / YTD% / 12Mo%) + Risk group (MaxDD / VaR 95 / CVaR 95 / Calmar) + Efficiency group (Info Ratio / TE vs BM), composite score tag (A/B/C)
- Diff strip below table: selected candidate vs runner-up ±pp on each metric
- Radio select per row to designate SAA baseline
- Weight breakdown panel: auto-renders selected candidate's weights by bucket
- Investment rationale textarea (free text, exported to report) + review cycle dropdown (Quarterly / Semi-annual / Annual)
- Lock button: freezes SAA weights → passes to Page 6 as neutral position
- To revise SAA: must return to Page 2 and re-run

**Output to session:** `ResearchSession.saa`

---

### Page 6 — Tactical Asset Allocation (TAA)

**Purpose:** Design macro scenario-driven deviations from SAA and evaluate their impact.

**Data source — FRED API (St. Louis Fed, free):**
| Signal | FRED series_id |
|---|---|
| CPI YoY | CPIAUCSL |
| Core CPI | CPILFESL |
| Unemployment Rate | UNRATE |
| 10Y−2Y Yield Spread | T10Y2Y |
| GDP Growth | GDP |
| HY Credit Spread | BAMLH0A0HYM2 |

Endpoint: `GET https://api.stlouisfed.org/fred/series/observations?series_id=<ID>&api_key=<KEY>&file_type=json`

**Regime Classifier:**
- Heuristic signal-threshold model → 5 scenario probabilities
- Scenarios: Base / High Inflation / Stagflation / Recession / Rapid Disinflation
- Highest-probability scenario auto-suggests a tilt; analyst can override
- Future upgrade: replace with ML classifier

**Scenario Tilt Playbook:**
- 5 predefined scenario cards + Custom
- Each card: name + macro trigger conditions + per-asset preset Δ weight + rationale text
- Scenario cards match BMO GAM case framework (High Inflation / Stagflation / Recession / Rapid Disinflation / Base)

**Weight logic:** `TAA = SAA + Scenario Tilt (auto-populated) + Manual Override (slider)`
- Sliders pre-fill from scenario defaults; analyst drags to override
- Normalisation applied before finalisation

**Global constraints:** max deviation/asset, total active budget (live bar), min weight/asset, allow-short toggle.

**Operational Playbook table:** Signal → Trigger threshold → Action (3-column, scenario-specific); governance note (IC review cadence, max tilt collar).

**Output to session:** `ResearchSession.taa` (active_scenario, adjustments dict, rationale)

**ML extension point (future):** Scenario probabilities + signal suggestions replaceable by ML module. Interface: `→ List[TAASignal]`.

---

### Execution Exit — Same Day Buy

Accessible from top navigation after Page 2. Takes `ResearchSession.saa` (or `taa` if defined) weights into existing same-day buy execution flow. No changes to execution logic.

---

## 5. Existing Feature Full Mapping

| Existing component | New location | Change |
|---|---|---|
| `ticker_search.py` | Page 1 | None |
| `holdings.py` | Page 2 (weight input) + execution | Minimal UI adaptation |
| `transaction_panel.py` | Execution exit | None |
| `rebalance_panel.py` | Page 2 (per-candidate option) | None |
| `backtest/runner.py` | Page 3 (called by backend) | None |
| `backtest/multi_date_runner.py` | Multi-date mode (unchanged) | None |
| `analytics/engine.py` | Page 3 | None |
| `analytics/metrics.py` | Page 3 (return metrics) + Page 4 (risk metrics split out) | Risk indicators moved to Page 4 |
| `analytics/factor/` | Page 3 (factor decomposition tab) | None |
| `analytics/profiler.py` | Page 3 | None |
| `analytics/univariate.py` | Page 1 (quick-look drawer) + Page 3 | Reused in two places |
| `performance_table.py` | Page 3 | None |
| `profiler_tab.py` | Page 3 (Return Analysis → card drill-down) | None |
| `factor_workspace_tab.py` | Page 3 | None |
| `factor_regression_tab.py` | Page 3 | None |
| `group_dashboard.py` | Page 3 (cross-candidate comparison) | Adapted for PortfolioCandidates |
| `portfolio_card.py` | Page 5 (SAA scorecard) | Minimal adaptation |
| `summary_bar.py` | Page 1 + Page 5 | Reused |
| `viz/charts.py` | Pages 3, 4 | None |
| `viz/univariate_charts.py` | Pages 1, 3 | None |
| `univariate_panel.py` | Page 1 drawer + Page 3 | Reused |

---

## 6. Backend Layer Separation (ML Extensibility)

```
UI Layer (ui/)                   Compute Layer (analytics/, backtest/, portfolio/)
─────────────────────            ──────────────────────────────────────────────────
Reads from ResearchSession   ←→  Functions take plain inputs, return plain outputs
Writes user inputs to session    No imports from ui/
Calls compute layer by ref       No knowledge of ResearchSession structure
Shows stale/ready status         Returns typed result objects (BacktestResult, RiskResult)
```

**Rule:** No `import` from `ui/` anywhere in `analytics/`, `backtest/`, or `portfolio/`.

**Future ML slot:** Each ML-extensible function annotated `# ML_EXTENSIBLE`, accepts `backend: str = "statistical"`. When `backend="ml"`, dispatches to `analytics/ml/` (not yet created). UI layer never knows which backend ran.

Functions to mark `ML_EXTENSIBLE`:
- Expected return estimation (Page 2, feeds MVO)
- Risk / VaR forecasting (Page 4)
- Regime classification (Page 6, currently heuristic)
- TAA signal generation (Page 6)
- Portfolio return prediction (future)

**New module required:**
- `data/fred_fetcher.py` — FRED API client for Page 6 macro signals
- `analytics/risk.py` — dedicated risk module (VaR, CVaR, stress, drawdown analysis)
- `analytics/regime.py` — heuristic regime classifier (Page 6)

---

## 7. Implementation Phases

### Phase 1 — Foundation (no user-visible change)
- Define `ResearchSession` dataclass and sub-types in `portfolio/models.py`
- Add `purchase_date`, `backtest_start`, `backtest_end`, `factor_bucket` fields
- Enforce compute/UI layer separation
- Add `# ML_EXTENSIBLE` annotations

### Phase 2 — Page 1 & 2
- Refactor ticker search + holdings into Page 1 layout (2×2 buckets + All-Weather Map)
- Add backtest period selector
- Add correlation heatmap collapsible panel (FRED not needed here; uses price data)
- Build Page 2: EW + Manual candidates, config panel

### Phase 3 — Page 3 (Performance)
- Reorganise existing analytics into Page 3 tab layout
- BackTest multi-strategy charts + Daily Return single-selector
- Factor Decomp: extend Y variable, add two-result-table layout, restore full Data Table
- Return Analysis: card view → profiler drill-down

### Phase 4 — Page 4 (Risk)
- Build `analytics/risk.py`
- Stress testing engine (apply historical crisis windows to current weights)
- Build Page 4 / Snapshot layout

### Phase 5 — Pages 5 & 6 (SAA + TAA)
- Build Page 5 scorecard + lock mechanism
- Build `data/fred_fetcher.py`
- Build `analytics/regime.py` (heuristic classifier)
- Build Page 6: signal dashboard + scenario tilt cards + slider overrides

### Phase 6 — Allocation Methods (Page 2 extension)
- Add MVO and Risk Parity to Page 2 (currently greyed placeholders)
- Add `analytics/covariance.py`

### Deferred
- ML backends (`analytics/ml/`)
- Automated TAA signal generation
- Dynamic universe / factor-based reconstitution
- Group mode → Simple mode ticker bridge

---

## 8. Out of Scope (Explicit Exclusions)

| Feature | Reason |
|---|---|
| Dynamic universe / factor rebalancing | Different problem domain |
| Credit / liquidity / counterparty risk | Beyond market risk scope |
| Automated TAA signal generation | Deferred (FRED data infrastructure now in place for manual signals) |
| ML model training and prediction | Deferred to post-SAA extension phase |
| Group mode modifications | Self-contained; no overlap |
| Multi-date mode modifications | Different problem (drip trading simulation) |
| Group mode → Simple mode ticker bridge | Nice-to-have; deferred |
