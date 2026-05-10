"""
data/notion_daily.py — Read/write the "Claude News" Daily Brief Notion database.

Schema: Thesis of News (title) | Date (date) | Daily News Summary (rich_text)

Database ID for pages.create: 35b980589b6380ae8599e5a88d32297f
Data source ID for querying:  35b98058-9b63-802b-b74a-000b02e29ec2

Auth & DB-ID resolution order:
    1. explicit args  →  2. st.session_state[notion_token / notion_daily_db_id]
    3. env vars NOTION_TOKEN / NOTION_DAILY_DB_ID

Failure mode: every public function raises NotionDailyUnavailable with a short,
actionable message. The UI catches that and renders a setup-hint card.

Note on Notion limits:
  - rich_text property: 2000-char limit per block. Summary is truncated.
  - Page body blocks: 2000-char limit per block. Long text is split on
    double-newlines and further chunked if any paragraph exceeds 2000 chars.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

import pandas as pd


class NotionDailyUnavailable(RuntimeError):
    """Raised when token / DB ID / package / network is missing."""


# Hard-coded IDs for the Claude News database.
_DEFAULT_DB_ID        = "35b980589b6380ae8599e5a88d32297f"
_DEFAULT_DS_ID        = "35b98058-9b63-802b-b74a-000b02e29ec2"

_RICH_TEXT_LIMIT      = 2000   # Notion hard cap per rich_text block
_BLOCK_CHAR_LIMIT     = 2000   # Notion hard cap per paragraph block


# ── Credential resolution ─────────────────────────────────────────────────────

def _resolve_credentials(
    token: Optional[str],
    database_id: Optional[str],
) -> tuple[str, str]:
    """Resolve (token, database_id) from explicit args → Streamlit session_state
    → env vars. Falls back to the hard-coded DB ID when the caller provides
    nothing and the env var is also missing."""
    tok  = (token or "").strip()
    dbid = (database_id or "").strip()

    if not tok or not dbid:
        try:
            import streamlit as st  # noqa: WPS433
            ss = st.session_state
            if not tok:
                tok  = (ss.get("notion_token") or "").strip()
            if not dbid:
                dbid = (ss.get("notion_daily_db_id") or "").strip()
        except Exception:
            pass

    if not tok:
        tok  = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not dbid:
        dbid = (os.environ.get("NOTION_DAILY_DB_ID") or "").strip()

    if not tok:
        raise NotionDailyUnavailable(
            "Notion token not set. Add it on the Home page → API Configuration."
        )
    # Fall back to the well-known DB ID if still missing.
    if not dbid:
        dbid = _DEFAULT_DB_ID

    return tok, dbid


# ── Notion client helper ──────────────────────────────────────────────────────

def _get_client(token: str):
    """Return an initialised notion_client.Client. Raises NotionDailyUnavailable
    if the package is not installed."""
    try:
        from notion_client import Client  # type: ignore
    except ImportError as exc:
        raise NotionDailyUnavailable(
            "notion-client not installed. Run `pip install notion-client`."
        ) from exc
    try:
        return Client(auth=token)
    except Exception as exc:
        raise NotionDailyUnavailable(f"Notion client init failed: {exc}") from exc


# ── Data-source ID resolution (mirrors notion_news.py) ───────────────────────

def _resolve_data_source_id(client, database_id: str) -> str:
    """Return the first data_source ID for the given database.
    Mirrors the pattern from data/notion_news.py."""
    try:
        db = client.databases.retrieve(database_id=database_id)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == "object_not_found":
            raise NotionDailyUnavailable(
                "Daily Brief database not found. Check the DB ID and that your "
                "integration is connected (DB → ⋯ → Connections)."
            ) from exc
        if code == "unauthorized":
            raise NotionDailyUnavailable(
                "Token rejected by Notion. Re-check it on the Home page."
            ) from exc
        raise NotionDailyUnavailable(f"databases.retrieve failed: {exc}") from exc

    sources = db.get("data_sources") or []
    if not sources:
        # Fall back to the hard-coded data-source ID so a freshly-connected
        # integration that hasn't indexed yet still works for querying.
        return _DEFAULT_DS_ID
    return sources[0]["id"]


# ── Block chunking ────────────────────────────────────────────────────────────

def _split_into_blocks(text: str) -> list[str]:
    """Split *text* into chunks of ≤ _BLOCK_CHAR_LIMIT characters.

    Strategy:
    1. Split on double-newlines (paragraph boundaries).
    2. If any paragraph still exceeds the limit, hard-chop it at _BLOCK_CHAR_LIMIT.
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    for para in paragraphs:
        if not para.strip():
            continue
        while len(para) > _BLOCK_CHAR_LIMIT:
            chunks.append(para[:_BLOCK_CHAR_LIMIT])
            para = para[_BLOCK_CHAR_LIMIT:]
        if para:
            chunks.append(para)
    return chunks or [""]


