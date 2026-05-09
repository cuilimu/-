"""
analytics/news_digest.py — AI-generated weekly news digest.

Calls Claude Sonnet 4.6 with the past N days of items from the Notion
"Investment Research News & Opinions" database and returns a markdown
brief: TL;DR, themes, market-moving stories, ticker/macro tags.

Design notes
------------
* Sonnet 4.6 picked over Opus 4.7 — summarising 50–200 dated headlines is
  Sonnet's sweet spot; Opus would be ~1.7× the cost for marginal gain.
* `effort: "medium"` instead of the default `high` — saves ~30% output
  tokens on what is fundamentally a synthesis task, not deep reasoning.
* Streams the response so the Streamlit UI can render markdown live.
* No prompt caching for v1 — the digest is run on demand (typically once
  per week per user). The 5-min cache TTL won't survive between runs, so
  paying the 1.25× write premium with no read would be a net loss. Add
  caching only if usage shows repeated regenerates within a session.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

import pandas as pd


_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8000
_MAX_ITEMS = 200  # hard cap to keep input under ~30K tokens


_SYSTEM_PROMPT = """You are an investment-research analyst writing a weekly \
news brief for a portfolio manager covering global equities (with a TMT / \
semiconductor lean). You will receive the past week's curated headlines \
from the analyst's Notion database.

Your job:

1. **TL;DR** — 3–5 bullets at the top capturing the week's most market-moving \
narratives. Each bullet is one sentence, no preamble.

2. **Themes** — group items into 3–6 themes (e.g. "AI capex / semis", \
"Fed & rates", "Geopolitics", "Earnings"). Use H2 markdown headings. \
Under each theme, surface the 2–4 most consequential items with a one-line \
synthesis — not a re-statement of the headline. Mention tickers in **bold** \
when relevant.

3. **Watchlist for next week** — short bulleted list of catalysts to watch \
(earnings dates, macro releases, policy events) inferable from the items.

