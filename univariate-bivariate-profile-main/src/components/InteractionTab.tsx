import { useState, useMemo, useCallback } from 'react';
import { DatasetPayload, VariableInfo } from '@/lib/statistics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { RefreshCw, X } from 'lucide-react';

interface InteractionTabProps {
  payload: DatasetPayload;
  rawData: Record<string, unknown>[];
}

// Compute Pearson correlation between two numeric arrays
function pearsonCorrelation(x: number[], y: number[]): number | null {
  if (x.length !== y.length || x.length < 2) return null;
  
  const n = x.length;
  const sumX = x.reduce((a, b) => a + b, 0);
  const sumY = y.reduce((a, b) => a + b, 0);
  const sumXY = x.reduce((a, v, i) => a + v * y[i], 0);
  const sumX2 = x.reduce((a, v) => a + v * v, 0);
  const sumY2 = y.reduce((a, v) => a + v * v, 0);
  
  const numerator = n * sumXY - sumX * sumY;
  const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
  
  if (denominator === 0) return null;
  return numerator / denominator;
}

// Get numeric values from column
function getNumericColumn(data: Record<string, unknown>[], colName: string): number[] {
  return data
    .map(row => row[colName])
    .filter(v => v !== null && v !== undefined && v !== '')
    .map(v => Number(v))
    .filter(n => isFinite(n));
}

// Get paired numeric values (both columns must be valid for each row)
function getPairedValues(data: Record<string, unknown>[], col1: string, col2: string): { x: number; y: number }[] {
  return data
    .map(row => {
      const v1 = row[col1];
      const v2 = row[col2];
      if (v1 === null || v1 === undefined || v1 === '' || v2 === null || v2 === undefined || v2 === '') {
        return null;
      }
      const n1 = Number(v1);
      const n2 = Number(v2);
      if (!isFinite(n1) || !isFinite(n2)) return null;
      return { x: n1, y: n2 };
    })
    .filter((v): v is { x: number; y: number } => v !== null);
}

// Downsample scatter data to max points for performance
function downsampleScatter<T extends { x: number; y: number }>(data: T[], maxPoints: number = 1000): T[] {
  if (data.length <= maxPoints) return data;
  
  const step = Math.ceil(data.length / maxPoints);
  const sampled: T[] = [];
  for (let i = 0; i < data.length; i += step) {
    sampled.push(data[i]);
  }
  return sampled;
}

// Color palette for category coloring (5 distinct, accessible colors)
const CATEGORY_COLORS = [
  'hsl(221, 83%, 53%)',  // Blue
  'hsl(25, 95%, 53%)',   // Orange
  'hsl(142, 71%, 45%)',  // Green
  'hsl(0, 84%, 60%)',    // Red
  'hsl(271, 81%, 56%)',  // Purple
];

// Random sample without replacement
function randomSample<T>(arr: T[], sampleSize: number): T[] {
  const shuffled = [...arr];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, sampleSize);
}

// Color scale for heatmap: blue (negative) -> white (zero) -> red (positive)
function getCorrelationColor(value: number | null): string {
  if (value === null) return 'hsl(var(--muted))';
  const clamped = Math.max(-1, Math.min(1, value));
  
  if (clamped >= 0) {
    // White to red (0 to 1)
    const intensity = Math.round(clamped * 255);
    return `rgb(255, ${255 - intensity}, ${255 - intensity})`;
  } else {
    // White to blue (0 to -1)
    const intensity = Math.round(-clamped * 255);
    return `rgb(${255 - intensity}, ${255 - intensity}, 255)`;
  }
}

