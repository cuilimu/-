"""
analytics/arimax/rules.py

Hard rules: sign / p-value / AR–MA root stationarity / coefficient magnitude / VIF.
Soft rules: weighted-normalised composite over forecast metrics, or single-metric ranking.

Ported from the engine. Removed the `model_results.json` round-trip (engine
wrote then re-read; we just keep the dicts in memory).
"""
from __future__ import annotations

from typing import Any, Iterable, Literal, Optional

import numpy as np
import pandas as pd

from stock_engine.analytics.arimax.preprocess import parse_x_combo


def hard_rule_reject_sarimax(
    res: Any,
    x_combo_lst: list[str],
    expected_sign: Optional[dict[str, str]] = None,
    alpha: float = 0.05,
    enforce_sig_for: Optional[set[str]] = None,
    require_stationary: bool = True,
    require_invertible: bool = True,
    max_abs_ar: Optional[float] = None,
    max_abs_ma: Optional[float] = None,
    X_for_vif: Optional[pd.DataFrame] = None,
    vif_max: Optional[float] = None,
) -> dict:
    """Apply hard rules to one fitted pmdarima ARIMA / SARIMAX-result and report verdict."""
    reasons: list[str] = []
    diag: dict[str, Any] = {}

    param_names = res.arima_res_.param_names
    exog_names = [n for n in param_names if n.startswith("x")]
    mapping = {x_name: x_combo_lst[i] for i, x_name in enumerate(exog_names)}
    new_param_names = [mapping.get(n, n) for n in param_names]

    params = pd.Series(res.params().copy(), index=new_param_names)
    pvals = pd.Series(res.pvalues().copy(), index=new_param_names)

    diag["exog_names_detected"] = list(x_combo_lst)

    expected_sign = expected_sign or {}
    if enforce_sig_for is None:
        enforce_sig_for = {k for k, v in expected_sign.items() if v != "undetermined"}

    # Sign rules
    for name, exp in expected_sign.items():
        if name not in params.index:
            continue
        beta = float(params[name])
        if exp == "+" and beta <= 0:
            reasons.append(f"SIGN: {name} expected '+', got {beta:.6g}")
        elif exp == "-" and beta >= 0:
            reasons.append(f"SIGN: {name} expected '-', got {beta:.6g}")
        elif exp == "!=0" and np.isclose(beta, 0.0, atol=1e-12):
            reasons.append(f"SIGN: {name} expected !=0, got {beta:.6g}")

    # p-value rules
    for name in enforce_sig_for:
        if name in pvals.index:
            pv = float(pvals[name])
            if not np.isfinite(pv) or pv > alpha:
                reasons.append(f"PVALUE: {name} p={pv:.4g} > {alpha}")

    # AR / MA root stationarity & invertibility
    try:
        if require_stationary:
            ar_roots = np.asarray(res.arroots())
            diag["min_abs_ar_root"] = (
                float(np.min(np.abs(ar_roots))) if ar_roots.size else None
            )
            if ar_roots.size and np.any(np.abs(ar_roots) <= 1.0):
                reasons.append(
                    f"STATIONARITY: AR root inside unit circle "
                    f"(min |root|={diag['min_abs_ar_root']:.4g})"
                )
        if require_invertible:
            ma_roots = np.asarray(res.maroots())
            diag["min_abs_ma_root"] = (
                float(np.min(np.abs(ma_roots))) if ma_roots.size else None
            )
            if ma_roots.size and np.any(np.abs(ma_roots) <= 1.0):
                reasons.append(
                    f"INVERTIBILITY: MA root inside unit circle "
                    f"(min |root|={diag['min_abs_ma_root']:.4g})"
                )
    except Exception as e:
        reasons.append(f"ROOT_CHECK_FAILED: {type(e).__name__}: {e}")

    # Coefficient magnitude bounds
    if max_abs_ar is not None:
        ar_names = [n for n in params.index if n.startswith("ar.L")]
        if ar_names:
            max_ar = float(np.max(np.abs(params[ar_names])))
            diag["max_abs_ar_coef"] = max_ar
            if max_ar > max_abs_ar:
                reasons.append(f"AR_MAG: max |AR|={max_ar:.4g} > {max_abs_ar}")
    if max_abs_ma is not None:
        ma_names = [n for n in params.index if n.startswith("ma.L")]
        if ma_names:
            max_ma = float(np.max(np.abs(params[ma_names])))
            diag["max_abs_ma_coef"] = max_ma
            if max_ma > max_abs_ma:
                reasons.append(f"MA_MAG: max |MA|={max_ma:.4g} > {max_abs_ma}")

    # VIF
    if X_for_vif is not None and vif_max is not None:
        from statsmodels.stats.outliers_influence import variance_inflation_factor

        X = X_for_vif.copy()
        const_cols = [c for c in X.columns if X[c].nunique(dropna=True) == 1]
        if const_cols:
            X = X.drop(columns=const_cols)
        X = X.dropna()
        if X.shape[1] >= 2 and X.shape[0] >= 5:
            X_np = X.to_numpy(dtype=float)
            vifs = [(col, float(variance_inflation_factor(X_np, i))) for i, col in enumerate(X.columns)]
            vif_df = pd.DataFrame(vifs, columns=["feature", "vif"]).sort_values("vif", ascending=False)
            max_vif_val = float(vif_df["vif"].max())
            diag["vif_top_max"] = (
                f"Top VIFs:\n{vif_df.head(10).to_string(index=False)}\nMax VIF: {max_vif_val:.4g}"
            )
            if max_vif_val > vif_max:
                reasons.append(f"VIF: max VIF={max_vif_val:.4g} > {vif_max}")
        else:
            diag["vif_top_max"] = (
                "VIF_CHECK_SKIPPED: insufficient rows/cols after NA/constant handling"
            )

    return {
        "pass_hard_rules": len(reasons) == 0,
        "reject_reasons": reasons,
        "diagnostics": diag,
    }


