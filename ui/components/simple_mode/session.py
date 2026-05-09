"""
ui/components/simple_mode/session.py — ResearchSession Streamlit state helpers.
No compute logic here — pure session_state plumbing.
"""
from __future__ import annotations

import uuid
from typing import Optional

import streamlit as st

from stock_engine.portfolio.models import (
    ResearchSession, Universe, AssetMeta, FactorBucket,
    PortfolioCandidate, AllocationMethod, CandidateStatus,
)
from stock_engine.sandbox.taa_module.types import BucketAssignment, MiniUniverse

SESSION_KEY = "research_session"
STEP_KEY    = "aa_step"

# ── Session CRUD ───────────────────────────────────────────────────────────────

def get_session() -> ResearchSession:
    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = ResearchSession(
            session_id=str(uuid.uuid4())[:8]
        )
    return st.session_state[SESSION_KEY]


def clear_session() -> None:
    st.session_state.pop(SESSION_KEY, None)
    st.session_state[STEP_KEY] = 1


def save_session(sess: ResearchSession) -> None:
    """Persist mutated session back to state."""
    st.session_state[SESSION_KEY] = sess


# ── Step navigation ────────────────────────────────────────────────────────────

def get_step() -> "int | str":
    return st.session_state.get(STEP_KEY, 1)


def set_step(n: "int | str") -> None:
    if isinstance(n, str):
        st.session_state[STEP_KEY] = n
    else:
        st.session_state[STEP_KEY] = max(1, min(7, n))
    st.rerun()


def next_step() -> None:
    step = get_step()
    if isinstance(step, int):
        set_step(step + 1)


def prev_step() -> None:
    step = get_step()
    if isinstance(step, int):
        set_step(step - 1)


# ── Universe helpers ───────────────────────────────────────────────────────────

def clear_taa_cache() -> None:
    """Invalidate the cached TAA result (universe change or bounds change)."""
    st.session_state.pop("_taa_cache",     None)
    st.session_state.pop("_taa_cache_key", None)


# Internal alias so existing call-sites don't need updating.
_clear_taa_cache = clear_taa_cache


def add_ticker(sess: ResearchSession, ticker: str) -> None:
    ticker = ticker.upper().strip()
    if ticker and ticker not in sess.universe.tickers:
        sess.universe.tickers.append(ticker)
        sess.universe.assets[ticker] = AssetMeta(ticker=ticker)
        clear_taa_cache()
    save_session(sess)


def remove_ticker(sess: ResearchSession, ticker: str) -> None:
    sess.universe.tickers = [t for t in sess.universe.tickers if t != ticker]
    sess.universe.assets.pop(ticker, None)
    for cand in sess.portfolios:
        cand.weights.pop(ticker, None)
        if cand.weights:
            cand.mark_stale()
    clear_taa_cache()
    save_session(sess)


def set_bucket(sess: ResearchSession, ticker: str, bucket: FactorBucket) -> None:
    if ticker in sess.universe.assets:
        sess.universe.assets[ticker].factor_bucket = bucket
        for cand in sess.portfolios:
            cand.mark_stale()
        clear_taa_cache()
    save_session(sess)


def build_mini_universe(sess: ResearchSession) -> MiniUniverse:
    """Convert ResearchSession.universe → MiniUniverse for the TAA module."""
    return MiniUniverse(assignments=[
        BucketAssignment(
            ticker=t,
            bucket=(
                sess.universe.assets[t].factor_bucket
                if t in sess.universe.assets
                else FactorBucket.UNASSIGNED
            ),
        )
        for t in sess.universe.tickers
    ])


# ── Candidate helpers ──────────────────────────────────────────────────────────

def ensure_default_candidates(sess: ResearchSession) -> None:
    """Create EW and Manual candidates if they don't exist yet."""
    ids = {c.candidate_id for c in sess.portfolios}
    if "ew" not in ids:
        sess.portfolios.append(PortfolioCandidate(
            candidate_id="ew",
            label="Equal Weight",
            method=AllocationMethod.EQUAL_WEIGHT,
        ))
    if "manual" not in ids:
        sess.portfolios.append(PortfolioCandidate(
            candidate_id="manual",
            label="Manual",
            method=AllocationMethod.MANUAL,
        ))
    save_session(sess)


def apply_equal_weights(sess: ResearchSession) -> None:
    tickers = sess.universe.tickers
    if not tickers:
        return
    w = round(1.0 / len(tickers), 6)
    cand = sess.get_candidate("ew")
    if cand:
        cand.weights = {t: w for t in tickers}
        cand.mark_stale()
    save_session(sess)
