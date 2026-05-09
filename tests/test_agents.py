"""
tests/test_agents.py — Unit and integration tests for the agents/ module.

Tests are structured in three layers:
  1. Pure-unit (no API, no disk I/O) — test data types and helpers
  2. Patch-logic tests — test CodePatch merging, snippet parsing, numeric sanity
  3. Pipeline smoke tests — mock the Anthropic client, verify orchestration order

Run:
    pytest tests/test_agents.py -v
    pytest tests/test_agents.py -v -k "not slow"
"""
from __future__ import annotations

import asyncio
import math
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from stock_engine.agents.base import AgentContext, AgentResult, CodePatch
from stock_engine.agents.fixer import FixerAgent, _merge_patches
from stock_engine.agents.specialists import _parse_patches
from stock_engine.agents.verifier import _numeric_sanity_check, _syntax_check_patches


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def dummy_client():
    """Minimal AsyncAnthropic mock — returns a canned text response."""
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="VERIFIED: all checks passed")]
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


@pytest.fixture
def ctx(tmp_path):
    """AgentContext pointing at a minimal fake codebase."""
    (tmp_path / "analytics").mkdir()
    (tmp_path / "analytics" / "engine.py").write_text(
        "def sharpe(ret, rf=0.04, ann=252):\n    return (ret.mean()*ann - rf) / (ret.std()*ann**0.5)\n"
    )
    return AgentContext(
        user_query="Add Calmar ratio",
        codebase_path=str(tmp_path),
        relevant_code={"analytics/engine.py": "def sharpe(): pass\n"},
    )


@pytest.fixture
def aggregated_result():
    return AgentResult(
        agent_name="AggregatorAgent",
        content="Aggregated plan",
        code_patches=[
            CodePatch(
                file_path="analytics/engine.py",
                description="Fix Sharpe sign",
                old_snippet="return ret.mean() / ret.std()",
                new_snippet="return (ret.mean() - rf) / ret.std() * ann**0.5",
            )
        ],
        issues=[],
    )


# ── 1. Pure-unit: data types ───────────────────────────────────────────────────

class TestAgentResult:
    def test_to_context_block_includes_agent_name(self):
        r = AgentResult(agent_name="TestAgent", content="hello", issues=["bad thing"])
        block = r.to_context_block()
        assert "TestAgent" in block
        assert "bad thing" in block

    def test_to_context_block_no_issues(self):
        r = AgentResult(agent_name="A", content="ok")
        block = r.to_context_block()
        assert "none" in block

    def test_to_context_block_lists_patches(self):
        r = AgentResult(
            agent_name="A",
            content="ok",
            code_patches=[CodePatch("foo.py", "desc", "old", "new")],
        )
        block = r.to_context_block()
        assert "foo.py" in block
        assert "desc" in block


class TestCodePatch:
    def test_fields_preserved(self):
        p = CodePatch("a/b.py", "do thing", "old line", "new line")
        assert p.file_path == "a/b.py"
        assert p.old_snippet == "old line"
        assert p.new_snippet == "new line"


# ── 2. Patch parsing helpers ───────────────────────────────────────────────────

class TestParsePatches:
    def test_extracts_single_patch_and_issue(self):
        text = textwrap.dedent("""
            Some preamble.
            PATCH: analytics/engine.py
            DESCRIPTION: fix annualisation
            OLD: return ret.mean() * 252
            NEW: return ret.mean() * ann_factor
            ISSUE: Missing annualisation_factor from Config
        """)
        patches, issues = _parse_patches(text)
        assert len(patches) == 1
        assert patches[0].file_path == "analytics/engine.py"
        assert patches[0].description == "fix annualisation"
        assert "252" in patches[0].old_snippet
        assert "ann_factor" in patches[0].new_snippet
        assert len(issues) == 1
        assert "annualisation_factor" in issues[0]

    def test_extracts_multiple_patches(self):
        text = textwrap.dedent("""
            PATCH: file_a.py
            DESCRIPTION: first
            OLD: x = 1
            NEW: x = 2
            PATCH: file_b.py
            DESCRIPTION: second
            OLD: y = 3
            NEW: y = 4
        """)
        patches, _ = _parse_patches(text)
        assert len(patches) == 2
        assert patches[0].file_path == "file_a.py"
        assert patches[1].file_path == "file_b.py"

    def test_no_patches_no_issues(self):
        patches, issues = _parse_patches("Everything looks fine.")
        assert patches == []
        assert issues == []


# ── 3. Merge patches (FixerAgent logic) ───────────────────────────────────────

class TestMergePatches:
    def test_fix_applied_within_existing_patch(self):
        original = [
            CodePatch("f.py", "original desc", "old_orig", "new_orig with bug")
        ]
        fix = [
            CodePatch("f.py", "fixed bug", "with bug", "without bug")
        ]
        merged = _merge_patches(original, fix)
        assert len(merged) == 1
        assert "without bug" in merged[0].new_snippet
        assert "with bug" not in merged[0].new_snippet

    def test_fix_for_new_file_appended(self):
        original = [CodePatch("a.py", "d", "o", "n")]
        fix = [CodePatch("b.py", "new file fix", "x", "y")]
        merged = _merge_patches(original, fix)
        assert len(merged) == 2
        assert merged[1].file_path == "b.py"

    def test_original_not_mutated(self):
        original = [CodePatch("f.py", "d", "o", "n")]
        fix = [CodePatch("f.py", "fix", "n", "n_fixed")]
        _merge_patches(original, fix)
        assert original[0].new_snippet == "n"  # unchanged


