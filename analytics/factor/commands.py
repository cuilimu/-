"""
analytics/factor/commands.py
STATA-style command parser and executor for ReturnWorkspace.

Supported commands:
  reg  y x1 x2 [x3...] [, robust | method(name) window(n)]
  corr x1 x2 [x3...]
  summ x1 [x2...]
  scatter x y
  rolling x y [, w(N)]
  gen  name = resid | name = fitted | name = <expr>
  drop name
  ls / desc
  help [command]
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union
import pandas as pd
import numpy as np

from stock_engine.analytics.factor.workspace import ReturnWorkspace
from stock_engine.analytics.factor.methods import METHOD_REGISTRY, MethodResult


# ── Result container ──────────────────────────────────────────────────────

@dataclass
class CommandOutput:
    cmd: str
    kind: str          # "text" | "figure" | "table" | "error"
    content: Any       # str | plotly.Figure | pd.DataFrame
    metadata: dict = field(default_factory=dict)


# ── Public entry point ────────────────────────────────────────────────────

def execute(raw: str, workspace: ReturnWorkspace) -> CommandOutput:
    """Parse and execute one command string. Never raises — errors returned as CommandOutput."""
    cmd = raw.strip()
    if not cmd:
        return CommandOutput(cmd=cmd, kind="text", content="")
    verb, rest, opts = _parse(cmd)

    try:
        if verb == "reg":
            return _cmd_reg(cmd, rest, opts, workspace)
        elif verb == "corr":
            return _cmd_corr(cmd, rest, workspace)
        elif verb == "summ":
            return _cmd_summ(cmd, rest, workspace)
        elif verb == "scatter":
            return _cmd_scatter(cmd, rest, opts, workspace)
        elif verb == "rolling":
            return _cmd_rolling(cmd, rest, opts, workspace)
        elif verb == "gen":
            return _cmd_gen(cmd, rest, workspace)
        elif verb == "drop":
            return _cmd_drop(cmd, rest, workspace)
        elif verb in ("ls", "desc", "dir"):
            return _cmd_ls(cmd, workspace)
        elif verb == "help":
            return _cmd_help(cmd, rest)
        else:
            return _err(cmd, f"Unknown command '{verb}'. Type  help  for usage.")
    except Exception as exc:
        return _err(cmd, f"Unexpected error: {exc}")


# ── Command implementations ───────────────────────────────────────────────

def _cmd_reg(cmd: str, rest: str, opts: dict, workspace: ReturnWorkspace) -> CommandOutput:
    tokens = rest.split()
    if len(tokens) < 2:
        return _err(cmd, "Usage: reg y x1 [x2 ...] [, robust | method(name)]")
    y_name = tokens[0]
    x_names = tokens[1:]
    missing = [v for v in [y_name] + x_names if v not in workspace]
    if missing:
        return _err(cmd, f"Variable(s) not in workspace: {', '.join(missing)}")

    method_name = opts.get("method", "robust" if "robust" in opts else "ols")
    if method_name not in METHOD_REGISTRY:
        return _err(cmd, f"Unknown method '{method_name}'. Available: {list(METHOD_REGISTRY)}")

    method = METHOD_REGISTRY[method_name]
    y = workspace[y_name].rename(y_name)
    X = pd.concat([workspace[n].rename(n) for n in x_names], axis=1)

    result: MethodResult = method.fit(y, X)
    if result.error:
        return _err(cmd, result.error)

    workspace.set_last_result(result.residuals, result.fitted, cmd)
    text = method.format_output(result, cmd)
    return CommandOutput(cmd=cmd, kind="text", content=text,
                         metadata={"result": result})


def _cmd_corr(cmd: str, rest: str, workspace: ReturnWorkspace) -> CommandOutput:
    names = rest.split()
    if len(names) < 2:
        return _err(cmd, "Usage: corr x1 x2 [x3 ...]")
    missing = [v for v in names if v not in workspace]
    if missing:
        return _err(cmd, f"Variable(s) not in workspace: {', '.join(missing)}")

    df = pd.concat([workspace[n].rename(n) for n in names], axis=1).dropna()
    mat = df.corr()

    # Format STATA-style
    lines = [f". {cmd}", f"(obs={len(df)})", ""]
    header = f"{'':>14}" + "".join(f"{n:>10}" for n in names)
    lines.append(header)
    lines.append("-" * (14 + 10 * len(names)))
    for i, row in enumerate(names):
        row_str = f"{row:>14}"
        for j, col in enumerate(names):
            if j > i:
                row_str += f"{'':>10}"
            else:
                row_str += f"{mat.loc[row, col]:>10.4f}"
        lines.append(row_str)

    return CommandOutput(cmd=cmd, kind="text", content="\n".join(lines),
                         metadata={"corr_matrix": mat, "n_obs": len(df)})


def _cmd_summ(cmd: str, rest: str, workspace: ReturnWorkspace) -> CommandOutput:
    names = rest.split() if rest.strip() else workspace.ls()
    missing = [v for v in names if v not in workspace]
    if missing:
        return _err(cmd, f"Variable(s) not in workspace: {', '.join(missing)}")

    rows = []
    for n in names:
        s = workspace[n].dropna()
        rows.append({
            "Variable": n,
            "N": len(s),
            "Mean": s.mean(),
            "Std Dev": s.std(),
            "Min": s.min(),
            "p25": s.quantile(0.25),
            "Median": s.median(),
            "p75": s.quantile(0.75),
            "Max": s.max(),
        })
    tbl = pd.DataFrame(rows).set_index("Variable")

    lines = [f". {cmd}", ""]
    w = 12
    header = f"{'Variable':>16}" + "".join(f"{c:>{w}}" for c in tbl.columns)
    lines += [header, "-" * (16 + w * len(tbl.columns))]
    for vname, row in tbl.iterrows():
        line = f"{str(vname):>16}"
        for col, val in row.items():
            if col == "N":
                line += f"{int(val):>{w}}"
            else:
                line += f"{val:>{w}.4f}"
        lines.append(line)

    return CommandOutput(cmd=cmd, kind="text", content="\n".join(lines),
                         metadata={"table": tbl})


def _cmd_scatter(cmd: str, rest: str, opts: dict, workspace: ReturnWorkspace) -> CommandOutput:
    try:
        import plotly.graph_objects as go
        from scipy import stats as sp_stats
    except ImportError:
        return _err(cmd, "plotly / scipy required for scatter")
    tokens = rest.split()
    if len(tokens) < 2:
        return _err(cmd, "Usage: scatter x y")
    xn, yn = tokens[0], tokens[1]
    missing = [v for v in [xn, yn] if v not in workspace]
    if missing:
        return _err(cmd, f"Variable(s) not in workspace: {', '.join(missing)}")
    df = pd.concat([workspace[xn].rename(xn), workspace[yn].rename(yn)], axis=1).dropna()
    slope, intercept, r, p, _ = sp_stats.linregress(df[xn], df[yn])
    x_line = pd.Series([df[xn].min(), df[xn].max()])
    y_line = intercept + slope * x_line
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[xn], y=df[yn], mode="markers",
                              marker=dict(color="#660874", opacity=0.7, size=7),
                              name="Monthly returns",
                              text=df.index.strftime("%Y-%m"), hovertemplate="%{text}<br>x=%{x:.4f} y=%{y:.4f}"))
    fig.add_trace(go.Scatter(x=x_line, y=y_line, mode="lines",
                              line=dict(color="#e03030", dash="dash", width=1.5),
                              name=f"OLS fit  β={slope:.3f}  R²={r**2:.3f}"))
    fig.update_layout(title=f"scatter  {xn}  {yn}   ρ={r:.4f}  p={p:.3f}",
                      xaxis_title=xn, yaxis_title=yn,
                      paper_bgcolor="#fff", plot_bgcolor="#fff",
                      height=420, margin=dict(l=60, r=20, t=50, b=50))
    return CommandOutput(cmd=cmd, kind="figure", content=fig,
                         metadata={"r": r, "p": p, "slope": slope})


def _cmd_rolling(cmd: str, rest: str, opts: dict, workspace: ReturnWorkspace) -> CommandOutput:
    try:
        import plotly.graph_objects as go
    except ImportError:
        return _err(cmd, "plotly required for rolling")
    tokens = rest.split()
    if len(tokens) < 2:
        return _err(cmd, "Usage: rolling x y [, w(N)]")
    xn, yn = tokens[0], tokens[1]
    missing = [v for v in [xn, yn] if v not in workspace]
    if missing:
        return _err(cmd, f"Variable(s) not in workspace: {', '.join(missing)}")
    w = int(opts.get("w", opts.get("window", 12)))
    df = pd.concat([workspace[xn].rename(xn), workspace[yn].rename(yn)], axis=1).dropna()
    roll_corr = df[xn].rolling(w).corr(df[yn]).dropna()
    fig = go.Figure()
    fig.add_hline(y=0, line_dash="dot", line_color="#cccccc")
    fig.add_trace(go.Scatter(x=roll_corr.index, y=roll_corr.values,
                              mode="lines", line=dict(color="#660874", width=2),
                              name=f"{w}M rolling corr"))
    fig.update_layout(title=f"rolling  {xn}  {yn}  window={w}M",
                      xaxis_title="Date", yaxis_title="Correlation",
                      paper_bgcolor="#fff", plot_bgcolor="#fff",
                      height=360, margin=dict(l=60, r=20, t=50, b=40))
    return CommandOutput(cmd=cmd, kind="figure", content=fig)


def _cmd_gen(cmd: str, rest: str, workspace: ReturnWorkspace) -> CommandOutput:
    # Syntax: gen name = resid | gen name = fitted | gen name = expr
    m = re.match(r"(\w+)\s*=\s*(.+)", rest.strip())
    if not m:
        return _err(cmd, "Usage: gen <name> = resid | fitted | <expression>")
    new_name, expr = m.group(1).strip(), m.group(2).strip()

    if expr == "resid":
        s = workspace.get_last_residuals()
        if s is None:
            return _err(cmd, "No regression run yet — run  reg  first")
        workspace.add(new_name, s.rename(new_name))
    elif expr == "fitted":
        s = workspace.get_last_fitted()
        if s is None:
            return _err(cmd, "No regression run yet — run  reg  first")
        workspace.add(new_name, s.rename(new_name))
    else:
        # Safe expression eval over workspace columns
        ns = {col: workspace[col] for col in workspace.ls()}
        try:
            result_s = eval(expr, {"__builtins__": {}, "abs": abs, "log": __import__("math").log}, ns)  # noqa: S307
            if not isinstance(result_s, pd.Series):
                return _err(cmd, f"Expression must evaluate to a pd.Series, got {type(result_s)}")
            workspace.add(new_name, result_s.rename(new_name))
        except Exception as exc:
            return _err(cmd, f"Expression error: {exc}")

    return CommandOutput(cmd=cmd, kind="text",
                         content=f"({new_name} added to workspace, {workspace[new_name].count()} obs)")


def _cmd_drop(cmd: str, rest: str, workspace: ReturnWorkspace) -> CommandOutput:
    name = rest.strip()
    if workspace.drop(name):
        return CommandOutput(cmd=cmd, kind="text", content=f"({name} dropped)")
    return _err(cmd, f"Variable '{name}' not found in workspace")


def _cmd_ls(cmd: str, workspace: ReturnWorkspace) -> CommandOutput:
    cols = workspace.ls()
    if not cols:
        return CommandOutput(cmd=cmd, kind="text", content="(workspace is empty)")
    df = workspace.describe()
    lines = [f". {cmd}", f"  {len(cols)} variables in workspace:", ""]
    lines.append(f"  {'Variable':>20}  {'N':>5}  {'Mean':>10}  {'Std':>10}  {'Min':>10}  {'Max':>10}")
    lines.append("  " + "-" * 70)
    for vname in cols:
        row = df.loc[vname] if vname in df.index else None
        if row is not None:
            lines.append(f"  {vname:>20}  {int(row['count']):>5}  {row['mean']:>10.4f}"
                         f"  {row['std']:>10.4f}  {row['min']:>10.4f}  {row['max']:>10.4f}")
        else:
            lines.append(f"  {vname:>20}")
    return CommandOutput(cmd=cmd, kind="text", content="\n".join(lines))


def _cmd_help(cmd: str, rest: str) -> CommandOutput:
    text = """\
