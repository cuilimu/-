"""
session_io.py — disk-based session persistence for the Simple Mode AA workflow.

Sessions are stored as JSON files in a `sessions/` directory at the project
root (one level above the stock_engine package directory).

Each file: `sessions/{session_id}.json`

Computed results (backtest_result, risk_result) are NOT serialised — they are
large, transient, and re-computed on demand when the user runs Steps 5/6.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date, datetime
from typing import Optional, Tuple

from stock_engine.portfolio.models import (
    AllocationMethod, AssetMeta, CandidateStatus, FactorBucket,
    PortfolioCandidate, ResearchSession, Universe,
)

# ── Storage path ──────────────────────────────────────────────────────────────
# session_io.py lives at:  stock_engine/ui/components/simple_mode/session_io.py
# parents[0] = simple_mode/   parents[1] = components/
# parents[2] = ui/            parents[3] = stock_engine/
# parents[4] = project root
_HERE = pathlib.Path(__file__).resolve()
SESSIONS_DIR: pathlib.Path = _HERE.parents[4] / "sessions"

_FORMAT_VERSION = 1


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _sess_to_dict(
    sess: ResearchSession,
    *,
    step: int,
    label: str,
    capital: float,
    taa_min_w: float,
    taa_max_w: float,
) -> dict:
    u = sess.universe
    return {
        "format_version": _FORMAT_VERSION,
        "session_id":     sess.session_id,
        "saved_at":       datetime.now().isoformat(),
        "label":          label,
        "step":           step,
        "config": {
            "capital":   capital,
            "taa_min_w": taa_min_w,
            "taa_max_w": taa_max_w,
        },
        "universe": {
            "tickers":        u.tickers,
            "purchase_date":  u.purchase_date.isoformat() if u.purchase_date else None,
            "backtest_start": u.backtest_start.isoformat() if u.backtest_start else None,
            "backtest_end":   u.backtest_end.isoformat() if u.backtest_end else None,
            "assets": {
                t: {
                    "factor_bucket": m.factor_bucket.value,
                    "asset_class":   m.asset_class,
                    "sector":        m.sector,
                    "region":        m.region,
                    "user_tags":     m.user_tags,
                }
                for t, m in u.assets.items()
            },
        },
        "portfolios": [
            {
                "candidate_id": p.candidate_id,
                "label":        p.label,
                "method":       p.method.value,
                "weights":      p.weights,
                "constraints":  p.constraints,
                "status":       p.status.value,
            }
            for p in sess.portfolios
        ],
    }


def _dict_to_sess(
    d: dict,
) -> Tuple[ResearchSession, int, float, float, float]:
    """Deserialise a saved dict. Returns (sess, step, taa_min_w, taa_max_w, capital)."""
    u = d["universe"]
    universe = Universe(
        tickers=u["tickers"],
        purchase_date=(date.fromisoformat(u["purchase_date"])
                       if u.get("purchase_date") else None),
        backtest_start=(date.fromisoformat(u["backtest_start"])
                        if u.get("backtest_start") else None),
        backtest_end=(date.fromisoformat(u["backtest_end"])
                      if u.get("backtest_end") else None),
        assets={
            t: AssetMeta(
                ticker=t,
                factor_bucket=FactorBucket(m.get("factor_bucket", "unassigned")),
                asset_class=m.get("asset_class", "equity"),
                sector=m.get("sector"),
                region=m.get("region"),
                user_tags=m.get("user_tags", []),
            )
            for t, m in u.get("assets", {}).items()
        },
    )
    portfolios = [
        PortfolioCandidate(
            candidate_id=p["candidate_id"],
            label=p["label"],
            method=AllocationMethod(p.get("method", "equal_weight")),
            weights=p.get("weights", {}),
            constraints=p.get("constraints", {}),
            status=CandidateStatus(p.get("status", "not_run")),
        )
        for p in d.get("portfolios", [])
    ]
    sess = ResearchSession(
        session_id=d["session_id"],
        created_at=datetime.fromisoformat(
            d.get("saved_at", datetime.now().isoformat())
        ),
        universe=universe,
        portfolios=portfolios,
    )
    cfg     = d.get("config", {})
    step    = int(d.get("step", 1))
    capital = float(cfg.get("capital", 100_000.0))
    min_w   = float(cfg.get("taa_min_w", 5.0))
    max_w   = float(cfg.get("taa_max_w", 80.0))
    return sess, step, min_w, max_w, capital


# ── Public API ────────────────────────────────────────────────────────────────

def save_session_to_disk(
    sess: ResearchSession,
    *,
    step: int,
    label: str = "",
    capital: float = 100_000.0,
    taa_min_w: float = 5.0,
    taa_max_w: float = 80.0,
) -> pathlib.Path:
    """Serialise and write *sess* to ``sessions/{session_id}.json``.

    If *label* is blank, auto-names as ``YYYY-MM-DD · TICKER1/TICKER2/...``.
    Returns the file path written.
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not label.strip():
        tickers_preview = "/".join(sess.universe.tickers[:3])
        label = datetime.now().strftime("%Y-%m-%d") + (
            f" · {tickers_preview}" if tickers_preview else ""
        )
    d = _sess_to_dict(
        sess,
        step=step,
        label=label,
        capital=capital,
        taa_min_w=taa_min_w,
        taa_max_w=taa_max_w,
    )
    path = SESSIONS_DIR / f"{sess.session_id}.json"
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def list_saved_sessions() -> list[dict]:
    """Return summary dicts for all saved sessions, newest-first.

    Each dict: ``session_id``, ``saved_at``, ``label``, ``n_tickers``, ``step``.
    """
    if not SESSIONS_DIR.exists():
        return []
    summaries: list[dict] = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            summaries.append({
                "session_id": d.get("session_id", f.stem),
                "saved_at":   d.get("saved_at", ""),
                "label":      d.get("label", f.stem),
                "n_tickers":  len(d.get("universe", {}).get("tickers", [])),
                "step":       int(d.get("step", 1)),
            })
        except Exception:
            continue
    summaries.sort(key=lambda x: x["saved_at"], reverse=True)
    return summaries


def load_session_from_disk(
    session_id: str,
) -> Optional[Tuple[ResearchSession, int, float, float, float]]:
    """Load ``sessions/{session_id}.json``.

    Returns ``(sess, step, taa_min_w, taa_max_w, capital)`` or ``None``.
    """
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return _dict_to_sess(d)
    except Exception:
        return None


def delete_session_from_disk(session_id: str) -> None:
    """Delete ``sessions/{session_id}.json`` if it exists."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
