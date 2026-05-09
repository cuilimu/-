"""
python fix_phase1_files.py
Writes analytics/risk.py, analytics/regime.py, data/fred_fetcher.py to disk
from within Windows Python — bypasses sandbox mount sync issues.
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).parent

FILES = {}

# ─────────────────────────────────────────────────────────────────────────────
FILES["analytics/risk.py"] = r'''"""
analytics/risk.py — Market risk metrics for PortfolioCandidate.
Computes VaR, CVaR, drawdown analysis, stress testing, and tracking error.
All functions are stateless. No imports from ui/.
# ML_EXTENSIBLE: compute_var() can dispatch to analytics/ml/ for ML-based VaR.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from stock_engine.portfolio.models import RiskResult

STRESS_SCENARIOS = [
    {"name": "2008 GFC",         "start": "2008-09-01", "end": "2009-03-31"},
    {"name": "2020 COVID Crash",  "start": "2020-02-01", "end": "2020-03-31"},
    {"name": "2022 Rate Shock",   "start": "2022-01-01", "end": "2022-10-31"},
    {"name": "2000 Dot-com",      "start": "2000-03-01", "end": "2002-10-31"},
]
TOP_N_DRAWDOWNS = 5

def compute_risk(
    returns: pd.Series,
    weights: Dict[str, float],
    constituent_returns: Optional[pd.DataFrame] = None,
    benchmark_returns: Optional[pd.Series] = None,
    factor_betas: Optional[Dict[str, float]] = None,
    factor_r2: Optional[float] = None,
) -> RiskResult:
    result = RiskResult()
    if returns.empty or len(returns) < 10:
        return result
    result.annualised_vol = float(returns.std() * np.sqrt(252))
    result.var_95_param,  result.cvar_95_param  = _var_cvar_parametric(returns, 0.95)
    result.var_99_param,  result.cvar_99_param  = _var_cvar_parametric(returns, 0.99)
    result.var_95_hist,   result.cvar_95_hist   = _var_cvar_historical(returns, 0.95)
    result.var_99_hist,   result.cvar_99_hist   = _var_cvar_historical(returns, 0.99)
    dd_series = _drawdown_series(returns)
    result.max_drawdown = float(dd_series.min())
    trough_idx = dd_series.idxmin()
    cum = (1 + returns).cumprod()
    peak_idx = cum.loc[:trough_idx].idxmax()
    result.max_drawdown_start = peak_idx.date() if hasattr(peak_idx, "date") else None
    result.max_drawdown_end   = trough_idx.date() if hasattr(trough_idx, "date") else None
    post_trough = cum.loc[trough_idx:]
    peak_val = float(cum.loc[peak_idx])
    recovered = post_trough[post_trough >= peak_val]
    if not recovered.empty:
        result.max_drawdown_recovery = (recovered.index[0] - trough_idx).days
    result.drawdown_events = _top_n_drawdowns(returns, n=TOP_N_DRAWDOWNS)
    ann_ret = float((1 + returns).prod() ** (252 / len(returns)) - 1)
    if result.max_drawdown and result.max_drawdown != 0:
        result.calmar_ratio = ann_ret / abs(result.max_drawdown)
    if benchmark_returns is not None:
        aligned = returns.align(benchmark_returns, join="inner")
        active = aligned[0] - aligned[1]
        result.tracking_error = float(active.std() * np.sqrt(252))
        if result.tracking_error > 0:
            result.information_ratio = float(active.mean() * 252) / result.tracking_error
    if constituent_returns is not None:
        result.stress_results = _stress_test(weights, constituent_returns, benchmark_returns)
    if factor_betas:
        result.factor_betas = factor_betas
    if factor_r2 is not None:
        result.factor_r2 = factor_r2
    return result

def _var_cvar_parametric(returns: pd.Series, confidence: float) -> Tuple[float, float]:
    from scipy.stats import norm
    mu, sig = float(returns.mean()), float(returns.std())
    alpha = 1 - confidence
    var  = float(norm.ppf(alpha, loc=mu, scale=sig))
    cvar = float(mu - sig * norm.pdf(norm.ppf(alpha)) / alpha)
    return var, cvar

