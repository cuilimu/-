"""
agents/base.py — Core types and BaseAgent ABC.

Design principle (from Anthropic's "Building effective agents"):
  Each agent is a single-purpose Claude API call with a tight system prompt.
  Agents do NOT share mutable state — they communicate only through AgentResult.
  Keep context minimal: only pass what the agent needs to do its job.
"""
from __future__ import annotations

import json
import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic


# ── Wire protocol ──────────────────────────────────────────────────────────────

@dataclass
class CodePatch:
    """A proposed change to a single file."""
    file_path: str          # relative to codebase root (e.g. "analytics/engine.py")
    description: str        # one-line intent
    old_snippet: str        # exact text to replace (empty → append)
    new_snippet: str        # replacement text


@dataclass
class AgentResult:
    """Standardised output of every agent.  Passed downstream as-is."""
    agent_name: str
    content: str                                      # narrative (analysis, plan, summary)
    code_patches: list[CodePatch] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)  # problems the agent flagged
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context_block(self) -> str:
        """Serialise this result so the next agent can read it as a message."""
        issues_str = "\n".join(f"  - {i}" for i in self.issues) or "  none"
        patches_str = "\n".join(
            f"  [{p.file_path}] {p.description}" for p in self.code_patches
        ) or "  none"
        return textwrap.dedent(f"""
            ### {self.agent_name} output
            {self.content}

            **Issues flagged:**
            {issues_str}

            **Proposed patches:**
            {patches_str}
        """).strip()


# ── Shared context passed through the pipeline ─────────────────────────────────

@dataclass
class AgentContext:
    """
    Immutable-ish state threaded through the whole pipeline.
    Agents READ from this; only the pipeline mutates `checkpoints`.

    checkpoints keys (set by each stage):
      "decomposition"  → dict produced by OrchestratorAgent
      "specialists"    → list[AgentResult] (4 parallel results)
      "aggregated"     → AgentResult from AggregatorAgent
      "verification"   → AgentResult from VerifierAgent
      "fixed"          → AgentResult from FixerAgent (may be same as aggregated)
    """
    user_query: str
    codebase_path: str                             # abs path to stock_engine root
    relevant_code: dict[str, str] = field(default_factory=dict)  # {rel_path: content}
    checkpoints: dict[str, Any] = field(default_factory=dict)
    max_fix_iterations: int = 3                    # evaluator-optimizer loop cap


# ── Base class every agent inherits ───────────────────────────────────────────

class BaseAgent(ABC):
    """
    One agent = one Claude call (or a small, bounded loop of calls).

    Model tiers:
      - Orchestrator / Aggregator / Verifier: claude-sonnet-4-6 (needs reasoning)
      - Specialists / Fixer / Output: claude-haiku-4-5-20251001 (speed, cost)
        Override MODEL in subclass to change.
    """

    MODEL: str = "claude-haiku-4-5-20251001"

    def __init__(self, client: anthropic.AsyncAnthropic) -> None:
        self._client = client

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult: ...

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _call(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        """Single-turn Claude call.  Returns the assistant text."""
        response = await self._client.messages.create(
            model=model or self.MODEL,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=messages,
        )
        return response.content[0].text

    async def _call_json(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> Any:
        """Call Claude and parse the response as JSON.  Raises on bad JSON."""
        raw = await self._call(messages, max_tokens=max_tokens, model=model)
        # Claude sometimes wraps JSON in a markdown fence — strip it
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("```")[1]
            if stripped.startswith("json"):
                stripped = stripped[4:]
        return json.loads(stripped.strip())

    @staticmethod
    def _user(text: str) -> dict[str, str]:
        return {"role": "user", "content": text}

    @staticmethod
    def _assistant(text: str) -> dict[str, str]:
        return {"role": "assistant", "content": text}
