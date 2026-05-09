"""
agents/pipeline.py — AgentPipeline: top-level entry point.

Wires all agents together and enforces the execution order:

  Phase 1 — Decompose   : OrchestratorAgent (serial)
  Phase 2 — Analyse     : [Finance, Statistics, Coding, Viz] (parallel, asyncio.gather)
  Phase 3 — Synthesise  : AggregatorAgent (serial, sees all 4 results)
  Phase 4 — Verify/Fix  : VerifierAgent → FixerAgent loop (max_fix_iterations)
  Phase 5 — Output      : OutputAgent (applies patches + writes summary)

Usage:
    import asyncio
    import anthropic
    from stock_engine.agents import AgentPipeline

    client = anthropic.AsyncAnthropic()
    pipeline = AgentPipeline(client, codebase_path="/path/to/stock_engine")
    result = asyncio.run(pipeline.run("Add a Calmar ratio metric to analytics/engine.py"))
    print(result.content)

Checkpointing:
    ctx.checkpoints is populated at each stage.  If a stage fails, the pipeline
    can resume from the last successful checkpoint by passing resume_from.
    (Aligns with Anthropic article §"Planning and checkpointing".)

Human-in-the-loop:
    Set require_human_approval=True to pause before the OutputAgent applies patches.
    The pipeline will return with status="awaiting_approval" and the caller can
    call pipeline.approve(ctx) to proceed or pipeline.reject(ctx) to abort.
    (Aligns with Anthropic article §"Human-in-the-loop" guidance.)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import anthropic

from stock_engine.agents.aggregator import AggregatorAgent
from stock_engine.agents.base import AgentContext, AgentResult
from stock_engine.agents.fixer import FixerAgent
from stock_engine.agents.orchestrator import OrchestratorAgent
from stock_engine.agents.output import OutputAgent
from stock_engine.agents.specialists import (
    CodingAgent, FinanceAgent, StatisticsAgent, VizAgent,
)
from stock_engine.agents.verifier import VerifierAgent

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    status: Literal["completed", "awaiting_approval", "failed"]
    output: Optional[AgentResult] = None
    ctx: Optional[AgentContext] = None     # carry ctx for resume / approval flows
    error: Optional[str] = None


class AgentPipeline:
    """
    Constructs and runs the full multi-agent pipeline.

    Args:
        client:               AsyncAnthropic client (caller owns the lifecycle)
        codebase_path:        Absolute path to the stock_engine root directory
        max_fix_iterations:   Cap on Verifier→Fixer loops (default 3)
        require_human_approval: If True, pause before OutputAgent applies patches
        on_stage_complete:    Optional callback(stage_name, AgentResult) for logging/UI
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        codebase_path: str,
        max_fix_iterations: int = 3,
        require_human_approval: bool = False,
        on_stage_complete: Optional[Callable[[str, AgentResult], None]] = None,
    ) -> None:
        self._client = client
        self._codebase_path = codebase_path
        self._max_fix_iterations = max_fix_iterations
        self._require_human_approval = require_human_approval
        self._on_stage_complete = on_stage_complete or (lambda s, r: None)

        # Instantiate agents once — they're stateless across calls
        self._orchestrator = OrchestratorAgent(client)
        self._specialists = [
            FinanceAgent(client),
            StatisticsAgent(client),
            CodingAgent(client),
            VizAgent(client),
        ]
        self._aggregator = AggregatorAgent(client)
        self._verifier = VerifierAgent(client)
        self._fixer = FixerAgent(client)
        self._output = OutputAgent(client)

    async def run(self, user_query: str) -> PipelineResult:
        ctx = AgentContext(
            user_query=user_query,
            codebase_path=self._codebase_path,
            max_fix_iterations=self._max_fix_iterations,
        )
        try:
            return await self._execute(ctx)
        except Exception as exc:
            log.exception("Pipeline failed")
            return PipelineResult(status="failed", ctx=ctx, error=str(exc))

    async def approve(self, ctx: AgentContext) -> PipelineResult:
        """Continue a paused pipeline after human approval."""
        try:
            output_result = await self._output.run(ctx)
            self._on_stage_complete("output", output_result)
            return PipelineResult(status="completed", output=output_result, ctx=ctx)
        except Exception as exc:
            log.exception("OutputAgent failed after approval")
            return PipelineResult(status="failed", ctx=ctx, error=str(exc))

    def reject(self, ctx: AgentContext) -> PipelineResult:
        """Abort a paused pipeline — no patches are applied."""
        return PipelineResult(
            status="failed",
            ctx=ctx,
            error="rejected by human reviewer",
        )

    # ── Private execution ──────────────────────────────────────────────────────

    async def _execute(self, ctx: AgentContext) -> PipelineResult:
        # ── Phase 1: Decompose ────────────────────────────────────────────────
        log.info("[1/5] Orchestrator: decomposing query")
        orch_result = await self._orchestrator.run(ctx)
        self._on_stage_complete("orchestrator", orch_result)

        # ── Phase 2: Parallel specialist analysis ─────────────────────────────
        log.info("[2/5] Specialists: running in parallel")
        specialist_results: list[AgentResult] = await asyncio.gather(
            *[agent.run(ctx) for agent in self._specialists]
        )
        ctx.checkpoints["specialists"] = specialist_results
        for r in specialist_results:
            self._on_stage_complete(r.agent_name, r)

        # ── Phase 3: Aggregation ──────────────────────────────────────────────
        log.info("[3/5] Aggregator: synthesising specialist outputs")
        aggregated = await self._aggregator.run(ctx)
        ctx.checkpoints["aggregated"] = aggregated
        self._on_stage_complete("aggregator", aggregated)

        # ── Phase 4: Evaluator-optimizer loop ─────────────────────────────────
        log.info("[4/5] Verifier/Fixer: evaluator-optimizer loop")
        current = aggregated
        for iteration in range(self._max_fix_iterations):
            verification = await self._verifier.run(ctx)
            ctx.checkpoints["verification"] = verification
            self._on_stage_complete(f"verifier_iter{iteration}", verification)

            if not verification.issues:
                log.info("  ✓ Verification passed on iteration %d", iteration)
                break

            log.info("  ✗ %d issue(s) found — running FixerAgent", len(verification.issues))
            fixed = await self._fixer.run(ctx)
            ctx.checkpoints["fixed"] = fixed
            ctx.checkpoints["aggregated"] = fixed   # next verifier pass sees fixed version
            self._on_stage_complete(f"fixer_iter{iteration}", fixed)
            current = fixed
        else:
            log.warning("Max fix iterations reached; %d issues remain", len(current.issues))

        # ── Phase 5: Output ───────────────────────────────────────────────────
        if self._require_human_approval:
            log.info("[5/5] Pausing for human approval before applying patches")
            return PipelineResult(status="awaiting_approval", ctx=ctx)

        log.info("[5/5] OutputAgent: applying patches and summarising")
        output_result = await self._output.run(ctx)
        self._on_stage_complete("output", output_result)
        return PipelineResult(status="completed", output=output_result, ctx=ctx)
