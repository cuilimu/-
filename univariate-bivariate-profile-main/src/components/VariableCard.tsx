import { VariableInfo, NumericDetails, CategoricalDetails, formatNumber, formatPercent } from '@/lib/statistics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Hash, Type, Calendar, ToggleLeft } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, ScatterChart, Scatter, ReferenceLine, ComposedChart, ReferenceArea } from 'recharts';

interface VariableCardProps {
  variable: VariableInfo;
}

function isNumericDetails(details: unknown): details is NumericDetails {
  return typeof details === 'object' && details !== null && 'tab1' in details;
}

function isCategoricalDetails(details: unknown): details is CategoricalDetails {
  return typeof details === 'object' && details !== null && 'top_values' in details;
}

const typeIcons = {
  numeric: Hash,
  categorical: Type,
  datetime: Calendar,
  boolean: ToggleLeft,
  other: Type
};

export function VariableCard({ variable }: VariableCardProps) {
  const Icon = typeIcons[variable.vtype] || Type;
  
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="w-5 h-5 text-primary" />
            <CardTitle className="text-lg">{variable.name}</CardTitle>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline">Type: {variable.vtype}</Badge>
            <Badge variant="outline">Dtype: {variable.dtype}</Badge>
          </div>
        </div>
        <div className="flex gap-4 text-sm text-muted-foreground mt-2">
          <span>Missing: {variable.missing_count} ({formatPercent(variable.missing_pct)})</span>
          <span>Unique: {variable.unique}</span>
        </div>
      </CardHeader>
      
      <CardContent>
        {variable.vtype === 'numeric' && isNumericDetails(variable.details) && (
          <NumericVariableDetails details={variable.details} />
        )}
        
        {(variable.vtype === 'categorical' || variable.vtype === 'boolean') && isCategoricalDetails(variable.details) && (
          <CategoricalVariableDetails details={variable.details} />
        )}
        
        {variable.vtype === 'datetime' && (
          <DatetimeVariableDetails details={variable.details as { min: string | null; max: string | null }} />
        )}
      </CardContent>
    </Card>
  );
}

