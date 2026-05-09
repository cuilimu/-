import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  calculatePearsonCorrelation,
  calculateSpearmanCorrelation,
  calculateKendallTau,
  calculateCovariance,
  createCrosstab,
  calculateChiSquare,
  calculateBoxPlotData,
  extractNumericColumn,
  extractCategoryColumn,
  isColumnNumeric,
  getUniqueCount,
  iterativeSortNumbers,
  CrosstabData,
  ChiSquareResults,
  BoxPlotData,
} from '@/lib/bivariateStatistics';

export interface BivariateStatistics {
  n: number;
  uniqueX: number;
  uniqueY: number;
  xIsNumeric: boolean;
  yIsNumeric: boolean;
  yUniqueCount: number;
  crosstab: CrosstabData;
  chiSquare: ChiSquareResults;
  correlations: {
    pearson: number | null;
    spearman: number | null;
    kendall: number | null;
    covariance: number | null;
  } | null;
  conditionalStats: Array<{
    y: string;
    count: number;
    mean: number;
    std: number;
    min: number;
    q25: number;
    median: number;
    q75: number;
    max: number;
  }> | null;
  boxPlotData: BoxPlotData[] | null;
  canShowBoxPlot: boolean;
}

interface UseBivariateAnalysisResult {
  statistics: BivariateStatistics | null;
  isLoading: boolean;
  progress: number;
  progressStage: string;
  progressSubStage: string;
  progressSubPercent: number;
  error: string | null;
  columnTypes: Record<string, 'numeric' | 'categorical'>;
}

// Cache for Y-dependent computations
interface YCache {
  varY: string;
  yRaw: unknown[];
  yCats: string[];
  yIsNumeric: boolean;
  yUniqueCount: number;
}

// Chunk size for processing large arrays
const CHUNK_SIZE = 50000;

// Yield to main thread
const yieldToMain = () => new Promise<void>(resolve => setTimeout(resolve, 0));

// Process array in chunks with progress callback
async function processInChunks<T, R>(
  array: T[],
  processor: (item: T, index: number) => R,
  onProgress?: (percent: number) => void
): Promise<R[]> {
  const results: R[] = [];
  const total = array.length;
  
  for (let i = 0; i < total; i += CHUNK_SIZE) {
    const chunk = array.slice(i, Math.min(i + CHUNK_SIZE, total));
    for (let j = 0; j < chunk.length; j++) {
      results.push(processor(chunk[j], i + j));
    }
    if (onProgress) {
      onProgress(Math.min(100, Math.round(((i + chunk.length) / total) * 100)));
    }
    await yieldToMain();
  }
  
  return results;
}

