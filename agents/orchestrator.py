"""
agents/orchestrator.py — OrchestratorAgent.

Pattern: Orchestrator-subagents (Anthropic article §"Orchestrator-subagents").

Responsibilities:
  1. Read the user query.
  2. Load the most relevant source files from the codebase (routing).
  3. Produce a structured decomposition — one sub-task per specialist.
  4. Store the decomposition + relevant code in AgentContext for downstream agents.

The orchestrator does NOT execute tasks itself; it delegates.
It also decides which code files each specialist needs to see,
keeping each agent's context as tight as possible.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from stock_engine.agents.base import AgentContext, AgentResult, BaseAgent

# Files the orchestrator always loads (small, high-signal)
_ALWAYS_LOAD = [
    "config.py",
    "backtest/base.py",
    "analytics/engine.py",
    "portfolio/models.py",
]

# Specialist → files that are relevant to it
_SPECIALIST_FILES: dict[str, list[str]] = {
    "finance":    ["backtest/runner.py", "portfolio/rebalancer.py",
                   "portfolio/transaction.py", "data/base.py"],
    "statistics": ["analytics/engine.py", "analytics/metrics.py",
                   "analytics/univariate.py", "analytics/factor_regression.py"],
    "coding":     ["backtest/base.py", "backtest/runner.py",
                   "data/yfinance_provider.py", "exceptions.py"],
    "viz":        ["viz/charts.py", "viz/theme.py", "ui/app.py",
                   "ui/components/summary_bar.py"],
}


class OrchestratorAgent(BaseAgent):
    MODEL = "claude-sonnet-4-6"

    @property
    def name(self) -> str:
        return "OrchestratorAgent"

    @property
    def system_prompt(self) -> str:
        return """You are the orchestrator of a multi-agent stock backtesting system.
Your job is to decompose a user request into four focused sub-tasks, one per specialist:
  - finance:    financial logic, strategy semantics, market conventions
  - statistics: mathematical correctness of metrics and statistical methods
  - coding:     Python implementation, module boundaries, type safety, tests
  - viz:        chart design, colour palette, Streamlit layout, accessibility

Output ONLY a JSON object with this exact shape:
{
  "intent_summary": "<one sentence describing what the user wants>",
  "tasks": {
    "finance":    "<focused sub-task for the finance specialist>",
    "statistics": "<focused sub-task for the statistics specialist>",
    "coding":     "<focused sub-task for the coding specialist>",
    "viz":        "<focused sub-task for the viz specialist>"
  },
  "relevant_files": {
    "finance":    ["<rel path>", ...],
    "statistics": ["<rel path>", ...],
    "coding":     ["<rel path>", ...],
    "viz":        ["<rel path>", ...]
  }
}

Be specific. Give each specialist only the task they need — avoid overlap.
The files lists should be subsets of the known module files; do not invent paths."""

    async def run(self, ctx: AgentContext) -> AgentResult:
        # Load always-on files into ctx.relevant_code
        root = Path(ctx.codebase_path)
        for rel in _ALWAYS_LOAD:
            _load_file(root, rel, ctx)

        # Ask Claude to decompose and identify relevant files
        decomposition: dict[str, Any] = await self._call_json([
            self._user(
                f"User request:\n{ctx.user_query}\n\n"
                f"Known module files:\n{_module_tree(root)}"
            )
        ])

        ctx.checkpoints["decomposition"] = decomposition

        # Load the files each specialist will need
        for specialist, paths in decomposition.get("relevant_files", {}).items():
            for rel in paths:
                _load_file(root, rel, ctx)
        # Also load defaults per specialist
        for specialist, paths in _SPECIALIST_FILES.items():
            for rel in paths:
                _load_file(root, rel, ctx)

        return AgentResult(
            agent_name=self.name,
            content=decomposition.get("intent_summary", ctx.user_query),
            metadata={"decomposition": decomposition},
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_file(root: Path, rel: str, ctx: AgentContext) -> None:
    """Read a source file into ctx.relevant_code if it exists and isn't already loaded."""
    if rel in ctx.relevant_code:
        return
    path = root / rel
    if path.exists():
        try:
            ctx.relevant_code[rel] = path.read_text(encoding="utf-8")
        except Exception:
            pass


def _module_tree(root: Path) -> str:
    """Return a compact file listing of the stock_engine package."""
    lines = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).as_posix()
        if "__pycache__" not in rel and ".egg-info" not in rel:
            lines.append(rel)
    return "\n".join(lines)
