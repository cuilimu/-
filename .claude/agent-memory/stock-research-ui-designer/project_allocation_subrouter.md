---
name: Allocation Sub-Router — Design Spec Decisions
description: Design decisions from Proposal B (Asset Allocation Sub-Router) spec produced 2026-05-09. Covers strategy selector placement, sub-router file structure, shared context, empty states.
type: project
---

Proposal B: Asset Allocation (Step 4 in current live code, labeled Step 3 "Allocation" in APP_REDESIGN_PLAN) already has a sub-router in page2_allocation.py with `_SUB_KEY = "p2_active_sub"` routing between overview, equal_weight, manual, and coming-soon strategies. Spec upgrades this to a formal sub-router.

**Current state (2026-05-09):** `_STRATEGIES` list drives a `_render_strategy_selector` segmented button row and `_render_candidate_summaries` card list. Sub-page routing via session state key `p2_active_sub`. Back button exists. Column ratio: 1.4 (config) / 3.5 (right pane), gap="medium".

**Strategy selector placement decision:** Within the main zone, NOT in the sidebar. A sub-nav strip inside the sidebar would create ambiguity between the 8-step workflow steps and the strategy sub-pages. The strategy selector stays inside the main zone (top of the right column, above candidate summaries) — it is logically part of Step 4 content, not app-level navigation.

**Sub-router file structure for new strategy additions:** Each strategy gets one file at `ui/components/simple_mode/page2_{strategy_id}.py` with a single entry function `render_{strategy_id}_subpage(sess, config, cand)`. The strategy registry `_STRATEGIES` in `page2_allocation.py` is the only file that needs editing to register the new strategy — routing is dispatched by `strategy["id"]` string lookup.

**Shared context header:** Always-visible 32px bar below the strategy selector strip. Shows: locked TICKERS count, DATE RANGE (start → end), CAPITAL amount. Background CARD_BG, border-bottom 1px CARD_BORDER, font monospace 10px. Does NOT collapse — allocation strategies depend heavily on these parameters and analysts must see them at all times.

**Empty state (no strategy selected):** Overview grid of strategy cards (the current implementation). Empty state appears when `p2_active_sub` is None. Cards for unavailable strategies show "COMING SOON" badge in MAIN_TEXT_SECONDARY, cursor: not-allowed.

**Why:** Identified during 2026-05-09 structural redesign spec. The existing sub-router pattern in page2_allocation.py is already sound; the spec formalizes its conventions and adds the always-visible shared context bar.

**How to apply:** When adding a new strategy, the pattern is: (1) append to `_STRATEGIES` in page2_allocation.py, (2) create `page2_{strategy_id}.py` with `render_{strategy_id}_subpage`, (3) add dispatch case in `render_page2` or `_render_subpage_header` dispatcher. No other files need editing.
