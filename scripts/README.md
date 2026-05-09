# Dev scripts for stock_engine

## bench_arimax.py — ARIMAX offline bench

Runs the full ARIMAX pipeline (preprocess → build_combinations → split → fit
→ hard rules → soft rules) on synthetic data, **without launching Streamlit**.

### When to use

- Changing anything in `analytics/arimax/*.py` (preprocess, model, rules,
  pipeline, metrics)
- Reproducing a pipeline-level bug fast
- Verifying a fix works before going through the Streamlit restart cycle

### When NOT to use

- UI/CSS changes — those need the actual Streamlit run
- Bugs that only reproduce with the user's specific real data shape (rare —
  the bench's synthetic data already mirrors the typical shape)

### Why this works when Streamlit's hot-reload doesn't

Streamlit re-runs your *script* on file change but does **not** re-import
sub-modules already in `sys.modules`. So edits to `analytics/arimax/*.py`
need a full Streamlit kill+restart to take effect. This bench is a fresh
Python process every invocation — your latest source is always loaded.

### Quick examples

```bash
# default — daily freq, max_lag=2, 500 synthetic obs (~10–20s on a laptop)
python stock_engine/scripts/bench_arimax.py

# reproduce the "y_train shrunk to nothing" path (freq mismatch)
python stock_engine/scripts/bench_arimax.py --freq QE --max-lag 4

# stress test with longer history
python stock_engine/scripts/bench_arimax.py --n-obs 1500

# skip rules — just exercise model fits
python stock_engine/scripts/bench_arimax.py --no-rules

# log-transform path
python stock_engine/scripts/bench_arimax.py --transform log
```

### What the output looks like

```
=== ARIMAX bench === freq=D · max_lag=2 · n_obs=500 · transform=original

  target_df       (500, 1)  2022-01-01 → 2023-05-15
  mev_df          (500, 2)  cols=['ICSA', 'UNRATE']
  raw merged      (500, 3)

Pipeline stages:
  preprocess     ( 0.04s)  → df (497, 6)
  build_combos   ( 0.00s)  → 9 combos
  split_data     ( 0.00s)  → train=397, test=100
  run_models     (15.42s)  → 9/9 fit · 0 failed · avg 1.71s/combo
  hard_rules     ( 0.18s)  → 7/9 passed
  rank_top       ( 0.01s)  → top 3

top-N ranking:
   X_combo                     order         rmse         mape   smape  mase
   ICSA_lag1                  (1,1,1)        0.012        2.34   1.99   0.98
   UNRATE_lag2                (0,1,1)        0.013        2.41   2.04   1.01
   ICSA_lag1 + UNRATE_lag1    (2,1,2)        0.012        2.30   1.95   0.96
```

Stages, timings, and per-combo failure counts make it obvious where a
regression slipped in.

### Iterating workflow

1. You edit `analytics/arimax/preprocess.py`
2. Run `python stock_engine/scripts/bench_arimax.py` — 15s, see it pass/fail
3. If it passes, **then** restart Streamlit and validate the UI

This compresses what used to be a 5–10 minute round-trip into ~30 seconds.

---

## Adding more bench scripts

Anything new should:
- Be self-contained (synthetic data or a generator function inline)
- Not depend on Streamlit (`import streamlit` should fail-fast or not appear)
- Print structured output (stage label · timing · key counts), not silent
- Return non-zero exit code on failure (so it composes with shell scripts /
  CI / `&&` chains)
