"""
ui/styles/ — Per-page CSS, kept out of the Python files.

Goal: feature code in `ui/components/**` should not contain a `<style>`
block or a hardcoded hex colour. Render-time CSS lives here as plain
`.css` files, injected once on first use.

Usage:
    from stock_engine.ui.styles import inject
    inject("page1_news")  # loads ui/styles/page1_news.css

The file is read once per process (cached) and re-emitted into the DOM
on every Streamlit rerun via st.markdown. Streamlit dedupes identical
<style> nodes, so calling inject() in a tab's render function is safe.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st

_STYLES_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def _read_css(name: str) -> str:
    path = _STYLES_DIR / f"{name}.css"
    if not path.exists():
        raise FileNotFoundError(f"ui/styles/{name}.css not found")
    return path.read_text(encoding="utf-8")


def inject(name: str) -> None:
    """Inject ui/styles/<name>.css into the page once per rerun."""
    css = _read_css(name)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
