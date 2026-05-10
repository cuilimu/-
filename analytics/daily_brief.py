"""
analytics/daily_brief.py — Daily market brief generator.

Steps: DuckDuckGo news search → yfinance prices → Claude report → Notion write.
All public functions raise DailyBriefError on failure.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Iterator, Optional

import pandas as pd


class DailyBriefError(RuntimeError):
    """Raised when any step of the daily brief pipeline fails."""


TICKERS = [
    "SOXX", "NVDA", "INTC", "MU", "WDC", "AMAT", "LRCX", "KLAC", "ASML",
    "AVGO", "MRVL", "TSM", "META", "MSFT", "GOOGL", "AMZN",
    "000660.KS", "005930.KS", "VRT", "CAT", "PWR", "EME", "FIX", "GNRC", "CMI",
]

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 6000

_SYSTEM_PROMPT = """You are a senior sell-side analyst covering TMT / semiconductors.
Write a concise daily market brief in CHINESE (Simplified) for a portfolio manager.
Be dense and signal-rich — readable in under 2 minutes.

Use these EXACT headings:

## 一、宏观环境
[3-5 bullets summarising macro news: employment, tariffs, geopolitics]

## 二、半导体/科技板块
[3-5 bullets on semiconductor and tech news. Bold important tickers like **NVDA**.]

## 三、市场数据综合判断
[2-3 sentences synthesising price moves with news. Call out any ticker that moved >±3%.]

THESIS: [Single sentence ≤25 words capturing today's core narrative.]

Rules: Only use facts from the provided input. Output pure Markdown. No HTML, no preamble."""


def search_news(query: str, max_results: int = 8) -> list[dict]:
    """Return up to max_results news items via DuckDuckGo News.
    Each item: {title, body, url, date, source}. Raises DailyBriefError on failure."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore[no-redef]
    except ImportError as exc:
        raise DailyBriefError(
            "ddgs not installed. Run: pip install ddgs"
        ) from exc
    try:
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results))
    except Exception as exc:
        raise DailyBriefError(f"DuckDuckGo search failed: {str(exc)[:160]}") from exc


def _fmt_news(items: list[dict], label: str) -> str:
    if not items:
        return f"### {label}\n[No results found]"
    lines = [f"### {label}"]
    for i, item in enumerate(items, 1):
        title = (item.get("title") or "").strip()
        body = (item.get("body") or "").strip()[:200]
        src = item.get("source") or ""
        dt = item.get("date") or ""
        lines.append(f"{i}. [{dt}] **{title}** ({src})")
        if body:
            lines.append(f"   {body}")
    return "\n".join(lines)


