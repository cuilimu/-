"""
analytics/arimax/preprocess.py

Resample, MEV growth-rate transforms (log_diff / diff), lag generation,
exogenous combination enumeration, and chronological train/test split.

Ported from the ARIMAX Engine notebook (Data_Preprocess, Exgogenous_Combinations,
train_test_split). Function signatures preserved; module-level state removed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, product
from typing import Optional

import numpy as np
import pandas as pd


def data_preprocess(
    raw: pd.DataFrame,
    target: str,
    mevs: list[str],
    mevs_guide: dict[str, str],
    ds_column: str,
    max_lag: int,
    max_number_of_exogenous_variables: int = 2,
    freq: str = "QE",
    include_non_lags: bool = False,
) -> pd.DataFrame:
    """
    Resample `raw` to `freq`, transform MEVs per `mevs_guide`
    ('log_diff' or 'diff'), build lagged exog matrix, return wide df
    with `[lagged exogs..., target]` and `ds_column` as a regular column.

    `raw` MUST be DatetimeIndexed.
    """
    q = raw.resample(freq).last()
    f = str(freq).upper()
    if f.startswith("Q"):
        q.index = q.index.to_period("Q").to_timestamp("Q")
    elif f.startswith("M"):
        q.index = q.index.to_period("M").to_timestamp("M")
    elif f.startswith("W"):
        q.index = q.index.to_period("W").to_timestamp("W")
    # Defensive: `to_period().to_timestamp()` usually preserves index.name
    # but some pandas versions / edge inputs reset it. We need the index
    # named `ds_column` because the merge below relies on `.reset_index()`
    # turning the index into a column with that name.
    q.index.name = ds_column

    df = q.dropna()
    y = df[target].astype(float)
    X = df[mevs].astype(float)

    X_growth = X.copy()
    for mev, guide in mevs_guide.items():
        if mev not in X.columns:
            continue
        if guide == "log_diff":
            X_growth[mev] = np.log(X[mev]) - np.log(X[mev].shift())
        elif guide == "diff":
            X_growth[mev] = X[mev].diff(1)
    X_growth = X_growth.dropna()

    X_lagged = X_growth.copy()
    for col in X_growth.columns:
        for lag in range(1, max_lag + 1):
            X_lagged[f"{col}_lag{lag}"] = X_growth[col].shift(lag)
    X_lagged = X_lagged.dropna()

    X_only_lags = X_lagged.loc[:, X_lagged.columns.str.contains(r"_lag\d+$")].copy()

    base_panel = X_lagged if include_non_lags else X_only_lags

    # Match the original ARIMAX notebook (Data_Preprocess) 1:1 — plain
    # `.reset_index()` with no kwargs. The index is named `ds_column` (set
    # defensively above), so reset_index lifts it into a column with the
    # right name. Earlier ports of this used `reset_index(names=ds_column)`
    # which broke under pandas 3.0+ in some edge cases (Series rather than
    # DataFrame at the call site). The original is simpler and works.
    out = pd.merge(
        base_panel.reset_index(),
        y.reset_index(),
        left_on=ds_column,
        right_on=ds_column,
        how="left",
    )
    return out


def exogenous_combinations(
    df: pd.DataFrame,
    target: str,
    ds_column: str,
    max_number_of_exogenous_variables: int = 2,
) -> list[list[str]]:
    """
    Group columns by base variable (everything before _lagN), then enumerate
    every combination of size 0..k with at most one lag-version per base.
    """
    X_df = df.drop(columns=[target, ds_column], errors="ignore")
    groups: dict[str, list[str]] = defaultdict(list)
    for col in X_df.columns:
        base = col.split("_lag")[0]
        groups[base].append(col)

    all_combos: list[list[str]] = [[]]
    base_vars = list(groups.keys())
    for k in range(1, max_number_of_exogenous_variables + 1):
        for bases in combinations(base_vars, k):
            for versions in product(*(groups[b] for b in bases)):
                all_combos.append(list(versions))
    return all_combos


@dataclass
class TrainTestSplit:
    train_data: pd.DataFrame
    test_data: pd.DataFrame
    y_train: np.ndarray
    y_test: np.ndarray
    y_test_oot: np.ndarray  # empty array when oot_test=False


def train_test_split(
    df: pd.DataFrame,
    target: str,
    train_threshold: float = 0.8,
    oot_test: bool = False,
    oot_threshold: float = 0.9,
) -> TrainTestSplit:
    """Chronological split. `oot_test=True` carves a 3rd block for out-of-time evaluation."""
    n = df.shape[0]
    train_len = int(n * train_threshold)

    if oot_test:
        oot_len = int(n * oot_threshold)
        train_data = df.iloc[:train_len]
        test_data = df.iloc[train_len:oot_len]
        oot_data = df.iloc[oot_len:]
        return TrainTestSplit(
            train_data=train_data,
            test_data=test_data,
            y_train=train_data[target].to_numpy(),
            y_test=test_data[target].to_numpy(),
            y_test_oot=oot_data[target].to_numpy(),
        )

    train_data = df.iloc[:train_len]
    test_data = df.iloc[train_len:]
    return TrainTestSplit(
        train_data=train_data,
        test_data=test_data,
        y_train=train_data[target].to_numpy(),
        y_test=test_data[target].to_numpy(),
        y_test_oot=np.array([]),
    )


def parse_x_combo(x: str) -> list[str]:
    """Reverse of ' + '.join(combo); '(none)' → []."""
    if x == "(none)":
        return []
    return [v.strip() for v in x.split("+")]
