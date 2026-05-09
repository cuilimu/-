import {
  mean,
  median,
  mode,
  standardDeviation,
  variance,
  min,
  max,
  quantile,
  sum,
  interquartileRange,
} from 'simple-statistics';

// ============================================================
// Types matching the Python notebook payload structure
// ============================================================

export interface QuantileStats {
  min: number | null;
  p05: number | null;
  q1: number | null;
  median: number | null;
  q3: number | null;
  p95: number | null;
  max: number | null;
  range: number | null;
  iqr: number | null;
}

export interface DescriptiveStats {
  std: number | null;
  cv: number | null;
  kurtosis: number | null;
  mean: number | null;
  mad: number | null;
  skewness: number | null;
  sum: number | null;
  variance: number | null;
  monotonicity: number | null;
}

export interface ValueCount {
  value: string | number;
  count: number;
  freq_pct: number;
}

export interface HistogramData {
  edges: number[];
  counts: number[];
}

export interface CDFData {
  x: number[];
  y: number[];
}

export interface QQData {
  x: number[];
  y: number[];
  line: { slope: number | null; intercept: number | null };
}

export interface ACFData {
  lags: number[];
  acf: number[];
  confInterval: number; // 95% confidence interval (±1.96/sqrt(n))
}

export interface LineSeriesData {
  index: number[];
  values: number[];
}

export interface NumericDetails {
  n_total: number;
  n_null: number;
  n_nonnull: number;
  zeros: number | null;
  infs: number | null;
  tab1: {
    quantiles: QuantileStats;
    descriptive: DescriptiveStats;
  };
  plots: {
    hist: HistogramData;
    cdf: CDFData;
    qq: QQData;
    acf: ACFData;
    lineSeries: LineSeriesData;
  };
  common_values: ValueCount[];
  extremes: {
    min10: ValueCount[];
    max10: ValueCount[];
  };
}

export interface CategoricalDetails {
  n_total: number;
  n_null: number;
  n_nonnull: number;
  unique: number;
  top_values: ValueCount[];
}

export interface DatetimeDetails {
  n_total: number;
  n_null: number;
  min: string | null;
  max: string | null;
}

export interface VariableInfo {
  name: string;
  dtype: string;
  vtype: 'numeric' | 'categorical' | 'datetime' | 'boolean' | 'other';
  missing_count: number;
  missing_pct: number;
  unique: number;
  details: NumericDetails | CategoricalDetails | DatetimeDetails | { note: string };
}

export interface Alert {
  Message: string;
  'Alert type': string;
}

export interface DatasetPayload {
  meta: {
    title: string;
    source_file: string;
    generated_at: string;
    rows: number;
    cols: number;
    missing_cells: number;
    missing_pct: number;
    duplicate_rows: number;
    duplicate_pct: number;
    type_counts: {
      numeric: number;
      categorical: number;
      datetime: number;
      boolean: number;
      other: number;
    };
  };
  variables: Record<string, VariableInfo>;
  repro: {
    platform: string;
    library: string;
  };
  alerts: {
    correlation: Alert[];
    zeros: Alert[];
    unique: Alert[];
    uniform: Alert[];
  };
  sample_data: {
    head: Record<string, unknown>[];
    tail: Record<string, unknown>[];
  };
}

// ============================================================
// Helper functions
// ============================================================

function safeFloat(x: unknown): number | null {
  if (x === null || x === undefined) return null;
  const n = Number(x);
  if (!isFinite(n)) return null;
  return n;
}

function isNumericValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false;
  const num = Number(value);
  return !isNaN(num) && isFinite(num);
}

function detectColumnType(values: unknown[]): 'numeric' | 'categorical' | 'datetime' | 'boolean' {
  const nonEmpty = values.filter(v => v !== null && v !== undefined && v !== '');
  if (nonEmpty.length === 0) return 'categorical';
  
  // Check for boolean
  const boolValues = nonEmpty.filter(v => typeof v === 'boolean' || v === 'true' || v === 'false');
  if (boolValues.length === nonEmpty.length) return 'boolean';
  
  // Check for datetime (ISO format strings)
  const datePattern = /^\d{4}-\d{2}-\d{2}/;
  const dateCount = nonEmpty.filter(v => typeof v === 'string' && datePattern.test(v)).length;
  if (dateCount > nonEmpty.length * 0.8) return 'datetime';
  
  // Check for numeric
  const numericCount = nonEmpty.filter(isNumericValue).length;
  if (numericCount > nonEmpty.length * 0.8) return 'numeric';
  
  return 'categorical';
}