def _make_paragraph_blocks(text: str) -> list[dict]:
    """Return a list of Notion paragraph block dicts for the given text."""
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": chunk},
                    }
                ]
            },
        }
        for chunk in _split_into_blocks(text)
    ]


# ── Write ─────────────────────────────────────────────────────────────────────

def write_daily_summary(
    report_date: date,
    thesis: str,
    summary: str,
    token: Optional[str] = None,
    database_id: Optional[str] = None,
) -> str:
    """Create a new page in the Claude News database.

    Parameters
    ----------
    report_date : date
        The date of the brief (used for the Date property).
    thesis : str
        Short one-sentence thesis (used as the page title).
    summary : str
        Full markdown report. Stored as rich_text property (truncated to
        2000 chars) AND as paragraph blocks in the page body.
    token : str, optional
        Notion integration token. Resolved via session_state / env if omitted.
    database_id : str, optional
        Target database ID. Defaults to the hard-coded Claude News DB ID.

    Returns
    -------
    str
        URL of the newly created Notion page.
    """
    tok, dbid = _resolve_credentials(token, database_id)
    client = _get_client(tok)

    # Truncate for the rich_text property (Notion's 2000-char limit).
    summary_preview = summary[:_RICH_TEXT_LIMIT]

    properties: dict = {
        "Thesis of News": {
            "title": [
                {
                    "type": "text",
                    "text": {"content": (thesis or "")[:_RICH_TEXT_LIMIT]},
                }
            ]
        },
        "Date": {
            "date": {"start": report_date.isoformat()}
        },
        "Daily News Summary": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": summary_preview},
                }
            ]
        },
    }

    # Build the full report as paragraph blocks for the page body.
    children = _make_paragraph_blocks(summary)

    try:
        page = client.pages.create(
            parent={"database_id": dbid},
            properties=properties,
            children=children,
        )
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == "object_not_found":
            raise NotionDailyUnavailable(
                "Daily Brief database not found. Check the DB ID and that your "
                "integration is connected (DB → ⋯ → Connections)."
            ) from exc
        if code == "unauthorized":
            raise NotionDailyUnavailable(
                "Notion token rejected. Re-check it on the Home page."
            ) from exc
        raise NotionDailyUnavailable(
            f"Failed to create Notion page: {str(exc)[:200]}"
        ) from exc

    return page.get("url") or ""


# ── Read ──────────────────────────────────────────────────────────────────────

