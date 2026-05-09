// Bivariate Analysis Statistics
// Based on Python notebook: Bivariate_Analysis_One_Variable.ipynb

export interface CrosstabData {
  xCategories: string[];
  yCategories: string[];
  jointFreq: number[][];  // [xIdx][yIdx]
  jointRelFreq: number[][];
  marginalX: number[];
  marginalY: number[];
  total: number;
}

export interface CorrelationMeasures {
  pearson: number | null;
  spearman: number | null;
  kendall: number | null;
  covariance: number | null;
}

export interface ChiSquareResults {
  chiSquare: number;
  phiCoefficient: number | null;  // Only for 2x2 tables
  cramersV: number;
  contingencyCoefficient: number;
  degreesOfFreedom: number;
}

export interface BoxPlotData {
  category: string;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  outliers: number[];
  count: number;
  mean: number;
}

export interface ScatterData {
  x: number[];
  y: number[];
  sampleSize: number;
}

// ============================================================
// Correlation Measures
// ============================================================

export function calculatePearsonCorrelation(x: number[], y: number[]): number | null {
  if (x.length !== y.length || x.length < 2) return null;
  
  const n = x.length;
  const meanX = x.reduce((a, b) => a + b, 0) / n;
  const meanY = y.reduce((a, b) => a + b, 0) / n;
  
  let sumXY = 0, sumX2 = 0, sumY2 = 0;
  for (let i = 0; i < n; i++) {
    const dx = x[i] - meanX;
    const dy = y[i] - meanY;
    sumXY += dx * dy;
    sumX2 += dx * dx;
    sumY2 += dy * dy;
  }
  
  const denom = Math.sqrt(sumX2 * sumY2);
  if (denom === 0) return null;
  
  return sumXY / denom;
}

/**
 * Iterative (bottom-up) merge sort to avoid stack overflow on large arrays
 * Returns a new sorted array without modifying the original
 */
function iterativeMergeSort<T>(arr: T[], compare: (a: T, b: T) => number): T[] {
  const n = arr.length;
  if (n <= 1) return arr.slice();
  
  let source = arr.slice();
  let target = new Array(n);
  
  for (let width = 1; width < n; width *= 2) {
    for (let i = 0; i < n; i += 2 * width) {
      const left = i;
      const mid = Math.min(i + width, n);
      const right = Math.min(i + 2 * width, n);
      
      // Merge source[left..mid) and source[mid..right) into target
      let li = left, ri = mid, k = left;
      while (li < mid && ri < right) {
        if (compare(source[li], source[ri]) <= 0) {
          target[k++] = source[li++];
        } else {
          target[k++] = source[ri++];
        }
      }
      while (li < mid) target[k++] = source[li++];
      while (ri < right) target[k++] = source[ri++];
    }
    [source, target] = [target, source];
  }
  
  return source;
}

/**
 * Specialized iterative merge sort for number arrays (faster than generic version)
 * Uses in-place comparison for better performance
 * Exported for use in conditional stats calculation
 */
export function iterativeSortNumbers(arr: number[]): number[] {
  const n = arr.length;
  if (n <= 1) return arr.slice();
  
  let source = arr.slice();
  let target = new Array(n);
  
  for (let width = 1; width < n; width *= 2) {
    for (let i = 0; i < n; i += 2 * width) {
      const left = i;
      const mid = Math.min(i + width, n);
      const right = Math.min(i + 2 * width, n);
      
      let li = left, ri = mid, k = left;
      while (li < mid && ri < right) {
        if (source[li] <= source[ri]) {
          target[k++] = source[li++];
        } else {
          target[k++] = source[ri++];
        }
      }
      while (li < mid) target[k++] = source[li++];
      while (ri < right) target[k++] = source[ri++];
    }
    [source, target] = [target, source];
  }
  
  return source;
}

// Alias for internal use
const iterativeMergeSortNumbers = iterativeSortNumbers;

export function calculateSpearmanCorrelation(x: number[], y: number[]): number | null {
  if (x.length !== y.length || x.length < 2) return null;
  
  const rankArray = (arr: number[]): number[] => {
    const indexed = arr.map((v, i) => ({ v, i }));
    // Use iterative merge sort to avoid stack overflow
    const sorted = iterativeMergeSort(indexed, (a, b) => a.v - b.v);
    const ranks = new Array(arr.length);
    for (let i = 0; i < sorted.length; i++) {
      ranks[sorted[i].i] = i + 1;
    }
    return ranks;
  };
  
  const rankX = rankArray(x);
  const rankY = rankArray(y);
  
  return calculatePearsonCorrelation(rankX, rankY);
}