// ============================================================
// Monotonicity Score (matching Python implementation)
// ============================================================
function monotonicityScore(values: number[]): number | null {
  const n = values.length;
  if (n < 3) return null;
  
  let inc = 0;
  let dec = 0;
  let total = 0;
  let prev = values[0];
  
  for (let i = 1; i < n; i++) {
    const cur = values[i];
    const d = cur - prev;
    if (d >= 0) inc++;
    if (d <= 0) dec++;
    total++;
    prev = cur;
  }
  
  if (total === 0) return null;
  return Math.max(inc / total, dec / total);
}

// ============================================================
// Skewness (Fisher-Pearson)
// ============================================================
function calculateSkewness(values: number[]): number | null {
  if (values.length < 3) return null;
  
  const n = values.length;
  const m = mean(values);
  const s = standardDeviation(values);
  
  if (s === 0) return null;
  
  const sumCubed = values.reduce((acc, val) => acc + Math.pow((val - m) / s, 3), 0);
  return (n / ((n - 1) * (n - 2))) * sumCubed;
}

// ============================================================
// Kurtosis (excess kurtosis)
// ============================================================
function calculateKurtosis(values: number[]): number | null {
  if (values.length < 4) return null;
  
  const n = values.length;
  const m = mean(values);
  const s = standardDeviation(values);
  
  if (s === 0) return null;
  
  const sumFourth = values.reduce((acc, val) => acc + Math.pow((val - m) / s, 4), 0);
  const kurtosis = ((n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3))) * sumFourth;
  const adjustment = (3 * Math.pow(n - 1, 2)) / ((n - 2) * (n - 3));
  
  return kurtosis - adjustment;
}

// ============================================================
// Median Absolute Deviation (MAD)
// ============================================================
function calculateMAD(values: number[]): number | null {
  if (values.length === 0) return null;
  const med = median(values);
  const absDeviations = values.map(v => Math.abs(v - med));
  return median(absDeviations);
}

// ============================================================
// Histogram data (50 bins, matching Python)
// ============================================================
function createHistogramData(values: number[], bins: number = 50): HistogramData {
  if (values.length === 0) return { edges: [], counts: [] };
  
  const vmin = min(values);
  const vmax = max(values);
  
  if (vmin === vmax) {
    return { edges: [vmin - 0.5, vmax + 0.5], counts: [values.length] };
  }
  
  const width = (vmax - vmin) / bins;
  const edges: number[] = [];
  const counts: number[] = new Array(bins).fill(0);
  
  for (let i = 0; i <= bins; i++) {
    edges.push(vmin + i * width);
  }
  
  for (const x of values) {
    const idx = x === vmax ? bins - 1 : Math.floor((x - vmin) / width);
    if (idx >= 0 && idx < bins) {
      counts[idx]++;
    }
  }
  
  return { edges, counts };
}

// ============================================================
// CDF data (downsampled)
// ============================================================
function createCDFData(values: number[], maxPoints: number = 400): CDFData {
  if (values.length === 0) return { x: [], y: [] };
  
  const xs = [...values].sort((a, b) => a - b);
  const n = xs.length;
  
  if (n === 1) return { x: [xs[0]], y: [1.0] };
  
  const step = Math.max(1, Math.floor(n / maxPoints));
  const xOut: number[] = [];
  const yOut: number[] = [];
  
  for (let i = 0; i < n; i += step) {
    xOut.push(xs[i]);
    yOut.push((i + 1) / n);
  }
  
  if (xOut[xOut.length - 1] !== xs[n - 1]) {
    xOut.push(xs[n - 1]);
    yOut.push(1.0);
  }
  
  return { x: xOut, y: yOut };
}

// ============================================================
// QQ plot data (normal quantiles)
// ============================================================
function normPPF(p: number): number {
  // Acklam approximation for inverse normal CDF
  if (p <= 0) return -Infinity;
  if (p >= 1) return Infinity;
  
  const a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
             1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
  const b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
             6.680131188771972e+01, -1.328068155288572e+01];
  const c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
             -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
  const d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
             3.754408661907416e+00];
  
  const plow = 0.02425;
  const phigh = 1 - plow;
  
  if (p < plow) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) /
           ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1);
  }
  if (p > phigh) {
    const q = Math.sqrt(-2 * Math.log(1 - p));
    return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) /
            ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1);
  }
  
  const q = p - 0.5;
  const r = q * q;
  return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q /
         (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1);
}

