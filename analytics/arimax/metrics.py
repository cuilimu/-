"""
analytics/arimax/metrics.py
Forecast accuracy metrics — ported from the ARIMAX Engine notebook.

mase() is reimplemented to be self-contained (no external m argument needed for
the engine's quarterly/monthly use-case): scaled by the in-sample naive lag-1
forecast error, matching the notebook's definition.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def mae(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(y_true, y_pred, eps: float = 1e-8) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + eps))))


def smape(y_true, y_pred, eps: float = 1e-8) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.abs(y_true) + np.abs(y_pred) + eps
    return float(np.mean(2.0 * np.abs(y_pred - y_true) / denom))


def mase(y_true, y_pred, y_train) -> float:
    """
    MASE scaled by the in-sample naive one-step forecast (y_t = y_{t-1}).
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    y_train = np.asarray(y_train, dtype=float)

    naive_errors = np.abs(y_train[1:] - y_train[:-1])
    scale = float(np.mean(naive_errors))
    if scale == 0.0:
        return float("nan")
    return float(np.mean(np.abs(y_true - y_pred)) / scale)


def evaluate_pmdarima(
    model,
    y_train,
    y_test,
    unique_id: int = 1,
    model_name: str = "AutoARIMA",
    exogenous_test: Optional[pd.DataFrame] = None,
):
    """
    Bulk-forecast (n_periods=len(y_test)) evaluation. Returns (long_df, wide_df, y_pred).
    """
    n_test = len(y_test)
    if exogenous_test is None:
        y_pred = model.predict(n_periods=n_test)
    else:
        y_pred = model.predict(n_periods=n_test, exogenous=exogenous_test)

    out = {
        "mae":   mae(y_test, y_pred),
        "mape":  mape(y_test, y_pred),
        "mase":  mase(y_test, y_pred, y_train=y_train),
        "rmse":  rmse(y_test, y_pred),
        "smape": smape(y_test, y_pred),
    }

    df_long = pd.DataFrame({
        "unique_id": unique_id,
        "metric": list(out.keys()),
        model_name: list(out.values()),
    })
    df_wide = pd.DataFrame([{"unique_id": unique_id, "model": model_name, **out}])
    return df_long, df_wide, y_pred
