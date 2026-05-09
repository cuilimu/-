"""
session_io_sim.py — disk persistence for simulation (Advanced Watchlist / Multi-date) sessions.

Sessions stored at: sessions/sim/{session_id}.json
Groups configuration and config are saved; backtest results are NOT (re-run on load).
"""
from __future__ import annotations

import json
import pathlib
import uuid
from datetime import datetime
from typing import Optional, Tuple

from stock_engine.portfolio.models import PortfolioGroup, TickerAllocation

_HERE = pathlib.Path(__file__).resolve()
# stock_engine/ui/components/session_io_sim.py
# parents[0] = components/   parents[1] = ui/
# parents[2] = stock_engine/  parents[3] = project root
SESSIONS_SIM_DIR: pathlib.Path = _HERE.parents[3] / "sessions" / "sim"

_FORMAT_VERSION = 1

_BUY_MODE_LABEL = {"same_day": "One-day Buy", "multi_date": "Multi-date Buy"}
_MODE_LABEL     = {"single": "Simple Mode",   "group": "Advanced Watchlist"}


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _groups_to_list(groups: list) -> list[dict]:
    out = []
    for g in groups:
        out.append({
            "name":             g.name,
            "starting_capital": g.starting_capital,
            "allocations": [
                {"ticker": a.ticker, "allocated_dollars": a.allocated_dollars}
                for a in g.allocations
            ],
        })
    return out


def _list_to_groups(data: list[dict]) -> list[PortfolioGroup]:
    groups = []
    for g in data:
        allocs = [
            TickerAllocation(
                ticker=a["ticker"],
                allocated_dollars=float(a.get("allocated_dollars", 0.0)),
            )
            for a in g.get("allocations", [])
        ]
        groups.append(PortfolioGroup(
            name=g["name"],
            starting_capital=float(g.get("starting_capital", 100_000.0)),
            allocations=allocs,
        ))
    return groups


# ── Public API ────────────────────────────────────────────────────────────────

def save_sim_session_to_disk(
    groups: list,
    *,
    mode: str = "group",
    buy_mode: str = "same_day",
    start_date: str,
    end_date: str,
    capital: float,
    price_field: str = "Close",
    benchmark: str = "SPY",
    slippage_bps: float = 0.0,
    label: str = "",
) -> pathlib.Path:
    SESSIONS_SIM_DIR.mkdir(parents=True, exist_ok=True)
    session_id = str(uuid.uuid4())[:8]
    if not label.strip():
        names_preview = "/".join(g.name for g in groups[:2])
        label = datetime.now().strftime("%Y-%m-%d") + (
            f" · {names_preview}" if names_preview else ""
        )
    n_tickers = sum(len(g.allocations) for g in groups)
    d = {
        "format_version": _FORMAT_VERSION,
        "session_id":     session_id,
        "saved_at":       datetime.now().isoformat(),
        "label":          label,
        "mode":           mode,
        "buy_mode":       buy_mode,
        "config": {
            "start_date":   start_date,
            "end_date":     end_date,
            "capital":      capital,
            "price_field":  price_field,
            "benchmark":    benchmark,
            "slippage_bps": slippage_bps,
        },
        "groups":    _groups_to_list(groups),
        "n_groups":  len(groups),
        "n_tickers": n_tickers,
    }
    path = SESSIONS_SIM_DIR / f"{session_id}.json"
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def list_saved_sim_sessions() -> list[dict]:
    """Return summary dicts newest-first."""
    if not SESSIONS_SIM_DIR.exists():
        return []
    summaries = []
    for f in SESSIONS_SIM_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            summaries.append({
                "session_id": d.get("session_id", f.stem),
                "saved_at":   d.get("saved_at", ""),
                "label":      d.get("label", f.stem),
                "n_groups":   int(d.get("n_groups", 0)),
                "n_tickers":  int(d.get("n_tickers", 0)),
                "mode":       d.get("mode", "group"),
                "buy_mode":   d.get("buy_mode", "same_day"),
            })
        except Exception:
            continue
    summaries.sort(key=lambda x: x["saved_at"], reverse=True)
    return summaries


def load_sim_session_from_disk(
    session_id: str,
) -> Optional[Tuple[list, str, str, dict]]:
    """Load a saved sim session.

    Returns ``(groups, mode, buy_mode, cfg_dict)`` or ``None``.
    ``cfg_dict`` keys: start_date, end_date, capital, price_field, benchmark, slippage_bps.
    """
    path = SESSIONS_SIM_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        groups   = _list_to_groups(d.get("groups", []))
        mode     = d.get("mode", "group")
        buy_mode = d.get("buy_mode", "same_day")
        cfg      = d.get("config", {})
        return groups, mode, buy_mode, {
            "start_date":   cfg.get("start_date"),
            "end_date":     cfg.get("end_date"),
            "capital":      float(cfg.get("capital", 100_000.0)),
            "price_field":  cfg.get("price_field", "Close"),
            "benchmark":    cfg.get("benchmark", "SPY"),
            "slippage_bps": float(cfg.get("slippage_bps", 0.0)),
        }
    except Exception:
        return None


def delete_sim_session_from_disk(session_id: str) -> None:
    path = SESSIONS_SIM_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