def _var_cvar_historical(returns: pd.Series, confidence: float) -> Tuple[float, float]:
    alpha = 1 - confidence
    var  = float(returns.quantile(alpha))
    cvar = float(returns[returns <= var].mean())
    return var, cvar

def _drawdown_series(returns: pd.Series) -> pd.Series:
    cum = (1 + returns).cumprod()
    return (cum - cum.cummax()) / cum.cummax()

def _top_n_drawdowns(returns: pd.Series, n: int = 5) -> List[Dict]:
    cum = (1 + returns).cumprod()
    dd  = _drawdown_series(returns)
    events, used_dates = [], set()
    for trough_idx in dd.sort_values().index.tolist():
        if len(events) >= n:
            break
        if trough_idx in used_dates:
            continue
        depth = float(dd.loc[trough_idx])
        if depth >= -0.03:
            continue
        peak_idx = cum.loc[:trough_idx].idxmax()
        post = cum.loc[trough_idx:]
        peak_val = float(cum.loc[peak_idx])
        recovered = post[post >= peak_val]
        recovery_end = recovered.index[0] if not recovered.empty else None
        recovery_days = (recovery_end - trough_idx).days if recovery_end else None
        end_mark = recovery_end or returns.index[-1]
        for d in pd.date_range(peak_idx, end_mark, freq="D"):
            used_dates.add(d)
        events.append({
            "period": f"{peak_idx.strftime('%b %Y')} – {trough_idx.strftime('%b %Y')}",
            "peak_date": peak_idx.date(), "trough_date": trough_idx.date(),
            "depth": depth, "recovery_days": recovery_days,
        })
    return sorted(events, key=lambda e: e["depth"])

def _stress_test(weights, constituent_returns, benchmark_returns=None):
    results = []
    for sc in STRESS_SCENARIOS:
        window = constituent_returns.loc[sc["start"]:sc["end"]]
        if window.empty:
            results.append({"scenario_name": sc["name"], "period": f"{sc['start']} – {sc['end']}",
                            "portfolio_return": None, "bm_return": None, "excess_return": None, "per_asset": {}})
            continue
        per_asset, port_return = {}, 0.0
        for ticker, w in weights.items():
            if ticker in window.columns:
                r = float((1 + window[ticker]).prod() - 1)
                per_asset[ticker] = r
                port_return += w * r
        bm_return = None
        if benchmark_returns is not None:
            bw = benchmark_returns.loc[sc["start"]:sc["end"]]
            if not bw.empty:
                bm_return = float((1 + bw).prod() - 1)
        excess = (port_return - bm_return) if bm_return is not None else None
        results.append({"scenario_name": sc["name"], "period": f"{sc['start']} – {sc['end']}",
                        "portfolio_return": port_return, "bm_return": bm_return,
                        "excess_return": excess, "per_asset": per_asset})
    return results
'''

# ─────────────────────────────────────────────────────────────────────────────
FILES["analytics/regime.py"] = r'''"""
analytics/regime.py — Heuristic macro regime classifier for Page 6 TAA.
# ML_EXTENSIBLE: classify() replaceable by HMM/RF via analytics/ml/regime_ml.py.
"""
from __future__ import annotations
from typing import Dict

REGIMES = ["base", "high_inflation", "stagflation", "recession", "rapid_disinflation"]

