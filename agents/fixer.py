"""
agents/fixer.py — FixerAgent.

Pattern: Evaluator-optimizer loop (paired with VerifierAgent).

Receives the aggregated plan + the list of issues from VerifierAgent.
Produces corrected patches for each issue.
Returns an updated AgentResult that replaces the aggregated one.

The pipeline runs Verifier → Fixer → Verifier in a loop (max ctx.max_fix_iterations).
Each iteration the fixer only sees the *remaining* issues — already-fixed ones are dropped.
"""
from __future__ import annotations

import textwrap
from copy import deepcopy

from stock_engine.agents.base import AgentContext, AgentResult, BaseAgent, CodePatch


class FixerAgent(BaseAgent):
    MODEL = "claude-haiku-4-5-20251001"

    @property
    def name(self) -> str:
        return "FixerAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are a bug-fixing engineer for a Python quantitative finance library.
            You will receive:
              - A list of specific bugs found by a verifier
              - The current proposed code patches that contain those bugs

            For EACH bug, produce a corrected patch in this exact format:
              PATCH: <file_path>
              DESCRIPTION: <what you fixed and why>
              OLD: <the exact buggy line(s) from the current NEW section>
              NEW: <corrected replacement>

            Rules:
              - Fix only what the verifier flagged — do not refactor other things
              - Preserve indentation and style of the surrounding code
              - If a bug cannot be fixed without more context, output:
                  UNFIXABLE: <file_path> — <reason>
              - Do not invent new patches unrelated to the reported issues
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        aggregated: AgentResult = ctx.checkpoints.get("aggregated")
        verification: AgentResult = ctx.checkpoints.get("verification")

        if not verification or not verification.issues:
            # Nothing to fix — pass aggregated through unchanged
            return deepcopy(aggregated)

        prompt = textwrap.dedent(f"""
            Bugs to fix:
            {chr(10).join(f'  - {i}' for i in verification.issues)}

            Current patches (may contain the bugs):
            {_patches_as_text(aggregated)}

            Relevant code context:
            {_code_context(ctx)}
        """).strip()

        response = await self._call([self._user(prompt)], max_tokens=4096)

        # Parse fixer's output into patches
        new_patches = _parse_fix_patches(response)
        unfixable = [
            line.strip()[10:].strip()
            for line in response.splitlines()
            if line.strip().startswith("UNFIXABLE:")
        ]

        # Merge: replace matching patches from aggregated with fixed versions
        merged = _merge_patches(aggregated.code_patches, new_patches)

        remaining_issues = unfixable  # only truly unfixable ones carry forward
        return AgentResult(
            agent_name=self.name,
            content=response,
            code_patches=merged,
            issues=remaining_issues,
            metadata={"fixed_count": len(new_patches), "unfixable": unfixable},
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_fix_patches(text: str) -> list[CodePatch]:
    patches: list[CodePatch] = []
    current: dict = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("PATCH:"):
            if current.get("file"):
                patches.append(_flush(current))
            current = {"file": s[6:].strip(), "desc": "", "old": [], "new": []}
        elif s.startswith("DESCRIPTION:") and current:
            current["desc"] = s[12:].strip()
        elif s.startswith("OLD:") and current:
            current["old"].append(s[4:].strip())
        elif s.startswith("NEW:") and current:
            current["new"].append(s[4:].strip())
    if current.get("file"):
        patches.append(_flush(current))
    return patches


def _flush(p: dict) -> CodePatch:
    return CodePatch(
        file_path=p["file"],
        description=p.get("desc", ""),
        old_snippet="\n".join(p.get("old", [])),
        new_snippet="\n".join(p.get("new", [])),
    )


def _merge_patches(original: list[CodePatch], fixes: list[CodePatch]) -> list[CodePatch]:
    """
    Apply fixes on top of original patches.
    For each fix: if a patch for the same file exists, apply the fix's OLD→NEW
    within the original patch's new_snippet.  Otherwise append as a new patch.
    """
    result = list(deepcopy(original))
    for fix in fixes:
        matched = False
        for i, orig in enumerate(result):
            if orig.file_path == fix.file_path:
                if fix.old_snippet and fix.old_snippet in orig.new_snippet:
                    result[i] = CodePatch(
                        file_path=orig.file_path,
                        description=f"{orig.description} → {fix.description}",
                        old_snippet=orig.old_snippet,
                        new_snippet=orig.new_snippet.replace(fix.old_snippet, fix.new_snippet, 1),
                    )
                    matched = True
                    break
        if not matched:
            result.append(fix)
    return result


def _patches_as_text(result: AgentResult) -> str:
    lines = []
    for p in result.code_patches:
        lines.append(
            f"FILE: {p.file_path}\nDESCRIPTION: {p.description}\n"
            f"OLD:\n{p.old_snippet}\nNEW:\n{p.new_snippet}"
        )
    return "\n---\n".join(lines) if lines else "(no patches)"


def _code_context(ctx: AgentContext) -> str:
    parts = []
    for rel, code in ctx.relevant_code.items():
        parts.append(f"### {rel}\n```python\n{code[:1500]}\n```")
    return "\n\n".join(parts[:6])  # cap context size