def fetch_prices(tickers: list[str] = TICKERS) -> pd.DataFrame:
    """Batch-download today's close + % change for all tickers via yfinance.
    Returns DataFrame with columns [ticker, price, change_pct]."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise DailyBriefError("yfinance not installed.") from exc

    try:
        raw = yf.download(
            tickers, period="2d", auto_adjust=True, progress=False, group_by="ticker",
        )
    except Exception as exc:
        raise DailyBriefError(f"yfinance download failed: {str(exc)[:160]}") from exc

    rows = []
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                closes = raw["Close"].dropna()
            else:
                closes = raw["Close"][ticker].dropna()
            price = float(closes.iloc[-1]) if len(closes) >= 1 else None
            prev  = float(closes.iloc[-2]) if len(closes) >= 2 else None
            chg   = round((price - prev) / prev * 100, 2) if price and prev else None
            rows.append({"ticker": ticker, "price": round(price, 2) if price else None, "change_pct": chg})
        except Exception:
            rows.append({"ticker": ticker, "price": None, "change_pct": None})
    return pd.DataFrame(rows)


def _fmt_prices(df: pd.DataFrame) -> str:
    lines = ["### Market Prices (Today)"]
    lines.append("| Ticker | Price | Chg% |")
    lines.append("|--------|-------|------|")
    for _, r in df.iterrows():
        p = r["price"]
        c = r["change_pct"]
        price = f"{p:.2f}" if p is not None and p == p else "N/A"   # NaN != NaN
        chg   = f"{c:+.2f}%" if c is not None and c == c else "N/A"
        flag  = " ⚡" if c is not None and c == c and abs(c) >= 3 else ""
        lines.append(f"| {r['ticker']} | {price} | {chg}{flag} |")
    return "\n".join(lines)


def _resolve_api_key(explicit: Optional[str]) -> str:
    key = (explicit or "").strip()
    if not key:
        try:
            import streamlit as st
            key = (st.session_state.get("anthropic_api_key") or "").strip()
        except Exception:
            pass
    if not key:
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise DailyBriefError(
            "Anthropic API key not set. Add it on the Home page → API Configuration."
        )
    return key


def _user_message(
    news_macro: list[dict],
    news_semi: list[dict],
    prices_df: pd.DataFrame,
    report_date: date,
) -> str:
    return "\n\n".join([
        f"Daily Brief Request — {report_date.isoformat()}",
        _fmt_news(news_macro, "Macro News (Employment / Tariffs / Geopolitics)"),
        _fmt_news(news_semi, "Semiconductor & Tech Sector News"),
        _fmt_prices(prices_df),
        "Write the daily brief now, in Chinese, following your system instructions.",
    ])


def stream_daily_brief(
    news_macro: list[dict],
    news_semi: list[dict],
    prices_df: pd.DataFrame,
    report_date: Optional[date] = None,
    api_key: Optional[str] = None,
) -> Iterator[str]:
    """Yield markdown text chunks from Claude. For Streamlit streaming UI."""
    if report_date is None:
        report_date = date.today()
    key = _resolve_api_key(api_key)
    try:
        import anthropic
    except ImportError as exc:
        raise DailyBriefError("anthropic SDK not installed.") from exc

    client = anthropic.Anthropic(api_key=key)
    try:
        with client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_message(news_macro, news_semi, prices_df, report_date)}],
        ) as stream:
            for chunk in stream.text_stream:
                yield chunk
    except anthropic.AuthenticationError as exc:
        raise DailyBriefError("Anthropic API key rejected. Re-check it on the Home page.") from exc
    except anthropic.RateLimitError as exc:
        raise DailyBriefError("Anthropic rate limit hit. Wait a minute and retry.") from exc
    except anthropic.APIStatusError as exc:
        raise DailyBriefError(f"Anthropic API error {exc.status_code}: {str(exc)[:160]}") from exc
    except anthropic.APIConnectionError as exc:
        raise DailyBriefError(f"Network error reaching Anthropic: {str(exc)[:120]}") from exc


def generate_daily_brief(
    news_macro: list[dict],
    news_semi: list[dict],
    prices_df: pd.DataFrame,
    report_date: Optional[date] = None,
    api_key: Optional[str] = None,
) -> str:
    """Non-streaming version — returns the full markdown report as a string."""
    return "".join(stream_daily_brief(news_macro, news_semi, prices_df, report_date, api_key))


def extract_thesis(report: str) -> str:
    """Parse the THESIS line from the report. Handles bold markers (**THESIS:**)."""
    import re
    for line in report.splitlines():
        m = re.search(r"\*{0,2}THESIS:\*{0,2}\s*(.*)", line, re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip("*").strip()
    return report.strip()[:80].replace("\n", " ")


_MACRO_QUERY = "US economy tariffs trade war employment geopolitics 2026"
_SEMI_QUERY  = "semiconductor AI chips NVDA ASML TSMC technology stocks 2026"


def run_full_pipeline(
    report_date: Optional[date] = None,
    anthropic_key: Optional[str] = None,
    notion_token: Optional[str] = None,
    notion_db_id: Optional[str] = None,
) -> tuple[str, str]:
    """Run all 4 steps. Returns (thesis, full_report_markdown)."""
    from stock_engine.data.notion_daily import write_daily_summary

    if report_date is None:
        report_date = date.today()

    news_macro = search_news(_MACRO_QUERY, max_results=8)
    news_semi  = search_news(_SEMI_QUERY, max_results=8)
    prices_df  = fetch_prices(TICKERS)
    report     = generate_daily_brief(news_macro, news_semi, prices_df, report_date, anthropic_key)
    thesis     = extract_thesis(report)

    write_daily_summary(
        report_date=report_date,
        thesis=thesis,
        summary=report,
        token=notion_token,
        database_id=notion_db_id,
    )
    return thesis, report
