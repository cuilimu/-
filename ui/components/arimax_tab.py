"""
ui/components/arimax_tab.py — ARIMAX Engine (STATA-style console layout).

Layout:
  ┌─────────── command bar (live config summary + Run/Reset) ──────────┐
  ┌─ config pane (380 px fixed) ─┐ ┌─── output area (flex) ──────────┐
  │  six accordion sections      │ │ menu bar (action+combo+Run)     │
  │  (Target/MEVs/…/Soft Rules)  │ │ console log (stacks newest-first)│
  │  scrolls internally          │ │ command line (: action [combo]) │
  │  sticky ← Back button        │ │                                  │
  └──────────────────────────────┘ └──────────────────────────────────┘

Right side is a STATA-style console: every menu-key click runs an action
and APPENDS an `ArxOutput` entry to a stacked log (`arx_console`). Actions
that need a combo (forecast / cv / resid / summary) read from a dropdown
populated with every X_combo from the engine's `results_df` — so every
(variable × lag) combination is selectable, not just the top-N.

Run lifecycle:
  • click Run ARIMAX Sweep → live progress block at the top of the console
  • sweep completes → seed the console with: completion summary text,
    top-N table, best-model forecast figure
  • user picks any subsequent action; results stack newest-first
  • Clear button wipes the console; Reset wipes config + console
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
import streamlit as st

import importlib
import inspect
import sys as _sys

# Streamlit hot-reload re-runs this file but keeps imported modules cached in
# sys.modules. If pipeline.py was edited while Streamlit was running, the
# ARIMAXPipeline class in cache may be the OLD version. Detect and fix that
# by force-reloading the arimax subpackage before using any of its symbols.
def _ensure_fresh_arimax() -> None:
    mod = _sys.modules.get("stock_engine.analytics.arimax.pipeline")
    if mod is None:
        return
    try:
        sig = inspect.signature(mod.ARIMAXPipeline.run_models)
    except (AttributeError, TypeError, ValueError):
        sig = None
    if sig is None or "on_step" not in sig.parameters:
        for key in [k for k in _sys.modules if k.startswith("stock_engine.analytics.arimax")]:
            del _sys.modules[key]

_ensure_fresh_arimax()

from stock_engine.analytics.arimax import ARIMAXConfig, ARIMAXPipeline, AutoARIMAParams
from stock_engine.analytics.arimax.fred_mev import (
    DEFAULT_FRED_PRESETS,
    fetch_fred_series,
)
from stock_engine.analytics.arimax.portfolio_target import (
    merge_target_with_mevs,
    portfolio_target_frame,
)
from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config
from stock_engine.ui import theme
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.viz.arimax_charts import (
    cv_forecasts_chart,
    decomposition_chart,
    forecast_with_ci_chart,
    pacf_chart,
    residual_diagnostics_chart,
    tsdisplay_chart,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_TARGET_NAME = "y"
_DS_COL = "DATE"

_FREQ_OPTIONS = ["QE", "ME", "W", "D", "B", "YE"]
_FREQ_HINTS = {
    "QE": "Quarterly (period-end)",
    "ME": "Monthly (period-end)",
    "W":  "Weekly",
    "D":  "Daily",
    "B":  "Business daily",
    "YE": "Yearly",
}
_DECOMP_PERIOD = {"QE": 4, "ME": 12, "W": 52, "D": 252, "B": 252, "YE": 1}

_TRANSFORM_OPTIONS = ["original", "log", "boxcox"]
_GUIDE_OPTIONS = ["log_diff", "diff", "none"]
_SOFT_METHODS = ["weighted", "mse", "mae", "rmse", "mape", "smape", "mase"]
_WEIGHT_KEYS = ["mse", "mae", "rmse", "mape", "smape", "mase"]
_SIGN_OPTIONS = ["+", "-", "undetermined"]
_TARGET_KIND_OPTIONS = ["return", "log_return", "excess_return"]

_AP_DEFAULTS: dict[str, Any] = {
    "start_p": 2,
    "d": None,
    "start_q": 2,
    "max_p": 5,
    "max_d": 2,
    "max_q": 5,
    "start_P": 1,
    "D": None,
    "start_Q": 1,
    "max_P": 2,
    "max_D": 1,
    "max_Q": 2,
    "max_order": 5,
    "m": 1,
    "seasonal": True,
    "stationary": False,
    "information_criterion": "aic",
    "alpha": 0.05,
    "test": "kpss",
    "seasonal_test": "ocsb",
    "stepwise": True,
    "n_jobs": 1,
    "random": False,
    "random_state": None,
    "n_fits": 10,
    "method": "lbfgs",
    "maxiter": 50,
    "with_intercept": "auto",
    "trend": None,
    "out_of_sample_size": 0,
    "scoring": "mse",
    "scoring_args": None,
    "suppress_warnings": True,
    "error_action": "ignore",
}

_DEFAULT_BASIC: dict[str, Any] = {
    "TARGET": _TARGET_NAME,
    "MEVS": ["T10Y3M", "BAAFFM", "INDPRO"],
    "MEVS_Guide": {
        "T10Y3M": "diff",
        "BAAFFM": "diff",
        "INDPRO": "log_diff",
    },
    "freq": "QE",
    "max_lag": 4,
    "max_number_of_Exogenous_Variables": 2,
    "include_non_lags": False,
    "train_threshold": 0.8,
    "oot_test": False,
    "oot_threshold": 0.9,
    "transform": "original",
    "trace": False,
    "use_tqdm": True,
    "target_kind": "log_return",
    "target_source": None,
    "risk_free_annual": 0.04,
    "arima_params": None,
}

_DEFAULT_RUN: dict[str, Any] = {
    "raw": None,
    "ds_column": _DS_COL,
    "expected_sign": None,
    "alpha": 0.05,
    "enforce_sig_for": None,
    "require_stationary": True,
    "require_invertible": True,
    "max_abs_ar": None,
    "max_abs_ma": None,
    "vif_max": 10.0,
    "soft_method": "weighted",
    "weights": None,
    "top_n": 3,
    "apply_hard": True,
}

# ── STATA-style console: each menu key click APPENDS an output entry to a
# stacked log. Actions tagged `needs_combo=True` reveal a lag-combination
# selector populated from the engine's results_df, so every lag combination
# is selectable — not only the top-N.
_ACTIONS: list[dict[str, Any]] = [
    {"key": "tsdisplay",    "label": "tsdisplay",  "group": "EDA",          "needs_combo": False},
    {"key": "decomp",       "label": "decomp",     "group": "EDA",          "needs_combo": False},
    {"key": "pacf",         "label": "pacf",       "group": "EDA",          "needs_combo": False},
    {"key": "stationarity", "label": "ndiffs",     "group": "Stationarity", "needs_combo": False},
    {"key": "seasonality",  "label": "nsdiffs",    "group": "Stationarity", "needs_combo": False},
    {"key": "top_models",   "label": "top-N",      "group": "Models",       "needs_combo": False},
    {"key": "all_combos",   "label": "all combos", "group": "Models",       "needs_combo": False},
    {"key": "summary",      "label": "summary",    "group": "Models",       "needs_combo": True},
    {"key": "forecast",     "label": "forecast",   "group": "Plots",        "needs_combo": True},
    {"key": "cv",           "label": "cv",         "group": "Plots",        "needs_combo": True},
    {"key": "resid",        "label": "residuals",  "group": "Plots",        "needs_combo": True},
    {"key": "downloads",    "label": "exports",    "group": "Other",        "needs_combo": False},
]
_ACTION_BY_KEY: dict[str, dict[str, Any]] = {a["key"]: a for a in _ACTIONS}
_ACTION_DESC: dict[str, str] = {
    "tsdisplay":    "Series + ACF + PACF (40 lags) of the training target.",
    "decomp":       "Seasonal decomposition (observed/trend/seasonal/residual).",
    "pacf":         "Partial autocorrelation of the training target.",
    "stationarity": "ADF / KPSS / PP unit-root tests and suggested d.",
    "seasonality":  "CH / OCSB seasonal-difference tests and suggested D.",
    "top_models":   "Soft-rule ranked top-N table (rank, MEVs, order, soft score).",
    "all_combos":   "Every fitted (variable × lag) combination with metrics.",
    "summary":      "SARIMAX statsmodels summary text for the selected combo.",
    "forecast":     "Forecast vs actual + CI band for the selected combo.",
    "cv":           "Sliding-window cross-validated forecast for the selected combo.",
    "resid":        "Residual diagnostics (residuals/hist/QQ/ACF/Ljung-Box).",
    "downloads":    "Download model artifacts + JSON config snapshots.",
}

_PROGRESS_BAR_WIDTH = 28          # blocks in the █/░ outer bar
_ROLLING_BAR_WIDTH  = 18          # blocks in the rolling-forecast inner bar
_AUTO_SWITCH_DELAY_SEC = 1.0      # pause on completion banner before summary
_PROGRESS_REFRESH_SEC = 0.12      # max repaint frequency for live progress


# ─────────────────────────────────────────────────────────────────────────────
# STATA-style console output entry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArxOutput:
    """A single entry in the stacked console log.

    `kind` controls how the renderer dispatches the entry:
        "text"          — fixed-width text body
        "figure"        — Plotly figure
        "table"         — pandas DataFrame
        "block"         — callable that draws Streamlit widgets (e.g. downloads)
        "error"         — red error block
        "stata_summary" — parsed SARIMAX report card; `content` is a dict with
                          `parsed` (dict from _parse_sarimax_summary_text) and
                          `raw` (original text) for fallback rendering.
    """
    cmd: str
    kind: str
    content: Any
    elapsed: float = 0.0
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    if "arx_basic" not in st.session_state:
        st.session_state["arx_basic"] = {**_DEFAULT_BASIC}
    if "arx_run" not in st.session_state:
        st.session_state["arx_run"] = {**_DEFAULT_RUN}
    st.session_state.setdefault("arx_step", 0)
    st.session_state.setdefault("arx_cfg_subroute", "main")
    st.session_state.setdefault("arx_live_log", [])
    st.session_state.setdefault("arx_console", [])      # list[ArxOutput]
    st.session_state.setdefault(
        "arx_run_meta",
        {"running": False, "start_time": 0.0, "total": 0,
         "completed": 0, "elapsed": 0.0},
    )


def _basic() -> dict[str, Any]:
    return st.session_state["arx_basic"]


def _run_cfg() -> dict[str, Any]:
    return st.session_state["arx_run"]


def _set_basic(key: str, value: Any) -> None:
    _basic()[key] = value


def _set_run(key: str, value: Any) -> None:
    _run_cfg()[key] = value


def _reset_state() -> None:
    st.session_state["arx_step"] = 0
    st.session_state["arx_cfg_subroute"] = "main"
    st.session_state["arx_basic"] = {**_DEFAULT_BASIC}
    st.session_state["arx_run"] = {**_DEFAULT_RUN}
    st.session_state["arx_live_log"] = []
    st.session_state["arx_console"] = []
    st.session_state["arx_run_meta"] = {
        "running": False, "start_time": 0.0, "total": 0,
        "completed": 0, "elapsed": 0.0,
    }
    for k in (
        "arx_mev_df", "arx_target_df", "arx_pipeline", "arx_cv_cache",
        "arx_basic_edited", "arx_run_edited", "arx_basic_seed",
        "arx_run_seed", "arx_config_collapsed", "arx_last_run_summary",
    ):
        st.session_state.pop(k, None)


def _console_append(out: ArxOutput) -> None:
    buf = st.session_state.setdefault("arx_console", [])
    buf.append(out)
    # Cap the log so we don't drown the page after dozens of clicks.
    if len(buf) > 50:
        del buf[: len(buf) - 50]


def _expander_default(section: str) -> bool:
    """Pre-run: Target + MEVs open, others closed. Post-run: all closed."""
    if st.session_state.get("arx_config_collapsed"):
        return False
    return section in ("target", "mevs")


# ─────────────────────────────────────────────────────────────────────────────
# Config sections — one per expander, no step headings
# ─────────────────────────────────────────────────────────────────────────────

def _ap() -> dict[str, Any]:
    b = _basic()
    if not b.get("arima_params"):
        b["arima_params"] = {**_AP_DEFAULTS}
    return b["arima_params"]


def _set_ap(key: str, value: Any) -> None:
    _ap()[key] = value


def _section_arima_params() -> None:
    ap = _ap()
    st.caption("Controls pmdarima auto_arima. Defaults match the standard ARIMAX sweep.")

    # ── Criterion ───────────────────────────────────────────────────────
    _IC_OPTS = ["aic", "bic", "hqic", "oob"]
    ic = st.selectbox(
        "Information criterion", _IC_OPTS,
        index=_IC_OPTS.index(ap.get("information_criterion", "aic")),
        key="arx_ap_ic",
        help="Model selection criterion. AIC is standard; BIC penalises complexity more.",
    )
    _set_ap("information_criterion", ic)

    # ── Stationarity test + alpha ────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        _TEST_OPTS = ["kpss", "adf", "pp"]
        test = st.selectbox(
            "Stationarity test", _TEST_OPTS,
            index=_TEST_OPTS.index(ap.get("test", "kpss")),
            key="arx_ap_test",
            help="Unit-root test used to determine d.",
        )
        _set_ap("test", test)
    with c2:
        alpha_ap = st.number_input(
            "Test α", min_value=0.01, max_value=0.10,
            value=float(ap.get("alpha", 0.05)), step=0.01, format="%.2f",
            key="arx_ap_alpha",
            help="Significance level for unit-root test.",
        )
        _set_ap("alpha", float(alpha_ap))

    # ── Order bounds ─────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        max_p = st.number_input(
            "max_p (AR)", min_value=1, max_value=20,
            value=int(ap.get("max_p", 5)), step=1, key="arx_ap_max_p",
        )
        _set_ap("max_p", int(max_p))
    with c2:
        max_q = st.number_input(
            "max_q (MA)", min_value=1, max_value=20,
            value=int(ap.get("max_q", 5)), step=1, key="arx_ap_max_q",
        )
        _set_ap("max_q", int(max_q))

    d_auto = st.toggle(
        "Auto-detect d (differencing)",
        value=(ap.get("d") is None),
        key="arx_ap_d_auto",
        help="On = auto_arima uses the stationarity test to pick d. Off = fix d manually.",
    )
    if d_auto:
        _set_ap("d", None)
    else:
        d_val = st.number_input(
            "Fixed d", min_value=0, max_value=2,
            value=int(ap.get("d") or 0), step=1, key="arx_ap_d_val",
        )
        _set_ap("d", int(d_val))

    # ── Seasonal ─────────────────────────────────────────────────────────
    seasonal_on = st.toggle(
        "Seasonal ARIMA (SARIMA)",
        value=bool(ap.get("seasonal", True)),
        key="arx_ap_seasonal",
        help="Enable seasonal ARIMA terms. Forced False for log/boxcox transforms.",
    )
    _set_ap("seasonal", bool(seasonal_on))
    if seasonal_on:
        _M_OPTS = [1, 4, 12, 52, 365]
        _M_LABELS = {1: "1 — none", 4: "4 — Quarterly", 12: "12 — Monthly",
                     52: "52 — Weekly", 365: "365 — Daily"}
        cur_m = int(ap.get("m", 1))
        m_idx = _M_OPTS.index(cur_m) if cur_m in _M_OPTS else 0
        m = st.selectbox(
            "Seasonal period m", options=_M_OPTS, index=m_idx,
            format_func=lambda x: _M_LABELS.get(x, str(x)),
            key="arx_ap_m",
        )
        _set_ap("m", int(m))
        c1, c2 = st.columns(2)
        with c1:
            max_P = st.number_input(
                "max_P (seasonal AR)", min_value=0, max_value=5,
                value=int(ap.get("max_P", 2)), step=1, key="arx_ap_max_P",
            )
            _set_ap("max_P", int(max_P))
        with c2:
            max_Q = st.number_input(
                "max_Q (seasonal MA)", min_value=0, max_value=5,
                value=int(ap.get("max_Q", 2)), step=1, key="arx_ap_max_Q",
            )
            _set_ap("max_Q", int(max_Q))

    # ── Search strategy ──────────────────────────────────────────────────
    st.markdown("**Search strategy**")
    _cur_strategy = (
        "stepwise" if ap.get("stepwise", True)
        else ("random" if ap.get("random", False) else "grid")
    )
    strategy = st.radio(
        "Mode", ["stepwise", "grid", "random"],
        index=["stepwise", "grid", "random"].index(_cur_strategy),
        horizontal=True,
        key="arx_ap_strategy",
        help="stepwise: fast Hyndman-Khandakar. grid: exhaustive. random: sample n_fits configs.",
    )
    _set_ap("stepwise", strategy == "stepwise")
    _set_ap("random", strategy == "random")
    if strategy == "random":
        c1, c2 = st.columns(2)
        with c1:
            n_fits = st.number_input(
                "n_fits", min_value=5, max_value=200,
                value=int(ap.get("n_fits", 10)), step=5, key="arx_ap_n_fits",
                help="Number of random configurations to evaluate.",
            )
            _set_ap("n_fits", int(n_fits))
        with c2:
            rs_val = ap.get("random_state")
            rs_input = st.number_input(
                "random_state (0 = None)", min_value=0, max_value=99999,
                value=int(rs_val) if rs_val is not None else 0,
                step=1, key="arx_ap_rs",
                help="PRNG seed (0 = None = non-reproducible).",
            )
            _set_ap("random_state", int(rs_input) if rs_input > 0 else None)

    # ── Advanced expander ────────────────────────────────────────────────
    with st.expander("Advanced"):
        st.caption("Rarely need changing.")

        c1, c2 = st.columns(2)
        with c1:
            sp = st.number_input(
                "start_p", min_value=0, max_value=int(ap.get("max_p", 5)),
                value=int(ap.get("start_p", 2)), step=1, key="arx_ap_start_p",
            )
            _set_ap("start_p", int(sp))
        with c2:
            sq = st.number_input(
                "start_q", min_value=0, max_value=int(ap.get("max_q", 5)),
                value=int(ap.get("start_q", 2)), step=1, key="arx_ap_start_q",
            )
            _set_ap("start_q", int(sq))

        c1, c2 = st.columns(2)
        with c1:
            md = st.number_input(
                "max_d", min_value=0, max_value=3,
                value=int(ap.get("max_d", 2)), step=1, key="arx_ap_max_d",
            )
            _set_ap("max_d", int(md))
        with c2:
            mo = st.number_input(
                "max_order", min_value=1, max_value=20,
                value=int(ap.get("max_order", 5)), step=1, key="arx_ap_max_order",
                help="Max p+q+P+Q (grid search cap).",
            )
            _set_ap("max_order", int(mo))

        if seasonal_on:
            c1, c2 = st.columns(2)
            with c1:
                sP = st.number_input(
                    "start_P", min_value=0, max_value=int(ap.get("max_P", 2)),
                    value=int(ap.get("start_P", 1)), step=1, key="arx_ap_start_P",
                )
                _set_ap("start_P", int(sP))
            with c2:
                sQ = st.number_input(
                    "start_Q", min_value=0, max_value=int(ap.get("max_Q", 2)),
                    value=int(ap.get("start_Q", 1)), step=1, key="arx_ap_start_Q",
                )
                _set_ap("start_Q", int(sQ))

            c1, c2 = st.columns(2)
            with c1:
                max_D = st.number_input(
                    "max_D", min_value=0, max_value=2,
                    value=int(ap.get("max_D", 1)), step=1, key="arx_ap_max_D",
                )
                _set_ap("max_D", int(max_D))
            with c2:
                _SEAS_TEST_OPTS = ["ocsb", "ch"]
                seas_test = st.selectbox(
                    "Seasonal test", _SEAS_TEST_OPTS,
                    index=_SEAS_TEST_OPTS.index(ap.get("seasonal_test", "ocsb")),
                    key="arx_ap_seas_test",
                )
                _set_ap("seasonal_test", seas_test)

            D_auto = st.toggle(
                "Auto D (seasonal differencing)",
                value=(ap.get("D") is None),
                key="arx_ap_D_auto",
            )
            if D_auto:
                _set_ap("D", None)
            else:
                D_v = st.number_input(
                    "Fixed D", min_value=0, max_value=1,
                    value=int(ap.get("D") or 0), step=1, key="arx_ap_D_val",
                )
                _set_ap("D", int(D_v))

        st.markdown("**Fitting**")
        _METHOD_OPTS = ["lbfgs", "bfgs", "newton", "nm", "cg", "ncg", "powell"]
        c1, c2 = st.columns(2)
        with c1:
            method_ap = st.selectbox(
                "Solver", _METHOD_OPTS,
                index=_METHOD_OPTS.index(ap.get("method", "lbfgs")),
                key="arx_ap_method",
            )
            _set_ap("method", method_ap)
        with c2:
            maxiter_ap = st.number_input(
                "maxiter", min_value=20, max_value=500,
                value=int(ap.get("maxiter", 50)), step=10, key="arx_ap_maxiter",
            )
            _set_ap("maxiter", int(maxiter_ap))

        c1, c2 = st.columns(2)
        with c1:
            _WI_OPTS = ["auto", "True", "False"]
            wi_val = ap.get("with_intercept", "auto")
            wi_str = ("True" if wi_val is True else "False" if wi_val is False else "auto")
            wi = st.selectbox(
                "with_intercept", _WI_OPTS,
                index=_WI_OPTS.index(wi_str if wi_str in _WI_OPTS else "auto"),
                key="arx_ap_wi",
                help="auto adapts during stepwise search.",
            )
            _set_ap("with_intercept", True if wi == "True" else (False if wi == "False" else "auto"))
        with c2:
            _TREND_OPTS = ["None", "n", "c", "t", "ct"]
            tr_val = ap.get("trend")
            tr_str = str(tr_val) if tr_val is not None else "None"
            trend_ap = st.selectbox(
                "trend", _TREND_OPTS,
                index=_TREND_OPTS.index(tr_str if tr_str in _TREND_OPTS else "None"),
                key="arx_ap_trend",
            )
            _set_ap("trend", None if trend_ap == "None" else trend_ap)

        st.markdown("**Validation & Behaviour**")
        c1, c2 = st.columns(2)
        with c1:
            oos = st.number_input(
                "OOS size", min_value=0, max_value=50,
                value=int(ap.get("out_of_sample_size", 0)), step=1, key="arx_ap_oos",
                help="out_of_sample_size: hold-out obs within auto_arima for OOS scoring.",
            )
            _set_ap("out_of_sample_size", int(oos))
        with c2:
            _SCORING_OPTS = ["mse", "mae"]
            scoring_ap = st.selectbox(
                "Scoring", _SCORING_OPTS,
                index=_SCORING_OPTS.index(ap.get("scoring", "mse")),
                key="arx_ap_scoring",
            )
            _set_ap("scoring", scoring_ap)

        c1, c2 = st.columns(2)
        with c1:
            n_jobs_ap = st.number_input(
                "n_jobs", min_value=1, max_value=16,
                value=int(ap.get("n_jobs", 1)), step=1, key="arx_ap_n_jobs",
                help="Parallel fits (grid search only).",
            )
            _set_ap("n_jobs", int(n_jobs_ap))
        with c2:
            _EA_OPTS = ["ignore", "warn", "raise", "trace"]
            ea = st.selectbox(
                "On error", _EA_OPTS,
                index=_EA_OPTS.index(ap.get("error_action", "ignore")),
                key="arx_ap_ea",
                help="error_action: what to do when a model fit fails.",
            )
            _set_ap("error_action", ea)

        sw = st.toggle(
            "Suppress warnings",
            value=bool(ap.get("suppress_warnings", True)),
            key="arx_ap_suppress",
        )
        _set_ap("suppress_warnings", bool(sw))


def _section_target(
    single_result: Optional[BacktestResult],
    group_results: dict[str, BacktestResult],
    mode: str,
) -> None:
    candidates: dict[str, BacktestResult] = {}
    if single_result is not None:
        _single_label = getattr(single_result, "strategy_name", None) or "Portfolio"
        candidates[_single_label] = single_result
    for name, res in (group_results or {}).items():
        if res is not None:
            candidates[f"Group: {name}"] = res
    if not candidates:
        st.warning("Run a backtest first — no portfolio NAV is available yet.")
        st.session_state["arx_target_df"] = None
        return

    b = _basic()
    src_keys = list(candidates.keys())
    prev_src = b.get("target_source")

    # In group mode a prior single-mode selection (no "Group: " prefix) is stale.
    stale = (mode == "group" and prev_src is not None and not prev_src.startswith("Group: "))

    if prev_src in src_keys and not stale:
        src_index = src_keys.index(prev_src)
    else:
        # No valid prior selection (or stale single/group mismatch) — pick
        # the most relevant default for the current mode.
        if mode == "group":
            group_keys = [k for k in src_keys if k.startswith("Group: ")]
            src_index = src_keys.index(group_keys[0]) if group_keys else 0
        else:
            src_index = 0

    chosen = st.selectbox(
        "Source", src_keys, index=src_index, key="arx_w_target_src",
        help="Which backtest result drives the target column `y`.",
    )
    _set_basic("target_source", chosen)

    c1, c2 = st.columns(2)
    with c1:
        kind = st.selectbox(
            "Target kind", _TARGET_KIND_OPTIONS,
            index=_TARGET_KIND_OPTIONS.index(b.get("target_kind", "log_return")),
            key="arx_w_target_kind",
            help="`log_return` is the usual ARIMAX choice — closer to stationary.",
        )
        _set_basic("target_kind", kind)
    with c2:
        rf = st.number_input(
            "Risk-free (annual)", min_value=0.0, max_value=0.20,
            value=float(b.get("risk_free_annual", 0.04)), step=0.01, format="%.3f",
            key="arx_w_target_rf",
            disabled=(kind != "excess_return"),
            help="Used only when target kind is `excess_return`.",
        )
        _set_basic("risk_free_annual", rf)

    try:
        target_df = portfolio_target_frame(
            result=candidates[chosen], kind=kind,
            risk_free_annual=rf, target_name=_TARGET_NAME,
        )
        st.session_state["arx_target_df"] = target_df
        st.caption(
            f"Target ready · {len(target_df)} obs · "
            f"{target_df.index.min().date()} → {target_df.index.max().date()}."
        )
    except Exception as exc:
        st.session_state["arx_target_df"] = None
        st.error(f"Failed to build target series: {exc}")


def _section_variables() -> None:
    api_key = (
        st.session_state.get("fred_api_key", "")
        or os.environ.get("FRED_API_KEY", "")
        or ""
    ).strip()
    if not api_key:
        st.warning(
            "FRED API key not set — MEV fetch will fail. "
            "Add it on the Home page or set `FRED_API_KEY`."
        )

    b = _basic()
    presets = list(DEFAULT_FRED_PRESETS.keys())
    chosen = st.multiselect(
        "FRED series", options=presets,
        default=[m for m in b.get("MEVS", []) if m in presets]
                or ["T10Y3M", "BAAFFM", "INDPRO"],
        key="arx_w_mev_ids",
        help="Optional — pick 0–4 macro drivers. Leave empty to run pure ARIMA (no exogenous). Each selected series gets transformed per the guide below.",
    )
    custom = st.text_input(
        "Additional series IDs (comma-separated)",
        value="", key="arx_w_mev_custom",
        help="Optional — any other FRED ID, e.g. M2SL, RSAFS.",
    )
    extras = [s.strip().upper() for s in custom.split(",") if s.strip()]
    series_ids = list(dict.fromkeys(chosen + extras))
    _set_basic("MEVS", series_ids)

    if series_ids:
        st.caption(
            "Transform guide — `log_diff` for level series, `diff` for "
            "rate-like, `none` to pass through."
        )
        guide = dict(b.get("MEVS_Guide", {}))
        guide = {k: v for k, v in guide.items() if k in series_ids}
        cols = st.columns(min(len(series_ids), 4))
        for i, sid in enumerate(series_ids):
            default = guide.get(sid, DEFAULT_FRED_PRESETS.get(sid, "log_diff"))
            with cols[i % len(cols)]:
                guide[sid] = st.selectbox(
                    sid, _GUIDE_OPTIONS,
                    index=_GUIDE_OPTIONS.index(default) if default in _GUIDE_OPTIONS else 0,
                    key=f"arx_w_guide_{sid}",
                )
        _set_basic("MEVS_Guide", guide)

    if not series_ids:
        st.caption("No MEVs selected — sweep will fit a pure ARIMA model.")

    fetch_disabled = not series_ids or not api_key
    if st.button(
        "Fetch MEVs",
        disabled=fetch_disabled,
        key="arx_w_mev_fetch",
        use_container_width=True,
    ):
        try:
            with st.spinner(f"Fetching {len(series_ids)} FRED series…"):
                mev_df = fetch_fred_series(series_ids, api_key=api_key or None)
            st.session_state["arx_mev_df"] = mev_df
            st.caption(
                f"Fetched {len(mev_df.columns)} series · {len(mev_df)} obs · "
                f"{mev_df.index.min().date()} → {mev_df.index.max().date()}."
            )
        except Exception as exc:
            st.error(f"Fetch failed: {exc}")

    mev_df = st.session_state.get("arx_mev_df")
    if mev_df is not None:
        st.caption(
            f"Cached · {len(mev_df.columns)} series · {len(mev_df)} obs."
        )


def _section_model_settings() -> None:
    b = _basic()
    c1, c2 = st.columns(2)
    with c1:
        freq = st.selectbox(
            "Resample frequency", _FREQ_OPTIONS,
            index=_FREQ_OPTIONS.index(b.get("freq", "QE")),
            format_func=lambda f: f"{f} — {_FREQ_HINTS[f]}",
            key="arx_w_freq",
        )
        _set_basic("freq", freq)
        max_lag = st.number_input(
            "Max lag", min_value=1, max_value=24,
            value=int(b.get("max_lag") or 4), step=1, key="arx_w_max_lag",
        )
        _set_basic("max_lag", int(max_lag))
    with c2:
        _n_mevs = len(b.get("MEVS", []))
        _max_k  = max(2, _n_mevs)   # always ≥ 2 so stored value=2 stays valid
        _val_k  = max(1, min(int(b.get("max_number_of_Exogenous_Variables", 2)), _max_k))
        # Streamlit validates the SESSION STATE value (not the value= param) against
        # min/max on every render. If the user previously set arx_w_kexog=3 and now
        # max_value=2, Streamlit raises StreamlitAPIException before the widget
        # even appears — crashing the entire column. Clamp the stored value first.
        _stored = st.session_state.get("arx_w_kexog")
        if _stored is not None and not (1 <= int(_stored) <= _max_k):
            st.session_state["arx_w_kexog"] = max(1, min(int(_stored), _max_k))
        k_exog = st.number_input(
            "Max exogenous vars / model",
            min_value=1, max_value=_max_k,
            value=_val_k,
            step=1, key="arx_w_kexog",
        )
        _set_basic("max_number_of_Exogenous_Variables", int(k_exog))
        transform = st.selectbox(
            "Endogenous transform", _TRANSFORM_OPTIONS,
            index=_TRANSFORM_OPTIONS.index(b.get("transform", "original")),
            key="arx_w_transform",
        )
        _set_basic("transform", transform)

    t1, t2, t3 = st.columns(3)
    with t1:
        v = st.toggle(
            "Include non-lags",
            value=bool(b.get("include_non_lags", False)),
            key="arx_w_inc_nonlags",
        )
        _set_basic("include_non_lags", bool(v))
    with t2:
        v = st.toggle(
            "Trace fitting",
            value=bool(b.get("trace", False)), key="arx_w_trace",
        )
        _set_basic("trace", bool(v))
    with t3:
        v = st.toggle(
            "Use tqdm",
            value=bool(b.get("use_tqdm", True)), key="arx_w_tqdm",
        )
        _set_basic("use_tqdm", bool(v))


def _section_train_test() -> None:
    b = _basic()
    train = st.slider(
        "Train fraction", min_value=0.50, max_value=0.95,
        value=float(b.get("train_threshold", 0.80)), step=0.05,
        key="arx_w_train",
    )
    _set_basic("train_threshold", float(train))

    train_pct = int(round(train * 100))
    test_pct = 100 - train_pct
    st.markdown(
        f"<div style='font-family:monospace;font-size:14px;'>"
        f"<span style='color:{theme.CHART_PORTFOLIO}'>Train {train_pct}%</span> · "
        f"<span style='color:{theme.MAIN_TEXT_SECONDARY}'>Test {test_pct}%</span><br>"
        f"<span style='color:{theme.CHART_PORTFOLIO}'>"
        f"{'█' * (train_pct // 5)}</span>"
        f"<span style='color:{theme.CARD_BORDER}'>"
        f"{'░' * (test_pct // 5)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    oot_on = st.toggle(
        "Enable out-of-time (OOT) holdout",
        value=bool(b.get("oot_test", False)), key="arx_w_oot_on",
    )
    _set_basic("oot_test", bool(oot_on))
    if oot_on:
        oot = st.slider(
            "OOT threshold", min_value=0.80, max_value=0.99,
            value=float(b.get("oot_threshold", 0.90)), step=0.01,
            key="arx_w_oot_thr",
        )
        _set_basic("oot_threshold", float(oot))


def _section_hard_rules() -> None:
    b = _basic()
    r = _run_cfg()
    apply_hard = st.toggle(
        "Apply hard rules", value=bool(r.get("apply_hard", True)),
        key="arx_w_apply_hard",
    )
    _set_run("apply_hard", bool(apply_hard))
    if not apply_hard:
        st.caption("Hard rules disabled — controls below are inert.")

    mevs = b.get("MEVS", [])
    if mevs:
        st.caption("Expected sign per MEV")
        sign = dict(r.get("expected_sign") or {})
        sign = {k: v for k, v in sign.items() if k in mevs}
        cols = st.columns(min(len(mevs), 3))
        for i, mev in enumerate(mevs):
            default = sign.get(mev, "undetermined")
            with cols[i % len(cols)]:
                sign[mev] = st.selectbox(
                    mev, _SIGN_OPTIONS,
                    index=_SIGN_OPTIONS.index(default) if default in _SIGN_OPTIONS else 2,
                    key=f"arx_w_sign_{mev}",
                    disabled=(not apply_hard),
                )
        _set_run("expected_sign", sign or None)

    st.caption("Coefficient & residual thresholds")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        alpha = st.number_input(
            "α (p-value)", min_value=0.001, max_value=0.50,
            value=float(r.get("alpha", 0.05)), step=0.005, format="%.3f",
            key="arx_w_alpha", disabled=(not apply_hard),
        )
        _set_run("alpha", float(alpha))
    with c2:
        vif = st.number_input(
            "VIF max (0=off)", min_value=0.0, max_value=100.0,
            value=float(r.get("vif_max") or 0.0), step=1.0,
            key="arx_w_vif", disabled=(not apply_hard),
        )
        _set_run("vif_max", float(vif) if vif > 0 else None)
    with c3:
        ar = st.number_input(
            "Max |AR| (0=off)", min_value=0.0, max_value=5.0,
            value=float(r.get("max_abs_ar") or 0.0), step=0.1,
            key="arx_w_ar", disabled=(not apply_hard),
        )
        _set_run("max_abs_ar", float(ar) if ar > 0 else None)
    with c4:
        ma = st.number_input(
            "Max |MA| (0=off)", min_value=0.0, max_value=5.0,
            value=float(r.get("max_abs_ma") or 0.0), step=0.1,
            key="arx_w_ma", disabled=(not apply_hard),
        )
        _set_run("max_abs_ma", float(ma) if ma > 0 else None)

    s1, s2 = st.columns(2)
    with s1:
        v = st.toggle(
            "Require stationary AR",
            value=bool(r.get("require_stationary", True)),
            key="arx_w_stat", disabled=(not apply_hard),
        )
        _set_run("require_stationary", bool(v))
    with s2:
        v = st.toggle(
            "Require invertible MA",
            value=bool(r.get("require_invertible", True)),
            key="arx_w_inv", disabled=(not apply_hard),
        )
        _set_run("require_invertible", bool(v))

    if mevs:
        st.caption("Enforce significance for (empty = check every MEV)")
        current = set(r.get("enforce_sig_for") or [])
        new_set: list[str] = []
        cols = st.columns(min(len(mevs), 4))
        for i, mev in enumerate(mevs):
            with cols[i % len(cols)]:
                on = st.checkbox(
                    mev, value=(mev in current), key=f"arx_w_enf_{mev}",
                    disabled=(not apply_hard),
                )
                if on:
                    new_set.append(mev)
        _set_run("enforce_sig_for", new_set or None)


def _section_soft_rules() -> None:
    r = _run_cfg()
    c1, c2 = st.columns(2)
    with c1:
        method = st.selectbox(
            "Soft method", _SOFT_METHODS,
            index=_SOFT_METHODS.index(r.get("soft_method", "weighted")),
            key="arx_w_soft_method",
        )
        _set_run("soft_method", method)
    with c2:
        top_n = st.number_input(
            "Top N", min_value=1, max_value=20,
            value=int(r.get("top_n", 3)), step=1, key="arx_w_topn",
        )
        _set_run("top_n", int(top_n))

    if method == "weighted":
        st.caption("Weights — blank → equal weights")
        weights = dict(r.get("weights") or {})
        cols = st.columns(3)
        for i, key in enumerate(_WEIGHT_KEYS):
            with cols[i % 3]:
                v = st.number_input(
                    key, min_value=0.0, max_value=10.0,
                    value=float(weights.get(key, 0.0)), step=0.1,
                    key=f"arx_w_wt_{key}",
                )
                if v > 0:
                    weights[key] = float(v)
                else:
                    weights.pop(key, None)
        _set_run("weights", weights or None)
    else:
        _set_run("weights", None)


# ─────────────────────────────────────────────────────────────────────────────
# Layout — command bar
# ─────────────────────────────────────────────────────────────────────────────

def _render_command_bar(blocked: bool, is_running: bool = False) -> tuple[bool, bool]:
    """Top command bar. Returns (run_clicked, reset_clicked).

    `is_running` — when True, both Run Sweep and Reset are force-disabled so a
    misclick can't kill an in-progress sweep (Streamlit cancels the running
    script on any new interaction, which would discard hundreds of partial
    fits)."""
    b = _basic()
    r = _run_cfg()

    target = b.get("target_source") or "—"
    target_kind = b.get("target_kind", "log_return")
    freq = b.get("freq", "QE")
    n_mevs = len(b.get("MEVS", []))
    apply_hard = bool(r.get("apply_hard", True))
    top_n = int(r.get("top_n", 3))

    pipe_color = theme.COLOR_GAIN if apply_hard else theme.MAIN_TEXT_SECONDARY
    sep = f'<span style="color:{theme.CARD_BORDER};margin:0 4px">|</span>'
    summary_html = (
        f'<div class="summary-bar" style="margin:0;height:32px;">'
        f'<span><b style="color:{theme.SECTION_HEADER}">TARGET</b> '
        f'<span style="color:{theme.MAIN_TEXT}">{target}</span> '
        f'<span style="color:{theme.MAIN_TEXT_SECONDARY}">· {target_kind}</span></span>'
        f'{sep}'
        f'<span><b style="color:{theme.SECTION_HEADER}">FREQ</b> '
        f'<span style="color:{theme.MAIN_TEXT}">{freq}</span></span>'
        f'{sep}'
        f'<span><b style="color:{theme.SECTION_HEADER}">MEVS</b> '
        f'<span style="color:{theme.MAIN_TEXT}">{n_mevs}</span></span>'
        f'{sep}'
        f'<span><b style="color:{theme.SECTION_HEADER}">HARD</b> '
        f'<span style="color:{pipe_color}">{"ON" if apply_hard else "OFF"}</span></span>'
        f'{sep}'
        f'<span><b style="color:{theme.SECTION_HEADER}">TOP N</b> '
        f'<span style="color:{theme.MAIN_TEXT}">{top_n}</span></span>'
        f'</div>'
    )

    c_summary, c_run, c_reset = st.columns([6, 2, 1])
    with c_summary:
        st.markdown(summary_html, unsafe_allow_html=True)
    with c_run:
        if is_running:
            # Enabled stop button — click interrupts the sweep (Streamlit kills
            # the in-flight script; _run_pipeline's finally block releases the
            # lock and pops _arx_progress_ctx automatically).
            run_clicked = False
            if st.button("⏹ Stop sweep", key="arx_stop_btn",
                         use_container_width=True):
                _meta = st.session_state.get("arx_run_meta") or {}
                _meta["running"] = False
                st.session_state["arx_run_meta"] = _meta
                st.session_state.pop("_arx_progress_ctx", None)
        else:
            run_clicked = st.button(
                "Run ARIMAX Sweep", type="primary",
                disabled=blocked, key="arx_run_btn",
                use_container_width=True,
            )
    with c_reset:
        reset_clicked = st.button(
            "Reset", key="arx_reset_btn",
            disabled=is_running, use_container_width=True,
        )

    last = st.session_state.get("arx_last_run_summary")
    if last:
        st.caption(last)

    return run_clicked, reset_clicked


# ─────────────────────────────────────────────────────────────────────────────
# Layout — config pane (with sticky bottom)
# ─────────────────────────────────────────────────────────────────────────────

def _render_config_panel(
    single_result: Optional[BacktestResult],
    group_results: dict[str, BacktestResult],
    mode: str,
    on_back: Optional[Callable[[], None]],
) -> None:
    # ── Sub-route toggle: Config | AutoARIMA ─────────────────────────────
    cfg_sr = st.session_state.get("arx_cfg_subroute", "main")
    sr_c1, sr_c2 = st.columns(2)
    with sr_c1:
        if st.button(
            "Config", key="arx_cfg_sr_main", use_container_width=True,
            type="primary" if cfg_sr == "main" else "secondary",
        ):
            st.session_state["arx_cfg_subroute"] = "main"
            st.rerun()
    with sr_c2:
        if st.button(
            "AutoARIMA", key="arx_cfg_sr_ap", use_container_width=True,
            type="primary" if cfg_sr == "advanced_arima" else "secondary",
        ):
            st.session_state["arx_cfg_subroute"] = "advanced_arima"
            st.rerun()

    st.markdown('<div class="arx-cfg-sr-rule"></div>', unsafe_allow_html=True)

    if cfg_sr == "advanced_arima":
        try:
            _section_arima_params()
        except Exception as _e:
            st.error(f"AutoARIMA params error: {type(_e).__name__}: {_e}")
    else:
        with st.expander("Target", expanded=_expander_default("target")):
            try:
                _section_target(single_result, group_results, mode)
            except Exception as _e:
                st.error(f"Target section error: {type(_e).__name__}: {_e}")
        with st.expander("MEVs", expanded=_expander_default("mevs")):
            try:
                _section_variables()
            except Exception as _e:
                st.error(f"MEVs section error: {type(_e).__name__}: {_e}")
        with st.expander("Model Settings", expanded=_expander_default("model")):
            try:
                _section_model_settings()
            except Exception as _e:
                st.error(f"Model Settings error: {type(_e).__name__}: {_e}")
        with st.expander("Train / Test", expanded=_expander_default("train")):
            try:
                _section_train_test()
            except Exception as _e:
                st.error(f"Train/Test section error: {type(_e).__name__}: {_e}")
        with st.expander("Hard Rules", expanded=_expander_default("hard")):
            try:
                _section_hard_rules()
            except Exception as _e:
                st.error(f"Hard Rules section error: {type(_e).__name__}: {_e}")
        with st.expander("Soft Rules", expanded=_expander_default("soft")):
            try:
                _section_soft_rules()
            except Exception as _e:
                st.error(f"Soft Rules section error: {type(_e).__name__}: {_e}")

    # Sticky footer — always visible at the bottom of the scrollable pane.
    if on_back is not None:
        st.markdown(
            '<div class="arx-sticky-back-anchor"></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="arx_sticky_back"):
            if st.button(
                "← Back to Step 7",
                key="arx_back_sticky",
                use_container_width=True,
            ):
                on_back()


# ─────────────────────────────────────────────────────────────────────────────
# Layout — output area: menu bar, console log, command line
# ─────────────────────────────────────────────────────────────────────────────

def _available_combos(pipe: Optional[ARIMAXPipeline]) -> list[str]:
    """Every X_combo from the engine's results_df (every (var × lag)
    combination), so the user can target any one of them — not just top-N."""
    if pipe is None or pipe.results_df is None:
        return []
    return pipe.results_df["X_combo"].astype(str).tolist()


def _render_menu_bar(
    pipe: Optional[ARIMAXPipeline], is_running: bool = False,
) -> Optional[tuple[str, Optional[str]]]:
    """Action selector + lag-combination selector + Run/Clear buttons.

    Returns (action, combo) when the user clicks Run, otherwise None.
    `combo` is None for actions that don't need one.

    `is_running` — when True, every interactive element (action pills, combo
    selector, Run, Clear) is force-disabled. This is the concurrency lock
    that prevents an action click from interrupting an in-progress sweep.
    """
    has_pipe = pipe is not None and pipe.results_df is not None

    # Group actions by category for the menu rendering. Pre-run we still show
    # every key (greyed-out via `disabled` if dependencies aren't met).
    grouped: dict[str, list[dict]] = {}
    for a in _ACTIONS:
        grouped.setdefault(a["group"], []).append(a)

    # Selected action — persisted in session so Run survives a rerun.
    selected = st.session_state.get("arx_menu_action", "tsdisplay")
    rows = list(grouped.items())

    # ── Collapsible menu (default closed) ────────────────────────────────
    # The user's primary input is the typed-command bar at the bottom; the
    # group cards + combo selectbox + Run/Clear are kept as a discoverable
    # escape hatch but folded away by default so they don't eat 240+ px.
    # Streamlit persists expander open/closed state across reruns, so the
    # user's preference sticks within a session.
    run_btn = False
    clear_btn = False
    chosen_combo: Optional[str] = None
    action_spec = _ACTION_BY_KEY.get(selected, _ACTIONS[0])
    blocked_run = False

    with st.expander("▾ Show keys", expanded=False):
        # Render each group as a row of pill-buttons. Clicking a pill sets
        # the action. We don't run on click — Run is its own button so the
        # combo selector has a chance to render first.
        for group, actions in rows:
            st.markdown(
                f'<div class="arx-menu-group-label">{group}</div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(len(actions))
            for col, a in zip(cols, actions):
                with col:
                    disabled_pre = (a["key"] not in {"tsdisplay", "decomp", "pacf",
                                                     "stationarity", "seasonality"}
                                    and not has_pipe)
                    is_active = (a["key"] == selected)
                    btn_label = f"● {a['label']}" if is_active else a["label"]
                    if st.button(
                        btn_label,
                        key=f"arx_menu_{a['key']}",
                        use_container_width=True,
                        disabled=disabled_pre or is_running,
                        help=_ACTION_DESC.get(a["key"], ""),
                    ):
                        st.session_state["arx_menu_action"] = a["key"]
                        selected = a["key"]
                        st.rerun()

        # Combo selector — rendered only when the active action needs one.
        action_spec = _ACTION_BY_KEY.get(selected, _ACTIONS[0])
        if action_spec["needs_combo"]:
            combos = _available_combos(pipe)
            if not combos:
                st.markdown(
                    '<div class="arx-menu-hint">'
                    'Run a sweep first to populate lag combinations.'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                default_idx = 0
                for i, c in enumerate(combos):
                    if c != "(none)":
                        default_idx = i
                        break
                prev = st.session_state.get("arx_menu_combo")
                if prev in combos:
                    default_idx = combos.index(prev)
                chosen_combo = st.selectbox(
                    "Lag combination",
                    combos,
                    index=default_idx,
                    key="arx_menu_combo_sel",
                    label_visibility="collapsed",
                    disabled=is_running,
                    help=(f"All {len(combos)} (variable × lag) combinations from "
                          "the sweep — pick any one."),
                )
                st.session_state["arx_menu_combo"] = chosen_combo

        # Run / Clear / pending status — split into two columns so Clear
        # stays available even when Run is disabled.
        c_run, c_clear, c_status = st.columns([2, 1, 5])
        blocked_run = action_spec["needs_combo"] and chosen_combo is None
        if (not has_pipe and selected in {"top_models", "all_combos", "summary",
                                           "forecast", "cv", "resid", "downloads"}):
            blocked_run = True
        with c_run:
            run_btn = st.button(
                "▶ Run",
                type="primary",
                disabled=blocked_run or is_running,
                key="arx_menu_run",
                use_container_width=True,
            )
        with c_clear:
            clear_btn = st.button(
                "Clear",
                key="arx_menu_clear",
                disabled=is_running,
                use_container_width=True,
                help="Clear the console log.",
            )
        with c_status:
            n = len(st.session_state.get("arx_console", []))
            running = st.session_state.get("arx_run_meta", {}).get("running", False)
            st.markdown(
                f'<div class="arx-menu-status">'
                f'{"⏵ running…" if running else f"{n} entries in log"} · '
                f'{_ACTION_DESC.get(selected, "")}'
                f'</div>',
                unsafe_allow_html=True,
            )

    if clear_btn:
        st.session_state["arx_console"] = []
        st.rerun()

    if run_btn and not blocked_run:
        return (selected, chosen_combo)
    return None


def _render_typed_input(is_running: bool = False) -> Optional[tuple[str, Optional[str]]]:
    """Bottom command input — type `action [combo]` and press Enter.
    A green `:` prompt sits to the left of the input.

    `is_running` — when True, the input is disabled and ANY pending text in
    state is ignored. This is the concurrency lock for the typed-command path
    (otherwise residual text from before the sweep could trigger _run_action
    and clobber the in-progress fit).
    """
    c_prompt, c_input = st.columns([0.04, 1])
    with c_prompt:
        st.markdown(
            '<div class="arx-cmd-prompt">:</div>',
            unsafe_allow_html=True,
        )
    with c_input:
        gen = st.session_state.get("_arx_cmd_gen", 0)
        placeholder = (
            "sweep running — typed input disabled"
            if is_running else
            ("type an action  ·  e.g. tsdisplay  |  forecast UNRATE_lag1  |  "
             f"keys: {' '.join(a['key'] for a in _ACTIONS)}")
        )
        typed = st.text_input(
            "command",
            key=f"arx_cmd_input_{gen}",
            placeholder=placeholder,
            label_visibility="collapsed",
            disabled=is_running,
        )
    if is_running or not typed:
        return None

    raw = typed.strip()
    parts = raw.split(maxsplit=1)
    action = parts[0].lower()
    combo = parts[1].strip() if len(parts) > 1 else None
    aliases = {"diag": "stationarity", "exports": "downloads", "diagnostics": "stationarity"}
    action = aliases.get(action, action)

    if action not in _ACTION_BY_KEY:
        st.warning(
            f"Unknown action '{typed}'. "
            f"Available: {', '.join(a['key'] for a in _ACTIONS)}"
        )
        return None
    return (action, combo)


# ─────────────────────────────────────────────────────────────────────────────
# Console output window — stacked log of ArxOutput entries
# ─────────────────────────────────────────────────────────────────────────────

def _render_results_header(
    will_run: bool, pipe: Optional[ARIMAXPipeline], n_entries: int,
) -> None:
    """Sticky purple Results panel header at the top of arx_window. Mirrors
    the .stata-panel-header pattern used by factor_workspace_tab so the
    ARIMAX output reads as a clearly framed 'virtual screen' panel."""
    if will_run:
        right_text = "running sweep…"
    elif n_entries == 0 and pipe is None:
        right_text = "no entries yet"
    elif n_entries == 0:
        right_text = "0 entries in log"
    else:
        right_text = f"{n_entries} entr{'y' if n_entries == 1 else 'ies'} in log"
    st.markdown(
        '<div class="arx-results-bar">'
        '<span class="arx-results-title">Results</span>'
        f'<span class="arx-results-count">{right_text}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_console_log(will_run: bool) -> None:
    """Render the stacked console log. During a sweep the live-progress
    block is rendered at the top (replaces itself, not appended). Pre-run
    with an empty log shows the idle pre-flight checklist."""
    pipe = st.session_state.get("arx_pipeline")
    log = st.session_state.get("arx_live_log", [])
    outputs: list[ArxOutput] = st.session_state.get("arx_console", [])

    _render_results_header(will_run, pipe, len(outputs))

    # ── Live progress (during sweep) ─────────────────────────────────────
    if will_run:
        st.markdown(
            '<div class="arx-section-label">LIVE SWEEP</div>',
            unsafe_allow_html=True,
        )
        progress_ph = st.empty()
        rolling_ph = st.empty()
        current_ph = st.empty()
        log_ph = st.empty()
        progress_ph.markdown(
            _format_progress_html(0, 1, 0.0, 0.0),
            unsafe_allow_html=True,
        )
        rolling_ph.markdown(
            '<div class="arx-rolling-bar" style="color:#888">Rolling forecast: initialising…</div>',
            unsafe_allow_html=True,
        )
        current_ph.markdown(
            '<div class="arx-current-model" style="color:#888">'
            'Initialising…</div>',
            unsafe_allow_html=True,
        )
        log_ph.markdown(_format_log_html([]), unsafe_allow_html=True)
        st.session_state["_arx_progress_ctx"] = {
            "progress": progress_ph,
            "rolling": rolling_ph,
            "current": current_ph,
            "log": log_ph,
        }
        return

    # ── Pre-run idle state (only when no partial results at all) ─────────
    if pipe is None and not outputs and not log:
        _render_idle_block()
        return

    # ── Sweep history or partial-sweep recovery ──────────────────────────
    if log:
        meta = st.session_state.get("arx_run_meta", {})
        total = meta.get("total", len(log)) or len(log)
        elapsed = meta.get("elapsed", 0.0)
        if pipe is not None:
            label = f"Sweep history · {len(log)} models · {_format_mmss(elapsed)}"
        else:
            label = f"Interrupted sweep · {len(log)}/{total} models completed before page refresh"
        with st.expander(label, expanded=False):
            fits_per_sec = (len(log) / elapsed) if elapsed > 1e-6 else 0.0
            st.markdown(
                _format_progress_html(len(log), total, elapsed, fits_per_sec),
                unsafe_allow_html=True,
            )
            st.markdown(_format_log_html(log), unsafe_allow_html=True)

    # ── Empty console ───────────────────────────────────────────────────
    if not outputs:
        st.markdown(
            '<div class="arx-empty">'
            '<h3>CONSOLE</h3>'
            '<p>No output yet. Pick an action from the menu above '
            '(or type one into the prompt below) and press <code>▶ Run</code>. '
            'Each click appends a result here — figures, tables, and text '
            'stack chronologically like a STATA log.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Stacked log — newest first ──────────────────────────────────────
    for out in reversed(outputs):
        _render_console_entry(out)


def _render_console_entry(out: ArxOutput) -> None:
    elapsed_str = f"{out.elapsed:.2f}s" if out.elapsed > 0 else ""
    st.markdown(
        f'<div class="arx-cons-entry">'
        f'<div class="arx-cons-prompt">. {_html_escape(out.cmd)}'
        f'<span class="arx-cons-elapsed">{elapsed_str}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if out.kind == "text":
        st.markdown(
            f'<pre class="arx-cons-text">{_html_escape(out.content)}</pre>',
            unsafe_allow_html=True,
        )
    elif out.kind == "error":
        st.markdown(
            f'<pre class="arx-cons-text arx-cons-err">{_html_escape(out.content)}</pre>',
            unsafe_allow_html=True,
        )
    elif out.kind == "figure":
        st.plotly_chart(
            out.content,
            use_container_width=True,
            key=f"arx_fig_{out.uid}",
        )
    elif out.kind == "table":
        st.dataframe(
            out.content,
            use_container_width=True,
            hide_index=True,
            key=f"arx_tbl_{out.uid}",
        )
    elif out.kind == "stata_summary":
        parsed = out.content.get("parsed") if isinstance(out.content, dict) else None
        raw    = out.content.get("raw", "") if isinstance(out.content, dict) else str(out.content)
        if parsed:
            st.markdown(_render_stata_report_card(parsed), unsafe_allow_html=True)
        else:
            st.markdown(
                f'<pre class="arx-cons-text">{_html_escape(raw)}</pre>',
                unsafe_allow_html=True,
            )
    elif out.kind == "block":
        # `content` is a callable that draws Streamlit widgets in-place.
        try:
            out.content(out.uid)
        except Exception as exc:
            st.error(f"Block render failed: {type(exc).__name__}: {exc}")


def _html_escape(s: Any) -> str:
    import html as _h
    return _h.escape(str(s))


def _render_stata_report_card(parsed: dict) -> str:
    """Build a self-contained HTML string for a STATA-style SARIMAX report
    card. Pure function — no Streamlit calls; safe to cache or inline."""
    title = _html_escape(parsed.get("title") or "SARIMAX Results")
    header_pairs = parsed.get("header") or []
    diag_pairs   = parsed.get("diag")   or []
    coefs        = parsed.get("coefs")  or []

    def _two_col_block(pairs: list, css_class: str) -> str:
        left, right = [], []
        for i, (label, value) in enumerate(pairs):
            target = left if i % 2 == 0 else right
            target.append(
                f'<div class="{css_class}-row">'
                f'<span class="{css_class}-lbl">{_html_escape(label)}</span>'
                f'<span class="{css_class}-val">{_html_escape(value)}</span>'
                f'</div>'
            )
        while len(left) < len(right):
            left.append(f'<div class="{css_class}-row"></div>')
        while len(right) < len(left):
            right.append(f'<div class="{css_class}-row"></div>')
        return (
            f'<div class="{css_class}">'
            f'<div>{"".join(left)}</div>'
            f'<div>{"".join(right)}</div>'
            f'</div>'
        )

    header_html = _two_col_block(header_pairs, "arx-stata-hdr")
    diag_html   = _two_col_block(diag_pairs,   "arx-stata-diag")

    if coefs:
        rows_html = "".join(
            f'<tr class="{c.get("sig_class", "insig")}">'
            f'<td>{_html_escape(c.get("name", ""))}</td>'
            f'<td class="num">{_html_escape(c.get("coef", ""))}</td>'
            f'<td class="num">{_html_escape(c.get("std_err", ""))}</td>'
            f'<td class="num">{_html_escape(c.get("z", ""))}</td>'
            f'<td class="num">{_html_escape(c.get("p_value", ""))}</td>'
            f'<td class="num">{_html_escape(c.get("ci_low", ""))}</td>'
            f'<td class="num">{_html_escape(c.get("ci_high", ""))}</td>'
            f'</tr>'
            for c in coefs
        )
    else:
        rows_html = (
            '<tr><td colspan="7" class="arx-stata-coef-empty">'
            '(no coefficient data)</td></tr>'
        )

    coef_html = (
        '<div class="arx-stata-coef">'
        '<table>'
        '<thead><tr>'
        '<th>Variable</th>'
        '<th class="num">coef</th>'
        '<th class="num">std err</th>'
        '<th class="z">z</th>'
        '<th class="p">P&gt;|z|</th>'
        '<th class="ci">[0.025</th>'
        '<th class="ci">0.975]</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
    )

    return (
        '<div class="arx-stata">'
        f'<div class="arx-stata-title">{title}</div>'
        '<hr class="arx-stata-rule">'
        f'{header_html}'
        '<hr class="arx-stata-rule">'
        f'{coef_html}'
        '<hr class="arx-stata-rule">'
        f'{diag_html}'
        '<hr class="arx-stata-rule">'
        '</div>'
    )


def _render_idle_block() -> None:
    """Pre-run idle panel — three blocks that fill the window so the empty
    state isn't a blank void. Live values come straight from session state.
    """
    b   = _basic()
    rc  = _run_cfg()

    target_kind   = b.get("target_kind") or "—"
    target_source = b.get("target_source") or "—"
    freq          = b.get("freq", "—")
    freq_label    = _FREQ_HINTS.get(freq, freq)
    mevs          = b.get("MEVS") or []
    mev_text      = ", ".join(mevs) if mevs else "—"
    max_lag       = b.get("max_lag", "—")
    max_exog      = b.get("max_number_of_Exogenous_Variables", "—")
    train_thr     = b.get("train_threshold")
    train_text    = f"{train_thr:.0%}" if isinstance(train_thr, (int, float)) else "—"
    top_n         = rc.get("top_n", "—")
    apply_hard    = "on" if rc.get("apply_hard") else "off"
    soft_method   = rc.get("soft_method", "—")

    recap_rows = [
        ("Target",         f"{target_kind} (source: {target_source})"),
        ("Frequency",      f"{freq} — {freq_label}"),
        ("MEVs",           mev_text),
        ("Max lag",        str(max_lag)),
        ("Max exog/model", str(max_exog)),
        ("Train fraction", train_text),
        ("Top-N · rules",  f"{top_n} · hard {apply_hard} · soft {soft_method}"),
    ]
    recap_html = "".join(
        f'<tr><td>{label}</td><td class="arx-idle-val">{value}</td></tr>'
        for label, value in recap_rows
    )

    keymap_rows = "".join(
        f'<tr><td>:{a["key"]}</td><td>{a["group"]}</td>'
        f'<td>{_ACTION_DESC.get(a["key"], "")}</td></tr>'
        for a in _ACTIONS
    )

    target_df = st.session_state.get("arx_target_df")
    mev_df    = st.session_state.get("arx_mev_df")
    fred_key  = (
        st.session_state.get("fred_api_key", "")
        or os.environ.get("FRED_API_KEY", "")
        or ""
    ).strip()

    if target_df is not None and len(target_df):
        target_status = (
            f'<span class="arx-ok">✓</span> Target '
            f'<span class="arx-note">· {len(target_df)} obs</span>'
        )
    else:
        target_status = (
            '<span class="arx-bad">✗</span> Target '
            '<span class="arx-note">· not set</span>'
        )

    _mevs_cfg = list(_basic().get("MEVS") or [])
    if mev_df is not None and len(mev_df):
        n_cols = max(0, len(mev_df.columns) - 1)
        mev_status = (
            f'<span class="arx-ok">✓</span> MEVs '
            f'<span class="arx-note">· {n_cols} series · {len(mev_df)} obs</span>'
        )
    elif not _mevs_cfg:
        mev_status = (
            '<span class="arx-ok">✓</span> MEVs '
            '<span class="arx-note">· none — pure ARIMA</span>'
        )
    else:
        mev_status = (
            '<span class="arx-bad">✗</span> MEVs '
            '<span class="arx-note">· not fetched</span>'
        )

    if fred_key:
        fred_status = (
            '<span class="arx-ok">✓</span> FRED key '
            '<span class="arx-note">· present</span>'
        )
    else:
        fred_status = (
            '<span class="arx-bad">✗</span> FRED key '
            '<span class="arx-note">· missing</span>'
        )

    st.markdown(
        f'''
<div class="arx-idle-recap">
  <div class="arx-section-label">Current Config</div>
  <table class="arx-idle-table">{recap_html}</table>
</div>
<div class="arx-idle-keymap">
  <div class="arx-section-label">Menu Keys</div>
  <table class="arx-idle-table arx-idle-keymap-table">{keymap_rows}</table>
</div>
<div class="arx-idle-check">
  <div class="arx-section-label">Pre-Flight</div>
  <div class="arx-idle-check-row">
    <span class="arx-idle-check-item">{target_status}</span>
    <span class="arx-idle-check-item">{mev_status}</span>
    <span class="arx-idle-check-item">{fred_status}</span>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )


# ── Live progress (log key) ──────────────────────────────────────────────────

def _format_mmss(seconds: float) -> str:
    import math
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "--:--"
    s = int(round(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _format_progress_html(
    completed: int, total: int, elapsed: float, fits_per_sec: float,
) -> str:
    pct = (completed / total) if total > 0 else 0.0
    fill = int(round(pct * _PROGRESS_BAR_WIDTH))
    bar = (
        f'<span class="arx-progress-fill">{"█" * fill}</span>'
        f'<span class="arx-progress-empty">{"░" * (_PROGRESS_BAR_WIDTH - fill)}</span>'
    )
    eta = (total - completed) / fits_per_sec if fits_per_sec > 1e-6 else float("inf")
    speed = (
        f"{fits_per_sec:.1f} fits/sec"
        if fits_per_sec >= 1.0
        else f"{(1.0 / max(fits_per_sec, 1e-6)):.1f} sec/fit"
    )
    return (
        f'<div class="arx-progress-bar">'
        f'Fitting models: [{bar}] {completed}/{total} ({pct * 100:.1f}%)\n'
        f'Speed: {speed}  |  Elapsed: {_format_mmss(elapsed)}  |  '
        f'ETA: {_format_mmss(eta)}'
        f'</div>'
    )


def _format_current_html(combo_cols: list[str]) -> str:
    label = ", ".join(combo_cols) if combo_cols else "(none — pure ARIMA)"
    target = _basic().get("target_source") or _TARGET_NAME
    target_kind = _basic().get("target_kind", "log_return")
    return (
        f'<div class="arx-current-model">'
        f'Current: ARIMAX(auto) — MEVs: [{label}] — Target: {target_kind} '
        f'(<i>{target}</i>)'
        f'</div>'
    )


def _format_rolling_html(step: int, total: int, combo_label: str) -> str:
    """Inner progress bar: rolling 1-step forecast within a single combo."""
    pct = (step / total) if total > 0 else 0.0
    fill = int(round(pct * _ROLLING_BAR_WIDTH))
    bar = (
        f'<span class="arx-progress-fill">{"█" * fill}</span>'
        f'<span class="arx-progress-empty">{"░" * (_ROLLING_BAR_WIDTH - fill)}</span>'
    )
    return (
        f'<div class="arx-rolling-bar">'
        f'Rolling forecast: [{bar}] {step}/{total} — {combo_label}'
        f'</div>'
    )


def _format_fitting_html(combo_label: str, elapsed: float) -> str:
    """Indeterminate bar shown while auto_arima is fitting (blocking, no steps).

    Cycles a 4-char fill block across the bar using elapsed time, giving the
    appearance of movement even though repaints only happen at callback edges.
    """
    period = 18          # one full cycle in seconds
    pos = int((elapsed % period) / period * _ROLLING_BAR_WIDTH)
    blk = 4              # width of the moving fill block
    chars = ['░'] * _ROLLING_BAR_WIDTH
    for i in range(blk):
        chars[(pos + i) % _ROLLING_BAR_WIDTH] = '█'
    bar_html = "".join(
        '<span class="arx-progress-fill">█</span>'
        if c == '█' else
        '<span class="arx-progress-empty">░</span>'
        for c in chars
    )
    return (
        f'<div class="arx-rolling-bar">'
        f'Auto-fitting:    [{bar_html}] {_format_mmss(elapsed)} — {combo_label}'
        f'</div>'
    )


def _format_log_html(entries: list[dict]) -> str:
    if not entries:
        return (
            '<div class="arx-log-stream" style="color:#888">'
            'Waiting for the first iteration to complete…'
            '</div>'
        )
    lines = []
    for e in entries:
        flag = ('<span class="arx-log-pass">✓</span>'
                if e.get("passed", True)
                else '<span class="arx-log-fail">✗</span>')
        order = e.get("order", "-")
        combo = e.get("combo", "(none)")
        aic = e.get("aic")
        bic = e.get("bic")
        pmev = e.get("p_mev")
        aic_s = f"{aic:.3f}" if aic is not None and aic == aic else "—"
        bic_s = f"{bic:.3f}" if bic is not None and bic == bic else "—"
        pmev_s = f"{pmev:.3f}" if pmev is not None and pmev == pmev else "—"
        idx = e.get("idx", 0)
        lines.append(
            f'<div class="arx-log-line">'
            f'<span class="arx-log-num">[{idx:>3}]</span> '
            f'ARIMA{order} | AIC: {aic_s} | BIC: {bic_s} | '
            f'p(MEV1): {pmev_s} {flag} '
            f'<span style="color:#888">{combo}</span>'
            f'</div>'
        )
    return f'<div class="arx-log-stream">{"".join(lines)}</div>'


# ── Action runner — each menu key maps to a function that returns the
#    ArxOutput entries to append to the console log. Handlers stay pure
#    (no st.* widgets) so the renderer treats every entry uniformly.
# ────────────────────────────────────────────────────────────────────────────

def _train_test_idx(pipe: ARIMAXPipeline) -> tuple[list, list, np.ndarray, np.ndarray]:
    train_idx = pipe.split.train_data[_DS_COL].tolist()
    test_idx = pipe.split.test_data[_DS_COL].tolist()
    return train_idx, test_idx, pipe.split.y_train, pipe.split.y_test


def _row_for_combo(pipe: ARIMAXPipeline, combo: str) -> Optional[pd.Series]:
    """Look up a combo in results_df. Returns None if not found."""
    if pipe.results_df is None:
        return None
    matches = pipe.results_df[pipe.results_df["X_combo"].astype(str) == str(combo)]
    if matches.empty:
        return None
    return matches.iloc[0]


def _resolve_y_train(pipe: Optional[ARIMAXPipeline]) -> Optional[np.ndarray]:
    """Best-effort fetch of the training target — falls back to the raw
    target series for actions that work pre-sweep (EDA / stationarity)."""
    if pipe is not None and pipe.split is not None:
        return np.asarray(pipe.split.y_train, dtype=float)
    target_df = st.session_state.get("arx_target_df")
    if target_df is not None and len(target_df):
        col = _basic().get("TARGET", _TARGET_NAME)
        if col in target_df.columns:
            return np.asarray(target_df[col].dropna().values, dtype=float)
        return np.asarray(target_df.iloc[:, 0].dropna().values, dtype=float)
    return None


def _action_tsdisplay(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    y = _resolve_y_train(pipe)
    if y is None or len(y) < 8:
        return [ArxOutput(cmd="tsdisplay", kind="error",
                          content="No target series available. Set the target / fetch MEVs first.")]
    fig = tsdisplay_chart(y, lag_max=min(40, len(y) - 1),
                           title=f"Time Series Display ({len(y)} obs)")
    return [ArxOutput(cmd="tsdisplay", kind="figure", content=fig)]


def _action_decomp(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    y = _resolve_y_train(pipe)
    if y is None or len(y) < 8:
        return [ArxOutput(cmd="decomp", kind="error",
                          content="No target series available.")]
    freq = str(_basic().get("freq", "QE"))
    period = _DECOMP_PERIOD.get(freq, 4)
    try:
        fig = decomposition_chart(y, period=period,
                                  title=f"Seasonal Decomposition (m={period})")
        return [ArxOutput(cmd=f"decomp, period({period})", kind="figure", content=fig)]
    except Exception as exc:
        return [ArxOutput(cmd=f"decomp, period({period})", kind="error",
                          content=f"Decomposition failed: {type(exc).__name__}: {exc}")]


def _action_pacf(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    y = _resolve_y_train(pipe)
    if y is None or len(y) < 8:
        return [ArxOutput(cmd="pacf", kind="error", content="No target series available.")]
    fig = pacf_chart(y, lags=min(40, len(y) - 1))
    return [ArxOutput(cmd="pacf, lags(40)", kind="figure", content=fig)]


def _action_stationarity(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    y = _resolve_y_train(pipe)
    if y is None or len(y) < 8:
        return [ArxOutput(cmd="stationarity", kind="error",
                          content="No target series available.")]
    try:
        from pmdarima.arima.utils import ndiffs
    except Exception as exc:
        return [ArxOutput(cmd="stationarity", kind="error",
                          content=f"pmdarima not available: {exc}")]
    try:
        n_adf  = int(ndiffs(y, test="adf"))
        n_kpss = int(ndiffs(y, test="kpss"))
        n_pp   = int(ndiffs(y, test="pp"))
        n_diff = max(n_adf, n_kpss, n_pp)
    except Exception as exc:
        return [ArxOutput(cmd="stationarity", kind="error",
                          content=f"ndiffs failed: {type(exc).__name__}: {exc}")]
    body = (
        f"Unit-root tests on training target ({len(y)} obs)\n"
        f"───────────────────────────────────────────────\n"
        f"  ADF Test suggests:   d = {n_adf}\n"
        f"  KPSS Test suggests:  d = {n_kpss}\n"
        f"  PP Test suggests:    d = {n_pp}\n"
        f"  ───\n"
        f"  Suggested non-seasonal d = max(ADF, KPSS, PP) = {n_diff}"
    )
    return [ArxOutput(cmd="stationarity", kind="text", content=body)]


def _action_seasonality(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    y = _resolve_y_train(pipe)
    if y is None or len(y) < 8:
        return [ArxOutput(cmd="seasonality", kind="error",
                          content="No target series available.")]
    try:
        from pmdarima.arima.utils import nsdiffs
    except Exception as exc:
        return [ArxOutput(cmd="seasonality", kind="error",
                          content=f"pmdarima not available: {exc}")]
    freq = str(_basic().get("freq", "QE"))
    m = _DECOMP_PERIOD.get(freq, 4)
    try:
        D_ch   = int(nsdiffs(y, m=m, max_D=50, test="ch"))
        D_ocsb = int(nsdiffs(y, m=m, max_D=50, test="ocsb"))
    except Exception as exc:
        return [ArxOutput(cmd="seasonality", kind="error",
                          content=f"nsdiffs failed: {type(exc).__name__}: {exc}")]
    body = (
        f"Seasonal-difference tests (m={m})\n"
        f"───────────────────────────────────────────────\n"
        f"  CH   suggests:  D = {D_ch}\n"
        f"  OCSB suggests:  D = {D_ocsb}"
    )
    return [ArxOutput(cmd=f"seasonality, m({m})", kind="text", content=body)]


def _action_top_models(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    if pipe is None or pipe.top_models is None:
        return [ArxOutput(cmd="top_models", kind="error",
                          content="No pipeline available — run a sweep first.")]
    top = pipe.top_models
    cols = [c for c in ("X_combo", "k_exog", "order", "soft_score",
                         "mse", "mae", "rmse", "mape", "smape", "mase")
            if c in top.columns]
    df = top[cols].copy()
    df.insert(0, "rank", range(len(df)))
    if "order" in df.columns:
        df["order"] = df["order"].astype(str)
    return [ArxOutput(cmd=f"top_models, n({len(df)})", kind="table", content=df)]


def _action_all_combos(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    if pipe is None or pipe.results_df is None:
        return [ArxOutput(cmd="all_combos", kind="error",
                          content="No results_df available — run a sweep first.")]
    rdf = pipe.results_df
    cols = [c for c in ("X_combo", "k_exog", "order",
                         "mse", "mae", "rmse", "mape", "smape", "mase")
            if c in rdf.columns]
    df = rdf[cols].copy()
    if "order" in df.columns:
        df["order"] = df["order"].astype(str)
    return [ArxOutput(cmd=f"all_combos, n({len(df)})", kind="table", content=df)]


def _parse_two_column_pairs(block: str) -> list[tuple[str, str]]:
    """Extract (label, value) pairs from a two-column key:value block. Each
    line typically has 1 or 2 pairs separated by 2+ spaces. Continuation lines
    (single token starting with '-', e.g. '- 214' as a Sample range tail)
    are appended to the LEFT-column pair of the preceding line, since STATA
    continuations belong to the left value, not the right."""
    pairs: list[tuple[str, str]] = []
    last_line_left_idx: Optional[int] = None
    for raw in block.splitlines():
        if not raw.strip():
            continue
        tokens = re.split(r"\s{2,}", raw.strip())
        if len(tokens) == 1:
            tok = tokens[0].strip()
            if (tok.startswith("-") and last_line_left_idx is not None
                    and last_line_left_idx < len(pairs)):
                last_label, last_value = pairs[last_line_left_idx]
                pairs[last_line_left_idx] = (last_label, f"{last_value} {tok}")
            continue
        first_idx = len(pairs)
        i = 0
        while i + 1 < len(tokens):
            label = tokens[i].strip()
            value = tokens[i + 1].strip()
            if label:
                pairs.append((label, value))
            i += 2
        if len(pairs) > first_idx:
            last_line_left_idx = first_idx
    return pairs


def _parse_sarimax_summary_text(txt: str) -> Optional[dict]:
    """Parse a statsmodels SARIMAX summary string into structured sections.
    Returns a dict on success; None on any failure (caller falls back to
    rendering the raw text inside <pre>). Never raises."""
    try:
        if not isinstance(txt, str) or not txt.strip():
            return None
        segments = re.split(r"(?m)^=+\s*$", txt)
        if len(segments) < 4:
            return None
        title_seg, header_seg, coef_seg, diag_seg = segments[:4]

        title = " ".join(title_seg.split()).strip() or "SARIMAX Results"
        header_pairs = _parse_two_column_pairs(header_seg)

        coefs: list[dict] = []
        for raw in coef_seg.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            if set(stripped) <= {"-"}:
                continue
            if "std err" in stripped or "P>|z|" in stripped:
                continue
            tokens = stripped.split()
            if len(tokens) == 7:
                name, c, se, z, p, ci_low, ci_high = tokens
                try:
                    p_float: Optional[float] = float(p)
                except (ValueError, TypeError):
                    p_float = None
                if p_float is None:
                    sig_class = "insig"
                elif p_float < 0.01:
                    sig_class = "sig-strong"
                elif p_float < 0.05:
                    sig_class = "sig-med"
                elif p_float < 0.10:
                    sig_class = "sig-weak"
                else:
                    sig_class = "insig"
                coefs.append({
                    "name": name, "coef": c, "std_err": se, "z": z,
                    "p_value": p, "p_float": p_float,
                    "ci_low": ci_low, "ci_high": ci_high,
                    "sig_class": sig_class,
                })
            elif coefs:
                coefs[-1]["name"] = coefs[-1]["name"] + " " + " ".join(tokens)

        diag_pairs = _parse_two_column_pairs(diag_seg)

        return {
            "title": title,
            "header": header_pairs,
            "coefs": coefs,
            "col_headers": ["", "coef", "std err", "z", "P>|z|", "[0.025", "0.975]"],
            "diag": diag_pairs,
        }
    except Exception:
        return None


def _action_summary(pipe: Optional[ARIMAXPipeline], combo: Optional[str]) -> list[ArxOutput]:
    if pipe is None or combo is None:
        return [ArxOutput(cmd="summary", kind="error",
                          content="Pick a lag combination first.")]
    row = _row_for_combo(pipe, combo)
    if row is None:
        return [ArxOutput(cmd=f"summary {combo}", kind="error",
                          content=f"Combo '{combo}' not found in results_df.")]
    txt = str(row.get("summary", "(no summary available)"))
    parsed = _parse_sarimax_summary_text(txt)
    if parsed is not None:
        return [ArxOutput(cmd=f"summary {combo}", kind="stata_summary",
                          content={"parsed": parsed, "raw": txt})]
    return [ArxOutput(cmd=f"summary {combo}", kind="text", content=txt)]


def _action_forecast(pipe: Optional[ARIMAXPipeline], combo: Optional[str]) -> list[ArxOutput]:
    if pipe is None or combo is None:
        return [ArxOutput(cmd="forecast", kind="error",
                          content="Pick a lag combination first.")]
    row = _row_for_combo(pipe, combo)
    if row is None:
        return [ArxOutput(cmd=f"forecast {combo}", kind="error",
                          content=f"Combo '{combo}' not found in results_df.")]
    train_idx, test_idx, y_train, y_test = _train_test_idx(pipe)
    fig = forecast_with_ci_chart(
        train_idx=train_idx, y_train=y_train,
        test_idx=test_idx, y_test=y_test,
        y_pred=row["forecasts"], conf_int=row["confs"],
        title=f"ARIMA{row['order']} + {combo}",
        height=560,
    )
    return [ArxOutput(cmd=f"forecast {combo}", kind="figure", content=fig)]


def _action_resid(pipe: Optional[ARIMAXPipeline], combo: Optional[str]) -> list[ArxOutput]:
    if pipe is None or combo is None:
        return [ArxOutput(cmd="resid", kind="error",
                          content="Pick a lag combination first.")]
    row = _row_for_combo(pipe, combo)
    if row is None:
        return [ArxOutput(cmd=f"resid {combo}", kind="error",
                          content=f"Combo '{combo}' not found in results_df.")]
    try:
        resid = np.asarray(row["model"].resid())
    except Exception as exc:
        return [ArxOutput(cmd=f"resid {combo}", kind="error",
                          content=f"resid() failed: {type(exc).__name__}: {exc}")]
    fig = residual_diagnostics_chart(
        resid, title=f"Residual Diagnostics — ARIMA{row['order']} + {combo}",
    )
    return [ArxOutput(cmd=f"resid {combo}", kind="figure", content=fig)]


def _action_cv(pipe: Optional[ARIMAXPipeline], combo: Optional[str]) -> list[ArxOutput]:
    if pipe is None or combo is None:
        return [ArxOutput(cmd="cv", kind="error",
                          content="Pick a lag combination first.")]
    row = _row_for_combo(pipe, combo)
    if row is None:
        return [ArxOutput(cmd=f"cv {combo}", kind="error",
                          content=f"Combo '{combo}' not found in results_df.")]
    cache: dict[str, Any] = st.session_state.setdefault("arx_cv_cache", {})
    if combo in cache:
        return [ArxOutput(cmd=f"cv {combo} (cached)", kind="figure", content=cache[combo])]

    try:
        from pmdarima import model_selection
        from stock_engine.analytics.arimax.preprocess import parse_x_combo
    except Exception as exc:
        return [ArxOutput(cmd=f"cv {combo}", kind="error",
                          content=f"pmdarima not available: {exc}")]

    y_train = pipe.split.y_train
    train_data = pipe.split.train_data
    cv = model_selection.SlidingWindowForecastCV(window_size=20, step=6, h=6)

    try:
        if combo == "(none)":
            preds = model_selection.cross_val_predict(
                row["pipeline"], y_train, cv=cv, verbose=0, averaging="median",
            )
        else:
            cols = parse_x_combo(combo)
            X = train_data[cols].to_numpy(dtype=float)
            preds = model_selection.cross_val_predict(
                row["pipeline"], y_train, X=X, cv=cv,
                verbose=0, averaging="median",
            )
    except Exception as exc:
        return [ArxOutput(cmd=f"cv {combo}", kind="error",
                          content=f"CV failed: {type(exc).__name__}: {exc}")]

    fig = cv_forecasts_chart(
        np.asarray(y_train, dtype=float),
        [np.asarray(preds, dtype=float)],
        [f"ARIMA{row['order']} + {combo}"],
        overall_title=f"Sliding-window CV ({combo})",
    )
    cache[combo] = fig
    return [ArxOutput(cmd=f"cv {combo}", kind="figure", content=fig)]


def _action_downloads(pipe: Optional[ARIMAXPipeline]) -> list[ArxOutput]:
    if pipe is None:
        return [ArxOutput(cmd="downloads", kind="error",
                          content="No pipeline available — run a sweep first.")]

    def _draw(uid: str) -> None:
        _render_downloads(pipe, key_prefix=f"console_{uid}")

    return [ArxOutput(cmd="downloads", kind="block", content=_draw)]


_ACTION_FUNCS: dict[str, Callable[..., list[ArxOutput]]] = {
    "tsdisplay":    lambda p, c: _action_tsdisplay(p),
    "decomp":       lambda p, c: _action_decomp(p),
    "pacf":         lambda p, c: _action_pacf(p),
    "stationarity": lambda p, c: _action_stationarity(p),
    "seasonality":  lambda p, c: _action_seasonality(p),
    "top_models":   lambda p, c: _action_top_models(p),
    "all_combos":   lambda p, c: _action_all_combos(p),
    "summary":      lambda p, c: _action_summary(p, c),
    "forecast":     lambda p, c: _action_forecast(p, c),
    "cv":           lambda p, c: _action_cv(p, c),
    "resid":        lambda p, c: _action_resid(p, c),
    "downloads":    lambda p, c: _action_downloads(p),
}


def _run_action(action: str, combo: Optional[str]) -> None:
    """Execute an action and append its output(s) to the console log."""
    pipe: Optional[ARIMAXPipeline] = st.session_state.get("arx_pipeline")
    fn = _ACTION_FUNCS.get(action)
    if fn is None:
        _console_append(ArxOutput(
            cmd=action, kind="error",
            content=f"Unknown action '{action}'.",
        ))
        return
    t0 = time.time()
    try:
        outs = fn(pipe, combo)
    except Exception as exc:
        outs = [ArxOutput(
            cmd=f"{action} {combo or ''}".strip(),
            kind="error",
            content=f"{type(exc).__name__}: {exc}",
        )]
    elapsed = time.time() - t0
    for o in outs:
        o.elapsed = elapsed
        _console_append(o)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline runner — with live progress wired into the log view placeholders
# ─────────────────────────────────────────────────────────────────────────────

def _safe_p_mev1(model: Any) -> Optional[float]:
    """Best-effort fetch of the first MEV's p-value from a fitted model."""
    try:
        pv = getattr(model, "pvalues", None)
        if pv is None:
            return None
        if callable(pv):
            pv = pv()
        if hasattr(pv, "to_dict"):
            d = pv.to_dict()
            for name, val in d.items():
                if name not in ("intercept", "const") and not str(name).startswith("ar."):
                    return float(val)
            return None
        if isinstance(pv, (list, tuple, np.ndarray)) and len(pv) > 1:
            return float(pv[1])
    except Exception:
        return None
    return None


