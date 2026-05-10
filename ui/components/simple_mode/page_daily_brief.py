"""
ui/components/simple_mode/page_daily_brief.py — Step 1 Daily Market Brief page.

Replaces the render_stub(1) call in simple_aa.py.

Layout:
  Top toolbar: title "DAILY MARKET BRIEF" + "Generate Today's Brief" button.
  Below: past summaries list from Notion (thesis cards, clickable).
  Selected row expands into a full markdown report panel.

Generation flow (on button click):
  1. Spinner "搜索新闻、拉取价格数据..."
  2. search_news + fetch_prices
  3. Spinner "调用 Claude 生成报告..."
  4. st.write_stream(stream_daily_brief(...)) — live streaming
  5. write_daily_summary to Notion
  6. Refresh past summaries list

Session state keys:
  db_brief_df       — cached DataFrame from Notion
  db_brief_selected — index of selected row (int or None)
  db_brief_report   — last generated full report markdown
"""
from __future__ import annotations

import html as _html
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st

from stock_engine.ui.styles import inject as _inject_css


# ── State keys ────────────────────────────────────────────────────────────────
_K_DF       = "db_brief_df"
_K_SEL      = "db_brief_selected"
_K_REPORT   = "db_brief_report"
_K_ERR      = "db_brief_error"


# ── Helper: info / error card ─────────────────────────────────────────────────

