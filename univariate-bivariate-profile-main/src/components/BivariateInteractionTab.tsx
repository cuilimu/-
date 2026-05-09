import { useState, useMemo, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { RefreshCw, ScatterChart, AlertTriangle, Play, Settings2 } from 'lucide-react';
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
import {
  calculatePearsonCorrelation,
  calculateSpearmanCorrelation,
  calculateKendallTau,
  calculateEllipseParams,
  generateEllipsePoints,
  extractNumericColumn,
} from '@/lib/bivariateStatistics';
import { Progress } from '@/components/ui/progress';

interface BivariateInteractionTabProps {
  data: Record<string, unknown>[];
  varX: string;
  varY: string;
  xIsNumeric: boolean;
  yIsNumeric: boolean;
}

const MAX_SCATTER_POINTS = 2000;

interface ScatterDataResult {
  x: number[];
  y: number[];
  sampleSize: number;
  totalSize: number;
  isDownsampled: boolean;
}

export function BivariateInteractionTab({ 
  data, 
  varX, 
  varY, 
  xIsNumeric, 
  yIsNumeric 
}: BivariateInteractionTabProps) {
  // Configuration state (user sets these before loading)
  const [samplePercent, setSamplePercent] = useState<number>(10);
  const [sampleSeed, setSampleSeed] = useState<number>(12345);
  const [showEllipse1, setShowEllipse1] = useState<boolean>(true);
  const [showEllipse2, setShowEllipse2] = useState<boolean>(true);
  const [ellipse1Level, setEllipse1Level] = useState<number>(70);
  const [ellipse2Level, setEllipse2Level] = useState<number>(80);
  const [showTooltips, setShowTooltips] = useState<boolean>(false);

  // Lazy loading state
  const [isLoaded, setIsLoaded] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadProgress, setLoadProgress] = useState<number>(0);
  const [scatterData, setScatterData] = useState<ScatterDataResult | null>(null);

  // Get valid data count for display
  const validDataInfo = useMemo(() => {
    if (!xIsNumeric || !yIsNumeric) return { validCount: 0, totalCount: data.length };
    
    let validCount = 0;
    for (const row of data) {
      const xVal = row[varX];
      const yVal = row[varY];
      if (xVal != null && yVal != null && !isNaN(Number(xVal)) && !isNaN(Number(yVal))) {
        validCount++;
      }
    }
    return { validCount, totalCount: data.length };
  }, [data, varX, varY, xIsNumeric, yIsNumeric]);

  // Resample function
  const handleResample = useCallback(() => {
    setSampleSeed(prev => prev + Math.floor(Math.random() * 10000) + 1);
    setIsLoaded(false);
    setScatterData(null);
  }, []);

  // Load scatter data with progress
  const handleLoadScatter = useCallback(async () => {
    if (!xIsNumeric || !yIsNumeric) return;

    setIsLoading(true);
    setLoadProgress(0);

    // Use setTimeout to allow UI to update
    await new Promise(resolve => setTimeout(resolve, 50));

    try {
      setLoadProgress(10);
      
      // Extract numeric columns
      const xNums = extractNumericColumn(data, varX);
      const yNums = extractNumericColumn(data, varY);
      
      setLoadProgress(30);
      await new Promise(resolve => setTimeout(resolve, 20));

      // Align and filter valid data
      const valid: { x: number; y: number }[] = [];
      for (let i = 0; i < xNums.length; i++) {
        if (!isNaN(xNums[i]) && !isNaN(yNums[i])) {
          valid.push({ x: xNums[i], y: yNums[i] });
        }
      }

      setLoadProgress(50);
      await new Promise(resolve => setTimeout(resolve, 20));

      if (valid.length === 0) {
        setScatterData(null);
        setIsLoaded(true);
        setIsLoading(false);
        return;
      }

      // Calculate sample size
      const targetSampleSize = Math.floor(valid.length * samplePercent / 100);
      const sampleSize = Math.max(1, Math.min(targetSampleSize, MAX_SCATTER_POINTS));

      setLoadProgress(60);
      await new Promise(resolve => setTimeout(resolve, 20));

      let sampled: typeof valid;
      
      if (sampleSize >= valid.length) {
        sampled = valid;
      } else {
        // Seeded random sampling
        const seededRandom = (s: number) => {
          const x = Math.sin(s) * 10000;
          return x - Math.floor(x);
        };

        sampled = [];
        const indices = new Set<number>();
        let s = sampleSeed;
        while (indices.size < sampleSize && indices.size < valid.length) {
          const idx = Math.floor(seededRandom(s) * valid.length);
          if (!indices.has(idx)) {
            indices.add(idx);
            sampled.push(valid[idx]);
          }
          s++;
        }
      }

      setLoadProgress(90);
      await new Promise(resolve => setTimeout(resolve, 20));

      setScatterData({
        x: sampled.map(p => p.x),
        y: sampled.map(p => p.y),
        sampleSize: sampled.length,
        totalSize: valid.length,
        isDownsampled: sampled.length < valid.length * samplePercent / 100,
      });

      setLoadProgress(100);
      setIsLoaded(true);
    } finally {
      setIsLoading(false);
    }
  }, [data, varX, varY, xIsNumeric, yIsNumeric, samplePercent, sampleSeed]);

  // Calculate correlations on loaded sample
  const sampleCorrelations = useMemo(() => {
    if (!scatterData || scatterData.x.length < 2) return null;
    
    return {
      pearson: calculatePearsonCorrelation(scatterData.x, scatterData.y),
      spearman: calculateSpearmanCorrelation(scatterData.x, scatterData.y),
      kendall: calculateKendallTau(scatterData.x, scatterData.y),
    };
  }, [scatterData]);

  // Calculate ellipse points only when data is loaded
  const ellipseData = useMemo(() => {
    if (!scatterData) return { ellipse1: null, ellipse2: null };
    
    const { x, y } = scatterData;
    
    const ellipse1Params = showEllipse1 ? calculateEllipseParams(x, y, ellipse1Level) : null;
    const ellipse2Params = showEllipse2 ? calculateEllipseParams(x, y, ellipse2Level) : null;
    
    return {
      ellipse1: ellipse1Params ? generateEllipsePoints(ellipse1Params) : null,
      ellipse2: ellipse2Params ? generateEllipsePoints(ellipse2Params) : null,
    };
  }, [scatterData, showEllipse1, showEllipse2, ellipse1Level, ellipse2Level]);

  // Check if both variables are numeric
  if (!xIsNumeric || !yIsNumeric) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <ScatterChart className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
          <p className="text-muted-foreground">
            Interaction analysis requires two numeric variables.
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            Currently: {varX} ({xIsNumeric ? 'numeric' : 'categorical'}) vs {varY} ({yIsNumeric ? 'numeric' : 'categorical'})
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Configuration Card */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
                <Settings2 className="w-4 h-4" />
                Configure Scatter Analysis
              </CardTitle>
              <CardDescription className="text-xs">
                {varX} vs {varY} — Set parameters before loading
              </CardDescription>
            </div>
            <Badge variant="outline" className="text-xs">
              {validDataInfo.validCount.toLocaleString()} valid pairs / {validDataInfo.totalCount.toLocaleString()} total rows
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Sampling Configuration */}
          <div className="p-4 rounded-lg bg-muted/30 space-y-4">
            <h3 className="text-sm font-semibold text-muted-foreground mb-2">
              Sampling Settings
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label className="text-xs font-medium">Sample Percentage</Label>
                <div className="flex items-center gap-3">
                  <Slider
                    value={[samplePercent]}
                    onValueChange={([val]) => {
                      setSamplePercent(val);
                      setIsLoaded(false);
                    }}
                    min={1}
                    max={100}
                    step={1}
                    className="flex-1"
                  />
                  <span className="text-sm font-mono w-12 text-right">{samplePercent}%</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  ≈ {Math.min(Math.floor(validDataInfo.validCount * samplePercent / 100), MAX_SCATTER_POINTS).toLocaleString()} points
                  {Math.floor(validDataInfo.validCount * samplePercent / 100) > MAX_SCATTER_POINTS && 
                    ` (capped at ${MAX_SCATTER_POINTS.toLocaleString()})`}
                </p>
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-medium">Random Seed</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    value={sampleSeed}
                    onChange={(e) => {
                      setSampleSeed(parseInt(e.target.value) || 0);
                      setIsLoaded(false);
                    }}
                    className="font-mono text-sm"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleResample}
                    className="gap-1.5 shrink-0"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    New Seed
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Ellipse Configuration */}
          <div className="p-4 rounded-lg bg-muted/30 space-y-4">
            <h3 className="text-sm font-semibold text-muted-foreground mb-2">
              Confidence Ellipses
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <Checkbox
                    id="ellipse1-config"
                    checked={showEllipse1}
                    onCheckedChange={(checked) => setShowEllipse1(checked === true)}
                  />
                  <Label htmlFor="ellipse1-config" className="text-xs font-medium flex-shrink-0">
                    Ellipse 1 (dashed)
                  </Label>
                </div>
                <div className="flex items-center gap-3 pl-6">
                  <Slider
                    value={[ellipse1Level]}
                    onValueChange={([val]) => setEllipse1Level(val)}
                    min={50}
                    max={99}
                    step={1}
                    className="flex-1"
                    disabled={!showEllipse1}
                  />
                  <span className="text-sm font-mono w-12 text-right">{ellipse1Level}%</span>
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <Checkbox
                    id="ellipse2-config"
                    checked={showEllipse2}
                    onCheckedChange={(checked) => setShowEllipse2(checked === true)}
                  />
                  <Label htmlFor="ellipse2-config" className="text-xs font-medium flex-shrink-0">
                    Ellipse 2 (solid)
                  </Label>
                </div>
                <div className="flex items-center gap-3 pl-6">
                  <Slider
                    value={[ellipse2Level]}
                    onValueChange={([val]) => setEllipse2Level(val)}
                    min={50}
                    max={99}
                    step={1}
                    className="flex-1"
                    disabled={!showEllipse2}
                  />
                  <span className="text-sm font-mono w-12 text-right">{ellipse2Level}%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Display Options */}
          <div className="p-4 rounded-lg bg-muted/30">
            <div className="flex items-center gap-3">
              <Checkbox
                id="showTooltips-config"
                checked={showTooltips}
                onCheckedChange={(checked) => setShowTooltips(checked === true)}
              />
              <Label htmlFor="showTooltips-config" className="text-xs">
                Show Tooltips on Hover (may impact performance with many points)
              </Label>
            </div>
          </div>

          {/* Load Button */}
          <div className="flex justify-center pt-2">
            <Button
              onClick={handleLoadScatter}
              disabled={isLoading}
              size="lg"
              className="gap-2 min-w-[200px]"
            >
              {isLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  {isLoaded ? 'Reload Scatter Plot' : 'Load Scatter Plot'}
                </>
              )}
            </Button>
          </div>

          {/* Loading Progress */}
          {isLoading && (
            <div className="space-y-2">
              <Progress value={loadProgress} className="h-2" />
              <p className="text-xs text-center text-muted-foreground">
                Processing {validDataInfo.validCount.toLocaleString()} data points...
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Scatter Plot Card - Only shown when loaded */}
      {isLoaded && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
                  <ScatterChart className="w-4 h-4" />
                  Scatter Plot Result
                </CardTitle>
                <CardDescription className="text-xs">
                  {varX} vs {varY}
                </CardDescription>
              </div>
              {scatterData && (
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline">
                    {scatterData.sampleSize.toLocaleString()} of {scatterData.totalSize.toLocaleString()} points
                  </Badge>
                  {scatterData.isDownsampled && (
                    <Badge variant="secondary" className="gap-1">
                      <AlertTriangle className="w-3 h-3" />
                      Capped at {MAX_SCATTER_POINTS.toLocaleString()}
                    </Badge>
                  )}
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {!scatterData ? (
              <div className="py-12 text-center">
                <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                <p className="text-muted-foreground">No valid numeric data for scatter plot.</p>
              </div>
            ) : (
              <>
                {/* Scatter Plot */}
                <div className="p-4 rounded-lg bg-muted/30">
                  <div className="h-[400px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <RechartsScatter>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis
                          dataKey="x"
                          type="number"
                          name={varX}
                          tickFormatter={(v) => v.toFixed(2)}
                          tick={{ fontSize: 10 }}
                          label={{ value: varX, position: 'insideBottom', offset: -5, fontSize: 11 }}
                        />
                        <YAxis
                          dataKey="y"
                          type="number"
                          name={varY}
                          tickFormatter={(v) => v.toFixed(2)}
                          tick={{ fontSize: 10 }}
                          label={{ value: varY, angle: -90, position: 'insideLeft', fontSize: 11 }}
                        />
                        {showTooltips && (
                          <Tooltip
                            formatter={(value: number) => value.toFixed(4)}
                            labelFormatter={() => ''}
                          />
                        )}
                        <Legend />
                        <Scatter
                          name={`${samplePercent}% sample (n=${scatterData.sampleSize})`}
                          data={scatterData.x.map((x, i) => ({
                            x,
                            y: scatterData.y[i],
                          }))}
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
                              
                              return (
                                <path
                                  d={pathData + ' Z'}
                                  fill="none"
                                  stroke={stroke}
                                  strokeWidth={2}
                                  strokeDasharray={dashArray}
                                  opacity={0.8}
                                />
                              );
                            };
                            
                            return (
                              <g>
                                {renderEllipse(ellipseData.ellipse1, 'hsl(24, 80%, 60%)', '8,4')}
                                {renderEllipse(ellipseData.ellipse2, 'hsl(24, 90%, 45%)')}
                              </g>
                            );
                          }}
                        />
                      </RechartsScatter>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                    <span>Seed: {sampleSeed}</span>
                    {showEllipse1 && (
                      <span className="flex items-center gap-1">
                        <span className="w-4 h-0.5 bg-orange-400" style={{ borderStyle: 'dashed' }}></span>
                        {ellipse1Level}% ellipse
                      </span>
                    )}
                    {showEllipse2 && (
                      <span className="flex items-center gap-1">
                        <span className="w-4 h-0.5 bg-orange-600"></span>
                        {ellipse2Level}% ellipse
                      </span>
                    )}
                  </div>
                </div>

                {/* Sample Correlations */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 rounded-lg bg-muted/30">
                    <h4 className="text-xs font-semibold text-muted-foreground mb-1">
                      Pearson (sample)
                    </h4>
                    <p className="text-lg font-mono font-semibold">
                      {sampleCorrelations?.pearson?.toFixed(6) ?? 'N/A'}
                    </p>
                  </div>
                  <div className="p-4 rounded-lg bg-muted/30">
                    <h4 className="text-xs font-semibold text-muted-foreground mb-1">
                      Spearman (sample)
                    </h4>
                    <p className="text-lg font-mono font-semibold">
                      {sampleCorrelations?.spearman?.toFixed(6) ?? 'N/A'}
                    </p>
                  </div>
                  <div className="p-4 rounded-lg bg-muted/30">
                    <h4 className="text-xs font-semibold text-muted-foreground mb-1">
                      Kendall's tau (sample)
                    </h4>
                    <p className="text-lg font-mono font-semibold">
                      {sampleCorrelations?.kendall?.toFixed(6) ?? 'N/A'}
                    </p>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}