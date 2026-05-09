"""
data/notion_news.py — Read the user's "Investment Research News & Opinions"
Notion database into a tidy DataFrame for the Step-1 News tab.

Schema-agnostic: walks every property on each page and normalises by Notion
type (title, rich_text, multi_select, select, status, date, url, people,
checkbox, number, email, phone_number, files). Unknown types fall back to
`str(value)` so a property rename or addition in Notion never crashes the UI.

Auth & DB-ID resolution order:
    1. explicit args  →  2. st.session_state[notion_token / notion_news_db_id]
    3. env vars NOTION_TOKEN / NOTION_NEWS_DB_ID

Failure mode: every public function raises NotionUnavailable with a short,
actionable message. The UI catches that and renders a setup-hint card —
nothing in the rest of the Step-1 page should ever blow up because the
user hasn't configured Notion yet.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import pandas as pd


class NotionUnavailable(RuntimeError):
    """Raised when token / DB ID / package / network is missing."""


# ── Credential resolution ─────────────────────────────────────────────────────

def _resolve_credentials(
    token: Optional[str],
    database_id: Optional[str],
) -> tuple[str, str]:
    """Resolve token and database_id from explicit args → Streamlit
    session_state → env vars. Raises NotionUnavailable if either is missing."""
    tok = (token or "").strip()
    dbid = (database_id or "").strip()

    if not tok or not dbid:
        try:
            import streamlit as st  # noqa: WPS433 — optional at module load
            ss = st.session_state
            if not tok:
                tok = (ss.get("notion_token") or "").strip()
            if not dbid:
                dbid = (ss.get("notion_news_db_id") or "").strip()
        except Exception:
            pass

    if not tok:
        tok = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not dbid:
        dbid = (os.environ.get("NOTION_NEWS_DB_ID") or "").strip()

    if not tok:
        raise NotionUnavailable(
            "Notion token not set. Add it on the Home page → API Configuration."
        )
    if not dbid:
        raise NotionUnavailable(
            "Notion News DB ID not set. Add it on the Home page → API Configuration."
        )
    return tok, dbid


# ── Property normalisation ────────────────────────────────────────────────────

def _flatten_rich_text(rich: Iterable[dict]) -> str:
    return "".join(part.get("plain_text", "") for part in (rich or []))


def _norm_property(prop: dict) -> Any:
    """Return a single Python value for a Notion property dict.
    Unknown types fall back to str(prop)."""
    ptype = prop.get("type")
    val = prop.get(ptype)
    if val is None:
        return None

    if ptype == "title":
        return _flatten_rich_text(val) or None
    if ptype == "rich_text":
        return _flatten_rich_text(val) or None
    if ptype == "select":
        return val.get("name") if val else None
    if ptype == "status":
        return val.get("name") if val else None
    if ptype == "multi_select":
        return [opt.get("name") for opt in val if opt.get("name")]
    if ptype == "date":
        return val.get("start") if val else None
    if ptype == "url":
        return val or None
    if ptype == "email":
        return val or None
    if ptype == "phone_number":
        return val or None
    if ptype == "checkbox":
        return bool(val)
    if ptype == "number":
        return val
    if ptype == "people":
        return [p.get("name") or p.get("id") for p in val] if val else []
    if ptype == "files":
        out = []
        for f in val or []:
            if f.get("type") == "external":
                out.append(f.get("external", {}).get("url"))
            elif f.get("type") == "file":
                out.append(f.get("file", {}).get("url"))
        return [u for u in out if u]
    if ptype == "created_time":
        return val
    if ptype == "last_edited_time":
        return val
    if ptype == "created_by":
        return (val or {}).get("name") or (val or {}).get("id")
    if ptype == "last_edited_by":
        return (val or {}).get("name") or (val or {}).get("id")
    if ptype == "formula":
        # Recurse into the formula's underlying type
        inner = val or {}
        inner_type = inner.get("type")
        return inner.get(inner_type) if inner_type else None
    if ptype == "rollup":
        inner = val or {}
        inner_type = inner.get("type")
        return inner.get(inner_type) if inner_type else None
    if ptype == "relation":
        return [r.get("id") for r in val] if val else []

    return str(val)


# ── Pagination + DataFrame builder ────────────────────────────────────────────

@dataclass
class NewsRow:
    title: str
    url: Optional[str]
    raw: dict  # full normalised property map


def _resolve_data_source_id(client, database_id: str) -> str:
    """Notion deprecated `/v1/databases/{id}/query` in 2025-09 in favour of
    querying *data sources* (a database can have one or more). For the common
    single-source case, the database's first data_source is the right target.
    Raises NotionUnavailable if the DB has no data sources visible to the
    integration (typically: the integration isn't a connection on the DB)."""
    try:
        db = client.databases.retrieve(database_id=database_id)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == "object_not_found":
            raise NotionUnavailable(
                "Database not found. Either the ID is wrong, or your "
                "integration isn't added as a connection on the database "
                "(open the DB → ⋯ menu → Connections)."
            ) from exc
        if code == "unauthorized":
            raise NotionUnavailable(
                "Token rejected by Notion. Re-check it on the Home page."
            ) from exc
        raise NotionUnavailable(f"databases.retrieve failed: {exc}") from exc

    sources = db.get("data_sources") or []
    if not sources:
        raise NotionUnavailable(
            "Database has no data sources visible to this integration. "
            "Open the DB in Notion → ⋯ → Connections, and add your "
            "integration."
        )
    return sources[0]["id"]


def _iter_pages(client, data_source_id: str, page_size: int = 100):
    """Yield every page in the data source, transparently following has_more."""
    cursor: Optional[str] = None
    while True:
        kwargs = {"data_source_id": data_source_id, "page_size": page_size}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.data_sources.query(**kwargs)
        for page in resp.get("results", []):
            yield page
        if not resp.get("has_more"):
            return
        cursor = resp.get("next_cursor")


def fetch_news_df(
    token: Optional[str] = None,
    database_id: Optional[str] = None,
    limit: Optional[int] = 200,
) -> pd.DataFrame:
    """Return a DataFrame of news items, newest-first when a date column exists.

    Columns are derived from whatever properties live on the Notion pages,
    plus two synthetic columns:
      - `_url`    — direct page URL on notion.so
      - `_edited` — page.last_edited_time (ISO string)
    """
    tok, dbid = _resolve_credentials(token, database_id)

    try:
        from notion_client import Client  # type: ignore
    except ImportError as exc:
        raise NotionUnavailable(
            "notion-client not installed. Run "
            "`pip install notion-client` (or reinstall this project)."
        ) from exc

    try:
        client = Client(auth=tok)
    except Exception as exc:
        raise NotionUnavailable(f"Notion client init failed: {exc}") from exc

    data_source_id = _resolve_data_source_id(client, dbid)

    rows: list[dict] = []
    try:
        for page in _iter_pages(client, data_source_id):
            props = page.get("properties", {})
            row = {name: _norm_property(p) for name, p in props.items()}
            row["_url"] = page.get("url")
            row["_edited"] = page.get("last_edited_time")
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    except Exception as exc:
        msg = str(exc)
        # notion-client wraps API errors with helpful .code attributes
        code = getattr(exc, "code", None)
        if code == "object_not_found":
            raise NotionUnavailable(
                "Database not found. Either the ID is wrong, or your "
                "integration isn't added as a connection on the database "
                "(open the DB → ⋯ → Connections)."
            ) from exc
        if code == "unauthorized":
            raise NotionUnavailable(
                "Token rejected by Notion. Re-check it on the Home page."
            ) from exc
        raise NotionUnavailable(f"Notion query failed: {msg[:160]}") from exc

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Promote the first date-like column for sorting if present.
    date_col = _pick_date_column(df)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
        df = df.sort_values(date_col, ascending=False, na_position="last")
    elif "_edited" in df.columns:
        df["_edited"] = pd.to_datetime(df["_edited"], errors="coerce", utc=True)
        df = df.sort_values("_edited", ascending=False, na_position="last")

    return df.reset_index(drop=True)


def _pick_date_column(df: pd.DataFrame) -> Optional[str]:
    """Best-effort: prefer a column literally called 'Date', otherwise the
    first column whose dtype parses as a date."""
    for cand in ("Date", "date", "Published", "Publish Date", "Created"):
        if cand in df.columns:
            return cand
    return None


def pick_title_column(df: pd.DataFrame) -> Optional[str]:
    """Heuristic: the column most likely to be the page title.
    Notion always has exactly one `title` property; we identify it by being
    a non-null string column with the longest average value among string-y
    columns, ignoring synthetic `_*` columns."""
    if df.empty:
        return None
    candidates = [
        c for c in df.columns
        if not c.startswith("_") and df[c].dtype == object
    ]
    best, best_len = None, -1.0
    for c in candidates:
        sample = df[c].dropna().astype(str)
        if sample.empty:
            continue
        avg = sample.str.len().mean()
        if avg > best_len:
            best, best_len = c, avg
    return best