Style rules:
- Be concise and signal-dense. A PM reads this in 90 seconds.
- Cite sources inline as `[link](url)` only for the most important items \
(don't link every bullet — it's noisy).
- If two items contradict each other, name the contradiction explicitly.
- If the input is sparse or low-signal, say so directly rather than padding.
- Never invent facts not present in the input items.
- Output pure markdown. No HTML, no opening/closing pleasantries."""


class DigestUnavailable(RuntimeError):
    """Raised when the API key is missing, the SDK isn't installed, or the
    API rejects the request. The UI catches this and shows a setup hint."""


@dataclass
class DigestInput:
    """Filtered, formatted news items ready to be sent to Claude."""
    rows_text: str
    n_items: int
    window_days: int
    earliest: Optional[pd.Timestamp]
    latest: Optional[pd.Timestamp]


# ── Input prep ───────────────────────────────────────────────────────────────

def _resolve_date_column(df: pd.DataFrame) -> Optional[str]:
    for c in ("Date", "date", "Published", "Publish Date", "Created"):
        if c in df.columns:
            return c
    return None


def _resolve_title_column(df: pd.DataFrame) -> Optional[str]:
    """Notion exposes exactly one `title` property — it always normalises to
    a non-empty `str`. Identify it by being the object column where every
    non-null value is a string (excluding list-typed multi-select columns)
    with the longest average length."""
    if df.empty:
        return None
    best, best_len = None, -1.0
    for c in df.columns:
        if str(c).startswith("_"):
            continue
        if df[c].dtype != object:
            continue
        sample = df[c].dropna()
        if sample.empty:
            continue
        # Must be predominantly string (not list / dict / etc.)
        if not all(isinstance(v, str) for v in sample):
            continue
        avg = sample.str.len().mean()
        if avg > best_len:
            best, best_len = c, avg
    return best


def prepare_digest_input(df: pd.DataFrame, window_days: int = 7) -> DigestInput:
    """Filter df to items in the last `window_days` and serialise into the
    text block that Claude reads. Returns DigestInput; an empty result
    has `n_items == 0` and the caller should not invoke the model."""
    if df.empty:
        return DigestInput(rows_text="", n_items=0, window_days=window_days,
                           earliest=None, latest=None)

    title_col = _resolve_title_column(df)
    date_col  = _resolve_date_column(df)

    # Filter by date if we have a real date column
    if date_col is not None:
        dt = pd.to_datetime(df[date_col], errors="coerce", utc=True)
        cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=window_days)
        mask = dt >= cutoff
        sub = df.loc[mask].copy()
        sub["_dt_for_sort"] = dt.loc[mask]
    else:
        # Fall back to last_edited_time
        if "_edited" in df.columns:
            dt = pd.to_datetime(df["_edited"], errors="coerce", utc=True)
            cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=window_days)
            mask = dt >= cutoff
            sub = df.loc[mask].copy()
            sub["_dt_for_sort"] = dt.loc[mask]
        else:
            sub = df.copy()
            sub["_dt_for_sort"] = pd.NaT

    sub = sub.sort_values("_dt_for_sort", ascending=False, na_position="last")
    sub = sub.head(_MAX_ITEMS)

    if sub.empty:
        return DigestInput(rows_text="", n_items=0, window_days=window_days,
                           earliest=None, latest=None)

    # Build one line per item
    lines: list[str] = []
    for _, row in sub.iterrows():
        ts = row.get("_dt_for_sort")
        if pd.isna(ts):
            date_str = "—"
        else:
            date_str = pd.Timestamp(ts).strftime("%Y-%m-%d")

        title = (row.get(title_col) if title_col else None) or "(untitled)"
        if not isinstance(title, str):
            title = str(title)
        title = title.replace("\n", " ").strip()

        # Tags: first list-typed column with non-people semantics
        tags: list[str] = []
        for col, val in row.items():
            if isinstance(col, str) and col.startswith("_"):
                continue
            if col == title_col:
                continue
            if isinstance(val, list) and val and all(isinstance(v, str) for v in val):
                if isinstance(col, str) and col.lower() in (
                    "people", "owner", "assigned to", "author"
                ):
                    continue
                tags = [v for v in val if v]
                break

        # URL
        url = row.get("_url") or ""
        if not isinstance(url, str):
            url = ""

        # Other notable text properties (e.g. summary, notes, takeaway)
        extra_parts: list[str] = []
        for col, val in row.items():
            if not isinstance(col, str) or col.startswith("_"):
                continue
            if col in (title_col, date_col, "_dt_for_sort"):
                continue
            if isinstance(val, str) and len(val) > 0 and len(val) <= 400:
                extra_parts.append(f"{col}: {val.replace(chr(10), ' ').strip()}")

        line = f"- [{date_str}] {title}"
        if tags:
            line += f" | tags: {', '.join(tags)}"
        if url:
            line += f" | url: {url}"
        if extra_parts:
            line += f" | {' ; '.join(extra_parts[:3])}"
        lines.append(line)

    earliest = sub["_dt_for_sort"].min()
    latest   = sub["_dt_for_sort"].max()

    return DigestInput(
        rows_text="\n".join(lines),
        n_items=len(lines),
        window_days=window_days,
        earliest=earliest if not pd.isna(earliest) else None,
        latest=latest if not pd.isna(latest) else None,
    )


# ── Claude call ──────────────────────────────────────────────────────────────

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
        raise DigestUnavailable(
            "Anthropic API key not set. Add it on the Home page → API "
            "Configuration (starts with `sk-ant-`)."
        )
    return key


def stream_digest(
    digest_input: DigestInput,
    api_key: Optional[str] = None,
) -> Iterator[str]:
    """Yield text chunks of the markdown digest as Claude generates them.
    Raises DigestUnavailable if the SDK is missing / key is bad / API rejects."""
    if digest_input.n_items == 0:
        raise DigestUnavailable(
            f"No items in the past {digest_input.window_days} days to summarise."
        )

    key = _resolve_api_key(api_key)

    try:
        import anthropic
    except ImportError as exc:
        raise DigestUnavailable(
            "anthropic SDK not installed. Run `pip install anthropic`."
        ) from exc

    client = anthropic.Anthropic(api_key=key)

    # Header that gives Claude the framing of the input
    window_label = (
        f"{digest_input.earliest.strftime('%Y-%m-%d') if digest_input.earliest is not None else '—'} "
        f"→ {digest_input.latest.strftime('%Y-%m-%d') if digest_input.latest is not None else '—'}"
    )
    user_msg = (
        f"Past {digest_input.window_days} days of curated news "
        f"({digest_input.n_items} items, window {window_label}):\n\n"
        f"{digest_input.rows_text}\n\n"
        "Write the weekly brief now, following the structure in your "
        "system instructions."
    )

    try:
        with client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for chunk in stream.text_stream:
                yield chunk
    except anthropic.AuthenticationError as exc:
        raise DigestUnavailable(
            "Anthropic rejected the API key. Re-check it on the Home page."
        ) from exc
    except anthropic.RateLimitError as exc:
        raise DigestUnavailable(
            "Anthropic rate limit hit. Wait a minute and retry."
        ) from exc
    except anthropic.APIStatusError as exc:
        raise DigestUnavailable(
            f"Anthropic API error {exc.status_code}: {str(exc)[:160]}"
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise DigestUnavailable(
            f"Network error reaching Anthropic: {str(exc)[:120]}"
        ) from exc