export function useBivariateAnalysis(
  data: Record<string, unknown>[],
  varX: string,
  varY: string,
  columns: string[]
): UseBivariateAnalysisResult {
  const [statistics, setStatistics] = useState<BivariateStatistics | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStage, setProgressStage] = useState('');
  const [progressSubStage, setProgressSubStage] = useState('');
  const [progressSubPercent, setProgressSubPercent] = useState(0);
  const [error, setError] = useState<string | null>(null);
  
  // Y-cache ref to persist across X changes
  const yCacheRef = useRef<YCache | null>(null);
  
  // Computation ID to handle race conditions
  const computationIdRef = useRef(0);

  // Pre-compute column types (fast operation - sample first 100 rows)
  const columnTypes = useMemo(() => {
    const types: Record<string, 'numeric' | 'categorical'> = {};
    columns.forEach(col => {
      types[col] = isColumnNumeric(data, col) ? 'numeric' : 'categorical';
    });
    return types;
  }, [data, columns]);

  // Async computation with progress updates and chunked processing
  const computeStatistics = useCallback(async () => {
    if (!varX || !varY || !data.length) {
      setStatistics(null);
      return;
    }

    const computationId = ++computationIdRef.current;
    setIsLoading(true);
    setProgress(0);
    setError(null);

    try {
      const xIsNumeric = columnTypes[varX] === 'numeric';
      const yIsNumeric = columnTypes[varY] === 'numeric';
      const dataLength = data.length;
      const isLargeDataset = dataLength > 100000;

      await yieldToMain();
      if (computationIdRef.current !== computationId) return;

      setProgressStage('Extracting data...');
      setProgress(5);

      // Check Y cache - if Y hasn't changed, reuse cached values
      let yRaw: unknown[];
      let yCats: string[];
      let yUniqueCount: number;

      if (yCacheRef.current && yCacheRef.current.varY === varY) {
        // Reuse cached Y data
        yRaw = yCacheRef.current.yRaw;
        yCats = yCacheRef.current.yCats;
        yUniqueCount = yCacheRef.current.yUniqueCount;
        setProgress(15);
      } else {
        // Compute Y data with chunked processing for large datasets
        setProgressStage('Processing Y variable...');
        
        if (isLargeDataset) {
          yRaw = await processInChunks(
            data,
            row => row[varY],
            p => setProgress(5 + Math.round(p * 0.05))
          );
          if (computationIdRef.current !== computationId) return;
          
          yCats = await processInChunks(
            data,
            row => String(row[varY] ?? ''),
            p => setProgress(10 + Math.round(p * 0.03))
          );
        } else {
          yRaw = data.map(row => row[varY]);
          yCats = extractCategoryColumn(data, varY);
        }
        
        if (computationIdRef.current !== computationId) return;
        yUniqueCount = getUniqueCount(yRaw);
        
        // Cache Y data
        yCacheRef.current = {
          varY,
          yRaw,
          yCats,
          yIsNumeric,
          yUniqueCount,
        };
        setProgress(15);
      }

      await yieldToMain();
      if (computationIdRef.current !== computationId) return;

      setProgressStage('Processing X variable...');
      let xCats: string[];
      
      if (isLargeDataset) {
        xCats = await processInChunks(
          data,
          row => String(row[varX] ?? ''),
          p => setProgress(15 + Math.round(p * 0.1))
        );
      } else {
        xCats = extractCategoryColumn(data, varX);
      }
      
      if (computationIdRef.current !== computationId) return;
      setProgress(25);

      await yieldToMain();
      if (computationIdRef.current !== computationId) return;

      setProgressStage('Building crosstab...');
      const crosstab = createCrosstab(xCats, yCats);
      setProgress(40);

      await yieldToMain();
      if (computationIdRef.current !== computationId) return;

      setProgressStage('Computing chi-square...');
      const chiSquare = calculateChiSquare(crosstab);
      setProgress(50);

      const n = dataLength;
      const uniqueX = new Set(xCats).size;
      const uniqueY = new Set(yCats).size;

      let correlations = null;
      let conditionalStats = null;

      if (xIsNumeric) {
        await yieldToMain();
        if (computationIdRef.current !== computationId) return;

        setProgressStage('Extracting numeric values...');
        let xNums: number[];
        let yNums: number[];
        
        if (isLargeDataset) {
          xNums = await processInChunks(
            data,
            row => {
              const val = row[varX];
              if (val === null || val === undefined || val === '') return NaN;
              const num = Number(val);
              return isNaN(num) ? NaN : num;
            },
            p => setProgress(50 + Math.round(p * 0.05))
          );
          if (computationIdRef.current !== computationId) return;
          
          if (yIsNumeric) {
            yNums = await processInChunks(
              data,
              row => {
                const val = row[varY];
                if (val === null || val === undefined || val === '') return NaN;
                const num = Number(val);
                return isNaN(num) ? NaN : num;
              },
              p => setProgress(55 + Math.round(p * 0.05))
            );
          } else {
            yNums = xCats.map((_, i) => i);
          }
        } else {
          xNums = extractNumericColumn(data, varX);
          yNums = yIsNumeric ? extractNumericColumn(data, varY) : xCats.map((_, i) => i);
        }
        
        if (computationIdRef.current !== computationId) return;
        setProgress(60);

        // Build aligned array with chunking for large datasets
        setProgressStage('Aligning data...');
        const aligned: { x: number; y: number; yCat: string }[] = [];
        
        if (isLargeDataset) {
          for (let i = 0; i < xNums.length; i += CHUNK_SIZE) {
            const end = Math.min(i + CHUNK_SIZE, xNums.length);
            for (let j = i; j < end; j++) {
              if (!isNaN(xNums[j])) {
                aligned.push({ x: xNums[j], y: yNums[j], yCat: yCats[j] });
              }
            }
            await yieldToMain();
            if (computationIdRef.current !== computationId) return;
            setProgress(60 + Math.round(((i + CHUNK_SIZE) / xNums.length) * 5));
          }
        } else {
          for (let i = 0; i < xNums.length; i++) {
            if (!isNaN(xNums[i])) {
              aligned.push({ x: xNums[i], y: yNums[i], yCat: yCats[i] });
            }
          }
        }

        const x = aligned.map(p => p.x);
        const y = aligned.map(p => p.y);

        // Calculate correlations if both numeric
        if (yIsNumeric) {
          await yieldToMain();
          if (computationIdRef.current !== computationId) return;

          setProgressStage('Computing correlations...');
          setProgressSubStage('');
          setProgressSubPercent(0);

          // Pearson (fast - O(n))
          setProgressSubStage('Pearson correlation (1/3)');
          setProgressSubPercent(0);
          await yieldToMain();
          const pearson = calculatePearsonCorrelation(x, y);
          setProgressSubPercent(33);
          setProgress(68);
          await yieldToMain();
          if (computationIdRef.current !== computationId) return;
          
          // Spearman (medium - O(n log n))
          setProgressSubStage('Spearman correlation (2/3)');
          await yieldToMain();
          const spearman = calculateSpearmanCorrelation(x, y);
          setProgressSubPercent(66);
          setProgress(71);
          await yieldToMain();
          if (computationIdRef.current !== computationId) return;
          
          // Kendall (slowest - O(n log n) with high constant)
          setProgressSubStage('Kendall tau-b (3/3) — may take longer');
          await yieldToMain();
          const kendall = calculateKendallTau(x, y);
          setProgressSubPercent(100);
          setProgress(74);
          await yieldToMain();
          if (computationIdRef.current !== computationId) return;
          
          setProgressSubStage('');
          setProgressSubPercent(0);
          setProgressStage('Computing covariance...');
          correlations = {
            pearson,
            spearman,
            kendall,
            covariance: calculateCovariance(x, y),
          };
          setProgress(75);
        }

        // Calculate conditional stats when Y is categorical OR numeric with ≤5 unique values
        if (!yIsNumeric || yUniqueCount <= 5) {
          await yieldToMain();
          if (computationIdRef.current !== computationId) return;

          setProgressStage('Computing conditional statistics...');
          const groups: Record<string, number[]> = {};
          
          // Process in chunks for large datasets
          if (isLargeDataset) {
            for (let i = 0; i < aligned.length; i += CHUNK_SIZE) {
              const end = Math.min(i + CHUNK_SIZE, aligned.length);
              for (let j = i; j < end; j++) {
                const p = aligned[j];
                if (!groups[p.yCat]) groups[p.yCat] = [];
                groups[p.yCat].push(p.x);
              }
              await yieldToMain();
              if (computationIdRef.current !== computationId) return;
            }
          } else {
            aligned.forEach(p => {
              if (!groups[p.yCat]) groups[p.yCat] = [];
              groups[p.yCat].push(p.x);
            });
          }

          conditionalStats = Object.entries(groups).map(([category, values]) => {
            // Use iterative sort to avoid stack overflow on large groups
            const sorted = iterativeSortNumbers(values);
            const count = sorted.length;
            const sum = sorted.reduce((a, b) => a + b, 0);
            const mean = sum / count;
            const variance = sorted.reduce((acc, v) => acc + (v - mean) ** 2, 0) / (count - 1);
            const std = Math.sqrt(variance);

            return {
              y: category,
              count,
              mean,
              std: isNaN(std) ? 0 : std,
              min: sorted[0],
              q25: sorted[Math.floor(count * 0.25)],
              median: sorted[Math.floor(count * 0.5)],
              q75: sorted[Math.floor(count * 0.75)],
              max: sorted[count - 1],
            };
          }).sort((a, b) => b.count - a.count);
          setProgress(85);
        }
      }

      // Calculate box plot data
      await yieldToMain();
      if (computationIdRef.current !== computationId) return;

      setProgressStage('Computing box plots...');
      let boxPlotData: BoxPlotData[] | null = null;
      const canShowBoxPlot =
        (xIsNumeric && !yIsNumeric) ||
        (!xIsNumeric && yIsNumeric) ||
        (xIsNumeric && yIsNumeric && yUniqueCount <= 5);

      if (canShowBoxPlot) {
        if (xIsNumeric && (!yIsNumeric || yUniqueCount <= 5)) {
          const numVals = extractNumericColumn(data, varX);
          boxPlotData = calculateBoxPlotData(numVals, yCats);
        } else if (!xIsNumeric && yIsNumeric) {
          const numVals = extractNumericColumn(data, varY);
          boxPlotData = calculateBoxPlotData(numVals, xCats);
        }
      }
      setProgress(95);

      await yieldToMain();
      if (computationIdRef.current !== computationId) return;

      setProgressStage('Finalizing...');
      setProgress(100);

      setStatistics({
        n,
        uniqueX,
        uniqueY,
        xIsNumeric,
        yIsNumeric,
        yUniqueCount,
        crosstab,
        chiSquare,
        correlations,
        conditionalStats,
        boxPlotData,
        canShowBoxPlot,
      });

    } catch (err) {
      if (computationIdRef.current === computationId) {
        setError(err instanceof Error ? err.message : 'Analysis failed');
        setStatistics(null);
      }
    } finally {
      if (computationIdRef.current === computationId) {
        setIsLoading(false);
      }
    }
  }, [varX, varY, data, columnTypes]);

  // Trigger computation when variables change
  useEffect(() => {
    computeStatistics();
  }, [computeStatistics]);

  return {
    statistics,
    isLoading,
    progress,
    progressStage,
    progressSubStage,
    progressSubPercent,
    error,
    columnTypes,
  };
}
