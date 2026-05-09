"""
analytics/arimax — ported ARIMAX engine.

End-to-end pipeline: preprocess → build all (variable × lag) combinations →
chronological split → fit auto-ARIMA(X) per combo with rolling 1-step
forecasts → hard rules (sign / p-value / root stationarity / VIF) → soft rules
(weighted-normalised composite over forecast metrics) → top-N.
"""
from stock_engine.analytics.arimax.metrics import (
    evaluate_pmdarima, mae, mape, mase, rmse, smape,
)
from stock_engine.analytics.arimax.model import (
    end_to_end_model_generations, run_one_combo,
)
from stock_engine.analytics.arimax.pipeline import ARIMAXConfig, ARIMAXPipeline, AutoARIMAParams
from stock_engine.analytics.arimax.preprocess import (
    TrainTestSplit, data_preprocess, exogenous_combinations, parse_x_combo, train_test_split,
)
from stock_engine.analytics.arimax.rules import (
    SoftMethod, hard_rule_reject_sarimax, hard_rules_filtering, soft_rules,
)

__all__ = [
    "ARIMAXConfig", "ARIMAXPipeline", "AutoARIMAParams",
    "TrainTestSplit", "data_preprocess", "exogenous_combinations", "parse_x_combo",
    "train_test_split",
    "run_one_combo", "end_to_end_model_generations",
    "hard_rule_reject_sarimax", "hard_rules_filtering", "soft_rules", "SoftMethod",
    "mae", "mape", "mase", "rmse", "smape", "evaluate_pmdarima",
]
