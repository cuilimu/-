"""
ARIMAX engine offline bench — exercises the full pipeline on synthetic data
WITHOUT requiring Streamlit. Use this for any analytics-layer change
(preprocess / model / rules / metrics) — iterate seconds, not minutes.

Why this exists
---------------
Streamlit's hot-reload re-runs your *script* on file change, but it does NOT
re-import sub-modules already in `sys.modules`. So changes to
`analytics/arimax/*.py` don't take effect until you fully kill+restart the
Streamlit process. This bench bypasses Streamlit entirely — every invocation
is a fresh Python process with a fresh import of your latest source.

Usage
-----
    python stock_engine/scripts/bench_arimax.py                   # default: freq=D, max_lag=2
    python stock_engine/scripts/bench_arimax.py --freq ME
    python stock_engine/scripts/bench_arimax.py --freq QE --max-lag 1 --n-obs 1500
    python stock_engine/scripts/bench_arimax.py --transform log
    python stock_engine/scripts/bench_arimax.py --no-rules        # skip hard/soft rules
    python stock_engine/scripts/bench_arimax.py --top-n 5
    python stock_engine/scripts/bench_arimax.py -h                # help

Exit code: 0 on success, 1 on any pipeline failure.
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

# Force UTF-8 stdout so the Windows cp1252 console can print arrows / box
# chars / Chinese path strings without UnicodeEncodeError. Harmless on
# non-Windows. Must come before any print().
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# Add the project root (parent of stock_engine/) to sys.path so the imports
# below work whether or not stock_engine is pip-installed in the active env.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from stock_engine.analytics.arimax import ARIMAXConfig, ARIMAXPipeline
from stock_engine.analytics.arimax.portfolio_target import merge_target_with_mevs


def make_synthetic_data(n_obs: int, seed: int = 42):
    """Build (target_df, mev_df) that mirrors what the Streamlit app passes
    in: DatetimeIndex named 'DATE', daily frequency, MEVs strictly positive
    (so log_diff transforms produce real numbers, not NaN)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n_obs, freq="D", name="DATE")

    # Target = log-returns of a noisy random walk (looks like portfolio NAV
    # log returns, which is the typical ARIMAX target).
    nav = np.exp(np.cumsum(rng.normal(0.0002, 0.012, n_obs)))
    log_returns = np.diff(np.log(nav), prepend=np.log(nav[0]))
    target_df = pd.DataFrame({"y": log_returns}, index=idx)

    # MEVs = positive trending series (log_diff requires positivity).
    icsa   = 200 + np.cumsum(rng.normal(0.05, 1.5, n_obs))
    icsa   = np.clip(icsa, 50, None)
    unrate = 4.0 + np.cumsum(rng.normal(0.0, 0.05, n_obs))
    unrate = np.clip(unrate, 1.0, 15.0)
    mev_df = pd.DataFrame({"ICSA": icsa, "UNRATE": unrate}, index=idx)
    return target_df, mev_df


def stage(label: str, t0: float, extra: str = "") -> None:
    print(f"  {label:<14} ({time.time() - t0:5.2f}s){'  ' + extra if extra else ''}")