function createQQData(values: number[], maxPoints: number = 400): QQData {
  if (values.length < 3) {
    return { x: [], y: [], line: { slope: null, intercept: null } };
  }
  
  const xs = [...values].sort((a, b) => a - b);
  const n = xs.length;
  const step = Math.max(1, Math.floor(n / maxPoints));
  
  const sample: number[] = [];
  for (let i = 0; i < n; i += step) {
    sample.push(xs[i]);
  }
  
  const m = sample.length;
  const theo = sample.map((_, i) => normPPF((i + 0.5) / m));
  
  // Fit line y = slope*x + intercept
  const mx = theo.reduce((a, b) => a + b, 0) / m;
  const my = sample.reduce((a, b) => a + b, 0) / m;
  
  let sxx = 0;
  let sxy = 0;
  for (let i = 0; i < m; i++) {
    sxx += (theo[i] - mx) ** 2;
    sxy += (theo[i] - mx) * (sample[i] - my);
  }
  
  const slope = sxx !== 0 ? sxy / sxx : null;
  const intercept = slope !== null ? my - slope * mx : null;
  
  return { x: theo, y: sample, line: { slope, intercept } };
}

// ============================================================
// ACF (Autocorrelation Function) data
// ============================================================
function createACFData(values: number[], maxLag: number = 40): ACFData {
  const n = values.length;
  if (n < 4) {
    return { lags: [], acf: [], confInterval: 0 };
  }
  
  const effectiveMaxLag = Math.min(maxLag, Math.floor(n / 2));
  const avg = mean(values);
  
  // Calculate variance (lag 0 autocorrelation denominator)
  let c0 = 0;
  for (let i = 0; i < n; i++) {
    c0 += (values[i] - avg) ** 2;
  }
  
  if (c0 === 0) {
    return { lags: [], acf: [], confInterval: 0 };
  }
  
  const lags: number[] = [];
  const acf: number[] = [];
  
  for (let lag = 0; lag <= effectiveMaxLag; lag++) {
    let ck = 0;
    for (let i = 0; i < n - lag; i++) {
      ck += (values[i] - avg) * (values[i + lag] - avg);
    }
    lags.push(lag);
    acf.push(ck / c0);
  }
  
  // 95% confidence interval: ±1.96/sqrt(n)
  const confInterval = 1.96 / Math.sqrt(n);
  
  return { lags, acf, confInterval };
}

// ============================================================
// Line Series data (observation index vs value)
// ============================================================
function createLineSeriesData(values: number[], maxPoints: number = 1000): LineSeriesData {
  const n = values.length;
  if (n === 0) {
    return { index: [], values: [] };
  }
  
  const step = Math.max(1, Math.floor(n / maxPoints));
  const index: number[] = [];
  const vals: number[] = [];
  
  for (let i = 0; i < n; i += step) {
    index.push(i);
    vals.push(values[i]);
  }
  
  // Ensure last point is included
  if (index[index.length - 1] !== n - 1) {
    index.push(n - 1);
    vals.push(values[n - 1]);
  }
  
  return { index, values: vals };
}