def fetch_daily_summaries(
    token: Optional[str] = None,
    database_id: Optional[str] = None,
    limit: int = 30,
) -> pd.DataFrame:
    """Return a DataFrame of the most recent daily summaries, newest-first.

    Columns: thesis, date, summary_preview, _url, _id

    Parameters
    ----------
    token : str, optional
        Notion integration token.
    database_id : str, optional
        Database ID. Defaults to the hard-coded Claude News DB ID.
    limit : int
        Maximum rows to return (default 30).

    Returns
    -------
    pd.DataFrame
        May be empty if no pages exist yet.
    """
    tok, dbid = _resolve_credentials(token, database_id)
    client = _get_client(tok)

    data_source_id = _resolve_data_source_id(client, dbid)

    rows: list[dict] = []
    cursor: Optional[str] = None

    try:
        while True:
            kwargs: dict = {"data_source_id": data_source_id, "page_size": min(limit, 100)}
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = client.data_sources.query(**kwargs)
            for page in resp.get("results", []):
                props = page.get("properties", {})

                # Thesis of News (title)
                thesis_prop = props.get("Thesis of News", {})
                thesis_rt = thesis_prop.get("title") or []
                thesis = "".join(p.get("plain_text", "") for p in thesis_rt).strip()

                # Date
                date_prop = props.get("Date", {})
                date_val = (date_prop.get("date") or {}).get("start") or ""

                # Daily News Summary (rich_text)
                summary_prop = props.get("Daily News Summary", {})
                summary_rt = summary_prop.get("rich_text") or []
                summary_preview = "".join(
                    p.get("plain_text", "") for p in summary_rt
                ).strip()

                rows.append({
                    "thesis":          thesis,
                    "date":            date_val,
                    "summary_preview": summary_preview,
                    "_url":            page.get("url") or "",
                    "_id":             page.get("id") or "",
                })

                if len(rows) >= limit:
                    break

            if len(rows) >= limit or not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

    except NotionDailyUnavailable:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == "object_not_found":
            raise NotionDailyUnavailable(
                "Daily Brief database not found. Check the DB ID and that your "
                "integration is connected (DB → ⋯ → Connections)."
            ) from exc
        if code == "unauthorized":
            raise NotionDailyUnavailable(
                "Notion token rejected. Re-check it on the Home page."
            ) from exc
        raise NotionDailyUnavailable(
            f"Notion query failed: {str(exc)[:160]}"
        ) from exc

    if not rows:
        return pd.DataFrame(columns=["thesis", "date", "summary_preview", "_url", "_id"])

    df = pd.DataFrame(rows)
    # Drop pages with neither a thesis nor a valid date (failed/empty writes)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=False)
    has_content = df["thesis"].str.strip().astype(bool) | df["date"].notna()
    df = df[has_content]
    if df.empty:
        return df.reset_index(drop=True)
    # Sort newest first
    df = df.sort_values("date", ascending=False, na_position="last").reset_index(drop=True)
    return df


# ── Full page body ────────────────────────────────────────────────────────────

def fetch_page_body(
    page_id: str,
    token: Optional[str] = None,
) -> str:
    """Retrieve the full report text from a page's block children.

    The daily brief is written as paragraph blocks (because the rich_text
    property is capped at 2000 chars). This function reassembles those blocks
    into a single markdown string suitable for rendering.

    Returns an empty string if the page has no text blocks or on any error.
    """
    tok, _ = _resolve_credentials(token, _DEFAULT_DB_ID)
    client = _get_client(tok)

    try:
        resp = client.blocks.children.list(block_id=page_id, page_size=100)
    except Exception:
        return ""

    parts: list[str] = []
    for block in resp.get("results", []):
        btype = block.get("type", "")
        bdata = block.get(btype, {})
        rich  = bdata.get("rich_text") or []
        text  = "".join(r.get("plain_text", "") for r in rich).strip()
        if not text:
            continue
        if btype == "heading_1":
            parts.append(f"# {text}")
        elif btype == "heading_2":
            parts.append(f"## {text}")
        elif btype == "heading_3":
            parts.append(f"### {text}")
        elif btype in ("bulleted_list_item", "numbered_list_item"):
            parts.append(f"- {text}")
        else:
            parts.append(text)

    # Handle pagination (unlikely for typical reports but correct to handle)
    while resp.get("has_more"):
        try:
            resp = client.blocks.children.list(
                block_id=page_id,
                page_size=100,
                start_cursor=resp.get("next_cursor"),
            )
        except Exception:
            break
        for block in resp.get("results", []):
            btype = block.get("type", "")
            bdata = block.get(btype, {})
            rich  = bdata.get("rich_text") or []
            text  = "".join(r.get("plain_text", "") for r in rich).strip()
            if text:
                parts.append(text)

    return "\n\n".join(parts)
