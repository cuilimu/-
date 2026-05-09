"""
data/api_keys.py — Centralized API-key registry, persistence, and testing.

Single source of truth for every external API key the app needs. The Home
page renders one input per registry entry; consumers (page_macro, page1
universe, page6 taa, etc.) read keys from `st.session_state[<id>]` exactly
as before — only the *input* surface is consolidated.

Storage: JSON at ~/.stock_engine/api_keys.json (chmod 600 on POSIX).
Loaded once at app startup into st.session_state so reruns stay fast.

To add a new provider: append one dict to KEY_REGISTRY and write a
`_test_<provider>` function. No other edits needed — the home panel and
the simple-mode sidebar status indicator both iterate this list.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

# ── Storage location ──────────────────────────────────────────────────────────
_KEYS_DIR  = Path.home() / ".stock_engine"
_KEYS_FILE = _KEYS_DIR / "api_keys.json"


def _ensure_dir() -> None:
    _KEYS_DIR.mkdir(parents=True, exist_ok=True)


# ── Provider validation ─────────────────────────────────────────────────────--
def _test_fred(key: str) -> tuple[bool, str]:
    """Hit FRED's /series endpoint with the supplied key. ~1s round-trip.
    Returns (ok, short_message) suitable for direct UI display."""
    key = (key or "").strip()
    if not key:
        return False, "Empty"
    try:
        import requests
        r = requests.get(
            "https://api.stlouisfed.org/fred/series",
            params={"series_id": "GDP", "api_key": key, "file_type": "json"},
            timeout=8,
        )
        if r.status_code == 200:
            return True, "Connected"
        # FRED returns a JSON body with error_message on failure
        try:
            err = r.json().get("error_message", r.text[:80])
        except Exception:
            err = r.text[:80]
        return False, f"{r.status_code}: {err}"
    except Exception as exc:
        return False, f"Network error: {str(exc)[:60]}"


def _test_notion(key: str) -> tuple[bool, str]:
    """Validate a Notion integration token by calling /v1/users/me.
    Does not validate the database ID (registry test fns receive only one
    value); per-database access is exercised lazily on the first fetch."""
    key = (key or "").strip()
    if not key:
        return False, "Empty"
    try:
        import requests
        r = requests.get(
            "https://api.notion.com/v1/users/me",
            headers={
                "Authorization": f"Bearer {key}",
                "Notion-Version": "2022-06-28",
            },
            timeout=8,
        )
        if r.status_code == 200:
            return True, "Connected"
        try:
            err = r.json().get("message", r.text[:80])
        except Exception:
            err = r.text[:80]
        return False, f"{r.status_code}: {err}"
    except Exception as exc:
        return False, f"Network error: {str(exc)[:60]}"


def _test_anthropic(key: str) -> tuple[bool, str]:
    """Validate an Anthropic API key by listing models. ~1s round-trip.
    The /v1/models endpoint exists on every paid tier and returns 401 fast
    on a bad key, so it's a cheap auth check without burning input tokens."""
    key = (key or "").strip()
    if not key:
        return False, "Empty"
    try:
        import requests
        r = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            params={"limit": 1},
            timeout=8,
        )
        if r.status_code == 200:
            return True, "Connected"
        try:
            err = r.json().get("error", {}).get("message", r.text[:80])
        except Exception:
            err = r.text[:80]
        return False, f"{r.status_code}: {err}"
    except Exception as exc:
        return False, f"Network error: {str(exc)[:60]}"


def _test_notion_db_id(value: str) -> tuple[bool, str]:
    """Sanity-check the database ID format only — real access requires the
    token, which the registry test fn doesn't receive. We strip dashes and
    check for a 32-char hex string (Notion's canonical ID shape)."""
    raw = (value or "").strip().replace("-", "")
    if not raw:
        return False, "Empty"
    if len(raw) != 32:
        return False, f"Not 32 hex chars (got {len(raw)})"
    try:
        int(raw, 16)
    except ValueError:
        return False, "Not hex"
    return True, "Format OK (access tested on first fetch)"


