"""
agents/aggregator.py — AggregatorAgent.

Pattern: Orchestrator-subagents / synthesis step.

Receives the four specialist AgentResults and produces a single, coherent plan:
  - Deduplicates overlapping issues
  - Merges code patches (file-by-file)
  - Resolves conflicts (e.g. Finance and Coding both propose changes to runner.py)
  - Writes a prioritised action list

This agent uses the heavier Sonnet model because synthesis requires judgment.
"""
from __future__ import annotations

import textwrap

from stock_engine.agents.base import AgentContext, AgentResult, BaseAgent, CodePatch


class AggregatorAgent(BaseAgent):
    MODEL = "claude-sonnet-4-6"

    @property
    def name(self) -> str:
        return "AggregatorAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are the synthesis coordinator for a multi-agent code review system.
            You receive analysis from four specialists (Finance, Statistics, Coding, Viz)
            and must produce ONE unified, actionable improvement plan.

            Your output must:
              1. List all unique issues in priority order (Critical > High > Medium > Low)
              2. For each proposed code change, decide: accept / reject / merge
                 - If two agents propose conflicting changes to the same file, pick the best
                   one and explain why.
              3. Output accepted patches in the standard format:
                   PATCH: <file_path>
                   DESCRIPTION: <intent>
                   OLD: <existing code>
                   NEW: <replacement>
              4. Flag any issues that require human review before applying
                 (use prefix: HUMAN_REVIEW: <description>)

            Be decisive. Do not hedge. The downstream VerifierAgent will catch math errors.
            Priority: correctness > maintainability > aesthetics.
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        specialist_results: list[AgentResult] = ctx.checkpoints.get("specialists", [])

        # Build the aggregation prompt from all specialist outputs
        specialist_blocks = "\n\n---\n\n".join(
            r.to_context_block() for r in specialist_results
        )

        prompt = textwrap.dedent(f"""
            User's original request: {ctx.user_query}

            Below are the four specialist analyses. Synthesise them into a unified plan.

            {specialist_blocks}
        """).strip()

        response = await self._call([self._user(prompt)], max_tokens=6000)

        # Parse patches and issues from the aggregated response
        patches: list[CodePatch] = []
        issues: list[str] = []
        human_reviews: list[str] = []

        current_patch: dict = {}
        for line in response.splitlines():
            s = line.strip()
            if s.startswith("PATCH:"):
                if current_patch.get("file"):
                    patches.append(_flush(current_patch))
                current_patch = {"file": s[6:].strip(), "desc": "", "old": [], "new": []}
            elif s.startswith("DESCRIPTION:") and current_patch:
                current_patch["desc"] = s[12:].strip()
            elif s.startswith("OLD:") and current_patch:
                current_patch["old"].append(s[4:].strip())
            elif s.startswith("NEW:") and current_patch:
                current_patch["new"].append(s[4:].strip())
            elif s.startswith("ISSUE:"):
                issues.append(s[6:].strip())
            elif s.startswith("HUMAN_REVIEW:"):
                human_reviews.append(s[13:].strip())

        if current_patch.get("file"):
            patches.append(_flush(current_patch))

        return AgentResult(
            agent_name=self.name,
            content=response,
            code_patches=patches,
            issues=issues,
            metadata={"human_reviews": human_reviews},
        )


def _flush(p: dict) -> CodePatch:
    return CodePatch(
        file_path=p["file"],
        description=p.get("desc", ""),
        old_snippet="\n".join(p.get("old", [])),
        new_snippet="\n".join(p.get("new", [])),
    )