def hard_rules_filtering(
    results_df: pd.DataFrame,
    train_data: pd.DataFrame,
    expected_sign: Optional[dict[str, str]] = None,
    alpha: float = 0.05,
    require_stationary: bool = True,
    require_invertible: bool = True,
    max_abs_ar: Optional[float] = None,
    max_abs_ma: Optional[float] = None,
    vif_max: Optional[float] = None,
    enforce_sig_for: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """
    Apply hard rules row-wise. Adds `pass_hard_rules`, `reject_reasons`,
    `diagnostics` columns to a copy of `results_df`. Returns only rows
    that pass all hard rules. The full annotated frame is exposed via
    the returned frame's `.attrs['annotated']` (so callers can inspect rejects).
    """
    annotated = results_df.copy().reset_index(drop=True)
    verdicts = []
    enforce_set_user = set(enforce_sig_for) if enforce_sig_for else None
    for i in range(len(annotated)):
        res = annotated.loc[i, "model"]
        x_combo_lst = parse_x_combo(annotated.loc[i, "X_combo"])
        X_for_vif = train_data.loc[:, x_combo_lst] if x_combo_lst else None
        # If the caller passed an explicit enforce_sig_for, intersect it with the
        # MEVs actually present in this combo (others have no coefficient to test).
        # Otherwise default to enforcing significance for every MEV in the combo.
        enforce_for_combo = (
            enforce_set_user.intersection(x_combo_lst)
            if enforce_set_user is not None
            else set(x_combo_lst)
        )
        verdict = hard_rule_reject_sarimax(
            res=res,
            x_combo_lst=x_combo_lst,
            expected_sign=expected_sign,
            alpha=alpha,
            enforce_sig_for=enforce_for_combo,
            require_stationary=require_stationary,
            require_invertible=require_invertible,
            max_abs_ar=max_abs_ar,
            max_abs_ma=max_abs_ma,
            X_for_vif=X_for_vif,
            vif_max=vif_max,
        )
        verdicts.append(verdict)

    verdict_df = pd.DataFrame(verdicts)
    annotated["pass_hard_rules"] = verdict_df["pass_hard_rules"].values
    annotated["reject_reasons"] = verdict_df["reject_reasons"].values
    annotated["diagnostics"] = verdict_df["diagnostics"].values

    survivors = annotated[annotated["pass_hard_rules"]].reset_index(drop=True)
    survivors.attrs["annotated"] = annotated
    return survivors


SoftMethod = Literal["weighted", "mse", "mae", "rmse", "mape", "smape", "mase"]
_TOP_COLS = [
    "X_combo", "k_exog", "order", "summary", "model", "pipeline",
    "soft_score", "forecasts", "confs",
]


def soft_rules(
    df: pd.DataFrame,
    method: SoftMethod = "weighted",
    weights: Optional[dict[str, float]] = None,
    top_n: int = 3,
) -> pd.DataFrame:
    """Rank candidates either by a weighted normalised composite or by a single metric."""
    if df.empty:
        return df.copy()

    if method == "weighted":
        metrics = ["mse", "mae", "rmse", "mape", "smape", "mase"]
        if weights is None:
            n = len(metrics)
            weights = {m: 1.0 / n for m in metrics}

        df_rank = df.copy()
        for metric in weights:
            min_val = df_rank[metric].min()
            max_val = df_rank[metric].max()
            denom = (max_val - min_val) if (max_val - min_val) != 0 else 1.0
            # smaller is better → invert
            df_rank[f"{metric}_norm"] = (max_val - df_rank[metric]) / denom

        df_rank["soft_score"] = sum(
            df_rank[f"{m}_norm"] * w for m, w in weights.items()
        )
        ranked = df_rank.sort_values("soft_score", ascending=False).head(top_n)
        return ranked[_TOP_COLS].reset_index(drop=True)

    df_rank = df.copy().sort_values([method]).head(top_n).reset_index(drop=True)
    df_rank["soft_score"] = df_rank[method]
    return df_rank[_TOP_COLS].reset_index(drop=True)
