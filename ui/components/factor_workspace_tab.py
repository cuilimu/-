"""
ui/components/factor_workspace_tab.py
Unified Factor Analysis workspace tab.

Structure:
  Factor Decomposition tab
    ├── [Regression Analysis]  sub-tab
    │     ├── Workspace DataFrame view
    │     ├── Command builder (GUI verb selector → Y/X pickers → STATA syntax)
    │     └── Output memo (accumulated STATA-style log)
    ├── [Univariate Analysis]  sub-tab
    │     ├── Series selector (portfolio / individual stocks; group selector in multi-group mode)
    │     └── Full univariate profile (KPI strips, alerts, all charts)
    └── [Bivariate Analysis]   sub-tab
          ├── Variable selectors (X, Y)
          ├── Scatter + 95% CI
          ├── Rolling correlation
          ├── Distribution (KDE)
          └── Conditional correlation by decile
"""
from __future__ import annotations
from typing import Optional
import html as _html_lib
import re
import time
import pandas as pd
import streamlit as st

from stock_engine.analytics.factor import (
    ReturnWorkspace, load_into_workspace, execute, CommandOutput,
)
from stock_engine.analytics.factor.bivariate import (
    compute_bivariate_stats, scatter_chart, rolling_corr_chart,
    distribution_chart, tail_analysis_chart, conditional_stats_chart,
)
from stock_engine.analytics.univariate import compute_univariate
from stock_engine.ui.components.univariate_panel import render_univariate_panel
from stock_engine.ui.styles import inject as _inject_css
from stock_engine.backtest.base import BacktestResult
from stock_engine.config import Config

# st.fragment (1.33+) scopes reruns to the decorated section only — eliminates white flash.
# Falls back to st.experimental_fragment (1.30+), then a no-op wrapper.
try:
    _fragment = st.fragment
except AttributeError:
    try:
        _fragment = st.experimental_fragment  # type: ignore[attr-defined]
    except AttributeError:
        import functools
        def _fragment(fn):  # type: ignore[misc]
            return fn

# ── CSS ───────────────────────────────────────────────────────────────────────

_FF_VARS    = {"mktrf","smb","hml","rmw","cma","umd","rf"}
_RESID_PFX  = ("resid","fitted","gen_")
_WS_KEY     = "factor_workspace"
_OUT_KEY    = "factor_output"
_VERB_KEY   = "factor_verb"
_BIV_X_KEY  = "biv_x"
_BIV_Y_KEY  = "biv_y"
_BIV_WIN    = "biv_window"
_REG_TABLE_KEY    = "factor_reg_table"
_GROUP_SAFE_KEY          = "factor_group_safe_names"    # list[str] of _safe(grp_name)
_GROUP_DISP_KEY          = "factor_group_display_names"  # list[str] original group names
_SEL_GROUP_KEY           = "factor_selected_group_idx"   # int index
_WS_FINGERPRINT_KEY      = "_ws_fingerprint"             # detects group/session changes
_SINGLE_PORTFOLIO_VAR_KEY = "factor_single_portfolio_var" # workspace var name for single portfolio

_VERBS = ["reg","corr","summ","scatter","rolling","gen","drop","ls"]

_VERB_HELP = {
    "reg":     "OLS regression  y ~ x1 x2 ...",
    "corr":    "Pearson correlation matrix",
    "summ":    "Descriptive statistics",
    "scatter": "Scatter plot with OLS fit",
    "rolling": "Rolling N-month correlation",
    "gen":     "Create derived variable (resid / fitted / expression)",
    "drop":    "Remove variable from workspace",
    "ls":      "List all workspace variables",
}

# ── Linear Regression sub-route / verb-chip session keys ─────────────────────
_LR_SUBROUTE_KEY    = "lr_subroute"    # "console" | "data_table"
_LR_ACTIVE_VERB_KEY = "lr_active_verb" # currently active verb in GUI builder
_LR_CMD_KEY         = "lr_cmd_input"   # direct command text-input value


# ── Ticker supplement (yfinance fallback) ────────────────────────────────────

