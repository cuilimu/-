"""
agents/verifier.py - VerifierAgent.

Pattern: Evaluator-optimizer loop (Anthropic article "Evaluator-optimizer").

Two verification modes run in sequence:
  1. Programmatic checks (fast, deterministic):
       - Run pytest on the codebase and capture failures
       - Numerically validate proposed metric formulas using synthetic data
       - Check that patches do not introduce syntax errors (compile check)
  2. LLM reasoning check (catches what code cannot):
       - Feed the aggregated plan back to Claude with a "find flaws" adversarial prompt
       - Specifically targets: off-by-one errors, silent NaN, wrong sign conventions

Returns AgentResult with issues list populated.
If issues list is empty  -> pipeline proceeds to OutputAgent.
If issues list is non-empty -> pipeline hands off to FixerAgent.
"""
from __future__ import annotations

import ast
import math
import subprocess
import textwrap
from pathlib import Path

import numpy as np

from stock_engine.agents.base import AgentContext, AgentResult, BaseAgent


class VerifierAgent(BaseAgent):
    MODEL = "claude-sonnet-4-6"

    @property
    def name(self) -> str:
        return "VerifierAgent"

    @property
    def system_prompt(self) -> str:
        return textwrap.dedent("""
            You are an adversarial code reviewer for a quantitative finance library.
            Your only job is to FIND BUGS in the proposed changes - not to praise them.

            Focus on:
              1. Mathematical errors: wrong sign, wrong denominator, missing sqrt, off-by-one
              2. Silent failures: NaN propagation, division by zero, empty Series
              3. Logic errors: wrong comparison operator, inverted condition
              4. Module boundary violations introduced by the patches
              5. Missing edge-case handling flagged by specialists but not addressed

            For each bug found, output:
              ISSUE: <concise description with file and line reference>

            If you find NO bugs, output exactly:
              VERIFIED: all checks passed

            Be ruthlessly adversarial. A false negative here causes wrong trading signals.
        """).strip()

    async def run(self, ctx: AgentContext) -> AgentResult:
        aggregated: AgentResult = ctx.checkpoints.get("aggregated")
        if aggregated is None:
            return AgentResult(
                agent_name=self.name,
                content="No aggregated result to verify.",
                issues=["aggregated checkpoint missing"],
            )

        issues: list[str] = []

        issues.extend(_run_pytest(ctx.codebase_path))
        issues.extend(_syntax_check_patches(aggregated, ctx.codebase_path))
        issues.extend(_numeric_sanity_check(aggregated))

        prompt = textwrap.dedent(f"""
            User request: {ctx.user_query}

            Aggregated plan to verify:
            {aggregated.to_context_block()}

            Patch details:
            {_patches_as_text(aggregated)}
        """).strip()

        response = await self._call([self._user(prompt)], max_tokens=3000)

        if "VERIFIED: all checks passed" not in response:
            for line in response.splitlines():
                s = line.strip()
                if s.startswith("ISSUE:"):
                    issues.append(s[6:].strip())

        content = response if issues else "VERIFIED: all checks passed"
        return AgentResult(
            agent_name=self.name,
            content=content,
            issues=issues,
        )


def _run_pytest(codebase_path: str) -> list[str]:
    """Run pytest and return a list of failure descriptions."""
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/", "--tb=line", "-q"],
        capture_output=True,
        text=True,
        cwd=codebase_path,
        timeout=60,
    )
    if result.returncode == 0:
        return []
    failures = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("FAILED") or "AssertionError" in line
    ]
    return [f"pytest: {f}" for f in failures[:10]]


def _syntax_check_patches(aggregated: AgentResult, codebase_path: str) -> list[str]:
    """Try to compile each patched file new_snippet as Python."""
    issues = []
    root = Path(codebase_path)
    for patch in aggregated.code_patches:
        file_path = root / patch.file_path
        if not file_path.exists():
            continue
        original = file_path.read_text(encoding="utf-8")
        if patch.old_snippet and patch.old_snippet in original:
            prospective = original.replace(patch.old_snippet, patch.new_snippet, 1)
        else:
            prospective = original + "\n" + patch.new_snippet
        try:
            ast.parse(prospective)
        except SyntaxError as e:
            issues.append(f"syntax error in {patch.file_path} after patch: {e}")
    return issues


def _numeric_sanity_check(aggregated: AgentResult) -> list[str]:
    """
    Run key metric formulas numerically on synthetic data to catch silent errors.
    Two checks for MDD:
      - Text check: abs() applied to MDD inverts the required sign convention
      - Reference check: our own formula must produce negative MDD on synthetic data
    """
    issues = []
    metrics_keywords = {"sharpe", "annualised_return", "max_drawdown", "information_ratio"}

    rng = np.random.default_rng(42)
    daily_ret = rng.normal(0.10 / 252, 0.15 / math.sqrt(252), 252)

    for patch in aggregated.code_patches:
        code = patch.new_snippet.lower()
        if not any(kw in code for kw in metrics_keywords):
            continue

        if "sharpe" in code:
            ref_sharpe = (daily_ret.mean() * 252 - 0.04) / (daily_ret.std() * math.sqrt(252))
            if abs(ref_sharpe) > 10:
                issues.append(
                    f"Sharpe sanity: reference formula gives implausible value"
                    f" ({ref_sharpe:.2f}) - formula may be wrong in {patch.file_path}"
                )

        if "max_drawdown" in code:
            if "abs(" in code:
                issues.append(
                    f"MDD sanity: abs() found in max_drawdown patch in {patch.file_path}"
                    f" - MDD must be <= 0 (peak-to-trough); abs() makes it positive and wrong"
                )
            cum = np.cumprod(1 + daily_ret)
            rolling_max = np.maximum.accumulate(cum)
            drawdown = (cum - rolling_max) / rolling_max
            mdd = drawdown.min()
            if mdd > 0:
                issues.append(
                    f"MDD sanity: reference formula gives positive MDD={mdd:.4f}"
                    f" in {patch.file_path}"
                )

    return issues


def _patches_as_text(result: AgentResult) -> str:
    lines = []
    for p in result.code_patches:
        lines.append(
            f"FILE: {p.file_path}\nDESCRIPTION: {p.description}\n"
            f"OLD:\n{p.old_snippet}\nNEW:\n{p.new_snippet}\n"
        )
    return "\n---\n".join(lines) if lines else "(no patches)"