def _render_empty_card(title: str, body_html: str) -> None:
    st.markdown(
        f'<div class="db-empty-wrap">'
        f'<div class="db-empty-card">'
        f'<div class="db-empty-title">{_html.escape(title)}</div>'
        f'<p class="db-empty-body">{body_html}</p>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ── Notion data fetch (with simple in-session caching) ───────────────────────

def _load_summaries(force: bool = False) -> Optional[pd.DataFrame]:
    """Fetch the past summaries DataFrame from Notion.
    Stores result in session state. Returns None on error (error stored in _K_ERR)."""
    if not force and _K_DF in st.session_state:
        return st.session_state[_K_DF]

    try:
        from stock_engine.data.notion_daily import (
            NotionDailyUnavailable,
            fetch_daily_summaries,
        )
        df = fetch_daily_summaries(limit=30)
        st.session_state[_K_DF] = df
        st.session_state.pop(_K_ERR, None)
        return df
    except Exception as exc:
        st.session_state[_K_ERR] = str(exc)
        return None


# ── Markdown → HTML (thin wrapper, same pattern as page1_news.py) ────────────

def _render_md(md: str) -> str:
    try:
        import markdown  # type: ignore
        return markdown.markdown(md, extensions=["extra", "sane_lists"])
    except ImportError:
        return _minimal_md_to_html(md)


def _minimal_md_to_html(md: str) -> str:
    """Minimal MD→HTML fallback when the `markdown` package isn't available."""
    import re
    text = _html.escape(md)
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

    def close_lists() -> None:
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


# ── Generation flow ───────────────────────────────────────────────────────────

def _run_generation() -> None:
    """Called when the user clicks "Generate Today's Brief".
    Runs the full pipeline with spinners and live streaming, writes to Notion,
    then refreshes the summaries list."""
    from stock_engine.analytics.daily_brief import (
        DailyBriefError,
        _MACRO_QUERY,
        _SEMI_QUERY,
        TICKERS,
        extract_thesis,
        fetch_prices,
        search_news,
        stream_daily_brief,
    )
    from stock_engine.data.notion_daily import (
        NotionDailyUnavailable,
        write_daily_summary,
    )

    anthropic_key = (st.session_state.get("anthropic_api_key") or "").strip()
    notion_token  = (st.session_state.get("notion_token") or "").strip()
    notion_db_id  = (st.session_state.get("notion_daily_db_id") or "").strip()

    # Pre-flight credential check
    missing = []
    if not anthropic_key:
        missing.append("Anthropic API Key")
    if not notion_token:
        missing.append("Notion Token")
    if missing:
        st.session_state[_K_ERR] = (
            "Missing credentials: " + ", ".join(missing) +
            ". Add them on the Home page → API Configuration."
        )
        return

    report_date = date.today()
    news_macro: list = []
    news_semi: list  = []
    import pandas as pd
    prices_df: pd.DataFrame = pd.DataFrame()

    # Step 1: news + prices
    with st.spinner("搜索新闻、拉取价格数据 …"):
        try:
            news_macro = search_news(_MACRO_QUERY, max_results=8)
        except DailyBriefError as exc:
            st.session_state[_K_ERR] = f"Macro news search failed: {exc}"
            return
        except Exception as exc:
            st.session_state[_K_ERR] = f"Unexpected error searching macro news: {str(exc)[:200]}"
            return

        try:
            news_semi = search_news(_SEMI_QUERY, max_results=8)
        except DailyBriefError as exc:
            st.session_state[_K_ERR] = f"Sector news search failed: {exc}"
            return
        except Exception as exc:
            st.session_state[_K_ERR] = f"Unexpected error searching sector news: {str(exc)[:200]}"
            return

        try:
            prices_df = fetch_prices(TICKERS)
        except DailyBriefError as exc:
            st.session_state[_K_ERR] = f"Price fetch failed: {exc}"
            return
        except Exception as exc:
            st.session_state[_K_ERR] = f"Unexpected error fetching prices: {str(exc)[:200]}"
            return

    # Step 2: stream Claude report
    st.markdown('<div class="db-section-label">调用 Claude 生成报告…</div>', unsafe_allow_html=True)
    chunks: list[str] = []
    try:
        def _gen_stream():
            for chunk in stream_daily_brief(
                news_macro, news_semi, prices_df, report_date, anthropic_key
            ):
                chunks.append(chunk)
                yield chunk

        st.write_stream(_gen_stream())
        report_md = "".join(chunks).strip()
        st.session_state[_K_REPORT] = report_md
        st.session_state.pop(_K_ERR, None)
    except DailyBriefError as exc:
        st.session_state[_K_ERR] = str(exc)
        return
    except Exception as exc:
        st.session_state[_K_ERR] = f"Unexpected generation error: {str(exc)[:240]}"
        return

    # Step 3: write to Notion
    thesis = extract_thesis(report_md)
    try:
        write_daily_summary(
            report_date=report_date,
            thesis=thesis,
            summary=report_md,
            token=notion_token,
            database_id=notion_db_id or None,
        )
    except NotionDailyUnavailable as exc:
        # Non-fatal — the report was generated; surface as a warning.
        st.warning(f"Report generated but Notion write failed: {exc}")
    except Exception as exc:
        st.warning(f"Report generated but Notion write failed (unexpected): {str(exc)[:200]}")

    # Refresh summaries list
    st.session_state.pop(_K_DF, None)
    st.session_state[_K_SEL] = 0


# ── Past-summaries panel ──────────────────────────────────────────────────────

def _render_summaries_panel(df: pd.DataFrame) -> None:
    """Render the clickable thesis-card list + expanded report panel."""
    if df.empty:
        _render_empty_card(
            "No summaries yet",
            "Click <i>Generate Today's Brief</i> to create the first daily brief.",
        )
        return

    selected = st.session_state.get(_K_SEL, 0)

    st.markdown('<div class="db-section-label">PAST SUMMARIES</div>', unsafe_allow_html=True)
    st.markdown('<div class="db-thesis-list">', unsafe_allow_html=True)

    for i, row in df.iterrows():
        raw_date = row.get("date")
        try:
            date_str = raw_date.strftime("%Y-%m-%d")
        except Exception:
            date_str = str(raw_date)[:10] if raw_date and str(raw_date) != "NaT" else "—"

        thesis_text = (row.get("thesis") or "").strip() or "(no thesis)"
        is_active = (i == selected)
        active_cls = " db-thesis-card--active" if is_active else ""

        # Render as a Streamlit button so clicks are properly wired.
        btn_key = f"db_thesis_card_{i}"
        col_card, col_link = st.columns([10, 1])
        with col_card:
            card_html = (
                f'<div class="db-thesis-card{active_cls}">'
                f'<span class="db-thesis-date">{_html.escape(date_str)}</span>'
                f'<span class="db-thesis-text">{_html.escape(thesis_text)}</span>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
            if st.button(
                "▶ View" if not is_active else "▼ Collapse",
                key=btn_key,
                use_container_width=False,
            ):
                if is_active:
                    st.session_state[_K_SEL] = None
                else:
                    st.session_state[_K_SEL] = i
                st.rerun()
        with col_link:
            url = row.get("_url") or ""
            if url:
                st.markdown(
                    f'<a href="{_html.escape(url)}" target="_blank" '
                    f'rel="noopener" style="font-size:10px;">↗</a>',
                    unsafe_allow_html=True,
                )

    st.markdown("</div>", unsafe_allow_html=True)

    # Expanded report — fetch full body from page blocks on demand
    sel = st.session_state.get(_K_SEL)
    if sel is not None and sel < len(df):
        row = df.iloc[sel]
        page_id = (row.get("_id") or "").strip()

        # Try full body first; fall back to summary_preview (≤2000 chars)
        full_text = ""
        if page_id:
            cache_key = f"db_brief_body_{page_id}"
            if cache_key not in st.session_state:
                with st.spinner("Loading full report…"):
                    try:
                        from stock_engine.data.notion_daily import fetch_page_body
                        full_text = fetch_page_body(page_id)
                        st.session_state[cache_key] = full_text
                    except Exception:
                        st.session_state[cache_key] = ""
            full_text = st.session_state.get(cache_key, "")

        if not full_text:
            full_text = (row.get("summary_preview") or "").strip()

        if full_text:
            st.markdown(
                f'<div class="db-report-wrap">{_render_md(full_text)}</div>',
                unsafe_allow_html=True,
            )
        else:
            _render_empty_card(
                "No content available",
                "The report body could not be loaded. "
                "Click ↗ to open the page directly in Notion.",
            )


# ── Newly generated report panel ─────────────────────────────────────────────

def _render_live_report() -> None:
    """Show the last generated report from session state (after generation)."""
    report_md = st.session_state.get(_K_REPORT)
    if not report_md:
        return
    st.markdown('<div class="db-section-label">LATEST GENERATED REPORT</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="db-report-wrap">{_render_md(report_md)}</div>',
        unsafe_allow_html=True,
    )


# ── Page entry point ──────────────────────────────────────────────────────────

def render_page_daily_brief() -> None:
    """Render the Step 1 Daily Market Brief page."""
    _inject_css("page_daily_brief")

    # ── Toolbar ───────────────────────────────────────────────────────────────
    col_info, col_btn = st.columns([5, 2], vertical_alignment="bottom")
    with col_info:
        st.markdown(
            '<div class="db-toolbar">'
            '<div class="db-toolbar-left">'
            '<div class="db-toolbar-title">DAILY MARKET BRIEF</div>'
            '<div class="db-toolbar-subtitle">Daily AI-generated summary of macro &amp; semis</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with col_btn:
        generate_clicked = st.button(
            "Generate Today's Brief",
            type="primary",
            use_container_width=True,
            key="db_generate_btn",
        )

    # ── Error banner (if any) ─────────────────────────────────────────────────
    err = st.session_state.get(_K_ERR)
    if err:
        _render_empty_card(
            "Error",
            f'<span class="db-error-text">{_html.escape(err)}</span>',
        )

    # ── Handle generation ─────────────────────────────────────────────────────
    if generate_clicked:
        st.session_state.pop(_K_ERR, None)
        st.session_state.pop(_K_REPORT, None)
        _run_generation()

    # ── Show freshly generated report (if just generated) ────────────────────
    if st.session_state.get(_K_REPORT) and not generate_clicked:
        _render_live_report()

    # ── Past summaries from Notion ────────────────────────────────────────────
    # Attempt to load (cached in session). Show setup hint if Notion creds missing.
    notion_token = (st.session_state.get("notion_token") or "").strip()
    if not notion_token:
        _render_empty_card(
            "Notion not configured",
            "Add your <b>Notion Token</b> (and optionally <b>Daily Brief DB ID</b>) "
            "on the Home page → API Configuration to load past summaries.",
        )
        return

    df = _load_summaries()
    if df is None:
        # Error already stored in _K_ERR — shown in the error banner above.
        return

    _render_summaries_panel(df)