def classify(signals: Dict[str, float]) -> Dict[str, float]:
    cpi      = signals.get("cpi_yoy",        2.5)
    core_cpi = signals.get("core_cpi_yoy",   2.5)
    unemp    = signals.get("unemployment",   4.0)
    yld_sprd = signals.get("yield_spread",   0.5)
    gdp      = signals.get("gdp_growth_qoq", 2.0)
    hy       = signals.get("hy_spread",      3.5)
    scores: Dict[str, float] = {r: 0.0 for r in REGIMES}
    if 2.0 <= cpi <= 3.2:        scores["base"] += 1.5
    if 2.0 <= core_cpi <= 3.2:   scores["base"] += 1.0
    if unemp <= 4.5:              scores["base"] += 0.8
    if 1.5 <= gdp <= 3.5:        scores["base"] += 1.0
    if hy <= 4.0:                 scores["base"] += 0.7
    if cpi > 3.5:                 scores["high_inflation"] += 2.0
    if cpi > 4.5:                 scores["high_inflation"] += 1.0
    if core_cpi > 3.2:            scores["high_inflation"] += 1.5
    if gdp >= 1.5:                scores["high_inflation"] += 0.5
    if yld_sprd < 0:              scores["high_inflation"] += 0.5
    if cpi > 4.0 and gdp < 1.5:  scores["stagflation"] += 3.0
    if unemp > 4.5:               scores["stagflation"] += 1.0
    if hy > 4.5:                  scores["stagflation"] += 0.8
    if gdp < 0:                   scores["recession"] += 3.0
    if gdp < -1.0:                scores["recession"] += 1.5
    if unemp > 5.5:               scores["recession"] += 2.0
    if hy > 6.0:                  scores["recession"] += 2.0
    if yld_sprd > 0.5:            scores["recession"] += 0.5
    if cpi < 2.5 and core_cpi < 3.0: scores["rapid_disinflation"] += 2.5
    if cpi < 2.0:                     scores["rapid_disinflation"] += 1.5
    if gdp >= 1.5:                    scores["rapid_disinflation"] += 0.8
    if yld_sprd > 0:                  scores["rapid_disinflation"] += 0.5
    total = sum(scores.values())
    if total == 0:
        return {r: 1.0 / len(REGIMES) for r in REGIMES}
    return {r: round(s / total, 4) for r, s in scores.items()}

def top_regime(scores: Dict[str, float]) -> str:
    return max(scores, key=lambda r: scores[r])