// ============================================================
// Top K value counts
// ============================================================
function topKValueCounts(values: unknown[], k: number = 10): ValueCount[] {
  const nonNull = values.filter(v => v !== null && v !== undefined && v !== '');
  const n = nonNull.length;
  if (n === 0) return [];
  
  const counts: Record<string, number> = {};
  for (const v of nonNull) {
    const key = String(v);
    counts[key] = (counts[key] || 0) + 1;
  }
  
  return Object.entries(counts)
    .map(([value, count]) => ({
      value,
      count,
      freq_pct: (count / n) * 100
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, k);
}

// ============================================================
// Extreme values (min/max 10 distinct)
// ============================================================
function extremeKTables(values: number[], k: number = 10): { min10: ValueCount[]; max10: ValueCount[] } {
  if (values.length === 0) return { min10: [], max10: [] };
  
  const n = values.length;
  const counts: Record<number, number> = {};
  for (const v of values) {
    counts[v] = (counts[v] || 0) + 1;
  }
  
  const uniqueSorted = [...new Set(values)].sort((a, b) => a - b);
  const mins = uniqueSorted.slice(0, k);
  const maxs = uniqueSorted.slice(-k).reverse();
  
  const min10: ValueCount[] = mins.map(v => ({
    value: v,
    count: counts[v],
    freq_pct: (counts[v] / n) * 100
  }));
  
  const max10: ValueCount[] = maxs.map(v => ({
    value: v,
    count: counts[v],
    freq_pct: (counts[v] / n) * 100
  }));
  
  return { min10, max10 };
}

// ============================================================
// Compute numeric details (matching Python structure)
// ============================================================
function computeNumericDetails(values: unknown[]): NumericDetails {
  const n_total = values.length;
  const nullCount = values.filter(v => v === null || v === undefined || v === '').length;
  const numericValues = values
    .filter(v => v !== null && v !== undefined && v !== '')
    .map(Number)
    .filter(n => isFinite(n));
  
  const n_nonnull = numericValues.length;
  
  // Zeros and infinites
  let zeros = 0;
  let infs = 0;
  for (const v of values) {
    if (v === 0 || v === '0') zeros++;
    const n = Number(v);
    if (!isFinite(n) && !isNaN(n)) infs++;
  }
  
  if (n_nonnull === 0) {
    return {
      n_total,
      n_null: nullCount,
      n_nonnull: 0,
      zeros,
      infs,
      tab1: {
        quantiles: { min: null, p05: null, q1: null, median: null, q3: null, p95: null, max: null, range: null, iqr: null },
        descriptive: { std: null, cv: null, kurtosis: null, mean: null, mad: null, skewness: null, sum: null, variance: null, monotonicity: null }
      },
      plots: { hist: { edges: [], counts: [] }, cdf: { x: [], y: [] }, qq: { x: [], y: [], line: { slope: null, intercept: null } }, acf: { lags: [], acf: [], confInterval: 0 }, lineSeries: { index: [], values: [] } },
      common_values: [],
      extremes: { min10: [], max10: [] }
    };
  }
  
  const vmin = min(numericValues);
  const vmax = max(numericValues);
  const q1 = quantile(numericValues, 0.25);
  const q3 = quantile(numericValues, 0.75);
  const med = median(numericValues);
  const avg = mean(numericValues);
  const std = standardDeviation(numericValues);
  const vari = variance(numericValues);
  const total = sum(numericValues);
  const skew = calculateSkewness(numericValues);
  const kurt = calculateKurtosis(numericValues);
  const mad = calculateMAD(numericValues);
  const monot = monotonicityScore(numericValues);
  const cv = avg !== 0 ? std / avg : null;
  
  return {
    n_total,
    n_null: nullCount,
    n_nonnull,
    zeros,
    infs,
    tab1: {
      quantiles: {
        min: vmin,
        p05: quantile(numericValues, 0.05),
        q1,
        median: med,
        q3,
        p95: quantile(numericValues, 0.95),
        max: vmax,
        range: vmax - vmin,
        iqr: q3 - q1
      },
      descriptive: {
        std,
        cv,
        kurtosis: kurt,
        mean: avg,
        mad,
        skewness: skew,
        sum: total,
        variance: vari,
        monotonicity: monot
      }
    },
    plots: {
      hist: createHistogramData(numericValues, 50),
      cdf: createCDFData(numericValues),
      qq: createQQData(numericValues),
      acf: createACFData(numericValues),
      lineSeries: createLineSeriesData(numericValues)
    },
    common_values: topKValueCounts(numericValues, 10),
    extremes: extremeKTables(numericValues, 10)
  };
}

// ============================================================
// Compute categorical details
// ============================================================
function computeCategoricalDetails(values: unknown[]): CategoricalDetails {
  const n_total = values.length;
  const n_null = values.filter(v => v === null || v === undefined || v === '').length;
  const n_nonnull = n_total - n_null;
  const unique = new Set(values.filter(v => v !== null && v !== undefined && v !== '')).size;
  return {
    n_total,
    n_null,
    n_nonnull,
    unique,
    top_values: topKValueCounts(values, 10)
  };
}

// ============================================================
// Alerts
// ============================================================

// Correlation alert: high-correlation pairs (numeric columns only)
function correlationAlerts(data: Record<string, unknown>[], threshold: number = 0.95): Alert[] {
  const alerts: Alert[] = [];
  if (data.length < 3) return alerts;
  
  const columns = Object.keys(data[0] || {});
  const numericCols = columns.filter(col => {
    const values = data.map(row => row[col]);
    return detectColumnType(values) === 'numeric';
  });
  
  if (numericCols.length < 2) return alerts;
  
  // Extract numeric values for each column
  const colData: Record<string, number[]> = {};
  for (const col of numericCols) {
    colData[col] = data.map(row => {
      const v = row[col];
      const n = Number(v);
      return isFinite(n) ? n : NaN;
    });
  }
  
  // Compute correlation for each pair (upper triangle)
  for (let i = 0; i < numericCols.length; i++) {
    for (let j = i + 1; j < numericCols.length; j++) {
      const col1 = numericCols[i];
      const col2 = numericCols[j];
      const arr1 = colData[col1];
      const arr2 = colData[col2];
      
      // Filter out pairs where either is NaN
      const pairs: [number, number][] = [];
      for (let k = 0; k < arr1.length; k++) {
        if (!isNaN(arr1[k]) && !isNaN(arr2[k])) {
          pairs.push([arr1[k], arr2[k]]);
        }
      }
      
      if (pairs.length < 3) continue;
      
      // Pearson correlation
      const n = pairs.length;
      const sumX = pairs.reduce((acc, p) => acc + p[0], 0);
      const sumY = pairs.reduce((acc, p) => acc + p[1], 0);
      const sumXY = pairs.reduce((acc, p) => acc + p[0] * p[1], 0);
      const sumX2 = pairs.reduce((acc, p) => acc + p[0] * p[0], 0);
      const sumY2 = pairs.reduce((acc, p) => acc + p[1] * p[1], 0);
      
      const num = n * sumXY - sumX * sumY;
      const den = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
      
      if (den === 0) continue;
      
      const corr = num / den;
      const absCorr = Math.abs(corr);
      
      if (absCorr >= threshold) {
        alerts.push({
          Message: `${col1} is highly overall correlated with ${col2}`,
          'Alert type': 'Correlation'
        });
        alerts.push({
          Message: `${col2} is highly overall correlated with ${col1}`,
          'Alert type': 'Correlation'
        });
      }
    }
  }
  
  return alerts;
}

function zeroAlerts(data: Record<string, unknown>[], threshold: number = 0.1): Alert[] {
  const alerts: Alert[] = [];
  const n = data.length;
  if (n === 0) return alerts;
  
  const columns = Object.keys(data[0]);
  for (const col of columns) {
    const values = data.map(row => row[col]);
    if (detectColumnType(values) !== 'numeric') continue;
    
    const zeros = values.filter(v => v === 0 || v === '0').length;
    const pct = zeros / n;
    
    if (zeros > 0 && pct >= threshold) {
      alerts.push({
        Message: `${col} has ${zeros} (${(pct * 100).toFixed(1)}%) zeros`,
        'Alert type': 'Zeros'
      });
    }
  }
  
  return alerts;
}

function uniqueAlerts(data: Record<string, unknown>[]): Alert[] {
  const alerts: Alert[] = [];
  const n = data.length;
  
  const columns = Object.keys(data[0] || {});
  for (const col of columns) {
    const values = data.map(row => row[col]);
    const unique = new Set(values.filter(v => v !== null && v !== undefined)).size;
    
    if (unique >= 0.8 * n) {
      alerts.push({
        Message: `${col} has too many unique values`,
        'Alert type': 'Unique'
      });
    }
  }
  
  return alerts;
}

function uniformAlerts(data: Record<string, unknown>[], bins: number = 10, tolerance: number = 0.2): Alert[] {
  const alerts: Alert[] = [];
  const columns = Object.keys(data[0] || {});
  
  for (const col of columns) {
    const values = data.map(row => row[col]);
    if (detectColumnType(values) !== 'numeric') continue;
    
    const numericValues = values.filter(isNumericValue).map(Number);
    if (numericValues.length === 0) continue;
    
    const vmin = min(numericValues);
    const vmax = max(numericValues);
    if (vmin === vmax) continue;
    
    const width = (vmax - vmin) / bins;
    const binCounts = new Array(bins).fill(0);
    
    for (const x of numericValues) {
      const idx = Math.min(Math.floor((x - vmin) / width), bins - 1);
      binCounts[idx]++;
    }
    
    const meanCount = mean(binCounts);
    if (meanCount === 0) continue;
    
    const isUniform = binCounts.every(c => Math.abs(c - meanCount) / meanCount <= tolerance);
    
    if (isUniform) {
      alerts.push({
        Message: `${col} is uniformly distributed`,
        'Alert type': 'Uniform'
      });
    }
  }
  
  return alerts;
}

// ============================================================
// Main payload builder (matching Python structure)
// ============================================================
export type ProgressCallback = (progress: number, stage: string) => void;

// Helper to yield control to the browser for UI updates
function yieldToMain(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0));
}

