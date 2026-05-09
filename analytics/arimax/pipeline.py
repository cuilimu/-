"""
analytics/arimax/pipeline.py

ARIMAXConfig and ARIMAXPipeline. Orchestrates:
   preprocess → combinations → split → fit → hard rules → soft rules.

Refactored from the engine: dependencies are imported (not injected via
fields), and there is no globals()-monkey-patching of train/test frames.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

import numpy as np
import pandas as pd

from stock_engine.analytics.arimax.metrics import (
    mae, mape, mase, rmse, smape,
)
from stock_engine.analytics.arimax.model import end_to_end_model_generations, run_one_combo
from stock_engine.analytics.arimax.preprocess import (
    TrainTestSplit, data_preprocess, exogenous_combinations, train_test_split,
)
from stock_engine.analytics.arimax.rules import (
    SoftMethod, hard_rules_filtering, soft_rules,
)


@dataclass
class AutoARIMAParams:
    """Full parameter set forwarded verbatim to ``pmdarima.auto_arima``.

    Defaults are identical to pmdarima's own defaults so existing pipelines
    are unaffected when ``arima_params`` is left at its zero-config state.

    Groups
    ------
    Order bounds      — start_p / d / start_q / max_p / max_d / max_q
    Seasonal bounds   — start_P / D / start_Q / max_P / max_D / max_Q /
                        max_order / m / seasonal
    Stationarity      — stationary / information_criterion / alpha /
                        test / seasonal_test
    Search strategy   — stepwise / n_jobs / random / random_state / n_fits
    Fitting           — method / maxiter / with_intercept / trend
    Validation        — out_of_sample_size / scoring / scoring_args
    Behaviour         — suppress_warnings / error_action

    Note: ``trace`` is intentionally omitted here — it lives on
    ``ARIMAXConfig.trace`` so the pipeline can toggle it independently.

    Note: ``seasonal`` is always overridden to ``False`` for ``log`` and
    ``boxcox`` endogenous transforms; the field only takes effect for
    ``transform="original"``.
    """

    # ── Order search bounds ────────────────────────────────────────────────
    start_p: int = 2
    d: Optional[int] = None          # None → auto-detect via stationarity test
    start_q: int = 2
    max_p: int = 5
    max_d: int = 2
    max_q: int = 5

    # ── Seasonal order bounds ──────────────────────────────────────────────
    start_P: int = 1
    D: Optional[int] = None          # None → auto-detect via seasonal test
    start_Q: int = 1
    max_P: int = 2
    max_D: int = 1
    max_Q: int = 2
    max_order: Optional[int] = 5    # Max p+q+P+Q when not stepwise; None = unlimited
    m: int = 1                       # Seasonal period (1 = non-seasonal)
    seasonal: bool = True            # Forced False for log/boxcox transforms

    # ── Stationarity / information criterion ──────────────────────────────
    stationary: bool = False
    information_criterion: str = "aic"   # "aic" | "bic" | "hqic" | "oob"
    alpha: float = 0.05                  # Unit-root test significance level
    test: str = "kpss"                   # "kpss" | "adf" | "pp"
    seasonal_test: str = "ocsb"          # "ocsb" | "ch"

    # ── Search strategy ────────────────────────────────────────────────────
    stepwise: bool = True
    n_jobs: int = 1                      # Parallel workers (non-stepwise only)
    random: bool = False                 # Random hyper-param search
    random_state: Optional[int] = None  # PRNG seed for random search
    n_fits: int = 10                     # Models to try when random=True

    # ── Fitting ────────────────────────────────────────────────────────────
    method: str = "lbfgs"               # scipy optimiser: newton/nm/bfgs/lbfgs/…
    maxiter: int = 50                    # Max optimiser iterations
    with_intercept: Any = "auto"        # bool | "auto"
    trend: Optional[str] = None         # Trend term ("n"/"c"/"t"/"ct")

    # ── Out-of-sample validation ───────────────────────────────────────────
    out_of_sample_size: int = 0         # Tail obs held out for scoring metric
    scoring: str = "mse"                # "mse" | "mae"
    scoring_args: Optional[dict] = None

    # ── Behaviour ─────────────────────────────────────────────────────────
    suppress_warnings: bool = True
    error_action: str = "ignore"        # "warn" | "raise" | "ignore" | "trace"


def _build_auto_arima_kwargs(
    params: AutoARIMAParams,
    trace: bool,
    force_nonseasonal: bool = False,
) -> dict:
    """Translate ``AutoARIMAParams`` + ``trace`` into a flat kwargs dict."""
    kw: dict = {
        "start_p":               params.start_p,
        "d":                     params.d,
        "start_q":               params.start_q,
        "max_p":                 params.max_p,
        "max_d":                 params.max_d,
        "max_q":                 params.max_q,
        "start_P":               params.start_P,
        "D":                     params.D,
        "start_Q":               params.start_Q,
        "max_P":                 params.max_P,
        "max_D":                 params.max_D,
        "max_Q":                 params.max_Q,
        "max_order":             params.max_order,
        "m":                     params.m,
        "seasonal":              False if force_nonseasonal else params.seasonal,
        "stationary":            params.stationary,
        "information_criterion": params.information_criterion,
        "alpha":                 params.alpha,
        "test":                  params.test,
        "seasonal_test":         params.seasonal_test,
        "stepwise":              params.stepwise,
        "n_jobs":                params.n_jobs,
        "random":                params.random,
        "random_state":          params.random_state,
        "n_fits":                params.n_fits,
        "method":                params.method,
        "maxiter":               params.maxiter,
        "with_intercept":        params.with_intercept,
        "trend":                 params.trend,
        "out_of_sample_size":    params.out_of_sample_size,
        "scoring":               params.scoring,
        "suppress_warnings":     params.suppress_warnings,
        "error_action":          params.error_action,
        "trace":                 trace,
    }
    if params.scoring_args is not None:
        kw["scoring_args"] = params.scoring_args
    return kw


@dataclass
class ARIMAXConfig:
    target: str
    mevs: list[str]
    mevs_guide: dict[str, str]

    freq: str
    max_lag: int
    max_number_of_exogenous_variables: int = 2
    include_non_lags: bool = False

    train_threshold: float = 0.8
    oot_test: bool = False
    oot_threshold: float = 0.9

    transform: Literal["original", "log", "boxcox"] = "original"
    trace: bool = False

    # Full auto_arima parameter set — leave at default for identical behaviour
    # to the previous hard-coded configuration.
    arima_params: AutoARIMAParams = field(default_factory=AutoARIMAParams)


@dataclass
class ARIMAXPipeline:
    config: ARIMAXConfig

    raw: Optional[pd.DataFrame] = None
    df: Optional[pd.DataFrame] = None
    all_combinations: Optional[list[list[str]]] = None
    split: Optional[TrainTestSplit] = None
    results_df: Optional[pd.DataFrame] = None
    results_after_hard: Optional[pd.DataFrame] = None
    top_models: Optional[pd.DataFrame] = None

    def set_raw(self, raw: pd.DataFrame) -> "ARIMAXPipeline":
        self.raw = raw
        return self

    # -------------------------
    # Step 1) preprocess
    # -------------------------
    def preprocess(self, ds_column: str) -> pd.DataFrame:
        if self.raw is None:
            raise ValueError("raw is None. Call set_raw(raw) first.")
        self.df = data_preprocess(
            raw=self.raw,
            target=self.config.target,
            mevs=self.config.mevs,
            mevs_guide=self.config.mevs_guide,
            ds_column=ds_column,
            freq=self.config.freq,
            max_lag=self.config.max_lag,
            max_number_of_exogenous_variables=self.config.max_number_of_exogenous_variables,
            include_non_lags=self.config.include_non_lags,
        )
        return self.df

    # -------------------------
    # Step 2) combinations
    # -------------------------
    def build_combinations(self, ds_column: str) -> list[list[str]]:
        if self.df is None:
            raise ValueError("df is None. Run preprocess() first.")
        if ds_column not in self.df.columns:
            raise ValueError(
                f"ds_column='{ds_column}' not in df.columns. "
                f"Available: {list(self.df.columns)}"
            )
        self.all_combinations = exogenous_combinations(
            df=self.df,
            target=self.config.target,
            ds_column=ds_column,
            max_number_of_exogenous_variables=self.config.max_number_of_exogenous_variables,
        )
        return self.all_combinations

    # -------------------------
    # Step 3) split
    # -------------------------
    def split_data(self) -> TrainTestSplit:
        if self.df is None:
            raise ValueError("df is None. Run preprocess() first.")
        self.split = train_test_split(
            df=self.df,
            target=self.config.target,
            train_threshold=self.config.train_threshold,
            oot_test=self.config.oot_test,
            oot_threshold=self.config.oot_threshold,
        )
        return self.split

    # -------------------------
    # Step 4) run models
    # -------------------------
    def run_models(
        self,
        use_tqdm: bool = False,
        progress_callback: Optional[Callable[[int, int, list[str]], None]] = None,
        on_fit_complete: Optional[Callable[[int, int, dict], None]] = None,
        on_step: Optional[Callable[[int, int], None]] = None,
    ) -> pd.DataFrame:
        if self.all_combinations is None:
            raise ValueError("all_combinations is None. Run build_combinations() first.")
        if self.split is None:
            raise ValueError("Run split_data() before run_models().")

        self.results_df = end_to_end_model_generations(
            all_combinations=self.all_combinations,
            y_train=self.split.y_train,
            y_test=self.split.y_test,
            train_data=self.split.train_data,
            test_data=self.split.test_data,
            transform=self.config.transform,
            trace=self.config.trace,
            arima_params=self.config.arima_params,
            use_tqdm=use_tqdm,
            progress_callback=progress_callback,
            on_fit_complete=on_fit_complete,
            on_step=on_step,
        )
        return self.results_df

    def run_one(self, combo_cols: list[str], transform: Optional[str] = None,
                use_tqdm: bool = False):
        if self.split is None:
            raise ValueError("Run split_data() before run_one().")
        return run_one_combo(
            combo_cols=combo_cols,
            y_train=self.split.y_train,
            y_test=self.split.y_test,
            train_data=self.split.train_data,
            test_data=self.split.test_data,
            transform=transform or self.config.transform,
            trace=self.config.trace,
            arima_params=self.config.arima_params,
            use_tqdm=use_tqdm,
        )

    # -------------------------
    # Step 5) hard rules
    # -------------------------
    def apply_hard_rules(
        self,
        expected_sign: Optional[dict[str, str]] = None,
        alpha: float = 0.05,
        require_stationary: bool = True,
        require_invertible: bool = True,
        max_abs_ar: Optional[float] = None,
        max_abs_ma: Optional[float] = None,
        vif_max: Optional[float] = None,
        enforce_sig_for: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        if self.results_df is None:
            raise ValueError("results_df is None. Run run_models() first.")
        if self.split is None:
            raise ValueError("split is None.")

        self.results_after_hard = hard_rules_filtering(
            results_df=self.results_df,
            train_data=self.split.train_data,
            expected_sign=expected_sign,
            alpha=alpha,
            require_stationary=require_stationary,
            require_invertible=require_invertible,
            max_abs_ar=max_abs_ar,
            max_abs_ma=max_abs_ma,
            vif_max=vif_max,
            enforce_sig_for=enforce_sig_for,
        )
        return self.results_after_hard

    # -------------------------
    # Step 6) soft rules
    # -------------------------
    def rank_top_models(
        self,
        method: SoftMethod = "weighted",
        weights: Optional[dict[str, float]] = None,
        top_n: int = 3,
    ) -> pd.DataFrame:
        base = self.results_after_hard if self.results_after_hard is not None else self.results_df
        if base is None:
            raise ValueError("No results available. Run run_models() first.")

        self.top_models = soft_rules(df=base, method=method, weights=weights, top_n=top_n)
        return self.top_models

    # -------------------------
    # Convenience: one-call run
    # -------------------------
    def run(
        self,
        raw: pd.DataFrame,
        ds_column: str,
        *,
        expected_sign: Optional[dict[str, str]] = None,
        alpha: float = 0.05,
        require_stationary: bool = True,
        require_invertible: bool = True,
        max_abs_ar: Optional[float] = None,
        max_abs_ma: Optional[float] = None,
        vif_max: Optional[float] = None,
        soft_method: SoftMethod = "weighted",
        weights: Optional[dict[str, float]] = None,
        top_n: int = 3,
        apply_hard: bool = True,
        progress_callback: Optional[Callable[[int, int, list[str]], None]] = None,
    ) -> pd.DataFrame:
        self.set_raw(raw)
        self.preprocess(ds_column=ds_column)
        self.build_combinations(ds_column=ds_column)
        self.split_data()
        self.run_models(progress_callback=progress_callback)

        if apply_hard:
            self.apply_hard_rules(
                expected_sign=expected_sign,
                alpha=alpha,
                require_stationary=require_stationary,
                require_invertible=require_invertible,
                max_abs_ar=max_abs_ar,
                max_abs_ma=max_abs_ma,
                vif_max=vif_max,
            )

        return self.rank_top_models(method=soft_method, weights=weights, top_n=top_n)