def _safe_aic_bic(model: Any) -> tuple[Optional[float], Optional[float]]:
    aic = bic = None
    try:
        a = getattr(model, "aic", None)
        aic = float(a() if callable(a) else a) if a is not None else None
    except Exception:
        aic = None
    try:
        b = getattr(model, "bic", None)
        bic = float(b() if callable(b) else b) if b is not None else None
    except Exception:
        bic = None
    return aic, bic


def _run_pipeline(target_df: pd.DataFrame, mev_df: Optional[pd.DataFrame]) -> None:
    b = _basic()
    r = _run_cfg()

    _ap_dict = b.get("arima_params") or {}
    try:
        arima_params = AutoARIMAParams(**_ap_dict) if _ap_dict else AutoARIMAParams()
    except Exception:
        arima_params = AutoARIMAParams()

    cfg = ARIMAXConfig(
        target=_TARGET_NAME,
        mevs=list(b.get("MEVS", [])),
        mevs_guide=dict(b.get("MEVS_Guide", {})),
        freq=str(b.get("freq", "QE")),
        max_lag=int(b.get("max_lag") or 4),
        max_number_of_exogenous_variables=int(b.get("max_number_of_Exogenous_Variables", 2)),
        include_non_lags=bool(b.get("include_non_lags", False)),
        train_threshold=float(b.get("train_threshold", 0.8)),
        oot_test=bool(b.get("oot_test", False)),
        oot_threshold=float(b.get("oot_threshold", 0.9)),
        transform=str(b.get("transform", "original")),  # type: ignore[arg-type]
        trace=bool(b.get("trace", False)),
        arima_params=arima_params,
    )

    if mev_df is not None:
        raw = merge_target_with_mevs(target_df, mev_df)
        if raw.empty:
            st.error("Merged (target × MEV) frame is empty — check date overlap.")
            return
    else:
        raw = target_df.copy()
        raw.index.name = "DATE"

    ctx = st.session_state.get("_arx_progress_ctx") or {}
    progress_ph = ctx.get("progress")
    rolling_ph  = ctx.get("rolling")
    current_ph  = ctx.get("current")
    log_ph      = ctx.get("log")

    def _set_status(msg: str) -> None:
        if current_ph is not None:
            current_ph.markdown(
                f'<div class="arx-current-model" style="color:{theme.SECTION_HEADER}">{msg}</div>',
                unsafe_allow_html=True,
            )

    pipe = ARIMAXPipeline(config=cfg)
    pipe.set_raw(raw)
    try:
        _set_status("Pre-processing data…")
        pipe.preprocess(ds_column=_DS_COL)
        n_after_preprocess = len(pipe.df) if pipe.df is not None else 0
        _set_status("Building (variable × lag) combinations…")
        pipe.build_combinations(ds_column=_DS_COL)
        _set_status("Splitting train / test…")
        pipe.split_data()
        # Pre-flight: if the data shrunk to nothing, raise a SPECIFIC error
        # showing the shrinkage trace so the user knows exactly which knob to
        # turn. The generic "y_train < 8" sanity check inside model.py only
        # sees the array length; here we have the full pipeline state.
        n_train = len(pipe.split.y_train) if pipe.split is not None else 0
        n_test  = len(pipe.split.y_test)  if pipe.split is not None else 0
        if n_train < 8:
            raise ValueError(
                f"Not enough training data — y_train has {n_train} obs (need ≥ 8).\n"
                f"\n"
                f"Data shrinkage trace:\n"
                f"  raw rows (target × MEVs joined):    {len(raw)}\n"
                f"  after resample('{cfg.freq}') + lag/transform dropna: {n_after_preprocess}\n"
                f"  train ({cfg.train_threshold:.0%} of total):              {n_train}\n"
                f"  test  (remaining):                  {n_test}\n"
                f"\n"
                f"Likely fixes (in order):\n"
                f"  1. Pick a finer freq. Currently '{cfg.freq}' — for short\n"
                f"     backtests use 'ME' (monthly) or even 'D' (daily).\n"
                f"  2. Lower max_lag. Currently {cfg.max_lag} — each lag drops\n"
                f"     that many rows from the head.\n"
                f"  3. Extend the backtest window. {len(raw)} raw rows is\n"
                f"     too few once resampled and lagged."
            )
    except Exception as exc:
        # Surface preprocessing errors via st.error instead of letting them
        # propagate up to the outer try/except: return in render_arimax_tab
        # which would silently abort the run with the progress bar stuck at 0%.
        # Include the full traceback so the offending file:line is visible —
        # without it we can only see the error type/message and have no way
        # to tell whether a stale module is being loaded or a bug remains.
        import traceback as _tb
        tb_text = _tb.format_exc()
        if progress_ph is not None:
            progress_ph.markdown(
                '<div class="arx-completion arx-completion-error">'
                f'Pre-run failed: {type(exc).__name__}: {exc}'
                '</div>',
                unsafe_allow_html=True,
            )
        st.error(f"Pre-run failed: {type(exc).__name__}: {exc}")
        with st.expander("Full traceback (click to expand)", expanded=True):
            st.code(tb_text, language="python")
        raise

    n_combos = len(pipe.all_combinations or [])
    if n_combos == 0:
        st.error("No combinations generated — check max_lag and MEV count.")
        return

    # Now that we know the real total, repaint the progress bar so the user
    # sees "0/N" instead of the "0/1" placeholder while the first fit runs.
    if progress_ph is not None:
        progress_ph.markdown(
            _format_progress_html(0, n_combos, 0.0, 0.0),
            unsafe_allow_html=True,
        )
    _set_status(f"Fitting {n_combos} models — first iteration in progress…")

    start_time = time.time()
    last_paint = [start_time]
    pending_combo: list[list[str]] = [[]]
    # Mutable inner-bar state shared between _on_progress, _on_step, _maybe_repaint.
    # phase: "fitting"  — auto_arima is running (blocking, no step callbacks)
    #        "rolling"  — rolling 1-step forecast loop is running
    rolling_state: dict = {"phase": "fitting", "step": 0, "total": 0, "combo": ""}

    # Live state we mutate on every callback; rendered to placeholders on a
    # throttled schedule so we don't flood the websocket.
    st.session_state["arx_live_log"] = []
    log_buffer = st.session_state["arx_live_log"]
    st.session_state["arx_run_meta"] = {
        "running": True, "start_time": start_time, "total": n_combos,
        "completed": 0, "elapsed": 0.0,
        "rolling_step": 0, "rolling_total": 0, "rolling_combo": "",
    }

    def _maybe_repaint(force: bool = False) -> None:
        now = time.time()
        if not force and (now - last_paint[0]) < _PROGRESS_REFRESH_SEC:
            return
        last_paint[0] = now
        elapsed = now - start_time
        completed = len(log_buffer)
        fps = (completed / elapsed) if elapsed > 1e-6 else 0.0
        if progress_ph is not None:
            progress_ph.markdown(
                _format_progress_html(completed, n_combos, elapsed, fps),
                unsafe_allow_html=True,
            )
        if rolling_ph is not None:
            phase = rolling_state["phase"]
            combo_label = rolling_state["combo"] or "initialising…"
            if phase == "fitting":
                rolling_ph.markdown(
                    _format_fitting_html(combo_label, elapsed),
                    unsafe_allow_html=True,
                )
            else:
                rs, rt = rolling_state["step"], rolling_state["total"]
                if rt > 0:
                    rolling_ph.markdown(
                        _format_rolling_html(rs, rt, combo_label),
                        unsafe_allow_html=True,
                    )
        if current_ph is not None:
            current_ph.markdown(
                _format_current_html(pending_combo[0]),
                unsafe_allow_html=True,
            )
        if log_ph is not None:
            log_ph.markdown(
                _format_log_html(list(reversed(log_buffer[-200:]))),
                unsafe_allow_html=True,
            )

    def _on_step(step_idx: int, total_steps: int) -> None:
        """Fired after each model.update() — switches inner bar to rolling phase."""
        rolling_state["phase"] = "rolling"
        rolling_state["step"] = step_idx + 1
        rolling_state["total"] = total_steps
        # Update arx_run_meta so a post-refresh render can show last-known state.
        meta = st.session_state.get("arx_run_meta") or {}
        meta["rolling_step"] = step_idx + 1
        meta["rolling_total"] = total_steps
        meta["rolling_combo"] = rolling_state["combo"]
        st.session_state["arx_run_meta"] = meta
        _maybe_repaint()

    def _on_progress(idx: int, total: int, combo: list[str]) -> None:
        """Fired before each combo fit — switches inner bar to fitting phase."""
        pending_combo[0] = combo
        combo_label = ", ".join(combo) if combo else "pure ARIMA"
        rolling_state["phase"] = "fitting"
        rolling_state["step"] = 0
        rolling_state["total"] = 0
        rolling_state["combo"] = combo_label
        # Force an immediate paint (bypass throttle) so the "Auto-fitting…" label
        # appears right away rather than waiting for the next callback.
        _maybe_repaint(force=True)

    def _on_complete(idx: int, total: int, row: dict) -> None:
        model = row.get("model")
        aic, bic = _safe_aic_bic(model)
        p_mev = _safe_p_mev1(model)
        order = row.get("order", "?")
        log_buffer.append({
            "idx": idx + 1,
            "order": order,
            "combo": row.get("X_combo", "(none)"),
            "aic": aic,
            "bic": bic,
            "p_mev": p_mev,
            "passed": True,  # hard rules applied below; provisional pass here
        })
        _maybe_repaint()

    try:
        pipe.run_models(
            progress_callback=_on_progress,
            on_fit_complete=_on_complete,
            on_step=_on_step,
        )
        if r.get("apply_hard", True):
            pipe.apply_hard_rules(
                expected_sign=r.get("expected_sign") or None,
                alpha=float(r.get("alpha", 0.05)),
                require_stationary=bool(r.get("require_stationary", True)),
                require_invertible=bool(r.get("require_invertible", True)),
                max_abs_ar=r.get("max_abs_ar"),
                max_abs_ma=r.get("max_abs_ma"),
                vif_max=r.get("vif_max"),
                enforce_sig_for=r.get("enforce_sig_for"),
            )
            # Annotate the live log with hard-rule pass/fail.
            passed_combos = (
                set(pipe.results_after_hard["X_combo"].astype(str).tolist())
                if pipe.results_after_hard is not None else
                {e["combo"] for e in log_buffer}
            )
            for e in log_buffer:
                e["passed"] = str(e["combo"]) in passed_combos

        pipe.rank_top_models(
            method=r.get("soft_method", "weighted"),
            weights=r.get("weights"),
            top_n=int(r.get("top_n", 3)),
        )

        elapsed = time.time() - start_time
        st.session_state["arx_pipeline"] = pipe
        st.session_state["arx_config_collapsed"] = True
        st.session_state["arx_run_meta"] = {
            "running": False, "start_time": start_time, "total": n_combos,
            "completed": len(log_buffer), "elapsed": elapsed,
        }
        n_passed = (
            len(pipe.results_after_hard)
            if pipe.results_after_hard is not None
            else n_combos
        )
        st.session_state["arx_last_run_summary"] = (
            f"Done · {n_combos} models fit · {n_passed} passed hard rules · "
            f"top {len(pipe.top_models)} kept."
        )

        # Final repaint with completion banner. The sweep results become the
        # first entries in the new console log so the user sees the top-N
        # ranking + best-model forecast immediately.
        _maybe_repaint(force=True)
        if progress_ph is not None:
            progress_ph.markdown(
                f'<div class="arx-completion">'
                f'Sweep complete — {n_combos} models fitted in '
                f'{_format_mmss(elapsed)} — top-N ranking added to console.'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Seed the console with the headline outputs from the sweep so the
        # user lands on a useful screen instead of an empty log.
        n_passed_text = (
            f"{n_passed} passed hard rules · "
            if r.get("apply_hard", True) else ""
        )
        # Per-combo failures (model.py records these on results_df.attrs);
        # surface them so the user knows N of M combos didn't fit and why.
        failures: list = []
        if pipe.results_df is not None:
            failures = pipe.results_df.attrs.get("fit_failures", []) or []
        n_fitted = n_combos - len(failures)
        failures_text = (
            f"\n  fit failures:     {len(failures)} of {n_combos} (skipped, sweep continued)"
            if failures else ""
        )
        _console_append(ArxOutput(
            cmd="run_arimax_sweep",
            kind="text",
            content=(
                f"Sweep complete\n"
                f"───────────────────────────────────────────────\n"
                f"  models fitted:    {n_fitted} of {n_combos}\n"
                f"  {n_passed_text}top-N kept:       {len(pipe.top_models)}\n"
                f"  elapsed:          {_format_mmss(elapsed)}"
                f"{failures_text}"
            ),
            elapsed=elapsed,
        ))
        # If there were failures, append a second console entry showing the
        # first few — actionable diagnostic without flooding the log.
        if failures:
            sample = failures[:5]
            tail = f"\n…and {len(failures) - 5} more" if len(failures) > 5 else ""
            _console_append(ArxOutput(
                cmd="fit_failures",
                kind="text",
                content=(
                    "Combinations that failed to fit:\n"
                    + "\n".join(f"  • {combo}: {err}" for combo, err in sample)
                    + tail
                ),
            ))
        # Top-N ranking — table.
        for o in _action_top_models(pipe):
            _console_append(o)
        # Best-model forecast — figure (only if a top model exists).
        if pipe.top_models is not None and len(pipe.top_models) > 0:
            best_combo = str(pipe.top_models.iloc[0]["X_combo"])
            for o in _action_forecast(pipe, best_combo):
                _console_append(o)

        time.sleep(_AUTO_SWITCH_DELAY_SEC)
    except Exception as exc:
        # Match the pre-run path: surface a traceback expander so the
        # offending file:line is visible. pmdarima's "no viable model" alone
        # is not enough to tell whether it's data shape, transform mismatch,
        # or something deeper.
        import traceback as _tb
        tb_text = _tb.format_exc()
        st.session_state["arx_run_meta"] = {
            **st.session_state.get("arx_run_meta", {}),
            "running": False,
        }
        if progress_ph is not None:
            progress_ph.markdown(
                '<div class="arx-completion arx-completion-error">'
                f'Run failed: {type(exc).__name__}: {exc}'
                '</div>',
                unsafe_allow_html=True,
            )
        st.error(f"Run failed: {type(exc).__name__}: {exc}")
        with st.expander("Full traceback (click to expand)", expanded=True):
            st.code(tb_text, language="python")
        raise
    finally:
        # Always release the concurrency lock — even if an exception escaped
        # the success/except branches above. Without this the `running` flag
        # could stay True forever and lock out the next sweep.
        meta = st.session_state.get("arx_run_meta") or {}
        meta["running"] = False
        st.session_state["arx_run_meta"] = meta
        st.session_state.pop("_arx_progress_ctx", None)


# ─────────────────────────────────────────────────────────────────────────────
# Config / model artifact exporters (used by the `downloads` action)
# ─────────────────────────────────────────────────────────────────────────────

def _to_python_json(obj: Any, ds_column: Optional[str] = None) -> str:
    """Match the React wizard's toPythonJson: True/False/None + raw→pd.read_csv."""
    text = json.dumps(obj, indent=4, default=str)
    text = (
        text.replace(": true", ": True")
            .replace(": false", ": False")
            .replace(": null", ": None")
    )
    if ds_column is not None and '"raw":' in text:
        ds = f'"{ds_column}"' if ds_column else '"DATE"'
        read_csv_block = (
            f'pd.read_csv(\n        "YOUR_FILE.csv",\n'
            f'        index_col={ds},\n        parse_dates=[{ds}]\n    )'
        )
        text = text.replace('"raw": None', f'"raw": {read_csv_block}')
        text = re.sub(
            r'"raw":\s*"([^"]+)"',
            lambda m: (
                f'"raw": pd.read_csv(\n        "{m.group(1)}",\n'
                f'        index_col={ds},\n        parse_dates=[{ds}]\n    )'
            ),
            text,
        )
    return text


def _basic_export_view() -> dict[str, Any]:
    drop = {"target_kind", "target_source", "risk_free_annual"}
    return {k: v for k, v in _basic().items() if k not in drop}


def _render_downloads(pipe: ARIMAXPipeline, key_prefix: str = "arx") -> None:
    if pipe.df is None or pipe.results_df is None or pipe.top_models is None:
        return

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pipe.df.to_excel(writer, sheet_name="preprocessed_dataset", index=False)
        pipe.results_df.drop(
            columns=["model", "pipeline", "summary"], errors="ignore"
        ).to_excel(writer, sheet_name="all_candidates", index=False)
        if pipe.results_after_hard is not None:
            pipe.results_after_hard.drop(
                columns=["model", "pipeline", "summary"], errors="ignore",
            ).to_excel(writer, sheet_name="Hard Rule Filtered", index=False)
        pipe.top_models.drop(
            columns=["model", "pipeline", "summary"], errors="ignore",
        ).to_excel(writer, sheet_name="Top Models", index=False)

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "model_output.xlsx",
            data=buf.getvalue(),
            file_name="model_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_dl_xlsx",
            use_container_width=True,
        )
    with c2:
        if pipe.all_combinations is not None:
            st.download_button(
                "lag_combinations.json",
                data=json.dumps(pipe.all_combinations, indent=2),
                file_name="lag_combinations.json",
                mime="application/json",
                key=f"{key_prefix}_dl_combos",
                use_container_width=True,
            )

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    st.caption("Wizard config exports — paste into a Jupyter notebook.")
    basic_text = _to_python_json(_basic_export_view())
    run_text = _to_python_json(_run_cfg(), ds_column=_run_cfg().get("ds_column"))
    c3, c4 = st.columns(2)
    with c3:
        st.download_button(
            "basic_config.json",
            data=basic_text,
            file_name="basic_config.json",
            mime="application/json",
            key=f"{key_prefix}_dl_basic",
            use_container_width=True,
        )
    with c4:
        st.download_button(
            "run_config.json",
            data=run_text,
            file_name="run_config.json",
            mime="application/json",
            key=f"{key_prefix}_dl_run",
            use_container_width=True,
        )