def _safe_vname(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    return s.strip("_") or "portfolio"


def _compute_ws_fingerprint(mode: str, single_result, group_results: dict) -> str:
    """Return a string that changes whenever the set of tickers/groups changes."""
    if mode == "group" and group_results:
        names = sorted(group_results.keys())
        tickers = sorted({
            t
            for res in group_results.values()
            if res and getattr(res, "tickers", None)
            for t in res.tickers
        })
        return "group|" + ",".join(names) + "|" + ",".join(tickers)
    if single_result and getattr(single_result, "tickers", None):
        return "single|" + ",".join(sorted(single_result.tickers))
    return ""


def _supplement_ticker_returns(
    ws: ReturnWorkspace,
    single_result,
    group_results: dict,
    config,
) -> list[str]:
    """
    price_map is never written to PortfolioSnapshot in the current backtest
    runner, so analytics/factor/loader._ticker_returns always returns None.
    This function fetches individual ticker monthly returns from yfinance and
    adds them to the workspace as excess returns (raw − rf), matching the
    convention used for the portfolio series.

    Returns a list of tickers that failed to load (empty = all OK).
    """
    from stock_engine.data.yfinance_provider import YFinanceProvider

    rf_series = None
    if "rf" in ws.ls():
        rf_series = ws["rf"]

    # Collect (workspace_prefix, result) pairs
    targets: list[tuple[str, object]] = []
    if single_result and single_result.tickers:
        targets.append(("", single_result))
    for gname, res in (group_results or {}).items():
        if res and res.tickers:
            targets.append((_safe_vname(gname) + "_", res))

    failed: list[str] = []
    for prefix, result in targets:
        prov = YFinanceProvider(config)
        for ticker in result.tickers:
            vname = prefix + ticker.lower()
            if vname in ws.ls():
                continue  # already loaded (price_map worked)
            try:
                df = prov.fetch_historical(
                    ticker,
                    result.start_date,
                    result.end_date,
                    frequency="1mo",
                )
                if df is None or df.empty:
                    failed.append(ticker)
                    continue
                price_col = next(
                    (c for c in [config.price_field.lower(), "close", "adj close"]
                     if c in df.columns),
                    None,
                )
                if price_col is None:
                    failed.append(ticker)
                    continue
                prices = df[price_col].dropna()
                if len(prices) < 4:
                    failed.append(ticker)
                    continue
                ret = prices.pct_change().dropna()
                # Standardise index to month-end timestamps (Period → Timestamp)
                try:
                    ret.index = ret.index.to_period("M").to_timestamp("M")
                except Exception:
                    pass
                # Subtract rf to get excess returns
                if rf_series is not None:
                    aligned_rf = rf_series.reindex(ret.index).fillna(0)
                    ret = ret - aligned_rf
                ws.add(vname, ret.rename(vname))
            except Exception as exc:
                failed.append(ticker)
    return failed


# ── Public entry point ────────────────────────────────────────────────────────

def render_factor_workspace_tab(
    single_result: Optional[BacktestResult],
    group_results: dict[str, BacktestResult],
    config: Config,
    mode: str = "single",
) -> None:
    _inject_css("quant_console")
    _inject_css("factor_workspace_tab")

    # ── Reset workspace when groups/session changes ───────────────────────
    # Compare a fingerprint of current tickers/groups against the one stored
    # when the workspace was last built.  If they differ (new session loaded,
    # groups renamed/changed), force a fresh load so stale variables and
    # stale reg_y options don't persist across sessions.
    _current_fp = _compute_ws_fingerprint(mode, single_result, group_results)
    if _current_fp and _current_fp != st.session_state.get(_WS_FINGERPRINT_KEY, ""):
        st.session_state[_WS_KEY]            = ReturnWorkspace()
        st.session_state[_WS_FINGERPRINT_KEY] = _current_fp
        st.session_state.pop(_REG_TABLE_KEY, None)
        st.session_state.pop(_OUT_KEY, None)
        st.session_state.pop("reg_y", None)
        st.session_state.pop(_SEL_GROUP_KEY, None)

    # ── Initialise workspace ──────────────────────────────────────────────
    ws: ReturnWorkspace = st.session_state.get(_WS_KEY, ReturnWorkspace())
    col_reload, col_note = st.columns([2, 8])
    with col_reload:
        reload = st.button("↺ Reload workspace", key="ws_reload",
                           help="Re-fetch FF factors and reload returns")
    with col_note:
        st.markdown(
            '<span style="color:#888;font-size:11px">'
            'All portfolio/stock series are <b>excess returns</b> (raw − rf).'
            '</span>', unsafe_allow_html=True)

    # Always keep group name lists in sync (needed even without reload)
    _grp_display = list((group_results or {}).keys())
    _grp_safe    = [_safe_vname(k) for k in _grp_display]
    st.session_state[_GROUP_DISP_KEY] = _grp_display
    st.session_state[_GROUP_SAFE_KEY] = _grp_safe
    _single_pvar = (
        _safe_vname(getattr(single_result, "strategy_name", None) or "portfolio")
        if single_result else "portfolio"
    )
    st.session_state[_SINGLE_PORTFOLIO_VAR_KEY] = _single_pvar

    if ws.is_empty() or reload:
        with st.spinner("Loading FF factors and portfolio returns…"):
            ws = ReturnWorkspace()
            load_into_workspace(ws, config,
                                single_result=single_result,
                                group_results=group_results or {})
            # Supplement: price_map is never set on snapshots, so load individual
            # ticker returns directly from yfinance for any tickers not yet in workspace
            _failed_tickers = _supplement_ticker_returns(
                ws, single_result, group_results or {}, config
            )
        st.session_state[_WS_KEY]  = ws
        st.session_state[_OUT_KEY] = []
        st.session_state["_ws_failed_tickers"] = _failed_tickers

        # ── Auto-run FF5 regression for every non-FF series ───────────────
        _avail_ff5 = [c for c in ["mktrf", "smb", "hml", "rmw", "cma"] if c in ws.ls()]
        _auto_targets = [c for c in ws.ls() if c not in _FF_VARS]
        if _avail_ff5 and _auto_targets:
            _auto_tbl: dict = {}
            _auto_outs: list = []
            for _yn in _auto_targets:
                _cmd_a = f"reg {_yn} {' '.join(_avail_ff5)}, robust"
                _out_a = execute(_cmd_a.strip(), ws)
                _auto_outs.append(_out_a)
                if _out_a.kind == "text" and "result" in _out_a.metadata:
                    _auto_tbl[_yn] = _out_a.metadata["result"]
            st.session_state[_REG_TABLE_KEY] = _auto_tbl
            st.session_state[_OUT_KEY] = _auto_outs

        st.toast("Workspace ready", icon="✅")

    # Warn about any tickers that failed to load from yfinance
    _failed = st.session_state.get("_ws_failed_tickers", [])
    if _failed:
        st.warning(
            f"⚠️ Could not load price data for: **{', '.join(_failed)}** — "
            "these tickers won't appear in the decomposition table. "
            "Check that the ticker symbols are valid on Yahoo Finance.",
            icon=None,
        )

    if ws.is_empty():
        st.warning("Run a backtest first, then return here.")
        return

    outputs: list[CommandOutput] = st.session_state.get(_OUT_KEY, [])

    # ── Sub-tabs ──────────────────────────────────────────────────────────
    tab_reg, tab_uv, tab_biv = st.tabs(
        ["Linear Regression", "Univariate Analysis", "Bivariate Analysis"]
    )

    with tab_reg:
        _render_regression_tab(ws, outputs, config)

    with tab_uv:
        _render_univariate_tab(single_result, group_results, config, mode)

    with tab_biv:
        _render_bivariate_tab(ws, config)


# ── Univariate Analysis sub-tab ───────────────────────────────────────────────

def _render_univariate_tab(
    single_result: Optional[BacktestResult],
    group_results: dict[str, BacktestResult],
    config: Config,
    mode: str,
) -> None:
    """
    Univariate profile sub-tab.

    Single-portfolio mode:
        Selectbox: ["Portfolio"] + individual tickers
        → renders univariate profile for chosen series

    Multi-group mode:
        Group selectbox → then series selectbox (same as single mode per group)
    """
    from stock_engine.analytics.engine import AnalyticsEngine
    from stock_engine.data.yfinance_provider import YFinanceProvider

    eng = AnalyticsEngine(config)

    def _daily_returns_for_ticker(ticker: str) -> Optional[pd.Series]:
        """Fetch daily close returns for a single ticker via yfinance."""
        try:
            prov = YFinanceProvider(config)
            df = prov.fetch_historical(
                ticker,
                config.default_start_date,
                config.effective_end_date(),
                frequency=config.default_frequency,
            )
            col = "close" if "close" in df.columns else df.columns[0]
            return df[col].dropna().pct_change().dropna()
        except Exception as e:
            st.warning(f"Could not load price data for {ticker}: {e}")
            return None

    def _render_for_result(result: BacktestResult, prefix: str) -> None:
        tickers = list(result.tickers) if result else []
        port_label = getattr(result, "strategy_name", None) or "Portfolio"
        options = [port_label] + tickers
        sel = st.selectbox(
            "Select series",
            options,
            key=f"uv_series_sel_{prefix}",
        )
        st.markdown("---")
        try:
            if sel == port_label:
                dr = eng.daily_returns(result)
                profile = compute_univariate(dr, config.annualisation_factor)
            else:
                dr = _daily_returns_for_ticker(sel)
                if dr is None or dr.empty:
                    st.warning(f"No return data available for {sel}.")
                    return
                profile = compute_univariate(dr, config.annualisation_factor)
            render_univariate_panel(profile)
        except Exception as e:
            st.warning(f"Univariate profile unavailable: {e}")

    if mode == "group" and group_results:
        group_names = list(group_results.keys())
        sel_group = st.selectbox(
            "Select group",
            group_names,
            key="uv_group_sel",
        )
        if sel_group:
            _render_for_result(group_results[sel_group], prefix=f"grp_{sel_group}")
    else:
        if not single_result:
            st.info("Run a backtest first to see univariate analysis.")
            return
        _render_for_result(single_result, prefix="single")


# ── Linear Regression sub-tab ─────────────────────────────────────────────────

def _get_verb_template(verb: str, ws: ReturnWorkspace) -> str:
    """Return a concrete command template using actual workspace variable names."""
    cols   = ws.ls() if not ws.is_empty() else []
    non_ff = [c for c in cols if c not in _FF_VARS]
    ff_av  = [c for c in cols if c in _FF_VARS and c != "rf"]

    y   = non_ff[0] if non_ff else "portfolio"
    x1  = ff_av[0] if ff_av else "mktrf"
    xs  = " ".join(ff_av[:3]) if ff_av else "mktrf smb hml"
    last = cols[-1] if cols else "var_name"

    return {
        "reg":     f"reg {y} {xs}, robust",
        "corr":    f"corr {y} {x1}",
        "summ":    "summ",
        "scatter": f"scatter {x1} {y}",
        "rolling": f"rolling {x1} {y}, w(12)",
        "gen":     "gen new_var = resid",
        "drop":    f"drop {last}",
        "ls":      "ls",
    }.get(verb, verb)


def _execute_and_store(cmd: str, ws: ReturnWorkspace, outputs: list) -> None:
    """Execute cmd, persist results in session state, trigger fragment rerun."""
    with st.status(f"Running `{cmd.strip()}`…", expanded=True) as _status:
        t0 = time.time()
        out = execute(cmd.strip(), ws)
        elapsed = time.time() - t0
        _status.update(
            label=f"✓ `{cmd.strip()}` — {elapsed:.2f}s",
            state="complete",
            expanded=False,
        )
    outputs.append(out)
    if out.kind == "text" and "result" in out.metadata:
        reg_tbl = st.session_state.get(_REG_TABLE_KEY, {})
        reg_tbl[out.metadata["result"].y_name] = out.metadata["result"]
        st.session_state[_REG_TABLE_KEY] = reg_tbl
    st.session_state[_OUT_KEY] = outputs
    st.session_state[_WS_KEY]  = ws
    st.rerun()


def _build_gui_cmd(ws: ReturnWorkspace, active_verb: str, cols_v, non_ff, all_x) -> str:
    """Render GUI arg controls for active_verb and return the built command string."""
    cmd = ""

    if active_verb == "reg":
        y_var = st.selectbox("Y (dependent)", non_ff or cols_v, key="lr_gui_reg_y")
        x_default = [c for c in _FF_VARS if c in cols_v and c != "rf"]
        x_vars = st.multiselect("X (regressors)", all_x,
                                default=x_default[:3], key="lr_gui_reg_x")
        c3, c4 = st.columns([3, 3])
        with c3:
            robust = st.checkbox("Robust SE", value=True, key="lr_gui_reg_robust")
        with c4:
            try:
                from stock_engine.analytics.factor.methods import METHOD_REGISTRY as _MR
                _methods = list(_MR.keys())
            except ImportError:
                _methods = ["ols"]
            method = st.selectbox("Method", _methods, key="lr_gui_reg_method")
        if x_vars:
            opts = ", robust" if robust and method == "ols" else (
                f", method({method})" if method != "ols" else ""
            )
            cmd = f"reg {y_var} {' '.join(x_vars)}{opts}"

    elif active_verb == "corr":
        vars_ = st.multiselect("Variables", cols_v, default=cols_v[:4], key="lr_gui_corr_vars")
        if vars_:
            cmd = f"corr {' '.join(vars_)}"

    elif active_verb == "summ":
        vars_ = st.multiselect("Variables (blank = all)", cols_v, key="lr_gui_summ_vars")
        cmd = f"summ {' '.join(vars_)}" if vars_ else "summ"

    elif active_verb == "scatter":
        c1, c2 = st.columns(2)
        with c1:
            xn = st.selectbox("X", cols_v, key="lr_gui_scat_x")
        with c2:
            yn_opts = [c for c in cols_v if c != xn] or cols_v
            yn = st.selectbox("Y", yn_opts, key="lr_gui_scat_y")
        cmd = f"scatter {xn} {yn}"

    elif active_verb == "rolling":
        c1, c2, c3 = st.columns([3, 3, 2])
        with c1:
            xn = st.selectbox("X", cols_v, key="lr_gui_rol_x")
        with c2:
            yn_opts = [c for c in cols_v if c != xn] or cols_v
            yn = st.selectbox("Y", yn_opts, key="lr_gui_rol_y")
        with c3:
            win = st.number_input("Window (M)", 6, 60, 12, key="lr_gui_rol_w")
        cmd = f"rolling {xn} {yn}, w({int(win)})"

    elif active_verb == "gen":
        c1, c2 = st.columns([2, 5])
        with c1:
            gen_name = st.text_input("New var name", key="lr_gui_gen_name")
        with c2:
            gen_expr_type = st.radio("Expression", ["resid", "fitted", "custom"],
                                     horizontal=True, key="lr_gui_gen_type")
        if gen_expr_type == "custom":
            gen_expr = st.text_input("Expression", key="lr_gui_gen_expr",
                                     placeholder="portfolio - mktrf")
        else:
            gen_expr = gen_expr_type
        if gen_name:
            cmd = f"gen {gen_name} = {gen_expr}"

    elif active_verb == "drop":
        if cols_v:
            drop_var = st.selectbox("Variable to drop", cols_v, key="lr_gui_drop_var")
            cmd = f"drop {drop_var}"

    elif active_verb == "ls":
        st.caption("Lists all variables in the workspace.")
        cmd = "ls"

    return cmd


def _render_lr_left(ws: ReturnWorkspace, outputs: list) -> None:
    """Left panel: verb chips + GUI builder + text input + Run (40% column)."""
    cols_v = ws.ls()
    non_ff = [c for c in cols_v if c not in _FF_VARS]
    active_verb = st.session_state.get(_LR_ACTIVE_VERB_KEY, "reg")

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="ws-section">Builder &mdash; {active_verb.upper()}</div>',
        unsafe_allow_html=True,
    )
    st.caption(_VERB_HELP.get(active_verb, ""))

    # ── Verb chip bar (prefill text input + switch GUI controls) ──────────
    chip_cols = st.columns(len(_VERBS))
    for i, verb in enumerate(_VERBS):
        with chip_cols[i]:
            if st.button(verb, key=f"lr_vc_{verb}", use_container_width=True):
                st.session_state[_LR_CMD_KEY] = _get_verb_template(verb, ws)
                st.session_state[_LR_ACTIVE_VERB_KEY] = verb
                st.rerun()

    # ── GUI arg controls (verb-specific) ──────────────────────────────────
    gui_cmd = _build_gui_cmd(ws, active_verb, cols_v, non_ff, cols_v)

    # ── STATA preview ─────────────────────────────────────────────────────
    if gui_cmd:
        st.markdown(f'<div class="stata-preview">. {gui_cmd}</div>', unsafe_allow_html=True)
        if st.button(
            "→ Copy to input",
            key="lr_copy_to_input",
            use_container_width=True,
            help="Prefill the command input with this GUI-built command",
        ):
            st.session_state[_LR_CMD_KEY] = gui_cmd
            st.rerun()

    # ── Command input + Run (single execution point) ──────────────────────
    direct = st.text_input(
        "Command",
        label_visibility="collapsed",
        placeholder="e.g.  reg portfolio mktrf smb hml, robust",
        key=_LR_CMD_KEY,
    )
    run_btn = st.button(
        "▶ Run",
        key="lr_run_direct",
        type="primary",
        use_container_width=True,
        disabled=not bool(direct),
    )

    if run_btn and direct:
        _execute_and_store(direct, st.session_state.get(_WS_KEY, ws), outputs)

    # ── Most recent figure pinned in left panel ───────────────────────────
    fig_outs = [o for o in outputs if o.kind == "figure"]
    if fig_outs:
        st.divider()
        st.plotly_chart(fig_outs[-1].content, use_container_width=True)


