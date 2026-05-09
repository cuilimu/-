"""
ui/components/simple_mode/page1_news.py — Step 1 → News tab.

The News tab does NOT show a raw list of items — it shows an AI-generated
weekly digest (TL;DR / themes / watchlist) produced by Claude Sonnet 4.6
from the past N days of items in the user's Notion "Investment Research
News & Opinions" database.

Top toolbar: window selector (7/14/30 d), item count for the window, a
"View raw items" expander, and a Generate / Regenerate button. Body:
streaming markdown report. Footer caption shows model + cost framing.

Failure modes (no Notion creds, no Anthropic key, fetch error, sparse
input) all fall through to a centred .api-cfg-card-style hint — never a
Streamlit exception bubble.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import time
from typing import Optional

import pandas as pd
import streamlit as st

from stock_engine.analytics.news_digest import (
    DigestUnavailable,
    prepare_digest_input,
    stream_digest,
)
from stock_engine.data.notion_news import (
    NotionUnavailable,
    fetch_news_df,
)
from stock_engine.ui.styles import inject as _inject_css


# ── State keys ───────────────────────────────────────────────────────────────
_K_WINDOW   = "p1_news_window_days"
_K_DIGEST   = "p1_news_digest_md"      # the latest generated markdown
_K_META     = "p1_news_digest_meta"    # dict: {generated_at, n_items, window_days, model}
_K_GEN_ERR  = "p1_news_digest_error"   # last error string (cleared on next success)


# ── Helpers ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cached_fetch_news(token: str, db_id: str) -> pd.DataFrame:
    return fetch_news_df(token=token, database_id=db_id)


def _render_empty_card(title: str, body_html: str) -> None:
    st.markdown(
        f'<div class="p1-news-empty-wrap">'
        f'<div class="p1-news-empty-card">'
        f'<div class="p1-news-empty-title">{_html.escape(title)}</div>'
        f'<p class="p1-news-empty-body">{body_html}</p>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ── Page entry ───────────────────────────────────────────────────────────────

def render_news_tab() -> None:
    """Render the Step-1 News tab: AI weekly digest + window selector +
    raw items expander."""
    _inject_css("page1_news")

    if _K_WINDOW not in st.session_state:
        st.session_state[_K_WINDOW] = 7

    notion_tok = (st.session_state.get("notion_token") or "").strip()
    notion_db  = (st.session_state.get("notion_news_db_id") or "").strip()
    anthro_key = (st.session_state.get("anthropic_api_key") or "").strip()

    # Toolbar
    col_title, col_win, col_btn = st.columns([3, 2, 1.5], vertical_alignment="bottom")
    with col_title:
        st.markdown(
            '<div class="p1-news-title">AI WEEKLY NEWS DIGEST</div>',
            unsafe_allow_html=True,
        )
    with col_win:
        st.session_state[_K_WINDOW] = st.selectbox(
            "Window",
            options=[7, 14, 30],
            format_func=lambda d: f"Past {d} days",
            index=[7, 14, 30].index(st.session_state[_K_WINDOW]),
            key="p1_news_window_select",
            label_visibility="collapsed",
        )
    with col_btn:
        existing = st.session_state.get(_K_DIGEST)
        gen_label = "Regenerate" if existing else "Generate"
        gen_clicked = st.button(
            gen_label, type="primary", use_container_width=True,
            key="p1_news_generate_btn",
        )

    # Pre-flight: do we have the credentials we need?
    missing = []
    if not notion_tok or not notion_db:
        missing.append("Notion (Token + News DB ID)")
    if not anthro_key:
        missing.append("Anthropic API key")
    if missing:
        _render_empty_card(
            "Setup needed",
            "Add the following on the Home page → API Configuration: "
            f"<b>{', '.join(missing)}</b>. Once configured, return here "
            "and click <i>Generate</i>.",
        )
        return

    # Fetch news (cached 5 min)
    try:
        df = _cached_fetch_news(notion_tok, notion_db)
    except NotionUnavailable as exc:
        _render_empty_card(
            "Couldn't load Notion",
            f'<span class="p1-news-error-text">{_html.escape(str(exc))}</span>',
        )
        return
    except Exception as exc:  # noqa: BLE001
        _render_empty_card(
            "Unexpected error reading Notion",
            f'<span class="p1-news-error-text">{_html.escape(str(exc)[:240])}</span>',
        )
        return

    # Prepare the input for the chosen window
    window_days = int(st.session_state[_K_WINDOW])
    digest_input = prepare_digest_input(df, window_days=window_days)

    # Window-info caption (renders even before generation)
    window_label = (
        f"{digest_input.earliest.strftime('%Y-%m-%d') if digest_input.earliest is not None else '—'} "
        f"→ {digest_input.latest.strftime('%Y-%m-%d') if digest_input.latest is not None else '—'}"
    )
    st.markdown(
        f'<div class="p1-news-window-info">'
        f'{digest_input.n_items} items · {window_label}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Raw-items expander — collapsed by default
    if not df.empty:
        with st.expander(f"View raw items in window ({digest_input.n_items})", expanded=False):
            if digest_input.n_items > 0:
                st.markdown(
                    f"<pre style='font-size:10px; color:#444; white-space:pre-wrap; "
                    f"max-height:240px; overflow-y:auto'>"
                    f"{_html.escape(digest_input.rows_text)}</pre>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption(f"No items in the past {window_days} days.")

    # Handle generate click — stream the digest into a placeholder
    if gen_clicked:
        if digest_input.n_items == 0:
            st.session_state[_K_GEN_ERR] = (
                f"No items in the past {window_days} days to summarise. "
                f"Pick a longer window or add items in Notion."
            )
            st.session_state.pop(_K_DIGEST, None)
        else:
            placeholder = st.empty()
            chunks: list[str] = []
            try:
                started = time.monotonic()
                placeholder.markdown(
                    '<div class="p1-digest-wrap"><i style="color:#888">'
                    'Calling Claude Sonnet 4.6…</i></div>',
                    unsafe_allow_html=True,
                )
                for chunk in stream_digest(digest_input, api_key=anthro_key):
                    chunks.append(chunk)
                    # Render a live preview — close the wrapper div on each tick
                    preview = "".join(chunks)
                    placeholder.markdown(
                        f'<div class="p1-digest-wrap">{_render_md(preview)}</div>',
                        unsafe_allow_html=True,
                    )
                elapsed = time.monotonic() - started
                final_md = "".join(chunks).strip()
                st.session_state[_K_DIGEST] = final_md
                st.session_state[_K_META] = {
                    "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
                    "n_items":      digest_input.n_items,
                    "window_days":  window_days,
                    "model":        "claude-sonnet-4-6",
                    "elapsed_s":    round(elapsed, 1),
                }
                st.session_state.pop(_K_GEN_ERR, None)
                placeholder.empty()
                st.rerun()  # rerender cleanly with the persisted digest
            except DigestUnavailable as exc:
                st.session_state[_K_GEN_ERR] = str(exc)
                placeholder.empty()
            except Exception as exc:  # noqa: BLE001
                st.session_state[_K_GEN_ERR] = f"Unexpected error: {str(exc)[:240]}"
                placeholder.empty()

    # Render persisted digest (or error)
    err = st.session_state.get(_K_GEN_ERR)
    if err and not st.session_state.get(_K_DIGEST):
        _render_empty_card(
            "Couldn't generate digest",
            f'<span class="p1-news-error-text">{_html.escape(err)}</span>',
        )
        return

    digest_md = st.session_state.get(_K_DIGEST)
    if digest_md:
        st.markdown(
            f'<div class="p1-digest-wrap">{_render_md(digest_md)}</div>',
            unsafe_allow_html=True,
        )
        meta = st.session_state.get(_K_META) or {}
        if meta:
            generated  = meta.get("generated_at", "")
            elapsed_s  = meta.get("elapsed_s", "")
            n_items    = meta.get("n_items", "")
            wd         = meta.get("window_days", "")
            model      = meta.get("model", "")
            st.markdown(
                f'<div class="p1-digest-meta">'
                f'Generated {generated} · {model} · {n_items} items, past {wd} days '
                f'· {elapsed_s}s'
                f'</div>',
                unsafe_allow_html=True,
            )
        return

    # No digest yet — prompt to generate
    if digest_input.n_items == 0:
        _render_empty_card(
            "No items in window",
            f"There are no items dated in the past {window_days} days. "
            "Try a longer window above, or add items in Notion.",
        )
    else:
        _render_empty_card(
            "Ready to generate",
            f"<b>{digest_input.n_items}</b> items in the past {window_days} days. "
            "Click <i>Generate</i> to have Claude Sonnet 4.6 produce a "
            "PM-style weekly brief (TL;DR · themes · watchlist).",
        )


# ── Markdown → HTML ──────────────────────────────────────────────────────────

def _render_md(md: str) -> str:
    """Use Streamlit's vendored markdown via st.markdown is the obvious path,
    but we need the digest INSIDE our styled `<div class="p1-digest-wrap">`,
    which means we have to convert MD → HTML ourselves so we can interpolate
    the result into our own wrapper."""
    try:
        import markdown  # type: ignore
        return markdown.markdown(md, extensions=["extra", "sane_lists"])
    except ImportError:
        # Fallback: minimal MD rendering — bold, italics, headings, lists, links.
        # Good enough for Claude's output, which is well-structured.
        return _minimal_md_to_html(md)


_HEADING_RE = None  # lazy-compiled in _minimal_md_to_html


def _minimal_md_to_html(md: str) -> str:
    """Very small MD→HTML fallback used only if the `markdown` package isn't
    installed. Handles headings (#/##/###), bold (**), italics (*), inline
    code (`), bullets (- / *), numbered lists, and [text](url) links. Not a
    full parser — Claude's output is well-formed enough for this to look OK."""
    import re
    text = _html.escape(md)

    # Re-allow our own links + inline code by un-escaping the markdown markers
    text = text.replace("&amp;#39;", "'")  # safety; rare path

    # Inline: bold, italics, code, links
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )

    out: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            close_lists()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{m.group(2)}</h{level}>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{m.group(1)}</li>")
            continue
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{m.group(1)}</li>")
            continue
        close_lists()
        out.append(f"<p>{line}</p>")

    close_lists()
    return "\n".join(out)
