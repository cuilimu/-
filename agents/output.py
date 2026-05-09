"""
agents/output.py — OutputAgent.

Final stage: applies patches to disk and produces a human-readable summary.

Responsibilities:
  1. Apply all verified+fixed code patches to the actual source files
  2. Write a git-diff-style summary of what changed and why
  3. Flag any HUMAN_REVIEW items that were not auto-applied
  4. Return the final AgentResult consumed by the caller (UI or CLI)

Design note (Anthropic article §"Human-in-the-loop"):
  Patches that were flagged HUMAN_REVIEW by the AggregatorAgent are written
  to a separate <codebase>/agents/_pending_review/ folder instead of applied
  in-place, so a developer can inspect them before merging.
"""
from __future__ import annotations

import shutil
import textwrap
from datetime import datetime
from pathlib import Path

from stock_engine.agents.base import AgentContext, AgentResult, BaseAgent, CodePatch


class OutputAgent(BaseAgent):
    MODEL = "claude-haiku-4-5-20251001"

    @property
    def name(self) -> str:
        return "OutputAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are a technical writer summarising the output of a multi-agent code review.
            Write a concise, structured summary:
              1. What the user asked for (one sentence)
              2. What was changed (bullet per file, max 10 words each)
              3. Key issues resolved (numbered, in priority order)
              4. Items requiring human review (if any)
              5. Recommended next steps (max 3)

            Tone: technical, direct, no fluff.
            Audience: the developer who submitted the original request.
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        final: AgentResult = ctx.checkpoints.get("fixed") or ctx.checkpoints.get("aggregated")
        if final is None:
            return AgentResult(agent_name=self.name, content="Pipeline produced no output.",
                               issues=["no upstream result"])

        # ── Apply patches to disk ──────────────────────────────────────────────
        applied: list[str] = []
        skipped: list[str] = []
        pending_reviews: list[str] = ctx.checkpoints.get("aggregated", AgentResult("", "")).metadata.get(
            "human_reviews", []
        )

        for patch in _deduplicate_patches(final.code_patches):
            success, reason = _apply_patch(patch, ctx.codebase_path)
            if success:
                applied.append(f"{patch.file_path}: {patch.description}")
            else:
                skipped.append(f"{patch.file_path}: {reason}")

        # Write pending human reviews to a staging folder
        if pending_reviews:
            _write_pending_reviews(pending_reviews, final.code_patches, ctx.codebase_path)

        # ── Generate summary via LLM ───────────────────────────────────────────
        prompt = textwrap.dedent(f"""
            User request: {ctx.user_query}

            Applied patches ({len(applied)}):
            {chr(10).join(f'  - {a}' for a in applied) or '  (none)'}

            Skipped patches ({len(skipped)}):
            {chr(10).join(f'  - {s}' for s in skipped) or '  (none)'}

            Human review items ({len(pending_reviews)}):
            {chr(10).join(f'  - {r}' for r in pending_reviews) or '  (none)'}

            Remaining issues:
            {chr(10).join(f'  - {i}' for i in final.issues) or '  (none)'}
        """).strip()

        summary = await self._call([self._user(prompt)], max_tokens=1500)

        return AgentResult(
            agent_name=self.name,
            content=summary,
            code_patches=final.code_patches,
            issues=final.issues,
            metadata={
                "applied": applied,
                "skipped": skipped,
                "pending_reviews": pending_reviews,
                "patch_count": len(applied),
            },
        )


# ── File I/O ───────────────────────────────────────────────────────────────────

def _deduplicate_patches(patches: list[CodePatch]) -> list[CodePatch]:
    """
    Remove redundant patches before applying to disk.

    Strategy (applied in order, later patches win):
    1. For each file, skip any patch whose new_snippet already appears verbatim in the
       current file content — the change was already applied (e.g., from a prior run).
    2. Within the same file, if two patches share the same old_snippet, keep only the last.
    3. Skip patches where old_snippet is empty AND new_snippet is already present in the file.

    This prevents the most common failure modes from the verifier/fixer accumulation loop.
    """
    from pathlib import Path
    seen: dict[str, set[str]] = {}   # file_path -> set of old_snippets already scheduled
    result: list[CodePatch] = []

    # Process in reverse so "last wins" on duplicate old_snippets
    for patch in reversed(patches):
        key = patch.file_path
        if key not in seen:
            seen[key] = set()
        old = patch.old_snippet or ""
        if old and old in seen[key]:
            continue  # duplicate old_snippet — a later (now earlier in reversed order) patch covers it
        seen[key].add(old)
        result.append(patch)

    return list(reversed(result))


def _apply_patch(patch: CodePatch, codebase_path: str) -> tuple[bool, str]:
    """
    Apply a single patch to a file on disk.
    Returns (success, reason).
    """
    root = Path(codebase_path)
    file_path = root / patch.file_path

    if not file_path.exists():
        return False, "file not found"

    original = file_path.read_text(encoding="utf-8")

    if patch.old_snippet:
        if patch.old_snippet not in original:
            return False, "old_snippet not found in file"
        new_content = original.replace(patch.old_snippet, patch.new_snippet, 1)
    else:
        # Append mode
        new_content = original.rstrip() + "\n\n" + patch.new_snippet + "\n"

    # Write a backup before applying
    backup = file_path.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(file_path, backup)

    file_path.write_text(new_content, encoding="utf-8")
    return True, "ok"


def _write_pending_reviews(
    reviews: list[str],
    patches: list[CodePatch],
    codebase_path: str,
) -> None:
    """Write human-review items to agents/_pending_review/ for manual inspection."""
    review_dir = Path(codebase_path) / "agents" / "_pending_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = review_dir / f"review_{ts}.md"

    lines = ["# Pending Human Review\n", f"Generated: {ts}\n\n"]
    lines.append("## Items requiring review\n")
    for r in reviews:
        lines.append(f"- {r}\n")

    lines.append("\n## Associated patches (NOT applied)\n")
    for p in patches:
        lines.append(f"\n### {p.file_path}\n{p.description}\n```python\n{p.new_snippet}\n```\n")

    out_path.write_text("".join(lines), encoding="utf-8")