/**
 * Calculate Kendall's Tau-b using O(n log n) merge-sort algorithm
 * Based on Knight (1966) - counts inversions via modified merge sort
 */
export function calculateKendallTau(x: number[], y: number[]): number | null {
  if (x.length !== y.length || x.length < 2) return null;
  
  const n = x.length;
  
  // Create pairs and use iterative sort to avoid stack overflow
  const pairs = x.map((xi, i) => ({ x: xi, y: y[i] }));
  const sortedPairs = iterativeMergeSort(pairs, (a, b) => a.x - b.x || a.y - b.y);
  
  // Extract y values in sorted-by-x order
  const yValues = sortedPairs.map(p => p.y);
  
  // Count ties in x
  const tiesX = countTiePairs(sortedPairs.map(p => p.x));
  
  // Count inversions and ties in y using merge sort
  const { inversions, ties: tiesY } = mergeCountInversions(yValues.slice());
  
  // Count joint ties (pairs tied in both x and y)
  const jointTies = countJointTies(sortedPairs);
  
  // Calculate Kendall Tau-b
  const n0 = (n * (n - 1)) / 2;
  const numerator = n0 - tiesX - tiesY + jointTies - 2 * inversions;
  const denominator = Math.sqrt((n0 - tiesX) * (n0 - tiesY));
  
  if (denominator === 0) return null;
  
  return numerator / denominator;
}

/**
 * Count the number of tied pairs in an array
 * Returns sum of t*(t-1)/2 for each group of t ties
 */
function countTiePairs(arr: number[]): number {
  const counts = new Map<number, number>();
  for (const val of arr) {
    counts.set(val, (counts.get(val) || 0) + 1);
  }
  
  let tiePairs = 0;
  for (const count of counts.values()) {
    if (count > 1) {
      tiePairs += (count * (count - 1)) / 2;
    }
  }
  return tiePairs;
}

/**
 * Count pairs tied in both x and y
 */