Available commands
──────────────────────────────────────────────────────────────────────
reg  y x1 x2 [...]             OLS regression (standard SE)
reg  y x1 x2 [...], robust     OLS with HC3 robust SE
reg  y x1 x2 [...], method(X)  Use method X (ols | robust | ridge*)
corr x1 x2 [...]               Pearson correlation matrix
summ [x1 x2 ...]               Descriptive statistics (all vars if blank)
scatter x y                    Scatter plot with OLS fit line
rolling x y [, w(N)]           Rolling N-month correlation (default 12)
gen  name = resid              Save last regression residuals to workspace
gen  name = fitted             Save last regression fitted values
gen  name = x1 - x2           Arithmetic derived variable
drop name                      Remove variable from workspace
ls / desc                      List all variables with summary stats
help [command]                 This help text

*future methods: ridge, lasso, rf, gbm
──────────────────────────────────────────────────────────────────────
Variables auto-loaded:  portfolio, group_*, <tickers>, mktrf, smb,
                        hml, rmw, cma, umd, rf"""
    return CommandOutput(cmd=cmd, kind="text", content=text)


# ── Parser ────────────────────────────────────────────────────────────────

def _parse(cmd: str) -> tuple[str, str, dict]:
    """Split  verb rest [, options]  →  (verb, rest, opts_dict)."""
    if "," in cmd:
        body, opts_str = cmd.split(",", 1)
    else:
        body, opts_str = cmd, ""
    tokens = body.strip().split(None, 1)
    verb = tokens[0].lower()
    rest = tokens[1].strip() if len(tokens) > 1 else ""
    opts = _parse_opts(opts_str)
    return verb, rest, opts


def _parse_opts(opts_str: str) -> dict:
    """Parse  robust method(ols) w(12)  →  {"robust": True, "method": "ols", "w": "12"}."""
    opts: dict = {}
    for token in opts_str.split():
        m = re.match(r"(\w+)\((.+?)\)", token)
        if m:
            opts[m.group(1).lower()] = m.group(2)
        else:
            opts[token.lower()] = True
    return opts


def _err(cmd: str, msg: str) -> CommandOutput:
    return CommandOutput(cmd=cmd, kind="error", content=msg)