export function InteractionTab({ payload, rawData }: InteractionTabProps) {
  const [dataSource, setDataSource] = useState<'full' | 'sample'>('full');
  const [samplePercent, setSamplePercent] = useState('20');
  const [sampleKey, setSampleKey] = useState(0); // Used to trigger redraw
  
  // Scatter plot state
  const [scatterVar1, setScatterVar1] = useState<string>('');
  const [scatterVar2, setScatterVar2] = useState<string>('');
  const [colorByVar, setColorByVar] = useState<string>('');
  const [showTooltips, setShowTooltips] = useState<boolean>(true);
  
  // Heatmap state
  const [heatmapVars, setHeatmapVars] = useState<string[]>([]);
  
  // Get numeric variable names only (filter out empty strings)
  const numericVars = useMemo(() => 
    Object.entries(payload.variables)
      .filter(([name, v]) => v.vtype === 'numeric' && name.trim() !== '')
      .map(([name]) => name)
      .sort(),
    [payload.variables]
  );
  
  // Get variables eligible for color-by (≤5 unique values, excluding X/Y vars)
  const colorEligibleVars = useMemo(() => 
    Object.entries(payload.variables)
      .filter(([name, v]) => 
        name.trim() !== '' && 
        v.unique <= 5 && 
        name !== scatterVar1 && 
        name !== scatterVar2
      )
      .map(([name]) => name)
      .sort(),
    [payload.variables, scatterVar1, scatterVar2]
  );
  
  // Compute working dataset with defensive fallback
  const safeRawData = rawData ?? [];
  
  const workingData = useMemo(() => {
    if (safeRawData.length === 0) return [];
    if (dataSource === 'full') return safeRawData;
    
    const pct = parseFloat(samplePercent);
    if (isNaN(pct) || pct <= 0 || pct >= 100) return safeRawData;
    
    const sampleSize = Math.max(1, Math.round(safeRawData.length * pct / 100));
    // sampleKey triggers recalculation when "Redraw" is clicked
    return randomSample(safeRawData, sampleSize);
  }, [safeRawData, dataSource, samplePercent, sampleKey]);
  
  const handleRedraw = useCallback(() => {
    setSampleKey(k => k + 1);
  }, []);
  
  // Scatter plot data with optional category
  const scatterData = useMemo(() => {
    if (!scatterVar1 || !scatterVar2 || scatterVar1 === scatterVar2) return [];
    
    const paired = workingData
      .map(row => {
        const v1 = row[scatterVar1];
        const v2 = row[scatterVar2];
        if (v1 === null || v1 === undefined || v1 === '' || v2 === null || v2 === undefined || v2 === '') {
          return null;
        }
        const n1 = Number(v1);
        const n2 = Number(v2);
        if (!isFinite(n1) || !isFinite(n2)) return null;
        
        // Get category value if color-by is selected
        let category = '';
        if (colorByVar) {
          const catVal = row[colorByVar];
          category = catVal === null || catVal === undefined || catVal === '' 
            ? 'N/A' 
            : String(catVal);
        }
        
        return { x: n1, y: n2, category };
      })
      .filter((v): v is { x: number; y: number; category: string } => v !== null);
    
    return downsampleScatter(paired, 2000);
  }, [workingData, scatterVar1, scatterVar2, colorByVar]);
  
  // Get unique categories and their colors
  const categoryColorMap = useMemo(() => {
    if (!colorByVar) return new Map<string, string>();
    
    const uniqueCategories = [...new Set(scatterData.map(d => d.category))].sort();
    const map = new Map<string, string>();
    uniqueCategories.forEach((cat, i) => {
      map.set(cat, CATEGORY_COLORS[i % CATEGORY_COLORS.length]);
    });
    return map;
  }, [scatterData, colorByVar]);
  
  // Category counts for legend
  const categoryCounts = useMemo(() => {
    if (!colorByVar) return new Map<string, number>();
    
    const counts = new Map<string, number>();
    scatterData.forEach(d => {
      counts.set(d.category, (counts.get(d.category) || 0) + 1);
    });
    return counts;
  }, [scatterData, colorByVar]);
  
  const scatterCorrelation = useMemo(() => {
    if (scatterData.length < 2) return null;
    return pearsonCorrelation(
      scatterData.map(d => d.x),
      scatterData.map(d => d.y)
    );
  }, [scatterData]);
  
  // Correlation matrix for heatmap
  const correlationMatrix = useMemo(() => {
    if (heatmapVars.length < 2) return null;
    
    // Extract columns
    const columns = heatmapVars.map(varName => getNumericColumn(workingData, varName));
    
    // Compute correlation matrix
    const matrix: (number | null)[][] = [];
    for (let i = 0; i < heatmapVars.length; i++) {
      matrix[i] = [];
      for (let j = 0; j < heatmapVars.length; j++) {
        if (i === j) {
          matrix[i][j] = 1;
        } else {
          // Get paired values
          const paired = getPairedValues(workingData, heatmapVars[i], heatmapVars[j]);
          const xs = paired.map(p => p.x);
          const ys = paired.map(p => p.y);
          matrix[i][j] = pearsonCorrelation(xs, ys);
        }
      }
    }
    
    return matrix;
  }, [workingData, heatmapVars]);
  
  const handleAddHeatmapVar = (varName: string) => {
    if (heatmapVars.length >= 5 || heatmapVars.includes(varName)) return;
    setHeatmapVars([...heatmapVars, varName]);
  };
  
  const handleRemoveHeatmapVar = (varName: string) => {
    setHeatmapVars(heatmapVars.filter(v => v !== varName));
  };
  
  return (
    <div className="space-y-6">
      {/* Data Source Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Data Source</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-6">
            <RadioGroup 
              value={dataSource} 
              onValueChange={(v) => setDataSource(v as 'full' | 'sample')}
              className="flex gap-4"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="full" id="full" />
                <Label htmlFor="full">Full Dataset ({rawData.length.toLocaleString()} rows)</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="sample" id="sample" />
                <Label htmlFor="sample">Random Sample</Label>
              </div>
            </RadioGroup>
            
            {dataSource === 'sample' && (
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min="1"
                  max="99"
                  value={samplePercent}
                  onChange={(e) => setSamplePercent(e.target.value)}
                  className="w-20"
                />
                <span className="text-sm text-muted-foreground">%</span>
                <Button variant="outline" size="sm" onClick={handleRedraw} className="gap-1">
                  <RefreshCw className="w-3 h-3" />
                  Redraw
                </Button>
                <Badge variant="secondary">
                  {workingData.length.toLocaleString()} rows
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
      
      {/* Sub-tabs for Scatter and Heatmap */}
      <Tabs defaultValue="scatter">
        <TabsList>
          <TabsTrigger value="scatter">Scatter Plot</TabsTrigger>
          <TabsTrigger value="heatmap">Correlation Heatmap</TabsTrigger>
        </TabsList>
        
        {/* Scatter Plot Tab */}
        <TabsContent value="scatter" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Select Variables</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-4">
                <div className="space-y-2">
                  <Label>X-Axis Variable</Label>
                  <Select value={scatterVar1} onValueChange={setScatterVar1}>
                    <SelectTrigger className="w-[200px]">
                      <SelectValue placeholder="Select variable" />
                    </SelectTrigger>
                    <SelectContent>
                      {numericVars.map(name => (
                        <SelectItem key={name} value={name}>{name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Y-Axis Variable</Label>
                  <Select value={scatterVar2} onValueChange={setScatterVar2}>
                    <SelectTrigger className="w-[200px]">
                      <SelectValue placeholder="Select variable" />
                    </SelectTrigger>
                    <SelectContent>
                      {numericVars.map(name => (
                        <SelectItem key={name} value={name}>{name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Color By (Optional)</Label>
                  <div className="flex items-center gap-1">
                    <Select value={colorByVar} onValueChange={setColorByVar}>
                      <SelectTrigger className="w-[200px]">
                        <SelectValue placeholder="None" />
                      </SelectTrigger>
                      <SelectContent>
                        {colorEligibleVars.map(name => (
                          <SelectItem key={name} value={name}>{name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {colorByVar && (
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        className="h-8 w-8" 
                        onClick={() => setColorByVar('')}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Variables with ≤5 unique values
                  </p>
                </div>
                <div className="space-y-2 flex flex-col justify-end">
                  <div className="flex items-center gap-2">
                    <Switch
                      id="show-tooltips"
                      checked={showTooltips}
                      onCheckedChange={setShowTooltips}
                    />
                    <Label htmlFor="show-tooltips" className="text-sm">Show Tooltips</Label>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Disable for better performance
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          {scatterData.length > 0 && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">
                    {scatterVar1} vs {scatterVar2}
                  </CardTitle>
                  {scatterCorrelation !== null && (
                    <Badge variant="outline">
                      r = {scatterCorrelation.toFixed(4)}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {scatterData.length.toLocaleString()} points displayed
                  {colorByVar && <span> | Colored by: {colorByVar}</span>}
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="h-[400px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis 
                        type="number" 
                        dataKey="x" 
                        name={scatterVar1}
                        stroke="hsl(var(--muted-foreground))"
                        tick={{ fontSize: 11 }}
                      />
                      <YAxis 
                        type="number" 
                        dataKey="y" 
                        name={scatterVar2}
                        stroke="hsl(var(--muted-foreground))"
                        tick={{ fontSize: 11 }}
                      />
                      {showTooltips && (
                        <Tooltip 
                          cursor={{ strokeDasharray: '3 3' }}
                          content={({ active, payload }) => {
                            if (!active || !payload?.length) return null;
                            const data = payload[0].payload;
                            return (
                              <div className="bg-background border rounded-lg p-2 text-xs shadow-lg">
                                <p><span className="text-muted-foreground">{scatterVar1}:</span> {data.x.toFixed(4)}</p>
                                <p><span className="text-muted-foreground">{scatterVar2}:</span> {data.y.toFixed(4)}</p>
                                {colorByVar && (
                                  <p><span className="text-muted-foreground">{colorByVar}:</span> {data.category}</p>
                                )}
                              </div>
                            );
                          }}
                        />
                      )}
                      <Scatter 
                        data={scatterData} 
                        fill="hsl(var(--primary))" 
                        fillOpacity={0.6}
                      >
                        {scatterData.map((entry, index) => (
                          <Cell 
                            key={`cell-${index}`} 
                            fill={colorByVar ? categoryColorMap.get(entry.category) || 'hsl(var(--primary))' : 'hsl(var(--primary))'} 
                            fillOpacity={0.6}
                            r={3}
                          />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
                
                {/* Color Legend */}
                {colorByVar && categoryColorMap.size > 0 && (
                  <div className="flex flex-wrap items-center gap-4 pt-2 border-t">
                    <span className="text-xs text-muted-foreground font-medium">Legend:</span>
                    {[...categoryColorMap.entries()].map(([category, color]) => (
                      <div key={category} className="flex items-center gap-1.5">
                        <div 
                          className="w-3 h-3 rounded-full" 
                          style={{ backgroundColor: color }}
                        />
                        <span className="text-xs">
                          {category} ({categoryCounts.get(category)?.toLocaleString() || 0})
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
          
          {scatterVar1 && scatterVar2 && scatterVar1 !== scatterVar2 && scatterData.length === 0 && (
            <Card className="h-32 flex items-center justify-center">
              <p className="text-muted-foreground">No valid data points for selected variables</p>
            </Card>
          )}
        </TabsContent>
        
        {/* Correlation Heatmap Tab */}
        <TabsContent value="heatmap" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Select Variables (up to 5)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {heatmapVars.map(varName => (
                  <Badge key={varName} variant="secondary" className="gap-1 pr-1">
                    {varName}
                    <button 
                      onClick={() => handleRemoveHeatmapVar(varName)}
                      className="ml-1 hover:bg-muted rounded-full p-0.5"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              
              {heatmapVars.length < 5 && (
                <Select value="" onValueChange={handleAddHeatmapVar}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="Add variable" />
                  </SelectTrigger>
                  <SelectContent>
                    {numericVars
                      .filter(name => !heatmapVars.includes(name))
                      .map(name => (
                        <SelectItem key={name} value={name}>{name}</SelectItem>
                      ))
                    }
                  </SelectContent>
                </Select>
              )}
            </CardContent>
          </Card>
          
          {correlationMatrix && heatmapVars.length >= 2 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Correlation Matrix</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr>
                        <th className="p-2 text-left"></th>
                        {heatmapVars.map(name => (
                          <th key={name} className="p-2 text-center font-medium truncate max-w-[100px]" title={name}>
                            {name.length > 12 ? name.slice(0, 12) + '...' : name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {heatmapVars.map((rowName, i) => (
                        <tr key={rowName}>
                          <td className="p-2 font-medium truncate max-w-[100px]" title={rowName}>
                            {rowName.length > 12 ? rowName.slice(0, 12) + '...' : rowName}
                          </td>
                          {heatmapVars.map((_, j) => {
                            const val = correlationMatrix[i][j];
                            return (
                              <td 
                                key={j} 
                                className="p-2 text-center border"
                                style={{ 
                                  backgroundColor: getCorrelationColor(val),
                                  color: val !== null && Math.abs(val) > 0.5 ? 'white' : 'inherit'
                                }}
                                title={val !== null ? val.toFixed(4) : 'N/A'}
                              >
                                {val !== null ? val.toFixed(2) : 'N/A'}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                
                {/* Color legend */}
                <div className="mt-4 flex items-center justify-center gap-2 text-xs">
                  <span>-1</span>
                  <div 
                    className="w-32 h-4 rounded" 
                    style={{ 
                      background: 'linear-gradient(to right, rgb(0, 0, 255), rgb(255, 255, 255), rgb(255, 0, 0))'
                    }} 
                  />
                  <span>+1</span>
                </div>
              </CardContent>
            </Card>
          )}
          
          {heatmapVars.length < 2 && (
            <Card className="h-32 flex items-center justify-center">
              <p className="text-muted-foreground">Select at least 2 variables to generate correlation heatmap</p>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