# ─────────────────────────────────────────────────────────────────────────────
# Public entry — two-pane layout with key-driven output window
# ─────────────────────────────────────────────────────────────────────────────

def render_arimax_tab(
    single_result: Optional[BacktestResult],
    group_results: dict[str, BacktestResult],
    config: Config,
    mode: str = "single",
    on_back: Optional[Callable[[], None]] = None,
) -> None:
    _init_state()
    _inject_css("quant_console")
    _inject_css("arimax_tab")
    # Page-level marker. CSS uses :has(.arx-page-marker) to convert col_main's
    # vertical stack into a flex column on this page only — that's what lets
    # `arx_main_grid` claim `flex: 1` of the remaining viewport height
    # instead of being limited to a hard-coded calc().
    st.markdown(
        '<div class="arx-page-marker"></div>',
        unsafe_allow_html=True,
    )

    target_df = st.session_state.get("arx_target_df")
    mev_df = st.session_state.get("arx_mev_df")
    # Read the widget key directly — Streamlit updates arx_w_mev_ids in session
    # state BEFORE the script reruns, whereas _basic()["MEVS"] is only updated
    # later in the same rerun when _section_variables() runs. Using the widget
    # key avoids a one-rerun lag that kept blocked=True after clearing MEVs.
    _widget_mevs = st.session_state.get("arx_w_mev_ids")  # None = not yet rendered
    _custom_raw = st.session_state.get("arx_w_mev_custom", "")
    _custom_ids = [s.strip().upper() for s in _custom_raw.split(",") if s.strip()]
    if _widget_mevs is not None:
        _mevs_current = list(_widget_mevs) + _custom_ids
    else:
        _mevs_current = list(_basic().get("MEVS") or [])
    _mevs_needed = bool(_mevs_current)
    blocked = target_df is None or (mev_df is None and _mevs_needed)

    # ── Concurrency lock ──────────────────────────────────────────────────
    # `running == True` means a sweep is in progress (set by _run_pipeline,
    # cleared in its finally). While running, every interactive widget below
    # is force-disabled — so a stray click can't trigger a Streamlit script
    # rerun and clobber the in-flight sweep (which fits potentially hundreds
    # of models and is very expensive). Stuck-state recovery: if `running`
    # is True but no _arx_progress_ctx exists in session, the previous sweep
    # was killed mid-flight (e.g. user navigated away and back). Force
    # release the lock so the user isn't stranded with all buttons frozen.
    is_running = bool(
        (st.session_state.get("arx_run_meta") or {}).get("running", False)
    )
    if is_running and "_arx_progress_ctx" not in st.session_state:
        meta = st.session_state.get("arx_run_meta") or {}
        # Compute elapsed up to the point of interruption so the partial-sweep
        # expander can show a meaningful time label.
        if meta.get("elapsed", 0.0) == 0.0 and meta.get("start_time"):
            meta["elapsed"] = time.time() - meta["start_time"]
        meta["running"] = False
        st.session_state["arx_run_meta"] = meta
        is_running = False

    run_clicked, reset_clicked = _render_command_bar(
        blocked=blocked, is_running=is_running,
    )

    will_run = bool(run_clicked and not blocked and not is_running)
    if will_run:
        # Reset the live-progress log; the runner will re-populate it.
        st.session_state["arx_live_log"] = []

    pipe: Optional[ARIMAXPipeline] = st.session_state.get("arx_pipeline")

    # ── Two-pane grid ──
    with st.container(key="arx_main_grid"):
        cols = st.columns([1, 3])
        with cols[0]:
            # Marker tag — picked up by `div[data-testid=stHorizontalBlock]
            # :has(.arx-grid-marker)` in `_ARX_CSS` to pin column widths.
            st.markdown(
                '<div class="arx-grid-marker"></div>',
                unsafe_allow_html=True,
            )
            with st.container(key="arx_config_pane", border=False):
                try:
                    _render_config_panel(
                        single_result, group_results, mode, on_back,
                    )
                except Exception as _cfg_exc:
                    st.error(
                        f"Config panel error ({type(_cfg_exc).__name__}): {_cfg_exc}\n\n"
                        "Click **Reset** in the command bar to recover."
                    )
        with cols[1]:
            with st.container(key="arx_output_pane", border=False):
                # Menu bar — pick action + (optional) lag combination.
                with st.container(key="arx_key_bar", border=False):
                    submitted = _render_menu_bar(pipe, is_running=is_running)
                # STATA-style stacking console — newest entries at top.
                with st.container(key="arx_window", border=False):
                    _render_console_log(will_run=will_run)
                # Bottom command input — type "action [combo]" to run inline.
                with st.container(key="arx_cmd_pane", border=False):
                    typed = _render_typed_input(is_running=is_running)

    # Action submission: menu Run-button takes precedence over typed input.
    # `is_running` already disabled the widgets, but defend in depth — if
    # somehow a click slipped through, suppress the action.
    pending: Optional[tuple[str, Optional[str]]] = (
        None if is_running else (submitted or typed)
    )

    if reset_clicked and not is_running:
        _reset_state()
        st.rerun()

    # Re-read; the config panel may have just populated target_df / mev_df.
    target_df = st.session_state.get("arx_target_df")
    mev_df = st.session_state.get("arx_mev_df")
    if will_run and target_df is not None:
        try:
            _effective_mev_df = mev_df if _mevs_needed else None
            _run_pipeline(target_df, _effective_mev_df)
        except Exception as exc:
            # _run_pipeline already calls st.error before re-raising in its
            # own except branches, but if an exception escapes outside those
            # (e.g. ARIMAXConfig construction, merge_target_with_mevs), we
            # surface it here so it never silently disappears.
            already_shown = isinstance(getattr(exc, "_arx_shown", None), bool)
            if not already_shown:
                st.error(f"Sweep aborted: {type(exc).__name__}: {exc}")
            return
        st.rerun()

    if pending and not will_run:
        action, combo = pending
        _run_action(action, combo)
        # Bump the input gen so the typed-command field re-mounts empty.
        if typed is not None:
            st.session_state["_arx_cmd_gen"] = (
                st.session_state.get("_arx_cmd_gen", 0) + 1
            )
        st.rerun()
