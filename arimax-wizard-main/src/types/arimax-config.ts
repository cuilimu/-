export interface BasicConfig {
  TARGET: string | null;
  MEVS: string[];
  MEVS_Guide: Record<string, string>;
  freq: string | null;
  max_lag: number | null;
  max_number_of_Exogenous_Variables: number;
  include_non_lags: boolean;
  train_threshold: number;
  oot_test: boolean;
  oot_threshold: number;
  transform: string;
  trace: boolean;
  use_tqdm: boolean;
}

export interface RunConfig {
  raw: string | null; // file path
  ds_column: string | null;
  expected_sign: Record<string, string> | null;
  alpha: number;
  enforce_sig_for: string[] | null;
  require_stationary: boolean;
  require_invertible: boolean;
  max_abs_ar: number | null;
  max_abs_ma: number | null;
  vif_max: number | null;
  soft_method: string;
  weights: Record<string, number> | null;
  top_n: number;
  apply_hard: boolean;
}

export interface ArimaxConfig {
  basic_config: BasicConfig;
  run_config: RunConfig;
}

export const DEFAULT_BASIC_CONFIG: BasicConfig = {
  TARGET: null,
  MEVS: [],
  MEVS_Guide: {},
  freq: null,
  max_lag: null,
  max_number_of_Exogenous_Variables: 2,
  include_non_lags: false,
  train_threshold: 0.8,
  oot_test: false,
  oot_threshold: 0.9,
  transform: "original",
  trace: false,
  use_tqdm: true,
};

export const DEFAULT_RUN_CONFIG: RunConfig = {
  raw: null,
  ds_column: null,
  expected_sign: null,
  alpha: 0.05,
  enforce_sig_for: null,
  require_stationary: true,
  require_invertible: true,
  max_abs_ar: null,
  max_abs_ma: null,
  vif_max: null,
  soft_method: "weighted",
  weights: null,
  top_n: 3,
  apply_hard: true,
};