# ── Registry ─────────────────────────────────────────────────────────────────
# Each entry's `id` doubles as the st.session_state key — that matches the
# pre-existing convention (e.g. st.session_state["fred_api_key"]) so existing
# consumers keep working without changes.
KEY_REGISTRY: list[dict] = [
    {
        "id":          "fred_api_key",
        "label":       "FRED",
        "name":        "Federal Reserve Economic Data",
        "description": "St. Louis Fed macro time-series. Powers Step 1 "
                       "(Macro Overview), Step 6 (TAA), and the "
                       "All-Weather beta workspace.",
        "signup_url":  "https://fred.stlouisfed.org/docs/api/api_key.html",
        "test":        _test_fred,
    },
    {
        "id":          "anthropic_api_key",
        "label":       "Anthropic",
        "name":        "Anthropic API Key",
        "description": "Powers the Step 1 → News tab AI digest. Starts with "
                       "`sk-ant-`. Sonnet 4.6 is used for summaries — about "
                       "$0.05–$0.10 per weekly digest run.",
        "signup_url":  "https://console.anthropic.com/settings/keys",
        "test":        _test_anthropic,
    },
    {
        "id":          "notion_token",
        "label":       "Notion Token",
        "name":        "Notion Integration Token",
        "description": "Internal-integration secret (starts with `ntn_` or "
                       "`secret_`). Powers Step 1 → News tab. Make sure the "
                       "integration is added as a connection on the database.",
        "signup_url":  "https://www.notion.so/profile/integrations",
        "test":        _test_notion,
    },
    {
        "id":          "notion_news_db_id",
        "label":       "Notion News DB ID",
        "name":        "Notion News Database ID",
        "description": "The 32-char ID of your Investment Research News "
                       "database. Found in the database URL between the "
                       "workspace slug and the `?v=` view parameter.",
        "signup_url":  "https://developers.notion.com/reference/retrieve-a-database",
        "test":        _test_notion_db_id,
    },
]


def get_entry(key_id: str) -> dict | None:
    return next((e for e in KEY_REGISTRY if e["id"] == key_id), None)


# ── Persistence ───────────────────────────────────────────────────────────────
def load_keys_from_file() -> dict[str, str]:
    """Return {key_id: value} from disk. Empty dict if file is missing or
    corrupt (deliberately silent — no key is recoverable from a load error).
    Whitespace is stripped: a single stray space in the saved JSON used to
    URL-encode as '+' and silently produced 400 Bad Request from FRED."""
    if not _KEYS_FILE.exists():
        return {}
    try:
        data = json.loads(_KEYS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v).strip() for k, v in data.items() if str(v).strip()}
        return {}
    except Exception:
        return {}


def save_keys_to_file(keys: dict[str, str]) -> None:
    """Persist the supplied {key_id: value} map to disk. Empty values are
    stripped so 'cleared' keys don't sit in the file. Whitespace is also
    trimmed — see load_keys_from_file for why."""
    _ensure_dir()
    clean = {k: v.strip() for k, v in keys.items() if v and v.strip()}
    _KEYS_FILE.write_text(
        json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8"
    )
    # Tighten file perms on POSIX — the file holds secrets.
    try:
        if os.name != "nt":
            os.chmod(_KEYS_FILE, 0o600)
    except Exception:
        pass


def keys_file_path() -> Path:
    """For the UI to show the user where their keys live."""
    return _KEYS_FILE


# ── Bridge into st.session_state (call once at app startup) ───────────────────
def hydrate_session_state(session_state) -> None:
    """Populate session_state from disk for every registry entry. Existing
    in-memory values (set during this run) are left alone — disk only fills
    gaps. Call this once per Streamlit run; cheap."""
    if session_state.get("_api_keys_hydrated"):
        return
    stored = load_keys_from_file()
    for entry in KEY_REGISTRY:
        kid = entry["id"]
        if not session_state.get(kid) and stored.get(kid):
            session_state[kid] = stored[kid]
    session_state["_api_keys_hydrated"] = True


def persist_one(key_id: str, value: str) -> None:
    """Write a single edited key back to disk, preserving the others."""
    current = load_keys_from_file()
    cleaned = (value or "").strip()
    if cleaned:
        current[key_id] = cleaned
    else:
        current.pop(key_id, None)
    save_keys_to_file(current)