export async function buildUnivariatePayloadAsync(
  data: Record<string, unknown>[], 
  fileName: string,
  onProgress?: ProgressCallback
): Promise<DatasetPayload> {
  const startTime = new Date().toISOString().replace('T', ' ').split('.')[0];
  const n_rows = data.length;
  const columns = Object.keys(data[0] || {});
  const n_cols = columns.length;
  
  // Count duplicates
  const seen = new Set<string>();
  let duplicates = 0;
  for (const row of data) {
    const key = JSON.stringify(row);
    if (seen.has(key)) duplicates++;
    seen.add(key);
  }
  
  // Missing cells
  let missingCells = 0;
  for (const row of data) {
    for (const col of columns) {
      if (row[col] === null || row[col] === undefined || row[col] === '') {
        missingCells++;
      }
    }
  }
  const totalCells = n_rows * n_cols;
  
  // Build variables
  const variables: Record<string, VariableInfo> = {};
  const typeCounts = { numeric: 0, categorical: 0, datetime: 0, boolean: 0, other: 0 };
  
  // Total steps: columns (70%) + alerts (30%)
  const totalSteps = columns.length + 4; // 4 alert types
  let currentStep = 0;
  
  for (const col of columns) {
    currentStep++;
    const progressPct = Math.round((currentStep / totalSteps) * 100);
    onProgress?.(progressPct, `Analyzing: ${col}`);
    
    // Yield to browser to allow UI update
    await yieldToMain();
    
    const values = data.map(row => row[col]);
    const vtype = detectColumnType(values);
    typeCounts[vtype]++;
    
    const nullCount = values.filter(v => v === null || v === undefined || v === '').length;
    const unique = new Set(values.filter(v => v !== null && v !== undefined)).size;
    
    let details: NumericDetails | CategoricalDetails | DatetimeDetails | { note: string };
    
    if (vtype === 'numeric') {
      details = computeNumericDetails(values);
    } else if (vtype === 'categorical' || vtype === 'boolean') {
      details = computeCategoricalDetails(values);
    } else if (vtype === 'datetime') {
      const nonNull = values.filter(v => v !== null && v !== undefined && v !== '').map(String).sort();
      details = {
        n_total: values.length,
        n_null: nullCount,
        min: nonNull[0] || null,
        max: nonNull[nonNull.length - 1] || null
      };
    } else {
      details = { note: 'Unsupported data type' };
    }
    
    variables[col] = {
      name: col,
      dtype: vtype === 'numeric' ? 'Float64' : vtype === 'datetime' ? 'Datetime' : 'String',
      vtype,
      missing_count: nullCount,
      missing_pct: (nullCount / n_rows) * 100,
      unique,
      details
    };
  }
  
  // Compute alerts with progress updates
  currentStep++;
  onProgress?.(Math.round((currentStep / totalSteps) * 100), 'Computing correlations...');
  await yieldToMain();
  const correlations = correlationAlerts(data);
  
  currentStep++;
  onProgress?.(Math.round((currentStep / totalSteps) * 100), 'Checking zero values...');
  await yieldToMain();
  const zeros = zeroAlerts(data);
  
  currentStep++;
  onProgress?.(Math.round((currentStep / totalSteps) * 100), 'Checking unique values...');
  await yieldToMain();
  const uniqueAlertsResult = uniqueAlerts(data);
  
  currentStep++;
  onProgress?.(Math.round((currentStep / totalSteps) * 100), 'Checking distributions...');
  await yieldToMain();
  const uniformAlertsResult = uniformAlerts(data);
  
  return {
    meta: {
      title: 'Univariate Analysis',
      source_file: fileName,
      generated_at: startTime,
      rows: n_rows,
      cols: n_cols,
      missing_cells: missingCells,
      missing_pct: totalCells > 0 ? (missingCells / totalCells) * 100 : 0,
      duplicate_rows: duplicates,
      duplicate_pct: n_rows > 0 ? (duplicates / n_rows) * 100 : 0,
      type_counts: typeCounts
    },
    variables,
    repro: {
      platform: navigator.userAgent,
      library: 'JavaScript (simple-statistics)'
    },
    alerts: {
      correlation: correlations,
      zeros: zeros,
      unique: uniqueAlertsResult,
      uniform: uniformAlertsResult
    },
    sample_data: {
      head: data.slice(0, 10),
      tail: data.slice(-10)
    }
  };
}