function countJointTies(pairs: { x: number; y: number }[]): number {
  const counts = new Map<string, number>();
  for (const p of pairs) {
    const key = `${p.x},${p.y}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  
  let jointTies = 0;
  for (const count of counts.values()) {
    if (count > 1) {
      jointTies += (count * (count - 1)) / 2;
    }
  }
  return jointTies;
}

/**
 * Iterative (bottom-up) merge sort that counts inversions in O(n log n)
 * Uses O(1) stack frames to avoid stack overflow on large datasets
 */
function mergeCountInversions(arr: number[]): { sorted: number[]; inversions: number; ties: number } {
  const n = arr.length;
  if (n <= 1) return { sorted: arr.slice(), inversions: 0, ties: 0 };
  
  let inversions = 0;
  let ties = 0;
  
  // Work arrays to avoid repeated allocations
  let source = arr.slice();
  let target = new Array(n);
  
  // Bottom-up merge sort: start with width=1, double each pass
  for (let width = 1; width < n; width *= 2) {
    for (let i = 0; i < n; i += 2 * width) {
      const left = i;
      const mid = Math.min(i + width, n);
      const right = Math.min(i + 2 * width, n);
      
      // Merge source[left..mid) and source[mid..right) into target[left..right)
      const result = mergeAndCountInPlace(source, target, left, mid, right);
      inversions += result.inversions;
      ties += result.ties;
    }
    // Swap source and target for next pass
    [source, target] = [target, source];
  }
  
  return { sorted: source, inversions, ties };
}

/**
 * Merge source[left..mid) and source[mid..right) into target, counting inversions and ties
 */
function mergeAndCountInPlace(
  source: number[],
  target: number[],
  left: number,
  mid: number,
  right: number
): { inversions: number; ties: number } {
  let inversions = 0;
  let ties = 0;
  let i = left;
  let j = mid;
  let k = left;
  
  while (i < mid && j < right) {
    if (source[i] < source[j]) {
      target[k++] = source[i++];
    } else if (source[i] > source[j]) {
      // All remaining elements in left subarray form inversions with source[j]
      inversions += mid - i;
      target[k++] = source[j++];
    } else {
      // Equal values: count consecutive duplicates in each subarray
      const val = source[i];
      let leftCount = 0;
      let rightCount = 0;
      while (i < mid && source[i] === val) { leftCount++; i++; }
      while (j < right && source[j] === val) { rightCount++; j++; }
      // Cross-ties between left and right subarrays
      ties += leftCount * rightCount;
      // Add all equal elements to target
      for (let c = 0; c < leftCount + rightCount; c++) target[k++] = val;
    }
  }
  
  // Copy remaining elements
  while (i < mid) target[k++] = source[i++];
  while (j < right) target[k++] = source[j++];
  
  return { inversions, ties };
}

export function calculateCovariance(x: number[], y: number[]): number | null {
  if (x.length !== y.length || x.length < 2) return null;
  
  const n = x.length;
  const meanX = x.reduce((a, b) => a + b, 0) / n;
  const meanY = y.reduce((a, b) => a + b, 0) / n;
  
  let sumXY = 0;
  for (let i = 0; i < n; i++) {
    sumXY += (x[i] - meanX) * (y[i] - meanY);
  }
  
  return sumXY / (n - 1);
}

export function getAllCorrelations(x: number[], y: number[]): CorrelationMeasures {
  return {
    pearson: calculatePearsonCorrelation(x, y),
    spearman: calculateSpearmanCorrelation(x, y),
    kendall: calculateKendallTau(x, y),
    covariance: calculateCovariance(x, y),
  };
}

// ============================================================
// Cross-tabulation (Contingency Table)
// ============================================================

export function createCrosstab(
  xValues: (string | number)[],
  yValues: (string | number)[]
): CrosstabData {
  if (xValues.length !== yValues.length) {
    throw new Error("Arrays must have equal length");
  }
  
  // Get unique categories
  const xCats = [...new Set(xValues.map(String))].sort();
  const yCats = [...new Set(yValues.map(String))].sort();
  
  // Create O(1) lookup maps instead of using indexOf
  const xIdxMap = new Map(xCats.map((cat, i) => [cat, i]));
  const yIdxMap = new Map(yCats.map((cat, i) => [cat, i]));
  
  // Initialize joint frequency matrix
  const jointFreq: number[][] = xCats.map(() => yCats.map(() => 0));
  
  // Count frequencies with O(1) lookups
  for (let i = 0; i < xValues.length; i++) {
    const xIdx = xIdxMap.get(String(xValues[i]));
    const yIdx = yIdxMap.get(String(yValues[i]));
    if (xIdx !== undefined && yIdx !== undefined) {
      jointFreq[xIdx][yIdx]++;
    }
  }
  
  const total = xValues.length;
  
  // Calculate relative frequencies
  const jointRelFreq = jointFreq.map(row => 
    row.map(val => val / total)
  );
  
  // Marginal frequencies
  const marginalX = jointFreq.map(row => row.reduce((a, b) => a + b, 0));
  const marginalY = yCats.map((_, yIdx) => 
    jointFreq.reduce((sum, row) => sum + row[yIdx], 0)
  );
  
  return {
    xCategories: xCats,
    yCategories: yCats,
    jointFreq,
    jointRelFreq,
    marginalX,
    marginalY,
    total,
  };
}

// ============================================================
// Chi-Square and Related Measures
// ============================================================

export function calculateChiSquare(crosstab: CrosstabData): ChiSquareResults {
  const { jointFreq, marginalX, marginalY, total, xCategories, yCategories } = crosstab;
  const k = xCategories.length;
  const l = yCategories.length;
  
  // Calculate expected frequencies and chi-square
  let chiSquare = 0;
  for (let i = 0; i < k; i++) {
    for (let j = 0; j < l; j++) {
      const observed = jointFreq[i][j];
      const expected = (marginalX[i] * marginalY[j]) / total;
      if (expected > 0) {
        chiSquare += Math.pow(observed - expected, 2) / expected;
      }
    }
  }
  
  // Phi coefficient (only for 2x2 tables)
  let phiCoefficient: number | null = null;
  if (k === 2 && l === 2) {
    phiCoefficient = Math.sqrt(chiSquare / total);
  }
  
  // Cramér's V
  const cramersV = Math.sqrt(chiSquare / (total * Math.min(k - 1, l - 1)));
  
  // Contingency Coefficient
  const contingencyCoefficient = Math.sqrt(chiSquare / (chiSquare + total));
  
  // Degrees of freedom
  const degreesOfFreedom = (k - 1) * (l - 1);
  
  return {
    chiSquare,
    phiCoefficient,
    cramersV,
    contingencyCoefficient,
    degreesOfFreedom,
  };
}

// ============================================================
// Box Plot Data (grouped by category)
// ============================================================

export function calculateBoxPlotData(
  numericValues: number[],
  categoryValues: (string | number)[]
): BoxPlotData[] {
  if (numericValues.length !== categoryValues.length) {
    throw new Error("Arrays must have equal length");
  }
  
  // Group values by category
  const groups: Record<string, number[]> = {};
  for (let i = 0; i < numericValues.length; i++) {
    const cat = String(categoryValues[i]);
    if (!groups[cat]) groups[cat] = [];
    if (numericValues[i] !== null && !isNaN(numericValues[i])) {
      groups[cat].push(numericValues[i]);
    }
  }
  
  const result: BoxPlotData[] = [];
  
  for (const [category, values] of Object.entries(groups)) {
    if (values.length === 0) continue;
    
    // Use iterative merge sort to avoid stack overflow on large groups
    const sorted = iterativeMergeSortNumbers(values);
    const n = sorted.length;
    
    const q1 = sorted[Math.floor(n * 0.25)];
    const median = sorted[Math.floor(n * 0.5)];
    const q3 = sorted[Math.floor(n * 0.75)];
    const iqr = q3 - q1;
    
    const lowerFence = q1 - 1.5 * iqr;
    const upperFence = q3 + 1.5 * iqr;
    
    const outliers: number[] = [];
    const nonOutliers: number[] = [];
    for (let i = 0; i < sorted.length; i++) {
      if (sorted[i] < lowerFence || sorted[i] > upperFence) {
        outliers.push(sorted[i]);
      } else {
        nonOutliers.push(sorted[i]);
      }
    }
    
    result.push({
      category,
      min: nonOutliers.length > 0 ? nonOutliers[0] : sorted[0],
      q1,
      median,
      q3,
      max: nonOutliers.length > 0 ? nonOutliers[nonOutliers.length - 1] : sorted[n - 1],
      outliers,
      count: n,
      mean: values.reduce((a, b) => a + b, 0) / n,
    });
  }
  
  // Sort categories - safe for small number of categories
  return result.sort((a, b) => a.category.localeCompare(b.category));
}

// ============================================================
// Scatter Plot Data (with optional sampling)
// ============================================================

export function createScatterData(
  x: number[],
  y: number[],
  samplePercent: number = 100,
  seed: number = 12345
): ScatterData {
  if (x.length !== y.length) {
    throw new Error("Arrays must have equal length");
  }
  
  // Filter out nulls/NaNs
  const valid: { x: number; y: number }[] = [];
  for (let i = 0; i < x.length; i++) {
    if (x[i] !== null && y[i] !== null && !isNaN(x[i]) && !isNaN(y[i])) {
      valid.push({ x: x[i], y: y[i] });
    }
  }
  
  if (samplePercent >= 100 || valid.length <= 100) {
    return {
      x: valid.map(p => p.x),
      y: valid.map(p => p.y),
      sampleSize: valid.length,
    };
  }
  
  // Seeded random sampling
  const sampleSize = Math.max(1, Math.floor(valid.length * samplePercent / 100));
  const seededRandom = (s: number) => {
    const x = Math.sin(s) * 10000;
    return x - Math.floor(x);
  };
  
  const sampled: typeof valid = [];
  const indices = new Set<number>();
  let s = seed;
  while (indices.size < sampleSize) {
    const idx = Math.floor(seededRandom(s) * valid.length);
    if (!indices.has(idx)) {
      indices.add(idx);
      sampled.push(valid[idx]);
    }
    s++;
  }
  
  return {
    x: sampled.map(p => p.x),
    y: sampled.map(p => p.y),
    sampleSize: sampled.length,
  };
}

// ============================================================
// ============================================================
// Confidence Ellipse Calculations
// ============================================================

export interface EllipseParams {
  centerX: number;
  centerY: number;
  radiusX: number;
  radiusY: number;
  rotation: number; // in radians
}

// Chi-squared quantiles for 2 degrees of freedom
const CHI2_QUANTILES: Record<number, number> = {
  50: 1.386,
  60: 1.833,
  70: 2.408,
  75: 2.773,
  80: 3.219,
  85: 3.794,
  90: 4.605,
  95: 5.991,
  99: 9.210,
};

export function getChiSquaredQuantile(confidenceLevel: number): number {
  // Linear interpolation for levels not in lookup
  const levels = Object.keys(CHI2_QUANTILES).map(Number).sort((a, b) => a - b);
  
  if (confidenceLevel <= levels[0]) return CHI2_QUANTILES[levels[0]];
  if (confidenceLevel >= levels[levels.length - 1]) return CHI2_QUANTILES[levels[levels.length - 1]];
  
  for (let i = 0; i < levels.length - 1; i++) {
    if (confidenceLevel >= levels[i] && confidenceLevel <= levels[i + 1]) {
      const t = (confidenceLevel - levels[i]) / (levels[i + 1] - levels[i]);
      return CHI2_QUANTILES[levels[i]] * (1 - t) + CHI2_QUANTILES[levels[i + 1]] * t;
    }
  }
  return CHI2_QUANTILES[95]; // fallback
}

export function calculateEllipseParams(
  x: number[],
  y: number[],
  confidenceLevel: number
): EllipseParams | null {
  if (x.length !== y.length || x.length < 3) return null;

  const n = x.length;
  const meanX = x.reduce((a, b) => a + b, 0) / n;
  const meanY = y.reduce((a, b) => a + b, 0) / n;

  // Calculate covariance matrix elements
  let varX = 0, varY = 0, covXY = 0;
  for (let i = 0; i < n; i++) {
    const dx = x[i] - meanX;
    const dy = y[i] - meanY;
    varX += dx * dx;
    varY += dy * dy;
    covXY += dx * dy;
  }
  varX /= (n - 1);
  varY /= (n - 1);
  covXY /= (n - 1);

  // Eigenvalue calculation for 2x2 symmetric matrix
  const trace = varX + varY;
  const det = varX * varY - covXY * covXY;
  const discriminant = Math.sqrt(Math.max(0, trace * trace / 4 - det));
  
  const lambda1 = trace / 2 + discriminant;
  const lambda2 = trace / 2 - discriminant;

  if (lambda1 <= 0 || lambda2 <= 0) return null;

  // Calculate rotation angle from eigenvector
  let rotation = 0;
  if (Math.abs(covXY) > 1e-10) {
    rotation = Math.atan2(lambda1 - varX, covXY);
  } else if (varY > varX) {
    rotation = Math.PI / 2;
  }

  // Scale by chi-squared quantile
  const chi2 = getChiSquaredQuantile(confidenceLevel);
  const scale = Math.sqrt(chi2);

  return {
    centerX: meanX,
    centerY: meanY,
    radiusX: Math.sqrt(lambda1) * scale,
    radiusY: Math.sqrt(lambda2) * scale,
    rotation,
  };
}

export function generateEllipsePoints(
  params: EllipseParams,
  numPoints: number = 100
): { x: number; y: number }[] {
  const points: { x: number; y: number }[] = [];
  const { centerX, centerY, radiusX, radiusY, rotation } = params;
  
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);

  for (let i = 0; i <= numPoints; i++) {
    const theta = (2 * Math.PI * i) / numPoints;
    const px = radiusX * Math.cos(theta);
    const py = radiusY * Math.sin(theta);
    
    // Rotate and translate
    const x = centerX + px * cos - py * sin;
    const y = centerY + px * sin + py * cos;
    
    points.push({ x, y });
  }

  return points;
}

// Helper to count unique values
export function getUniqueCount(values: (string | number | unknown)[]): number {
  return new Set(values.map(v => String(v ?? ''))).size;
}

// ============================================================
// Helper: Get numeric values from raw data
// ============================================================

export function extractNumericColumn(
  data: Record<string, unknown>[],
  column: string
): number[] {
  return data.map(row => {
    const val = row[column];
    if (val === null || val === undefined || val === '') return NaN;
    const num = Number(val);
    return isNaN(num) ? NaN : num;
  });
}

export function extractCategoryColumn(
  data: Record<string, unknown>[],
  column: string
): string[] {
  return data.map(row => String(row[column] ?? ''));
}

export function isColumnNumeric(
  data: Record<string, unknown>[],
  column: string
): boolean {
  const values = data.slice(0, 100).map(row => row[column]);
  const nonEmpty = values.filter(v => v !== null && v !== undefined && v !== '');
  const numericCount = nonEmpty.filter(v => !isNaN(Number(v))).length;
  return numericCount > nonEmpty.length * 0.8;
}
