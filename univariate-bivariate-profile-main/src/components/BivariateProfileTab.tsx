import { useMemo, useCallback, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Download, Hash, Table2, TrendingUp, BarChart3 } from 'lucide-react';
import { ConditionalFrequencyTable } from './ConditionalFrequencyTable';
import { BoxPlotChart } from './BoxPlotChart';
import { BivariateStatistics } from '@/hooks/useBivariateAnalysis';
import { CrosstabData } from '@/lib/bivariateStatistics';
import {
  calculatePearsonCorrelation,
  calculateSpearmanCorrelation,
  calculateKendallTau,
  calculateEllipseParams,
  generateEllipsePoints,
  extractNumericColumn,
} from '@/lib/bivariateStatistics';
import {
  ScatterChart as RechartsScatter,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Customized,
} from 'recharts';

interface BivariateProfileTabProps {
  varX: string;
  varY: string;
  statistics: BivariateStatistics;
  data: Record<string, unknown>[];
  onExportHTML: () => void;
}

function KPIItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold font-mono">{value}</p>
    </div>
  );
}

function fmt(v: number | null | undefined, digits = 6): string {
  if (v == null || isNaN(v)) return '—';
  return v.toFixed(digits);
}

/** Flat frequency rows derived from crosstab */
function JointFrequencyTable({ crosstab, title, showRel }: { crosstab: CrosstabData; title: string; showRel?: boolean }) {
  const rows = useMemo(() => {
    const result: { x: string; y: string; count: number; rel?: number }[] = [];
    const { xCategories, yCategories, jointFreq, jointRelFreq } = crosstab;
    for (let xi = 0; xi < xCategories.length; xi++) {
      for (let yi = 0; yi < yCategories.length; yi++) {
        result.push({
          x: xCategories[xi],
          y: yCategories[yi],
          count: jointFreq[xi][yi],
          rel: showRel ? jointRelFreq[xi][yi] : undefined,
        });
      }
    }
    // Sort descending by count
    result.sort((a, b) => b.count - a.count);
    return result;
  }, [crosstab, showRel]);

  // Show head 5 + tail 5 if large
  const MAX = 10;
  const truncated = rows.length > MAX;
  const displayRows = truncated ? [...rows.slice(0, 5), null, ...rows.slice(-5)] : rows;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold text-muted-foreground">{title}</CardTitle>
        {truncated && (
          <CardDescription className="text-xs">
            Showing head 5 and tail 5 rows (total {rows.length}).
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="max-h-[300px] overflow-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="text-left p-1.5 border-b border-border text-muted-foreground font-semibold">x</th>
                <th className="text-left p-1.5 border-b border-border text-muted-foreground font-semibold">y</th>
                <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">count</th>
                {showRel && <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">rel</th>}
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row, i) =>
                row === null ? (
                  <tr key={`sep-${i}`}>
                    <td colSpan={showRel ? 4 : 3} className="text-center p-1.5 text-muted-foreground border-b border-border">…</td>
                  </tr>
                ) : (
                  <tr key={i} className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">{row.x}</td>
                    <td className="p-1.5 border-b border-border">{row.y}</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{row.count.toLocaleString()}</td>
                    {showRel && <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.rel)}</td>}
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function MarginalTable({ categories, counts, total, label, showRel }: {
  categories: string[];
  counts: number[];
  total: number;
  label: string;
  showRel?: boolean;
}) {
  const rows = useMemo(() => {
    return categories.map((cat, i) => ({
      cat,
      count: counts[i],
      rel: counts[i] / total,
    })).sort((a, b) => b.count - a.count);
  }, [categories, counts, total]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="max-h-[300px] overflow-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="text-left p-1.5 border-b border-border text-muted-foreground font-semibold">{label.includes('Y') ? 'y' : 'x'}</th>
                {!showRel && <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">count</th>}
                {showRel && (
                  <>
                    <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">count</th>
                    <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">rel</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="hover:bg-muted/30">
                  <td className="p-1.5 border-b border-border">{row.cat}</td>
                  <td className="p-1.5 border-b border-border text-right font-mono">{row.count.toLocaleString()}</td>
                  {showRel && <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.rel)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function CondStatsTable({ stats }: { stats: BivariateStatistics['conditionalStats'] }) {
  if (!stats || stats.length === 0) {
    return <p className="text-xs text-muted-foreground">Not available (X must be numeric).</p>;
  }
  return (
    <div className="max-h-[300px] overflow-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {['y', 'count', 'mean', 'std', 'min', 'q25', 'median', 'q75', 'max'].map(h => (
              <th key={h} className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold first:text-left">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {stats.map((row, i) => (
            <tr key={i} className="hover:bg-muted/30">
              <td className="p-1.5 border-b border-border">{row.y}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{row.count.toLocaleString()}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.mean)}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.std)}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.min)}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.q25)}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.median)}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.q75)}</td>
              <td className="p-1.5 border-b border-border text-right font-mono">{fmt(row.max)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BivariateProfileTab({ varX, varY, statistics, data, onExportHTML }: BivariateProfileTabProps) {
  const { crosstab, chiSquare, correlations, conditionalStats, boxPlotData, canShowBoxPlot, xIsNumeric, yIsNumeric } = statistics;

  // Compute 1% sample for scatter + sample correlations
  const sampleInsights = useMemo(() => {
    if (!xIsNumeric || !yIsNumeric) return null;

    const xNums = extractNumericColumn(data, varX);
    const yNums = extractNumericColumn(data, varY);

    const valid: { x: number; y: number }[] = [];
    for (let i = 0; i < xNums.length; i++) {
      if (!isNaN(xNums[i]) && !isNaN(yNums[i])) {
        valid.push({ x: xNums[i], y: yNums[i] });
      }
    }

    if (valid.length === 0) return null;

    // 1% sample with fixed seed
    const sampleSize = Math.max(1, Math.min(Math.floor(valid.length * 0.01), 2000));
    let sampled: typeof valid;
    if (sampleSize >= valid.length) {
      sampled = valid;
    } else {
      const seededRandom = (s: number) => {
        const x = Math.sin(s) * 10000;
        return x - Math.floor(x);
      };
      sampled = [];
      const indices = new Set<number>();
      let s = 12345;
      while (indices.size < sampleSize && indices.size < valid.length) {
        const idx = Math.floor(seededRandom(s) * valid.length);
        if (!indices.has(idx)) {
          indices.add(idx);
          sampled.push(valid[idx]);
        }
        s++;
      }
    }

    const sx = sampled.map(p => p.x);
    const sy = sampled.map(p => p.y);

    return {
      x: sx,
      y: sy,
      sampleSize: sampled.length,
      totalSize: valid.length,
      pearson: calculatePearsonCorrelation(sx, sy),
      spearman: calculateSpearmanCorrelation(sx, sy),
      kendall: calculateKendallTau(sx, sy),
      ellipse80: calculateEllipseParams(sx, sy, 80) ? generateEllipsePoints(calculateEllipseParams(sx, sy, 80)!) : null,
      ellipse70: calculateEllipseParams(sx, sy, 70) ? generateEllipsePoints(calculateEllipseParams(sx, sy, 70)!) : null,
    };
  }, [data, varX, varY, xIsNumeric, yIsNumeric]);

  return (
    <div className="space-y-3">
      {/* Export Button */}
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onExportHTML} className="gap-2">
          <Download className="w-4 h-4" />
          Export as HTML
        </Button>
      </div>

      {/* Joint Empirical Distributions KPIs */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-muted-foreground">Joint Empirical Distributions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-6">
            <KPIItem label="Sample size (n)" value={statistics.n.toLocaleString()} />
            <KPIItem label="k = unique(x)" value={statistics.uniqueX.toString()} />
            <KPIItem label="l = unique(y)" value={statistics.uniqueY.toString()} />
            <KPIItem label="Cells in crosstab" value={(statistics.uniqueX * statistics.uniqueY).toString()} />
          </div>
        </CardContent>
      </Card>

      {/* Joint Absolute + Relative Frequencies (2-col) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <JointFrequencyTable crosstab={crosstab} title="Joint Absolute Frequencies (x,y)" />
        <JointFrequencyTable crosstab={crosstab} title="Joint Relative Frequencies (x,y)" showRel />
      </div>

      {/* Marginal Frequencies (3-col) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <MarginalTable
          categories={crosstab.xCategories}
          counts={crosstab.marginalX}
          total={crosstab.total}
          label="Marginal Abs Frequencies of X"
        />
        <MarginalTable
          categories={crosstab.xCategories}
          counts={crosstab.marginalX}
          total={crosstab.total}
          label="Marginal Rel Frequencies of X"
          showRel
        />
        <MarginalTable
          categories={crosstab.yCategories}
          counts={crosstab.marginalY}
          total={crosstab.total}
          label="Marginal Rel Frequencies of Y"
          showRel
        />
      </div>

      {/* X Conditional on Y + Box Plot (2-col, only when X numeric) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              X Conditional on Y (count/mean/std/min/q25/median/q75/max)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CondStatsTable stats={conditionalStats} />
            <p className="text-xs text-muted-foreground mt-2">Only available when X is numeric.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Box Plot: X Conditional on Y (1% sample)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {canShowBoxPlot && boxPlotData ? (
              <>
                <BoxPlotChart data={boxPlotData} />
                <p className="text-xs text-muted-foreground mt-2">Y levels capped to top 20 by count; the rest grouped as "Other".</p>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">Not available (X must be numeric).</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Correlation Measures */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
            <TrendingUp className="w-4 h-4" />
            Correlation Measures
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Association + Chi-square (2-col) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-2">Association (contingency-based)</h3>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr>
                    <th className="text-left p-1.5 border-b border-border text-muted-foreground font-semibold">Test</th>
                    <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">DF</th>
                    <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Chi-square</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{chiSquare.degreesOfFreedom}</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{fmt(chiSquare.chiSquare)}</td>
                  </tr>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Phi</td>
                    <td className="p-1.5 border-b border-border text-right font-mono"></td>
                    <td className="p-1.5 border-b border-border text-right font-mono">
                      {chiSquare.phiCoefficient != null ? fmt(chiSquare.phiCoefficient) : '—'}
                    </td>
                  </tr>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Contingency Coef</td>
                    <td className="p-1.5 border-b border-border text-right font-mono"></td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{fmt(chiSquare.contingencyCoefficient)}</td>
                  </tr>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Cramér's V</td>
                    <td className="p-1.5 border-b border-border text-right font-mono"></td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{fmt(chiSquare.cramersV)}</td>
                  </tr>
                </tbody>
              </table>
              <p className="text-xs text-muted-foreground mt-2">Phi is only meaningful for 2×2 tables; otherwise shown as blank.</p>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-2">Chi-square details</h3>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr>
                    <th className="text-left p-1.5 border-b border-border text-muted-foreground font-semibold">Measure</th>
                    <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Chi-square statistic</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{fmt(chiSquare.chiSquare)}</td>
                  </tr>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Degrees of freedom</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{chiSquare.degreesOfFreedom}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Correlations full data */}
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground mb-2">Correlations (full data)</h3>
            {correlations ? (
              <table className="w-full border-collapse text-xs max-w-md">
                <thead>
                  <tr>
                    <th className="text-left p-1.5 border-b border-border text-muted-foreground font-semibold">Measure</th>
                    <th className="text-right p-1.5 border-b border-border text-muted-foreground font-semibold">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Pearson</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{fmt(correlations.pearson)}</td>
                  </tr>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Spearman</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{fmt(correlations.spearman)}</td>
                  </tr>
                  <tr className="hover:bg-muted/30">
                    <td className="p-1.5 border-b border-border">Kendall's tau</td>
                    <td className="p-1.5 border-b border-border text-right font-mono">{fmt(correlations.kendall)}</td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <p className="text-xs text-muted-foreground">Not available (both X and Y must be numeric).</p>
            )}
            <p className="text-xs text-muted-foreground mt-2">Only available when X is numeric.</p>
          </div>
        </CardContent>
      </Card>

      {/* 1% Sample Data Insights */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-muted-foreground">1% Sample Data Insights</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {sampleInsights ? (
            <>
              {/* Scatter Plot */}
              <div className="p-3 rounded-lg bg-muted/30">
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">
                  Scatter (1% sample) + Prediction Ellipses (80%, 70%)
                </h3>
                <div className="h-[360px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsScatter>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="x"
                        type="number"
                        name={varX}
                        tickFormatter={(v) => v.toFixed(1)}
                        tick={{ fontSize: 10 }}
                        label={{ value: 'X', position: 'insideBottom', offset: -5, fontSize: 11 }}
                      />
                      <YAxis
                        dataKey="y"
                        type="number"
                        name={varY}
                        tickFormatter={(v) => v.toFixed(1)}
                        tick={{ fontSize: 10 }}
                        label={{ value: varY, angle: -90, position: 'insideLeft', fontSize: 11 }}
                      />
                      <Legend />
                      <Scatter
                        name={`1% sample (n=${sampleInsights.sampleSize})`}
                        data={sampleInsights.x.map((x, i) => ({ x, y: sampleInsights.y[i] }))}
                        fill="hsl(var(--primary))"
                        opacity={0.5}
                      />
                      <Customized
                        component={(props: any) => {
                          const { xAxisMap, yAxisMap } = props;
                          const xAxis = xAxisMap?.[0];
                          const yAxis = yAxisMap?.[0];
                          if (!xAxis?.scale || !yAxis?.scale) return null;

                          const renderEllipse = (
                            points: { x: number; y: number }[] | null,
                            stroke: string,
                            dashArray?: string
                          ) => {
                            if (!points || points.length === 0) return null;
                            const pathData = points
                              .map((p, i) => {
                                const px = xAxis.scale(p.x);
                                const py = yAxis.scale(p.y);
                                if (px === undefined || py === undefined) return null;
                                return `${i === 0 ? 'M' : 'L'} ${px} ${py}`;
                              })
                              .filter(Boolean)
                              .join(' ');
                            if (!pathData) return null;
                            return <path d={pathData + ' Z'} fill="none" stroke={stroke} strokeWidth={2} strokeDasharray={dashArray} opacity={0.8} />;
                          };

                          return (
                            <g>
                              {renderEllipse(sampleInsights.ellipse70, 'hsl(24, 80%, 60%)', '8,4')}
                              {renderEllipse(sampleInsights.ellipse80, 'hsl(24, 90%, 45%)')}
                            </g>
                          );
                        }}
                      />
                    </RechartsScatter>
                  </ResponsiveContainer>
                </div>
                <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <span className="w-4 h-0.5 bg-orange-400" style={{ borderStyle: 'dashed' }}></span>
                    70% ellipse
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-4 h-0.5 bg-orange-600"></span>
                    80% ellipse
                  </span>
                </div>
              </div>

              {/* Sample Correlations */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg bg-muted/30">
                  <h4 className="text-xs font-semibold text-muted-foreground mb-1">Pearson (1% sample) — X vs Y</h4>
                  <p className="text-lg font-mono font-semibold">{fmt(sampleInsights.pearson)}</p>
                </div>
                <div className="p-3 rounded-lg bg-muted/30">
                  <h4 className="text-xs font-semibold text-muted-foreground mb-1">Spearman (1% sample) — X vs Y</h4>
                  <p className="text-lg font-mono font-semibold">{fmt(sampleInsights.spearman)}</p>
                </div>
                <div className="p-3 rounded-lg bg-muted/30">
                  <h4 className="text-xs font-semibold text-muted-foreground mb-1">Kendall's tau (1% sample) — X vs Y</h4>
                  <p className="text-lg font-mono font-semibold">{fmt(sampleInsights.kendall)}</p>
                </div>
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">Not available (both X and Y must be numeric).</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
