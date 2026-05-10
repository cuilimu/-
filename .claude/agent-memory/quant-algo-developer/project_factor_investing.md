---
name: factor_investing module architecture
description: Key data flow, return types, file responsibilities, and conventions in the factor_investing analytics module
type: project
---

## File responsibilities

- `analytics/factor_investing/types.py` — pure dataclasses only; no logic. FactorInvestingResult is the top-level return object.
- `analytics/factor_investing/live_compute.py` — downloads yfinance data, computes price-based factors (MOM, HL1M, Beta, AnnVol12M, LogMktCap), returns (dict[str, pd.Series], metadata_dict).
- `analytics/factor_investing/engine.py` — orchestration: calls live_compute, live_loader (French), loader (CapitalIQ). Exposes run_quick / run_live / run_compute.
- `ui/components/simple_mode/page_factor_investing.py` — Streamlit UI, purely layout/charting.

## FactorInvestingResult fields (as of 2026-05-09)

```python
factor_stats: list[FactorStats]
quintile_returns: list[QuintileResult]
correlation: FactorCorrelationMatrix
source: Literal["precomputed", "computed", "live"]
as_of_date: pd.Timestamp
qspread_series: Dict[str, pd.Series]           # default={}
long_short_legs: Dict[str, Tuple[pd.Series, pd.Series]]  # default={} — (q5, q1) per factor
n_firms_series: pd.Series                       # default=empty — universe size per month
spy_monthly: pd.Series                          # default=empty — SPY benchmark returns
```

## compute_live_factors return signature

Returns `tuple[dict[str, pd.Series], dict]`:
- First element: factor_name -> qspread Series
- Second element: metadata dict with keys "long_short_legs", "n_firms_series", "spy_monthly"

**Why:** Added 2026-05-09 to pass Q5/Q1 leg data and universe size to the UI without breaking the dict[str, Series] contract for existing callers.

**How to apply:** Always unpack as `computed, meta = compute_live_factors(...)` in engine.py.

## Factor formula conventions

- MOM: average of 11 monthly returns from t-12 to t-2 (not cumulative). Requires i >= 13, min 8 valid months.
- HL1M: (MonthHigh - MonthClose) / (MonthClose - MonthLow). Requires High/Low data from yfinance.
- AnnVol12M: std of 12 monthly log-returns x sqrt(12). NOT daily vol.
- Beta: 48-month rolling OLS vs SPY monthly returns. NOT 252-day daily.
- All factors use _quintile_breakdown() which returns (q5_ret, q1_ret, qspread).

## Theme conventions in UI charts

Colors always come from `ARX_LIGHT_THEME` (imported from `stock_engine.viz.theme`):
- `t.color_portfolio` — main QSpread series (brand purple)
- `t.color_gain` — Q5 long leg (green)
- `t.color_loss` — Q1 short leg (red)
- `t.color_neutral` — SPY benchmark (grey)
No raw hex literals anywhere in .py files.
