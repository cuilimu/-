"""
scripts/daily_news_writer.py — Standalone CLI for the Daily Market Brief pipeline.

Usage:
    python scripts/daily_news_writer.py
    python scripts/daily_news_writer.py --date 2026-05-09

Loads API keys from ~/.stock_engine/api_keys.json, then runs all four pipeline
steps (DuckDuckGo news search → yfinance prices → Claude report → Notion write).

Exit codes: 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import date

# Force UTF-8 output so Chinese characters print cleanly on Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and publish a Daily Market Brief to Notion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "API keys are loaded from ~/.stock_engine/api_keys.json.\n"
            "Required keys: anthropic_api_key, notion_token, notion_daily_db_id\n\n"
            "Example:\n"
            "  python scripts/daily_news_writer.py\n"
            "  python scripts/daily_news_writer.py --date 2026-05-09\n"
        ),
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Report date in ISO format (default: today).",
    )
    return parser.parse_args()


def _parse_date(date_str: str | None) -> date:
    if date_str is None:
        return date.today()
    try:
        return date.fromisoformat(date_str)
    except ValueError as exc:
        print(f"ERROR: Invalid date format '{date_str}'. Expected YYYY-MM-DD.", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> None:
    args = _parse_args()
    report_date = _parse_date(args.date)

    print(f"Daily Market Brief — {report_date.isoformat()}")
    print("=" * 50)

    # Load keys
    print("Loading API keys from ~/.stock_engine/api_keys.json …")
    try:
        from stock_engine.data.api_keys import load_keys_from_file
        keys = load_keys_from_file()
    except Exception as exc:
        print(f"ERROR: Could not load API keys: {exc}", file=sys.stderr)
        sys.exit(1)

    anthropic_key    = keys.get("anthropic_api_key", "")
    notion_token     = keys.get("notion_token", "")
    notion_daily_db  = keys.get("notion_daily_db_id", "")

    if not anthropic_key:
        print("ERROR: 'anthropic_api_key' not found in ~/.stock_engine/api_keys.json", file=sys.stderr)
        sys.exit(1)
    if not notion_token:
        print("ERROR: 'notion_token' not found in ~/.stock_engine/api_keys.json", file=sys.stderr)
        sys.exit(1)

    print("Keys loaded.")

    # Run pipeline
    try:
        from stock_engine.analytics.daily_brief import (
            DailyBriefError,
            _MACRO_QUERY,
            _SEMI_QUERY,
            TICKERS,
            search_news,
            fetch_prices,
            generate_daily_brief,
            extract_thesis,
        )
        from stock_engine.data.notion_daily import (
            NotionDailyUnavailable,
            write_daily_summary,
        )

        print("Step 1/4 — Searching macro news …")
        news_macro = search_news(_MACRO_QUERY, max_results=8)
        print(f"  Found {len(news_macro)} macro articles.")

        print("Step 2/4 — Searching semiconductor/tech news …")
        news_semi = search_news(_SEMI_QUERY, max_results=8)
        print(f"  Found {len(news_semi)} sector articles.")

        print("Step 3/4 — Fetching prices for 25 tickers …")
        prices_df = fetch_prices(TICKERS)
        valid = prices_df["price"].notna().sum()
        print(f"  Retrieved prices for {valid}/{len(TICKERS)} tickers.")

        print("Step 4a/4 — Calling Claude Sonnet 4.6 …")
        report = generate_daily_brief(
            news_macro, news_semi, prices_df, report_date, anthropic_key
        )
        thesis = extract_thesis(report)
        print(f"  Thesis: {thesis}")

        print("Step 4b/4 — Writing to Notion …")
        url = write_daily_summary(
            report_date=report_date,
            thesis=thesis,
            summary=report,
            token=notion_token,
            database_id=notion_daily_db or None,
        )
        print(f"  Published: {url}")

    except DailyBriefError as exc:
        print(f"ERROR (pipeline): {exc}", file=sys.stderr)
        sys.exit(1)
    except NotionDailyUnavailable as exc:
        print(f"ERROR (Notion): {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR (unexpected): {exc}", file=sys.stderr)
        sys.exit(1)

    print()
    print("Done. Daily brief published successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
