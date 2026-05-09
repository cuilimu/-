"""
analytics/arimax/model.py

pmdarima auto_arima fitting with optional log/box-cox endogenous transforms
and rolling 1-step forecast over the test set. Refactored from the engine's
run_one_combo_new — all dependencies now passed explicitly (no globals).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np
import pandas as pd

from stock_engine.analytics.arimax.metrics import (
    mae, mape, mase, rmse, smape,
)

if TYPE_CHECKING:
    from stock_engine.analytics.arimax.pipeline import AutoARIMAParams


def run_one_combo(
    combo_cols: list[str],
    y_train: np.ndarray,
    y_test: np.ndarray,
    train_data: pd.DataFrame,
    test_data: pd.DataFrame,
    transform: str = "original",
    trace: bool = False,
    arima_params: "Optional[AutoARIMAParams]" = None,
    use_tqdm: bool = False,
    on_step: "Optional[Callable[[int, int], None]]" = None,
) -> tuple[dict, dict]:
    """
    Fit an auto-ARIMA(X) model and rolling-forecast across the test set
    one observation at a time, calling model.update after each step.

    Returns (metrics_row, predictions_dict).
    """
    # pmdarima is heavy and optional at install time; import lazily so the
    # rest of the package can be loaded without it.
    import pmdarima as pm
    from pmdarima.pipeline import Pipeline
    from pmdarima.preprocessing import BoxCoxEndogTransformer, LogEndogTransformer

    if len(combo_cols) == 0:
        X_train = None
        X_test: Optional[pd.DataFrame] = None
    else:
        X_train = train_data[combo_cols].reset_index(drop=True)
        X_test = test_data[combo_cols].reset_index(drop=True)

    # Build the pm.auto_arima keyword arguments.
    # When arima_params is provided, forward every field; otherwise fall back
    # to the previous hard-coded defaults so existing callers are unaffected.
    if arima_params is not None:
        from stock_engine.analytics.arimax.pipeline import _build_auto_arima_kwargs
        _base_kw = _build_auto_arima_kwargs(arima_params, trace=trace, force_nonseasonal=False)
        _nonseas_kw = _build_auto_arima_kwargs(arima_params, trace=trace, force_nonseasonal=True)
    else:
        _base_kw = dict(d=None, stepwise=True, suppress_warnings=True,
                        error_action="ignore", trace=trace)
        _nonseas_kw = dict(seasonal=False, d=None, stepwise=True,
                           suppress_warnings=True, error_action="ignore", trace=trace)

    if transform == "original":
        model: Any = pm.auto_arima(y_train, X=X_train, **_base_kw)
    elif transform == "log":
        auto = pm.auto_arima(y_train, X=X_train, **_nonseas_kw)
        model = Pipeline([
            ("log", LogEndogTransformer(lmbda=1e-6)),
            ("arima", auto),
        ])
        model.fit(y_train, X=X_train)
    elif transform == "boxcox":
        auto = pm.auto_arima(y_train, X=X_train, **_nonseas_kw)
        model = Pipeline([
            ("boxcox", BoxCoxEndogTransformer(lmbda=1e-6)),
            ("arima", auto),
        ])
        model.fit(y_train, X=X_train)
    else:
        raise ValueError(f"Unknown transform '{transform}' (expected 'original'/'log'/'boxcox')")

    forecasts: list[float] = []
    confs: list[list[float]] = []

    iterator: Any = range(len(y_test))
    if use_tqdm:
        try:
            from tqdm import tqdm
            iterator = tqdm(iterator, desc="Rolling update", unit="step",
                            position=1, leave=False)
        except ImportError:
            pass  # tqdm not installed — fall back to plain range silently

    for i in iterator:
        new_ob = y_test[i]
        X_ob = None if X_test is None else X_test.iloc[i:i + 1, :]

        if X_ob is None:
            fc, conf_int = model.predict(n_periods=1, return_conf_int=True)
        else:
            fc, conf_int = model.predict(n_periods=1, X=X_ob, return_conf_int=True)
        forecasts.append(float(np.asarray(fc).ravel()[0]))
        confs.append(np.asarray(conf_int).ravel().tolist())

        if X_ob is None:
            model.update([new_ob])
        else:
            model.update([new_ob], X=X_ob)

        if on_step is not None:
            on_step(i, len(y_test))

    arima_step = model.named_steps["arima"] if transform != "original" else model

    metrics = {
        "mse":   float(np.mean((np.asarray(y_test) - np.asarray(forecasts)) ** 2)),
        "mae":   mae(y_test, forecasts),
        "rmse":  rmse(y_test, forecasts),
        "mape":  mape(y_test, forecasts),
        "smape": smape(y_test, forecasts),
        "mase":  mase(y_test, forecasts, y_train),
    }

    row = {
        "X_combo": "(none)" if not combo_cols else " + ".join(combo_cols),
        "k_exog": len(combo_cols),
        "order": arima_step.order,
        "summary": arima_step.summary(),
        "model": arima_step,
        "pipeline": model,
        **metrics,
    }
    return row, {"forecasts": forecasts, "confs": confs}


def end_to_end_model_generations(
    all_combinations: list[list[str]],
    y_train: np.ndarray,
    y_test: np.ndarray,
    train_data: pd.DataFrame,
    test_data: pd.DataFrame,
    transform: str = "original",
    trace: bool = False,
    arima_params: "Optional[AutoARIMAParams]" = None,
    use_tqdm: bool = False,
    progress_callback: Optional[Callable[[int, int, list[str]], None]] = None,
    on_fit_complete: Optional[Callable[[int, int, dict], None]] = None,
    on_step: Optional[Callable[[int, int], None]] = None,
) -> pd.DataFrame:
    """
    Fit every combination.

    `progress_callback(idx, total, combo)` fires *before* each fit (used for a
    "currently fitting" indicator). `on_fit_complete(idx, total, row)` fires
    *after* each fit with the resulting metrics row — used for live AIC/BIC
    log streams in the UI.
    """
    # Sanity check on y_train BEFORE entering the loop — gives a clear,
    # actionable error instead of pmdarima's generic "no viable model" cry.
    y_arr = np.asarray(y_train, dtype=float).ravel()
    if y_arr.size < 8:
        raise ValueError(
            f"y_train has only {y_arr.size} observations — need ≥ 8 for "
            "auto_arima. Lower max_lag, raise train_threshold, or use a "
            "longer/finer-frequency input."
        )
    if not np.isfinite(y_arr).all():
        n_bad = int((~np.isfinite(y_arr)).sum())
        raise ValueError(
            f"y_train contains {n_bad} non-finite values (NaN/Inf). Check "
            "the target series and MEV transforms — log_diff on a series "
            "with non-positive values produces NaN."
        )
    if float(np.nanstd(y_arr)) < 1e-12:
        raise ValueError(
            "y_train has near-zero variance — series is effectively constant. "
            "auto_arima cannot fit. Check the target / kind selection."
        )

    rows: list[dict] = []
    preds: list[dict] = []
    failures: list[tuple[str, str]] = []  # (combo_str, error message)
    total = len(all_combinations)
    for idx, combo_cols in enumerate(all_combinations):
        if progress_callback is not None:
            progress_callback(idx, total, combo_cols)
        combo_str = "(none)" if not combo_cols else " + ".join(combo_cols)
        try:
            row, pred = run_one_combo(
                combo_cols=combo_cols,
                y_train=y_train,
                y_test=y_test,
                train_data=train_data,
                test_data=test_data,
                transform=transform,
                trace=trace,
                arima_params=arima_params,
                use_tqdm=use_tqdm,
                on_step=on_step,
            )
        except Exception as exc:
            # Per-combo isolation — one degenerate (var × lag) shouldn't kill
            # the entire sweep. Record the failure and continue.
            failures.append((combo_str, f"{type(exc).__name__}: {exc}"))
            if on_fit_complete is not None:
                # Synthetic placeholder row so the UI's live-progress bar
                # advances and the user sees which combo failed.
                on_fit_complete(idx, total, {
                    "X_combo": combo_str,
                    "k_exog": len(combo_cols),
                    "order": "FAILED",
                    "summary": f"Fit failed: {failures[-1][1]}",
                    "model": None,
                    "pipeline": None,
                    "mse": np.nan, "mae": np.nan, "rmse": np.nan,
                    "mape": np.nan, "smape": np.nan, "mase": np.nan,
                    "_fit_failed": True,
                    "_fit_error": failures[-1][1],
                })
            continue
        rows.append(row)
        preds.append(pred)
        if on_fit_complete is not None:
            on_fit_complete(idx, total, row)

    if not rows:
        # Every combo failed — surface the FIRST distinct error so the user
        # has something concrete to act on, plus the count so they know it's
        # systemic, not a single bad combo.
        first = failures[0][1] if failures else "(no diagnostic available)"
        raise ValueError(
            f"All {total} model combinations failed to fit. First error: "
            f"{first}. Common causes: y_train too short, target series too "
            "noisy / non-stationary, all MEVs degenerate after transform."
        )

    df = pd.concat([pd.DataFrame(rows), pd.DataFrame(preds)], axis=1)
    if failures:
        # Stash failure summary on the dataframe so the pipeline / UI can
        # surface it ('N of M combos failed') without having to rebuild it.
        df.attrs["fit_failures"] = failures
    return df