def run_bench(args: argparse.Namespace) -> int:
    print(f"=== ARIMAX bench === freq={args.freq} · max_lag={args.max_lag} · "
          f"n_obs={args.n_obs} · transform={args.transform}\n")

    target_df, mev_df = make_synthetic_data(n_obs=args.n_obs)
    print(f"  target_df       {target_df.shape}  "
          f"{target_df.index.min().date()} → {target_df.index.max().date()}")
    print(f"  mev_df          {mev_df.shape}    cols={list(mev_df.columns)}")

    cfg = ARIMAXConfig(
        target="y",
        mevs=list(mev_df.columns),
        mevs_guide={"ICSA": "log_diff", "UNRATE": "diff"},
        freq=args.freq,
        max_lag=args.max_lag,
        max_number_of_exogenous_variables=2,
        include_non_lags=False,
        train_threshold=0.8,
        oot_test=False,
        oot_threshold=0.9,
        transform=args.transform,
        trace=False,
    )

    raw = merge_target_with_mevs(target_df, mev_df)
    print(f"  raw merged      {raw.shape}\n")

    pipe = ARIMAXPipeline(config=cfg)
    pipe.set_raw(raw)

    print("Pipeline stages:")

    t0 = time.time(); pipe.preprocess(ds_column="DATE")
    stage("preprocess", t0, f"→ df {pipe.df.shape}")

    t0 = time.time(); pipe.build_combinations(ds_column="DATE")
    n_combos = len(pipe.all_combinations)
    stage("build_combos", t0, f"→ {n_combos} combos")

    t0 = time.time(); pipe.split_data()
    n_train = len(pipe.split.y_train)
    n_test = len(pipe.split.y_test)
    stage("split_data", t0, f"→ train={n_train}, test={n_test}")

    if n_train < 8:
        print(f"\n✗ y_train has {n_train} obs (< 8) — auto_arima will refuse. "
              f"Try --freq D or lower --max-lag. Bench stopped.")
        return 1

    failed: list[tuple[int, str]] = []
    completed_per_combo: list[float] = []
    last_t = [time.time()]

    def on_complete(idx, total, row):
        now = time.time()
        completed_per_combo.append(now - last_t[0])
        last_t[0] = now
        if row.get("_fit_failed"):
            failed.append((idx, row.get("X_combo", "?")))

    t0 = time.time()
    pipe.run_models(on_fit_complete=on_complete)
    elapsed = time.time() - t0
    n_succeeded = len(pipe.results_df) if pipe.results_df is not None else 0
    stage(
        "run_models", t0,
        f"→ {n_succeeded}/{n_combos} fit · {len(failed)} failed · "
        f"avg {elapsed / max(n_combos, 1):.2f}s/combo",
    )
    if failed:
        for idx, name in failed[:5]:
            print(f"      ✗ combo[{idx}] = {name}")
        if len(failed) > 5:
            print(f"      … {len(failed) - 5} more")

    if not args.no_rules and n_succeeded > 0:
        t0 = time.time()
        pipe.apply_hard_rules(alpha=0.05)
        n_passed = len(pipe.results_after_hard) if pipe.results_after_hard is not None else 0
        stage("hard_rules", t0, f"→ {n_passed}/{n_succeeded} passed")

        t0 = time.time()
        pipe.rank_top_models(method="weighted", top_n=args.top_n)
        stage("rank_top", t0, f"→ top {len(pipe.top_models)}")

        if pipe.top_models is not None and len(pipe.top_models) > 0:
            print("\ntop-N ranking:")
            cols = [c for c in ("X_combo", "order", "rmse", "mape", "smape", "mase")
                    if c in pipe.top_models.columns]
            print(pipe.top_models[cols].to_string(index=False))

    print(f"\nTotal wall time: {sum(completed_per_combo):.1f}s in run_models, "
          f"{n_succeeded} successful fits.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ARIMAX offline bench — synthetic data, no Streamlit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--freq", default="D",
                        help="Resample freq (D / ME / QE / W). Default D.")
    parser.add_argument("--max-lag", type=int, default=2,
                        help="Max lag (default 2)")
    parser.add_argument("--n-obs", type=int, default=500,
                        help="Synthetic raw obs count (default 500 ≈ 2 years daily)")
    parser.add_argument("--transform", choices=("original", "log", "boxcox"),
                        default="original")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--no-rules", action="store_true",
                        help="Skip hard/soft rules + ranking")
    args = parser.parse_args()
    try:
        return run_bench(args)
    except Exception as exc:
        import traceback
        print(f"\n✗ Bench failed at pipeline level: {type(exc).__name__}: {exc}\n")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