def _render_lr_right(ws: ReturnWorkspace, outputs: list) -> None:
    """Right panel: pure terminal output (60% column)."""
    text_outs = [o for o in outputs if o.kind in ("text", "error")]
    tbl_outs  = [o for o in outputs if o.kind == "table"]
    n = len(text_outs)

    # Results bar
    st.markdown(
        f'<div class="qc-results-bar">'
        f'<span>RESULTS</span>'
        f'<span style="font-size:10px;font-weight:400">'
        f'{n} command{"s" if n != 1 else ""} in log</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Console output panel
    if not text_outs:
        st.markdown(
            '<div class="stata-panel-body stata-panel-body--compact">'
            '<div class="lr-cmd-echo">Stock Engine &middot; Factor Workspace</div>'
            '<div class="lr-cmd-body">'
            'No commands run yet.<br>'
            'Use the builder on the left or type a command directly.'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        clr_col, _ = st.columns([2, 8])
        with clr_col:
            if st.button("Clear output", key="lr_clear_output", use_container_width=True):
                st.session_state[_OUT_KEY] = []
                st.rerun()
        body_html = "".join(_output_to_html(o) for o in text_outs)
        st.markdown(
            f'<div class="stata-panel-body stata-panel-body--compact">{body_html}</div>',
            unsafe_allow_html=True,
        )

    # Most recent table
    if tbl_outs:
        out = tbl_outs[-1]
        st.markdown(
            f'<div class="cmd-prompt">. {_html_lib.escape(out.cmd)}</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(out.content, use_container_width=True, height=180)


@_fragment
def _render_regression_tab(ws: ReturnWorkspace, outputs: list, config) -> None:
    ws      = st.session_state.get(_WS_KEY, ws)
    outputs = st.session_state.get(_OUT_KEY, outputs)
    subroute = st.session_state.get(_LR_SUBROUTE_KEY, "console")

    # ── Sub-route bar ─────────────────────────────────────────────────────
    _c0, _c1, _c2, _rest = st.columns([2, 2, 2, 6])
    with _c0:
        if st.button(
            "Console",
            key="lr_sr_console",
            type="primary" if subroute == "console" else "secondary",
            use_container_width=True,
        ):
            st.session_state[_LR_SUBROUTE_KEY] = "console"
            st.rerun()
    with _c1:
        if st.button(
            "Data Table",
            key="lr_sr_datatable",
            type="primary" if subroute == "data_table" else "secondary",
            use_container_width=True,
        ):
            st.session_state[_LR_SUBROUTE_KEY] = "data_table"
            st.rerun()
    with _c2:
        if st.button("↺ Reload WS", key="lr_sr_reload", use_container_width=True):
            for _k in (_WS_KEY, _OUT_KEY, _WS_FINGERPRINT_KEY, _REG_TABLE_KEY):
                st.session_state.pop(_k, None)
            st.rerun()

    st.markdown('<div class="lr-subroute-rule"></div>', unsafe_allow_html=True)

    # ── Data Table route ──────────────────────────────────────────────────
    if subroute == "data_table":
        df = ws.df()
        if df.empty:
            st.info("Workspace is empty. Click '↺ Reload WS' to reload.")
            return
        st.markdown(
            f'<div class="lr-data-header">'
            f'{len(df.columns)} variables &nbsp;&middot;&nbsp; {len(df)} months'
            f' &nbsp;&middot;&nbsp; '
            f'{df.index.min().strftime("%Y-%m")} &rarr; {df.index.max().strftime("%Y-%m")}'
            f'</div>',
            unsafe_allow_html=True,
        )
        display_df = df.copy()
        display_df.index = display_df.index.strftime("%Y-%m")
        display_df.index.name = "Date"
        st.dataframe(
            display_df.style.format("{:.4f}", na_rep="—"),
            use_container_width=True,
            height=min(600, 40 + 35 * len(df)),
        )
        return

    # ── Console route: left GUI builder | right terminal ──────────────────
    col_gui, col_term = st.columns([4, 6])

    with col_gui:
        _render_lr_left(ws, outputs)

    with col_term:
        _render_lr_right(ws, outputs)


# ── Bivariate Analysis sub-tab ────────────────────────────────────────────────

# ── Bivariate helpers ────────────────────────────────────────────────────────

_FF_VARS_SET = {"mktrf", "smb", "hml", "rmw", "cma", "umd", "rf"}
_BIV_FREQ_KEY = "biv_freq"


def _sig_stars(p: float) -> str:
    if p < 0.001: return " ***"
    if p < 0.01:  return " **"
    if p < 0.05:  return " *"
    return " (ns)"


def _get_daily_series(name: str, ws: ReturnWorkspace, config=None):
    """
    Return (pd.Series of daily values/returns, error_str).
    - FF factor names   → Ken French daily library via FactorDataProvider.fetch_daily()
    - Portfolio/group   → not supported (position-level data required)
    - Individual tickers → yfinance daily prices → pct_change
    """
    df_ws = ws.df()
    start = (df_ws.index.min() - pd.DateOffset(months=2)).strftime("%Y-%m-%d")
    end   = (df_ws.index.max() + pd.DateOffset(months=1)).strftime("%Y-%m-%d")

    # ── FF factor: fetch daily from Ken French ────────────────────────────
    if name in _FF_VARS_SET:
        try:
            from stock_engine.data.factor_data_provider import FactorDataProvider
            from stock_engine.config import Config as _Cfg
            cfg = config or _Cfg()
            prov = FactorDataProvider(cfg)
            daily_ff = prov.fetch_daily(start, end)
            if name not in daily_ff.columns:
                return None, f"'{name}' not in daily FF dataset (umd may be missing)"
            s = daily_ff[name].rename(name)
            return s, None
        except Exception as exc:
            return None, f"Daily FF fetch failed for '{name}': {exc}"

    # ── Portfolio aggregate: not supported ────────────────────────────────
    _spvar = st.session_state.get(_SINGLE_PORTFOLIO_VAR_KEY, "portfolio")
    _gpvars = set(st.session_state.get(_GROUP_SAFE_KEY, []))
    if name == _spvar or name in _gpvars:
        return None, f"'{name}' is a portfolio aggregate — daily returns require position-level data"

    # ── Individual ticker: yfinance ───────────────────────────────────────
    try:
        import yfinance as yf
        data = yf.download(name.upper(), start=start, end=end,
                           auto_adjust=True, progress=False)
        if data.empty:
            return None, f"No daily data found for '{name.upper()}'"
        # Handle both single-level and MultiIndex columns (yfinance ≥0.2.x)
        if isinstance(data.columns, pd.MultiIndex):
            close = data[("Close", name.upper())]
        else:
            close = data["Close"]
        daily = close.pct_change().dropna()
        daily.name = name
        return daily, None
    except Exception as exc:
        return None, f"yfinance error for '{name}': {exc}"


def _render_biv_kpis(stats, xname: str, yname: str, x: "pd.Series", freq: str) -> None:
    """Render grouped stat cards: Sample | Correlation | OLS Regression | Tail Analysis."""
    import math

    def _c(v):
        """Color helper."""
        try:
            if math.isnan(v): return "#1a1a1a"
        except Exception: return "#1a1a1a"
        return "#00b050" if v > 0 else "#e03030" if v < 0 else "#666666"

    def _m(label, value, color="#1a1a1a", note=""):
        note_html = (f'<div style="font-size:10px;color:#aaa;margin-top:1px">'
                     f'{note}</div>') if note else ""
        return (f'<div style="min-width:100px">'
                f'<div class="biv-stat-label">{label}</div>'
                f'<div class="biv-stat-value" style="color:{color};font-size:14px">{value}</div>'
                f'{note_html}</div>')

    def _row(*items):
        return ('<div style="display:flex;gap:28px;flex-wrap:wrap;margin-top:4px">' +
                "".join(items) + '</div>')

    def _card(title, body_html, color="#660874"):
        return (f'<div class="engine-card" style="padding:10px 14px;margin-bottom:6px">'
                f'<div style="font-size:10px;font-weight:700;color:{color};text-transform:uppercase;'
                f'letter-spacing:.5px;border-bottom:1px solid #f0e0f8;padding-bottom:4px;margin-bottom:8px">'
                f'{title}</div>' + body_html + '</div>')

    # ── Period label ──────────────────────────────────────────────────────
    try:
        period = f"{x.index.min().strftime('%Y-%m')} → {x.index.max().strftime('%Y-%m')}"
    except Exception:
        period = "—"

    # ── Row A: Sample  +  OLS Regression  (side by side) ─────────────────
    sample_html  = _card("Sample",
        _row(_m("N obs", str(stats.n_obs)),
             _m("Frequency", freq),
             _m("Period", period)))

    ols_html = _card("OLS Regression  ( y = α + β·x )",
        _row(_m("β (slope)", f"{stats.beta_yx:.4f}", _c(stats.beta_yx)),
             _m("α (intercept)", f"{stats.alpha_yx:.4f}", _c(stats.alpha_yx)),
             _m("R²", f"{stats.r_squared:.4f}",
                note=f"explains {stats.r_squared*100:.1f}% of variance")))

    col_a, col_b = st.columns(2)
    with col_a: st.markdown(sample_html,  unsafe_allow_html=True)
    with col_b: st.markdown(ols_html,     unsafe_allow_html=True)

    # ── Row B: Correlation (full width) ──────────────────────────────────
    ps  = _sig_stars(stats.pearson_p)
    ks  = _sig_stars(stats.kendall_p)
    corr_html = _card("Correlation Measures",
        _row(_m("Pearson ρ",
                f"{stats.pearson_r:.4f}{ps}", _c(stats.pearson_r),
                f"p = {stats.pearson_p:.4f}  |  parametric, linear"),
             _m("Spearman ρ",
                f"{stats.spearman_r:.4f}{ps}", _c(stats.spearman_r),
                "rank-based, monotone  |  same p as Pearson†"),
             _m("Kendall τ-b",
                f"{stats.kendall_tau:.4f}{ks}", _c(stats.kendall_tau),
                f"p = {stats.kendall_p:.4f}  |  concordance pairs"),
             _m("Covariance",
                f"{stats.covariance:.6f}", _c(stats.covariance),
                "sample cov (n−1)")))
    st.markdown(corr_html + '<div style="font-size:10px;color:#bbb;margin:-4px 0 6px 0">'
                '† Spearman p approximated via Pearson on ranks &nbsp;·&nbsp; '
                '<b>***</b> p&lt;0.001 &nbsp; <b>**</b> p&lt;0.01 &nbsp; <b>*</b> p&lt;0.05</div>',
                unsafe_allow_html=True)

    # ── Row C: Tail Analysis (full width) ────────────────────────────────
    bc = f"{stats.bear_corr:.4f}" if not _isnan(stats.bear_corr) else "—"
    uc = f"{stats.bull_corr:.4f}" if not _isnan(stats.bull_corr) else "—"
    tr = (f"{stats.tail_ratio:.3f}×" if not _isnan(stats.tail_ratio) else "—")
    bc_c = _c(stats.bear_corr) if not _isnan(stats.bear_corr) else "#1a1a1a"
    uc_c = _c(stats.bull_corr) if not _isnan(stats.bull_corr) else "#1a1a1a"
    tail_html = _card("Tail / Regime Analysis  (split on median of X)",
        _row(_m("Bear corr  (x ≤ median)", bc, bc_c, "ρ in lower-X regime"),
             _m("Bull corr  (x > median)", uc, uc_c, "ρ in upper-X regime"),
             _m("Tail ratio", tr, "#1a1a1a",
                "bear / bull  (>1 → stronger downside co-movement)")))
    st.markdown(tail_html, unsafe_allow_html=True)


def _render_bivariate_tab(ws: ReturnWorkspace, config=None) -> None:
    cols_v = ws.ls()
    if len(cols_v) < 2:
        st.warning("Need at least 2 variables in workspace.")
        return

    # ── Controls ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns([3, 3, 2, 2])
    with c1:
        xname = st.selectbox("X variable", cols_v, key=_BIV_X_KEY,
                              index=min(1, len(cols_v) - 1))
    with c2:
        remaining = [c for c in cols_v if c != xname]
        yname = st.selectbox("Y variable", remaining, key=_BIV_Y_KEY)
    with c3:
        window = st.number_input("Rolling window (M)", 6, 60, 12, key=_BIV_WIN)
    with c4:
        freq = st.radio("Frequency", ["Monthly", "Daily"],
                        horizontal=True, key=_BIV_FREQ_KEY,
                        help="Daily fetches from yfinance — only for individual tickers")

    # ── Resolve series ────────────────────────────────────────────────────
    if freq == "Daily":
        x_d, x_err = _get_daily_series(xname, ws, config)
        y_d, y_err = _get_daily_series(yname, ws, config)
        errs = [e for e in [x_err, y_err] if e]
        if errs:
            st.warning("⚠ Daily unavailable: " + "  |  ".join(errs) + "  →  falling back to monthly.")
            x, y, freq = ws[xname], ws[yname], "Monthly"
        else:
            x, y = x_d, y_d
    else:
        x, y = ws[xname], ws[yname]

    # ── Compute stats ─────────────────────────────────────────────────────
    stats = compute_bivariate_stats(x, y)
    if stats is None:
        st.warning("Insufficient overlapping observations (need ≥ 8).")
        return

    # ── KPI cards ─────────────────────────────────────────────────────────
    _render_biv_kpis(stats, xname, yname, x, freq)
    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────
    # Row 1: Scatter with ellipses  +  Rolling correlation
    r1l, r1r = st.columns(2)
    with r1l:
        st.plotly_chart(scatter_chart(x, y, xname, yname), use_container_width=True)
    with r1r:
        st.plotly_chart(rolling_corr_chart(x, y, xname, yname, int(window)),
                        use_container_width=True)

    # Row 2: KDE distribution  +  Tail (conditional rho by decile)
    r2l, r2r = st.columns(2)
    with r2l:
        st.plotly_chart(distribution_chart(x, y, xname, yname), use_container_width=True)
    with r2r:
        fig = tail_analysis_chart(x, y, xname, yname)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Insufficient data for tail analysis.")

    # Row 3: Conditional stats -- X distribution per Y quintile (full width)
    fig = conditional_stats_chart(x, y, xname, yname)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Insufficient data for conditional stats chart.")


# -- Factor Decomposition Results table -------------------------------------------

def _coef_cell(coef: float, t: float, p: float) -> str:
    """Render one cell: coef value + (t-stat) + [p-val]."""
    p_fmt = f"{p:.3f}" if p >= 0.001 else "<0.001"
    return (
        f'<td><span class="coef-val">{coef:.4f}</span>'
        f'<span class="coef-t">({t:.2f})</span>'
        f'<span class="coef-p">[p={p_fmt}]</span></td>'
    )


def _render_decomposition_table(reg_results: dict) -> None:
    if not reg_results:
        return

    all_factors: list[str] = []
    seen_factors: set[str] = set()
    for res in reg_results.values():
        for xn in res.x_names:
            if xn not in seen_factors:
                all_factors.append(xn)
                seen_factors.add(xn)

    factor_headers = "".join(
        f'<th>{f.upper()}</th>' for f in all_factors
    )
    header_row = (
        '<tr>'
        '<th class="col-name">Ticker / Portfolio</th>'
        '<th>Alpha (Monthly%)</th>'
        + factor_headers +
        '<th>N obs</th>'
        '</tr>'
    )

    rows_html = ""
    def _sort_key(y_name):
        low = y_name.lower()
        if low in ("portfolio", "group") or low.startswith("group_"):
            return (0, y_name)
        return (1, y_name)

    for y_name in sorted(reg_results.keys(), key=_sort_key):
        res = reg_results[y_name]

        has_alpha = "const" in res.coef.index
        if has_alpha:
            alpha_coef = res.coef["const"]
            alpha_t    = res.t_stats["const"]
            alpha_p    = res.p_values["const"]
            alpha_sig  = bool(alpha_p < 0.05 and alpha_coef > 0)
            alpha_cell = _coef_cell(alpha_coef, alpha_t, alpha_p)
        else:
            alpha_sig  = False
            alpha_cell = "<td>--</td>"

        low = y_name.lower()
        is_portfolio = low in ("portfolio",) or low.startswith("group_")
        if is_portfolio:
            row_class = "reg-row-portfolio"
        elif alpha_sig:
            row_class = "reg-row-sig"
        else:
            row_class = ""

        factor_cells = ""
        for fn in all_factors:
            if fn in res.coef.index:
                factor_cells += _coef_cell(res.coef[fn], res.t_stats[fn], res.p_values[fn])
            else:
                factor_cells += "<td>--</td>"

        rows_html += (
            f'<tr class="{row_class}">'
            f'<td class="col-name">{y_name}</td>'
            + alpha_cell
            + factor_cells +
            f'<td>{res.n_obs}</td>'
            '</tr>'
        )

    table_html = (
        '<div style="overflow-x:auto">'
        f'<table class="reg-table"><thead>{header_row}</thead><tbody>{rows_html}</tbody></table>'
        '</div>'
        '<div style="font-size:10px;color:#999;margin-top:4px">'
        'Coef &nbsp;|&nbsp; (t-stat) &nbsp;|&nbsp; [p-value] &nbsp;·&nbsp; '
        '<span style="color:#00b050">&#9632;</span> significant positive alpha (p&lt;0.05)&nbsp;'
        '<span style="color:#660874">&#9632;</span> portfolio/group row'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


# -- Output rendering -------------------------------------------------------------

def _output_to_html(out) -> str:
    import html as _h
    def _br(text: str) -> str:
        return _h.escape(text).replace("\n", "<br>")

    cmd_echo = f'<div class="lr-cmd-echo">. {_h.escape(out.cmd)}</div>'
    if out.kind == "error":
        body = f'<div class="lr-cmd-error-body">r(199): {_h.escape(out.content)}</div>'
    else:
        body = f'<div class="lr-cmd-body">{_br(out.content)}</div>'
    return f'<div style="margin-bottom:6px">{cmd_echo}{body}</div>'


def render_factor_decomp_panel(
    single_result: Optional[BacktestResult],
    group_results: dict,
    config: Config,
    mode: str = "single",
) -> None:
    """
    Factor Decomposition Results panel — embeddable in the Performance tab.

    Reads the regression table from the shared ``_REG_TABLE_KEY`` session key
    (auto-populated by the Analytics Workbench → Linear Regression tab).
    If the workspace has not been loaded yet, offers a one-click bootstrap
    that loads FF factors, runs all constituent regressions, and populates
    the table without requiring the user to visit the Workbench first.
    """
    _inject_css("quant_console")
    _inject_css("factor_workspace_tab")

    ws: ReturnWorkspace = st.session_state.get(_WS_KEY, ReturnWorkspace())

    # ── Bootstrap: workspace not yet loaded ──────────────────────────────
    if ws.is_empty():
        st.info(
            "Factor regression not run yet. "
            "Click below to load the workspace and run FF5 factor regressions."
        )
        _current_fp = _compute_ws_fingerprint(mode, single_result, group_results)
        col_btn, col_hint = st.columns([3, 7])
        with col_btn:
            do_load = st.button(
                "⚡ Load & Run All",
                key="perf_decomp_bootstrap",
                type="primary",
                use_container_width=True,
            )
        with col_hint:
            st.caption(
                "Runs FF5 (Mkt-RF, SMB, HML, RMW, CMA) regression "
                "for each portfolio and ticker series."
            )
        if do_load:
            with st.spinner("Loading workspace and running factor regressions…"):
                _ws = ReturnWorkspace()
                load_into_workspace(_ws, config,
                                    single_result=single_result,
                                    group_results=group_results or {})
                _supplement_ticker_returns(_ws, single_result, group_results or {}, config)
                st.session_state[_WS_KEY]            = _ws
                st.session_state[_WS_FINGERPRINT_KEY] = _current_fp
                _grp_display = list((group_results or {}).keys())
                _grp_safe    = [_safe_vname(k) for k in _grp_display]
                st.session_state[_GROUP_DISP_KEY] = _grp_display
                st.session_state[_GROUP_SAFE_KEY] = _grp_safe
                _avail_ff5 = [c for c in ["mktrf", "smb", "hml", "rmw", "cma"]
                              if c in _ws.ls()]
                _auto_tbl: dict = {}
                for _yn in [c for c in _ws.ls() if c not in _FF_VARS]:
                    if _avail_ff5:
                        _out = execute(
                            f"reg {_yn} {' '.join(_avail_ff5)}, robust", _ws
                        )
                        if _out.kind == "text" and "result" in _out.metadata:
                            _auto_tbl[_yn] = _out.metadata["result"]
                st.session_state[_REG_TABLE_KEY] = _auto_tbl
            st.toast("Factor decomposition complete", icon="✅")
            st.rerun()
        return

    # ── Run All Constituents ──────────────────────────────────────────────
    _all_vars  = ws.ls()
    _non_ff    = [c for c in _all_vars if c not in _FF_VARS
                  and not any(c.startswith(p) for p in _RESID_PFX)]
    _x_default = [c for c in _all_vars if c in _FF_VARS and c != "rf"]

    if _non_ff and _x_default:
        _btn_col, _hint_col, _ = st.columns([2, 5, 3])
        with _btn_col:
            _run_all = st.button(
                "⚡ Run All Constituents",
                key="perf_run_all_constituents",
                use_container_width=True,
            )
        with _hint_col:
            st.caption(
                f'`reg <series> {" ".join(_x_default[:4])}, robust` '
                f'for {len(_non_ff)} series'
            )
        if _run_all:
            _ws_ref  = st.session_state.get(_WS_KEY, ws)
            _reg_tbl = st.session_state.get(_REG_TABLE_KEY, {})
            _outs    = st.session_state.get(_OUT_KEY, [])
            for _yn in _non_ff:
                _out = execute(f"reg {_yn} {' '.join(_x_default)}, robust", _ws_ref)
                _outs.append(_out)
                if _out.kind == "text" and "result" in _out.metadata:
                    _reg_tbl[_yn] = _out.metadata["result"]
            st.session_state[_REG_TABLE_KEY] = _reg_tbl
            st.session_state[_OUT_KEY]        = _outs
            st.session_state[_WS_KEY]         = _ws_ref
            st.rerun()

    # ── Decomposition table ───────────────────────────────────────────────
    reg_results: dict = st.session_state.get(_REG_TABLE_KEY, {})
    if reg_results:
        _h_col, _clr_col = st.columns([8, 2])
        with _h_col:
            st.markdown(
                '<div class="ws-section">Factor Decomposition Results</div>',
                unsafe_allow_html=True,
            )
        with _clr_col:
            if st.button("Clear", key="perf_reg_tbl_clear", use_container_width=True):
                st.session_state[_REG_TABLE_KEY] = {}
                st.rerun()

        grp_display = st.session_state.get(_GROUP_DISP_KEY, [])
        grp_safe    = st.session_state.get(_GROUP_SAFE_KEY, [])
        if grp_display:
            sel_idx = st.session_state.get(_SEL_GROUP_KEY, 0)
            sel_idx = min(sel_idx, len(grp_display) - 1)
            chosen = st.selectbox(
                "Group",
                grp_display,
                index=sel_idx,
                key="perf_factor_group_selectbox",
                label_visibility="collapsed",
            )
            new_idx = grp_display.index(chosen)
            if new_idx != sel_idx:
                st.session_state[_SEL_GROUP_KEY] = new_idx
            safe_pfx = grp_safe[new_idx]
            display_results = {
                k: v for k, v in reg_results.items()
                if k == safe_pfx or k.startswith(safe_pfx + "_")
            }
        else:
            display_results = reg_results

        _render_decomposition_table(display_results)
    else:
        st.info(
            "No regression results yet. "
            "Click '⚡ Run All Constituents' above, or run regressions in "
            "Analytics Workbench → Linear Regression."
        )


def _isnan(v) -> bool:
    import math
    try:
        return math.isnan(v)
    except Exception:
        return False
