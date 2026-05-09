"""
agents/cli.py — Command-line entry point for the multi-agent pipeline.

Installed as `stock-agent` via pyproject.toml [project.scripts].

Usage examples:
    # Dry-run: show what would change, apply nothing to disk
    stock-agent --dry-run "Add Calmar ratio to PerformanceMetrics"

    # Full run: analyse, verify, fix, apply patches
    stock-agent "Add Calmar ratio to PerformanceMetrics"

    # Pipe from stdin
    echo "Explain what StatisticsAgent found" | stock-agent --stdin

    # Point at a different codebase root
    stock-agent --codebase /path/to/stock_engine "Improve drawdown chart colours"

    # More fix iterations before giving up
    stock-agent --max-iterations 5 "Fix Sharpe annualisation bug"

Environment:
    ANTHROPIC_API_KEY — required (read by the Anthropic SDK automatically)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import textwrap
from pathlib import Path

# ── Guard: clear error if anthropic SDK is missing ────────────────────────────
try:
    import anthropic
except ModuleNotFoundError:
    sys.exit(
        "ERROR: 'anthropic' package not installed.\n"
        "Run:  pip install anthropic\n"
        "Or:   pip install -e '.[agents]'  (after adding anthropic to pyproject.toml)"
    )

from stock_engine.agents.pipeline import AgentPipeline, PipelineResult


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-agent",
        description="Run the multi-agent analysis pipeline on the stock_engine codebase.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              stock-agent --dry-run "Add Calmar ratio to PerformanceMetrics"
              stock-agent "Fix Sharpe annualisation for monthly frequency"
              stock-agent --max-iterations 5 "Improve drawdown chart colour accessibility"
        """),
    )
    p.add_argument(
        "query",
        nargs="?",
        help="Natural-language request (omit if using --stdin)",
    )
    p.add_argument(
        "--stdin",
        action="store_true",
        help="Read query from stdin instead of positional argument",
    )
    p.add_argument(
        "--codebase",
        default=None,
        metavar="PATH",
        help="Absolute path to the stock_engine root (default: auto-detect from package location)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyse and verify but do NOT apply patches to disk (require_human_approval=True)",
    )
    p.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        metavar="N",
        help="Max Verifier→Fixer loop iterations (default: 3)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-stage completion messages and issue counts",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output final result as JSON instead of plain text",
    )
    return p


def _resolve_codebase(path: str | None) -> str:
    if path:
        resolved = Path(path).resolve()
        if not resolved.is_dir():
            sys.exit(f"ERROR: --codebase path does not exist: {resolved}")
        return str(resolved)
    # Auto-detect: walk up from this file until we find pyproject.toml
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return str(parent)
    sys.exit(
        "ERROR: Could not auto-detect codebase root.\n"
        "Use --codebase /path/to/stock_engine"
    )


def _stage_callback(verbose: bool):
    def _cb(stage: str, result) -> None:
        if not verbose:
            return
        issue_count = len(result.issues)
        patch_count = len(result.code_patches)
        tag = f"[{stage}]"
        print(
            f"  {tag:<30} issues={issue_count}  patches={patch_count}",
            file=sys.stderr,
        )
    return _cb


async def _run(args: argparse.Namespace) -> int:
    # ── Resolve query ──────────────────────────────────────────────────────────
    if args.stdin:
        query = sys.stdin.read().strip()
    elif args.query:
        query = args.query.strip()
    else:
        print("ERROR: Provide a query as a positional argument or use --stdin.", file=sys.stderr)
        return 1

    if not query:
        print("ERROR: Query is empty.", file=sys.stderr)
        return 1

    # ── Resolve ANTHROPIC_API_KEY ──────────────────────────────────────────────
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Export it before running:  export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        return 1

    codebase = _resolve_codebase(args.codebase)

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
        print(f"\n🔍 Query:    {query}", file=sys.stderr)
        print(f"📁 Codebase: {codebase}", file=sys.stderr)
        print(f"🔁 Max iter: {args.max_iterations}", file=sys.stderr)
        print(f"🏃 Mode:     {'dry-run' if args.dry_run else 'live'}\n", file=sys.stderr)

    # ── Build and run pipeline ─────────────────────────────────────────────────
    client = anthropic.AsyncAnthropic()
    pipeline = AgentPipeline(
        client=client,
        codebase_path=codebase,
        max_fix_iterations=args.max_iterations,
        require_human_approval=args.dry_run,
        on_stage_complete=_stage_callback(args.verbose),
    )

    result: PipelineResult = await pipeline.run(query)

    # ── Output ─────────────────────────────────────────────────────────────────
    if args.output_json:
        import json
        out = {
            "status": result.status,
            "error": result.error,
            "content": result.output.content if result.output else None,
            "applied": result.output.metadata.get("applied", []) if result.output else [],
            "skipped": result.output.metadata.get("skipped", []) if result.output else [],
            "pending_reviews": result.output.metadata.get("pending_reviews", []) if result.output else [],
            "remaining_issues": result.output.issues if result.output else [],
        }
        print(json.dumps(out, indent=2))
        return 0 if result.status in ("completed", "awaiting_approval") else 1

    # Plain text
    print()
    if result.status == "failed":
        print(f"❌ Pipeline failed: {result.error}", file=sys.stderr)
        return 1

    if result.status == "awaiting_approval":
        print("⏸  Dry-run complete — no files were modified.")
        print()
        if result.ctx and result.ctx.checkpoints.get("fixed"):
            fixed = result.ctx.checkpoints["fixed"]
            if fixed.code_patches:
                print("Patches that would be applied:")
                for p in fixed.code_patches:
                    print(f"  • {p.file_path}: {p.description}")
            if fixed.issues:
                print("\nRemaining issues (unfixable within iteration cap):")
                for i in fixed.issues:
                    print(f"  ⚠  {i}")
        return 0

    # Completed
    output = result.output
    print(output.content)

    applied = output.metadata.get("applied", [])
    skipped = output.metadata.get("skipped", [])
    pending = output.metadata.get("pending_reviews", [])

    if applied:
        print(f"\n✅ Applied {len(applied)} patch(es):")
        for a in applied:
            print(f"  • {a}")
    if skipped:
        print(f"\n⚠  Skipped {len(skipped)} patch(es) (snippet not found in file):")
        for s in skipped:
            print(f"  • {s}")
    if pending:
        print(f"\n🔎 {len(pending)} item(s) written to agents/_pending_review/ for human review.")

    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