# ── 4. VerifierAgent numeric sanity ───────────────────────────────────────────

class TestNumericSanity:
    def test_mdd_sign_issue_detected(self):
        """A patch wrapping MDD in abs() should be flagged (sign inversion)."""
        bad_patch = CodePatch(
            file_path="analytics/engine.py",
            description="broken max_drawdown",
            old_snippet="",
            new_snippet="max_drawdown = abs(drawdown.min())  # wrong: should be negative",
        )
        result = AgentResult(agent_name="A", content="", code_patches=[bad_patch])
        issues = _numeric_sanity_check(result)
        # The text-based abs() check must fire
        assert any("abs(" in i or "abs" in i.lower() for i in issues)

    def test_clean_patch_no_issues(self):
        """A patch without metric keywords should produce no numeric issues."""
        clean_patch = CodePatch(
            file_path="viz/theme.py",
            description="change colour",
            old_snippet="COLOR = 'red'",
            new_snippet="COLOR = 'blue'",
        )
        result = AgentResult(agent_name="A", content="", code_patches=[clean_patch])
        issues = _numeric_sanity_check(result)
        assert issues == []


# ── 5. Syntax check helper ────────────────────────────────────────────────────

class TestSyntaxCheck:
    def test_valid_patch_no_issues(self, tmp_path):
        (tmp_path / "f.py").write_text("x = 1\n")
        patch = CodePatch("f.py", "desc", "x = 1", "x = 2")
        result = AgentResult(agent_name="A", content="", code_patches=[patch])
        issues = _syntax_check_patches(result, str(tmp_path))
        assert issues == []

    def test_invalid_patch_syntax_flagged(self, tmp_path):
        (tmp_path / "f.py").write_text("x = 1\n")
        patch = CodePatch("f.py", "desc", "x = 1", "def (broken syntax:")
        result = AgentResult(agent_name="A", content="", code_patches=[patch])
        issues = _syntax_check_patches(result, str(tmp_path))
        assert any("syntax error" in i for i in issues)

    def test_missing_file_skipped(self, tmp_path):
        patch = CodePatch("nonexistent.py", "desc", "old", "new")
        result = AgentResult(agent_name="A", content="", code_patches=[patch])
        issues = _syntax_check_patches(result, str(tmp_path))
        assert issues == []  # silently skipped


# ── 6. Pipeline smoke (mocked Claude calls) ───────────────────────────────────

class TestPipelineMocked:
    """
    Verify the pipeline orchestration order and checkpoint population
    without hitting the actual Anthropic API.

    Each agent's _call method is patched to return a minimal valid response.
    """

    def _make_client(self, text: str = "VERIFIED: all checks passed") -> MagicMock:
        client = MagicMock()
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=msg)
        return client

    def test_pipeline_completes_and_sets_checkpoints(self, tmp_path):
        """All five phases run; checkpoints are populated."""
        from stock_engine.agents.pipeline import AgentPipeline

        # Minimal codebase for orchestrator's _module_tree
        (tmp_path / "config.py").write_text("class Config: pass\n")

        orchestrator_response = (
            '{"intent_summary": "test", "tasks": {'
            '"finance": "f", "statistics": "s", "coding": "c", "viz": "v"}, '
            '"relevant_files": {"finance": [], "statistics": [], "coding": [], "viz": []}}'
        )

        call_count = 0

        async def fake_create(**kwargs):
            nonlocal call_count
            call_count += 1
            msg = MagicMock()
            # First call = orchestrator (needs JSON), rest = anything
            if call_count == 1:
                msg.content = [MagicMock(text=orchestrator_response)]
            else:
                msg.content = [MagicMock(text="VERIFIED: all checks passed")]
            return msg

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(side_effect=fake_create)

        pipeline = AgentPipeline(
            client=client,
            codebase_path=str(tmp_path),
            max_fix_iterations=1,
            require_human_approval=False,
        )

        result = asyncio.run(pipeline.run("Add Calmar ratio"))

        assert result.status == "completed"
        assert result.ctx is not None
        assert "decomposition" in result.ctx.checkpoints
        assert "specialists" in result.ctx.checkpoints
        assert len(result.ctx.checkpoints["specialists"]) == 4

    def test_dry_run_returns_awaiting_approval(self, tmp_path):
        """require_human_approval=True must return status='awaiting_approval'."""
        from stock_engine.agents.pipeline import AgentPipeline

        (tmp_path / "config.py").write_text("class Config: pass\n")

        orchestrator_response = (
            '{"intent_summary": "test", "tasks": {'
            '"finance": "f", "statistics": "s", "coding": "c", "viz": "v"}, '
            '"relevant_files": {"finance": [], "statistics": [], "coding": [], "viz": []}}'
        )

        call_count = 0

        async def fake_create(**kwargs):
            nonlocal call_count
            call_count += 1
            msg = MagicMock()
            msg.content = [MagicMock(
                text=orchestrator_response if call_count == 1 else "all good"
            )]
            return msg

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(side_effect=fake_create)

        pipeline = AgentPipeline(
            client=client,
            codebase_path=str(tmp_path),
            max_fix_iterations=1,
            require_human_approval=True,
        )

        result = asyncio.run(pipeline.run("test query"))
        assert result.status == "awaiting_approval"
        assert result.output is None   # OutputAgent was NOT run
