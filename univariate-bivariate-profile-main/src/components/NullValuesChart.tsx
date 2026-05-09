import { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart';
import { VariableInfo } from '@/lib/statistics';

interface NullValuesChartProps {
  variables: Record<string, VariableInfo>;
}

export function NullValuesChart({ variables }: NullValuesChartProps) {
  const chartData = useMemo(() => {
    return Object.entries(variables)
      .map(([name, v]) => ({
        name: name.length > 15 ? name.slice(0, 15) + '…' : name,
        fullName: name,
        nullCount: v.missing_count,
        nullPct: v.missing_pct,
      }))
      .sort((a, b) => b.nullCount - a.nullCount);
  }, [variables]);

  const chartConfig = {
    nullCount: {
      label: 'Null Values',
      color: 'hsl(var(--chart-1))',
    },
  };

  if (chartData.length === 0) {
    return null;
  }

  const maxNullPct = Math.max(...chartData.map(d => d.nullPct));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Null Values by Column</CardTitle>
        <p className="text-xs text-muted-foreground">
          Distribution of missing values across all columns
        </p>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[300px] w-full">
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
            <XAxis type="number" tickFormatter={(value) => value.toLocaleString()} />
            <YAxis 
              type="category" 
              dataKey="name" 
              width={95}
              tick={{ fontSize: 11 }}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent 
                  formatter={(value, name, item) => (
                    <div className="flex flex-col gap-1">
                      <span className="font-medium">{item.payload.fullName}</span>
                      <span>Null Count: {Number(value).toLocaleString()}</span>
                      <span>Null %: {item.payload.nullPct.toFixed(2)}%</span>
                    </div>
                  )}
                />
              }
            />
            <Bar dataKey="nullCount" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, index) => (
                <Cell 
                  key={`cell-${index}`}
                  fill={entry.nullPct > 50 
                    ? 'hsl(var(--destructive))' 
                    : entry.nullPct > 20 
                      ? 'hsl(38 92% 50%)' 
                      : 'hsl(var(--chart-1))'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
        <div className="flex items-center justify-center gap-6 mt-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: 'hsl(var(--chart-1))' }} />
            <span>Low (&lt;20%)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: 'hsl(38 92% 50%)' }} />
            <span>Medium (20-50%)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: 'hsl(var(--destructive))' }} />
            <span>High (&gt;50%)</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
