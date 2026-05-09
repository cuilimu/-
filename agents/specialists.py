"""
agents/specialists.py — Four parallel domain-specialist agents.

Pattern: Parallelization / sectioning (Anthropic article §"Parallelization").

All four agents run concurrently via asyncio.gather() in pipeline.py.
Each agent sees only its assigned sub-task and the code files relevant to it.
They never communicate with each other — isolation prevents cross-contamination
and allows genuine parallel execution.

Specialist responsibilities:
  FinanceAgent     → strategy logic, market conventions, financial correctness
  StatisticsAgent  → metric math, edge cases, distributional assumptions
  CodingAgent      → Python impl quality, module boundaries, type safety, tests
  VizAgent         → chart design, palette, Streamlit UX, accessibility
"""
from __future__ import annotations

import textwrap
from typing import Optional

from stock_engine.agents.base import AgentContext, AgentResult, BaseAgent, CodePatch


# ── Shared helper ──────────────────────────────────────────────────────────────

def _build_code_block(ctx: AgentContext, specialist: str) -> str:
    """Assembles relevant source snippets for this specialist's context window."""
    from stock_engine.agents.orchestrator import _SPECIALIST_FILES
    relevant_rels = set(_SPECIALIST_FILES.get(specialist, []))
    decomp = ctx.checkpoints.get("decomposition", {})
    relevant_rels |= set(decomp.get("relevant_files", {}).get(specialist, []))

    parts = []
    for rel, code in ctx.relevant_code.items():
        if rel in relevant_rels:
            parts.append(f"### {rel}\n```python\n{code[:3000]}\n```")
    return "\n\n".join(parts) if parts else "(no code loaded)"


def _task_for(ctx: AgentContext, specialist: str) -> str:
    decomp = ctx.checkpoints.get("decomposition", {})
    return decomp.get("tasks", {}).get(specialist, ctx.user_query)


def _parse_patches(text: str) -> tuple[list[CodePatch], list[str]]:
    """
    Extract CodePatch objects and issues from an agent's narrative response.

    Expected format inside the response (agents are prompted to use it):

      PATCH: analytics/engine.py
      DESCRIPTION: Fix annualisation factor for monthly frequency
      OLD: annualised_return=self._annualised_return(dr),
      NEW: annualised_return=self._annualised_return(dr, self._config.annualisation_factor),

      ISSUE: Sharpe formula ignores annualisation_factor from Config — uses hardcoded 252.
    """
    patches: list[CodePatch] = []
    issues: list[str] = []

    current_patch: dict = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("PATCH:"):
            if current_patch.get("file"):
                patches.append(_flush_patch(current_patch))
            current_patch = {"file": s[6:].strip(), "desc": "", "old": [], "new": []}
        elif s.startswith("DESCRIPTION:") and current_patch:
            current_patch["desc"] = s[12:].strip()
        elif s.startswith("OLD:") and current_patch:
            current_patch["old"].append(s[4:].strip())
        elif s.startswith("NEW:") and current_patch:
            current_patch["new"].append(s[4:].strip())
        elif s.startswith("ISSUE:"):
            issues.append(s[6:].strip())

    if current_patch.get("file"):
        patches.append(_flush_patch(current_patch))

    return patches, issues


def _flush_patch(p: dict) -> CodePatch:
    return CodePatch(
        file_path=p["file"],
        description=p.get("desc", ""),
        old_snippet="\n".join(p.get("old", [])),
        new_snippet="\n".join(p.get("new", [])),
    )


# ── FinanceAgent ───────────────────────────────────────────────────────────────

class FinanceAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "FinanceAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are a buy-side quant analyst reviewing a Python stock backtesting engine.
            Your focus is FINANCIAL CORRECTNESS only:
              - Strategy signal semantics (long/short intent, rebalance triggers)
              - Transaction cost conventions (slippage in bps, fill-at-open logic)
              - Portfolio construction (equal-weight, dollar allocation, PortfolioGroup)
              - Benchmark comparison (SPY, information ratio interpretation)
              - Common financial traps: look-ahead bias, survivorship bias, rebalance timing

            When you find issues, output them as:
              ISSUE: <description>

            When you propose code changes, output them as:
              PATCH: <file_path>
              DESCRIPTION: <one-line intent>
              OLD: <exact existing line(s) to replace>
              NEW: <replacement line(s)>

            Do not touch statistics math or chart styling — those are other agents' domain.
            Be concise. Think like a portfolio manager reviewing a quant's code.
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        task = _task_for(ctx, "finance")
        code = _build_code_block(ctx, "finance")
        prompt = f"Task: {task}\n\nRelevant code:\n{code}"
        response = await self._call([self._user(prompt)])
        patches, issues = _parse_patches(response)
        return AgentResult(
            agent_name=self.name,
            content=response,
            code_patches=patches,
            issues=issues,
        )