// Synchronous version for backward compatibility (deprecated)
export function buildUnivariatePayload(
  data: Record<string, unknown>[], 
  fileName: string,
  onProgress?: ProgressCallback
): DatasetPayload {
  const startTime = new Date().toISOString().replace('T', ' ').split('.')[0];
  const n_rows = data.length;
  const columns = Object.keys(data[0] || {});
  const n_cols = columns.length;
  
  const seen = new Set<string>();
  let duplicates = 0;
  for (const row of data) {
    const key = JSON.stringify(row);
    if (seen.has(key)) duplicates++;
    seen.add(key);
  }
  
  let missingCells = 0;
  for (const row of data) {
    for (const col of columns) {
      if (row[col] === null || row[col] === undefined || row[col] === '') {
        missingCells++;
      }
    }
  }
  const totalCells = n_rows * n_cols;
  
  const variables: Record<string, VariableInfo> = {};
  const typeCounts = { numeric: 0, categorical: 0, datetime: 0, boolean: 0, other: 0 };
  
  for (const col of columns) {
    const values = data.map(row => row[col]);
    const vtype = detectColumnType(values);
    typeCounts[vtype]++;
    
    const nullCount = values.filter(v => v === null || v === undefined || v === '').length;
    const unique = new Set(values.filter(v => v !== null && v !== undefined)).size;
    
    let details: NumericDetails | CategoricalDetails | DatetimeDetails | { note: string };
    
    if (vtype === 'numeric') {
      details = computeNumericDetails(values);
    } else if (vtype === 'categorical' || vtype === 'boolean') {
      details = computeCategoricalDetails(values);
    } else if (vtype === 'datetime') {
      const nonNull = values.filter(v => v !== null && v !== undefined && v !== '').map(String).sort();
      details = {
        n_total: values.length,
        n_null: nullCount,
        min: nonNull[0] || null,
        max: nonNull[nonNull.length - 1] || null
      };
    } else {
      details = { note: 'Unsupported data type' };
    }
    
    variables[col] = {
      name: col,
      dtype: vtype === 'numeric' ? 'Float64' : vtype === 'datetime' ? 'Datetime' : 'String',
      vtype,
      missing_count: nullCount,
      missing_pct: (nullCount / n_rows) * 100,
      unique,
      details
    };
  }
  
  const correlations = correlationAlerts(data);
  const zeros = zeroAlerts(data);
  const uniqueAlertsResult = uniqueAlerts(data);
  const uniformAlertsResult = uniformAlerts(data);
  
  return {
    meta: {
      title: 'Univariate Analysis',
      source_file: fileName,
      generated_at: startTime,
      rows: n_rows,
      cols: n_cols,
      missing_cells: missingCells,
      missing_pct: totalCells > 0 ? (missingCells / totalCells) * 100 : 0,
      duplicate_rows: duplicates,
      duplicate_pct: n_rows > 0 ? (duplicates / n_rows) * 100 : 0,
      type_counts: typeCounts
    },
    variables,
    repro: {
      platform: navigator.userAgent,
      library: 'JavaScript (simple-statistics)'
    },
    alerts: {
      correlation: correlations,
      zeros: zeros,
      unique: uniqueAlertsResult,
      uniform: uniformAlertsResult
    },
    sample_data: {
      head: data.slice(0, 10),
      tail: data.slice(-10)
    }
  };
}

// ============================================================
// Formatting helpers
// ============================================================
export function formatNumber(value: number | null | undefined, decimals: number = 6): string {
  if (value === null || value === undefined) return '—';
  if (!isFinite(value)) return '—';
  
  const ax = Math.abs(value);
  if (ax !== 0 && (ax < 1e-4 || ax >= 1e6)) {
    return value.toExponential(4);
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

export function formatPercent(value: number | null | undefined, decimals: number = 3): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  return `${value.toFixed(decimals)}%`;
}