function NumericVariableDetails({ details }: { details: NumericDetails }) {
  const { tab1, plots, common_values, extremes } = details;
  const { quantiles, descriptive } = tab1;
  
  // Prepare histogram data
  const histData = plots.hist.counts.map((count, idx) => ({
    bin: idx,
    count,
    range: `${formatNumber(plots.hist.edges[idx], 2)} - ${formatNumber(plots.hist.edges[idx + 1], 2)}`
  }));
  
  // Prepare CDF data
  const cdfData = plots.cdf.x.map((x, idx) => ({
    x,
    y: plots.cdf.y[idx]
  }));
  
  // Prepare QQ data
  const qqData = plots.qq.x.map((x, idx) => ({
    theoretical: x,
    sample: plots.qq.y[idx]
  }));


  return (
    <Tabs defaultValue="statistics" className="w-full">
      <TabsList className="grid grid-cols-4 w-full">
        <TabsTrigger value="statistics">Statistics</TabsTrigger>
        <TabsTrigger value="plots">Plots</TabsTrigger>
        <TabsTrigger value="common">Common Values</TabsTrigger>
        <TabsTrigger value="extreme">Extreme Values</TabsTrigger>
      </TabsList>

      <TabsContent value="statistics" className="mt-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Quantile Statistics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <StatRow label="Minimum" value={formatNumber(quantiles.min)} />
              <StatRow label="5-th percentile" value={formatNumber(quantiles.p05)} />
              <StatRow label="Q1" value={formatNumber(quantiles.q1)} />
              <StatRow label="Median" value={formatNumber(quantiles.median)} />
              <StatRow label="Q3" value={formatNumber(quantiles.q3)} />
              <StatRow label="95-th percentile" value={formatNumber(quantiles.p95)} />
              <StatRow label="Maximum" value={formatNumber(quantiles.max)} />
              <StatRow label="Range" value={formatNumber(quantiles.range)} />
              <StatRow label="Interquartile range (IQR)" value={formatNumber(quantiles.iqr)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="py-3">
              <CardTitle className="text-sm">Descriptive Statistics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <StatRow label="Standard deviation" value={formatNumber(descriptive.std)} />
              <StatRow label="Coefficient of variation (CV)" value={formatNumber(descriptive.cv)} />
              <StatRow label="Kurtosis" value={formatNumber(descriptive.kurtosis)} />
              <StatRow label="Mean" value={formatNumber(descriptive.mean)} />
              <StatRow label="Median Absolute Deviation (MAD)" value={formatNumber(descriptive.mad)} />
              <StatRow label="Skewness" value={formatNumber(descriptive.skewness)} />
              <StatRow label="Sum" value={formatNumber(descriptive.sum)} />
              <StatRow label="Variance" value={formatNumber(descriptive.variance)} />
              <StatRow label="Monotonicity" value={descriptive.monotonicity !== null ? formatNumber(descriptive.monotonicity) : '—'} />
            </CardContent>
          </Card>
        </div>
        
        <div className="grid grid-cols-3 gap-4 mt-4">
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-muted-foreground mb-1">Non-null</p>
              <p className="font-semibold">{details.n_nonnull}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-muted-foreground mb-1">Zeros</p>
              <p className="font-semibold">{details.zeros ?? '—'}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-xs text-muted-foreground mb-1">Infinite</p>
              <p className="font-semibold">{details.infs ?? '—'}</p>
            </CardContent>
          </Card>
        </div>
      </TabsContent>

      <TabsContent value="plots" className="mt-4">
        <Tabs defaultValue="histogram">
          <TabsList className="flex-wrap h-auto gap-1">
            <TabsTrigger value="histogram">Histogram</TabsTrigger>
            <TabsTrigger value="boxplot">Box Plot</TabsTrigger>
            <TabsTrigger value="cdf">CDF</TabsTrigger>
            <TabsTrigger value="qq">QQ Plot</TabsTrigger>
          </TabsList>

          <TabsContent value="histogram" className="mt-4">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histData}>
                  <XAxis dataKey="bin" tick={false} />
                  <YAxis />
                  <Tooltip 
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-background border rounded-lg p-2 text-sm shadow-lg">
                            <p className="font-medium">Range: {data.range}</p>
                            <p>Count: {data.count}</p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>

          <TabsContent value="boxplot" className="mt-4">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  layout="vertical"
                  data={[{ name: 'Distribution', ...quantiles }]}
                  margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                >
                  <XAxis 
                    type="number" 
                    domain={[quantiles.min, quantiles.max]}
                    tickFormatter={(v) => formatNumber(v, 2)}
                  />
                  <YAxis type="category" dataKey="name" hide />
                  <Tooltip
                    content={({ active }) => {
                      if (active) {
                        return (
                          <div className="bg-background border rounded-lg p-3 text-sm shadow-lg space-y-1">
                            <p><span className="text-muted-foreground">Min:</span> <span className="font-mono">{formatNumber(quantiles.min)}</span></p>
                            <p><span className="text-muted-foreground">5th %:</span> <span className="font-mono">{formatNumber(quantiles.p05)}</span></p>
                            <p><span className="text-muted-foreground">Q1:</span> <span className="font-mono">{formatNumber(quantiles.q1)}</span></p>
                            <p><span className="text-muted-foreground">Median:</span> <span className="font-mono font-semibold">{formatNumber(quantiles.median)}</span></p>
                            <p><span className="text-muted-foreground">Q3:</span> <span className="font-mono">{formatNumber(quantiles.q3)}</span></p>
                            <p><span className="text-muted-foreground">95th %:</span> <span className="font-mono">{formatNumber(quantiles.p95)}</span></p>
                            <p><span className="text-muted-foreground">Max:</span> <span className="font-mono">{formatNumber(quantiles.max)}</span></p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  {/* Whisker line from min to max */}
                  <ReferenceArea
                    x1={quantiles.min}
                    x2={quantiles.max}
                    y1="Distribution"
                    y2="Distribution"
                    fill="none"
                    stroke="hsl(var(--muted-foreground))"
                    strokeWidth={1}
                  />
                  {/* Box from Q1 to Q3 */}
                  <ReferenceArea
                    x1={quantiles.q1}
                    x2={quantiles.q3}
                    fill="hsl(var(--primary))"
                    fillOpacity={0.3}
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                  />
                  {/* Median line */}
                  <ReferenceLine
                    x={quantiles.median}
                    stroke="hsl(var(--primary))"
                    strokeWidth={3}
                  />
                  {/* Min whisker cap */}
                  <ReferenceLine
                    x={quantiles.min}
                    stroke="hsl(var(--muted-foreground))"
                    strokeWidth={2}
                  />
                  {/* Max whisker cap */}
                  <ReferenceLine
                    x={quantiles.max}
                    stroke="hsl(var(--muted-foreground))"
                    strokeWidth={2}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-6 mt-3 text-xs text-muted-foreground">
              <span>Min: {formatNumber(quantiles.min)}</span>
              <span>Q1: {formatNumber(quantiles.q1)}</span>
              <span className="font-medium text-foreground">Median: {formatNumber(quantiles.median)}</span>
              <span>Q3: {formatNumber(quantiles.q3)}</span>
              <span>Max: {formatNumber(quantiles.max)}</span>
            </div>
          </TabsContent>

          <TabsContent value="cdf" className="mt-4">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={cdfData}>
                  <XAxis 
                    dataKey="x" 
                    tickFormatter={(v) => formatNumber(v, 2)} 
                    type="number"
                    domain={['dataMin', 'dataMax']}
                  />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                  <Tooltip 
                    formatter={(value: number) => [`${(value * 100).toFixed(2)}%`, 'Percentile']}
                    labelFormatter={(label) => `Value: ${formatNumber(label, 4)}`}
                  />
                  <Line type="stepAfter" dataKey="y" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </TabsContent>

          <TabsContent value="qq" className="mt-4">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart>
                  <XAxis dataKey="theoretical" name="Theoretical" tickFormatter={(v) => formatNumber(v, 1)} />
                  <YAxis dataKey="sample" name="Sample" tickFormatter={(v) => formatNumber(v, 2)} />
                  <Tooltip 
                    formatter={(value: number, name: string) => [formatNumber(value, 4), name]}
                  />
                  <Scatter data={qqData} fill="hsl(var(--primary))" />
                  {plots.qq.line.slope !== null && plots.qq.line.intercept !== null && (
                    <ReferenceLine 
                      stroke="hsl(var(--muted-foreground))" 
                      strokeDasharray="5 5"
                      segment={[
                        { x: Math.min(...plots.qq.x), y: plots.qq.line.slope * Math.min(...plots.qq.x) + plots.qq.line.intercept },
                        { x: Math.max(...plots.qq.x), y: plots.qq.line.slope * Math.max(...plots.qq.x) + plots.qq.line.intercept }
                      ]}
                    />
                  )}
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Normal Q-Q plot comparing sample quantiles to theoretical normal distribution quantiles.
            </p>
          </TabsContent>

        </Tabs>
      </TabsContent>

      <TabsContent value="common" className="mt-4">
        <ValueCountTable values={common_values} />
      </TabsContent>

      <TabsContent value="extreme" className="mt-4">
        <Tabs defaultValue="min">
          <TabsList>
            <TabsTrigger value="min">Minimum 10 values</TabsTrigger>
            <TabsTrigger value="max">Maximum 10 values</TabsTrigger>
          </TabsList>
          <TabsContent value="min" className="mt-4">
            <ValueCountTable values={extremes.min10} />
          </TabsContent>
          <TabsContent value="max" className="mt-4">
            <ValueCountTable values={extremes.max10} />
          </TabsContent>
        </Tabs>
      </TabsContent>
    </Tabs>
  );
}

function CategoricalVariableDetails({ details }: { details: CategoricalDetails }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground mb-1">Total</p>
            <p className="font-semibold">{details.n_total}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground mb-1">Non-null</p>
            <p className="font-semibold">{details.n_nonnull}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground mb-1">Missing</p>
            <p className="font-semibold">{details.n_null}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground mb-1">Unique</p>
            <p className="font-semibold">{details.unique}</p>
          </CardContent>
        </Card>
      </div>
      
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Top Values</CardTitle>
        </CardHeader>
        <CardContent>
          <ValueCountTable values={details.top_values} />
        </CardContent>
      </Card>
    </div>
  );
}

function DatetimeVariableDetails({ details }: { details: { min: string | null; max: string | null } }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Card>
        <CardContent className="pt-4">
          <p className="text-xs text-muted-foreground mb-1">Minimum</p>
          <p className="font-semibold">{details.min ?? '—'}</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <p className="text-xs text-muted-foreground mb-1">Maximum</p>
          <p className="font-semibold">{details.max ?? '—'}</p>
        </CardContent>
      </Card>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

function ValueCountTable({ values }: { values: { value: string | number; count: number; freq_pct: number }[] }) {
  if (values.length === 0) {
    return <p className="text-sm text-muted-foreground">No data available</p>;
  }
  
  const maxPct = Math.max(...values.map(v => v.freq_pct));
  
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[45%]">Value</TableHead>
          <TableHead className="w-[15%]">Count</TableHead>
          <TableHead>Frequency (%)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {values.map((row, idx) => (
          <TableRow key={idx}>
            <TableCell className="font-mono">{String(row.value)}</TableCell>
            <TableCell>{row.count}</TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-primary/40 rounded-full"
                    style={{ width: `${(row.freq_pct / maxPct) * 100}%` }}
                  />
                </div>
                <span className="text-xs font-mono w-16 text-right">
                  {formatPercent(row.freq_pct)}
                </span>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