# ── StatisticsAgent ────────────────────────────────────────────────────────────

class StatisticsAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "StatisticsAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are a quantitative statistician reviewing a Python finance library.
            Your focus is MATHEMATICAL CORRECTNESS only:
              - Annualisation formulas (252 trading days, 12 months, 4 quarters)
              - Sharpe ratio: (mean_return - rf) / std * sqrt(ann_factor)
              - Max drawdown: peak-to-trough on cumulative returns, NOT daily
              - Information ratio: tracking error denominator, benchmark alignment
              - Edge cases: fewer than 2 data points, zero-variance returns, NaN propagation
              - Distributional assumptions: normality assumed? fat tails ignored?
              - Factor regression: OLS assumptions, multicollinearity, R² interpretation

            When you find issues, output them as:
              ISSUE: <description with the correct formula>

            When you propose code changes, output them as:
              PATCH: <file_path>
              DESCRIPTION: <one-line intent>
              OLD: <exact existing line(s)>
              NEW: <corrected line(s)>

            Do not comment on strategy logic or visual design.
            Show your work: if a formula is wrong, state the correct version.
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        task = _task_for(ctx, "statistics")
        code = _build_code_block(ctx, "statistics")
        prompt = f"Task: {task}\n\nRelevant code:\n{code}"
        response = await self._call([self._user(prompt)])
        patches, issues = _parse_patches(response)
        return AgentResult(
            agent_name=self.name,
            content=response,
            code_patches=patches,
            issues=issues,
        )


# ── CodingAgent ────────────────────────────────────────────────────────────────

class CodingAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "CodingAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are a senior Python engineer reviewing a financial backtesting library.
            Your focus is CODE QUALITY only:
              - Module boundary violations (e.g. UI logic leaking into analytics)
              - Type annotation completeness and correctness
              - Exception handling (custom exceptions vs bare except)
              - Performance: unnecessary DataFrame copies, redundant fetches
              - Test coverage: which edge cases are untested?
              - Dataclass field ordering, dataclass vs TypedDict choices
              - Config object usage: all tuneable params must live in Config, not inline

            Module boundaries to enforce:
              data/       → fetch only, no computation
              backtest/   → loop + signals, no analytics
              analytics/  → stateless computation from BacktestResult
              portfolio/  → portfolio state + rebalancer math
              viz/        → charts from BacktestResult, no fetching
              ui/         → Streamlit only, orchestrates everything else

            When you find issues, output them as:
              ISSUE: <description>

            When you propose code changes, output them as:
              PATCH: <file_path>
              DESCRIPTION: <one-line intent>
              OLD: <exact existing line(s)>
              NEW: <replacement line(s)>

            Do not comment on financial domain semantics or chart aesthetics.
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        task = _task_for(ctx, "coding")
        code = _build_code_block(ctx, "coding")
        prompt = f"Task: {task}\n\nRelevant code:\n{code}"
        response = await self._call([self._user(prompt)])
        patches, issues = _parse_patches(response)
        return AgentResult(
            agent_name=self.name,
            content=response,
            code_patches=patches,
            issues=issues,
        )


# ── VizAgent ──────────────────────────────────────────────────────────────────

class VizAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "VizAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are a data visualisation designer reviewing a Streamlit + Plotly finance app.
            Your focus is VISUAL DESIGN AND UX only:
              - Chart type selection (line vs bar vs scatter vs heatmap)
              - Colour palette: distinguish signals clearly, colourblind-safe
              - Information hierarchy: most important metric most prominent
              - Axis labelling: units, date formats, percentage vs decimal
              - Annotations: drawdown shading, event markers, benchmark line
              - Streamlit layout: tab structure, sidebar vs main, column ratios
              - Accessibility: contrast ratios, no colour-only encoding
              - Performance: avoid re-rendering entire page on every widget change

            When you find issues, output them as:
              ISSUE: <description>

            When you propose code changes, output them as:
              PATCH: <file_path>
              DESCRIPTION: <one-line intent>
              OLD: <exact existing line(s)>
              NEW: <replacement line(s)>

            Do not comment on financial math or Python code structure.
            Think like a Bloomberg terminal designer with a minimalist aesthetic.
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        task = _task_for(ctx, "viz")
        code = _build_code_block(ctx, "viz")
        prompt = f"Task: {task}\n\nRelevant code:\n{code}"
        response = await self._call([self._user(prompt)])
        patches, issues = _parse_patches(response)
        return AgentResult(
            agent_name=self.name,
            content=response,
            code_patches=patches,
            issues=issues,
        )