SCENARIO_TILTS = {
    "base": {"description": "Neutral — no deviation from SAA",
             "growth": 0, "fin_cond": 0, "inflation": 0, "diversifier": 0,
             "triggers": "CPI 2-3%, unemployment <4.5%, GDP 2-3%"},
    "high_inflation": {"description": "UW long-duration bonds; OW real assets + quality growth",
                       "growth": +5, "fin_cond": -8, "inflation": +5, "diversifier": 0,
                       "triggers": "CPI >3.5% for 2 months, Core CPI sticky"},
    "stagflation": {"description": "Rotate to hard assets; reduce risk broadly",
                    "growth": -10, "fin_cond": -5, "inflation": +10, "diversifier": +5,
                    "triggers": "CPI >4%, GDP <1%, unemployment rising"},
    "recession": {"description": "Flight to quality; long duration as rates cut",
                  "growth": -15, "fin_cond": +10, "inflation": +5, "diversifier": 0,
                  "triggers": "GDP <0% (2 qtrs), unemployment >5.5%, HY spread >600bps"},
    "rapid_disinflation": {"description": "Risk-on; duration rally; reduce inflation hedge",
                           "growth": +10, "fin_cond": +5, "inflation": -8, "diversifier": -5,
                           "triggers": "CPI falling to <2.5%, Fed signalling cuts"},
}
'''

# ─────────────────────────────────────────────────────────────────────────────
FILES["data/fred_fetcher.py"] = r'''"""
data/fred_fetcher.py — FRED macro signal fetcher for Page 6 TAA.
Requires FRED_API_KEY env var or api_key= argument.
Caches to parquet; refreshes if stale > CACHE_HOURS hours.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import requests
from stock_engine.exceptions import DataError

FRED_BASE   = "https://api.stlouisfed.org/fred/series/observations"
LEVEL_SERIES = {
    "CPIAUCSL":     "cpi_level",
    "CPILFESL":     "core_cpi_level",
    "UNRATE":       "unemployment",
    "T10Y2Y":       "yield_spread",
    "GDP":          "gdp_level",
    "BAMLH0A0HYM2": "hy_spread",
}
SIGNAL_KEYS  = ["cpi_yoy", "core_cpi_yoy", "unemployment", "yield_spread", "gdp_growth_qoq", "hy_spread"]
CACHE_HOURS  = 12

class FredFetcher:
    """Fetches and caches FRED macro signals.
    # ML_EXTENSIBLE: regime classification consumes output via analytics/regime.py
    """
    def __init__(self, api_key: Optional[str] = None, cache_dir: str = ".cache") -> None:
        self._api_key = api_key or os.environ.get("FRED_API_KEY", "")
        if not self._api_key:
            raise DataError("FRED API key not set. Set FRED_API_KEY env var or pass api_key=.")
        self._cache_dir  = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self._cache_dir / "fred_signals.parquet"

    def latest(self) -> Dict[str, float]:
        df = self._load_or_refresh()
        row = df.iloc[-1]
        return {k: float(row[k]) for k in SIGNAL_KEYS if k in row and pd.notna(row[k])}

    def history(self, start: str, end: Optional[str] = None) -> pd.DataFrame:
        df = self._load_or_refresh()
        s  = pd.Timestamp(start)
        e  = pd.Timestamp(end) if end else pd.Timestamp.now()
        return df.loc[(df.index >= s) & (df.index <= e)].copy()

    def _load_or_refresh(self) -> pd.DataFrame:
        if self._cache_path.exists():
            age = datetime.now() - datetime.fromtimestamp(self._cache_path.stat().st_mtime)
            if age < timedelta(hours=CACHE_HOURS):
                return pd.read_parquet(self._cache_path)
        return self._fetch_and_cache()

    def _fetch_and_cache(self) -> pd.DataFrame:
        frames: Dict[str, pd.Series] = {}
        for sid, col in LEVEL_SERIES.items():
            try:
                frames[col] = self._fetch_series(sid)
            except Exception as exc:
                raise DataError(f"FRED fetch failed for {sid}: {exc}") from exc
        df = pd.DataFrame(frames).sort_index()
        df["cpi_yoy"]       = df["cpi_level"].pct_change(12) * 100
        df["core_cpi_yoy"]  = df["core_cpi_level"].pct_change(12) * 100
        df["gdp_level"]     = df["gdp_level"].ffill()
        df["gdp_growth_qoq"]= df["gdp_level"].pct_change(1) * 400
        df = df[SIGNAL_KEYS].dropna(how="all")
        df.to_parquet(self._cache_path)
        return df

    def _fetch_series(self, series_id: str) -> pd.Series:
        params = {"series_id": series_id, "api_key": self._api_key,
                  "file_type": "json", "observation_start": "2000-01-01", "frequency": "m"}
        resp = requests.get(FRED_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "observations" not in data:
            raise DataError(f"Unexpected FRED response for {series_id}")
        records = [(obs["date"], float(obs["value"]))
                   for obs in data["observations"] if obs["value"] not in (".", "")]
        if not records:
            raise DataError(f"No observations for {series_id}")
        dates, values = zip(*records)
        return pd.Series(values, index=pd.to_datetime(dates), name=series_id)
'''

# ── Write all files ────────────────────────────────────────────────────────────
for rel, content in FILES.items():
    target = ROOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    lines = content.strip().count("\n") + 1
    print(f"Written {lines:>4} lines → {rel}")

print("\nImport test:")
sys.path.insert(0, str(ROOT.parent))
from stock_engine.analytics.risk   import compute_risk
from stock_engine.analytics.regime import classify, SCENARIO_TILTS
from stock_engine.data.fred_fetcher import FredFetcher, SIGNAL_KEYS
print("  analytics/risk    OK")
print("  analytics/regime  OK")
print("  data/fred_fetcher OK")
print("\nAll Phase 1 files fixed.")
