import { ScrollArea } from '@/components/ui/scroll-area';

interface ConditionalStat {
  y: string;
  count: number;
  mean: number;
  std: number;
  min: number;
  q25: number;
  median: number;
  q75: number;
  max: number;
}

interface StatisticsDescriptionTableProps {
  data: ConditionalStat[];
  varX: string;
  varY: string;
}

export function StatisticsDescriptionTable({ data, varX, varY }: StatisticsDescriptionTableProps) {
  if (!data || data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No conditional statistics available.
      </p>
    );
  }

  const metrics = ['Count', 'Mean', 'Std', 'Min', 'Q25', 'Median', 'Q75', 'Max'];

  return (
    <div className="border rounded-lg overflow-hidden">
      <ScrollArea className="max-h-[300px]">
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse" style={{ minWidth: `${(data.length + 1) * 80}px` }}>
            <thead>
              <tr className="bg-muted/50">
                <th className="sticky left-0 z-10 bg-muted border-r border-b p-2 text-left font-semibold min-w-[80px]">
                  {varY} →
                </th>
                {data.slice(0, 20).map((row, idx) => (
                  <th key={idx} className="border-r border-b p-2 text-center font-medium min-w-[80px]">
                    <span className="truncate block" title={row.y}>
                      {row.y.length > 10 ? row.y.slice(0, 10) + '…' : row.y}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.map((metric, metricIdx) => (
                <tr key={metric} className={metricIdx % 2 === 0 ? 'bg-muted/10' : ''}>
                  <td className="sticky left-0 z-10 bg-background border-r border-b p-2 font-medium">
                    {metric}
                  </td>
                  {data.slice(0, 20).map((row, idx) => {
                    let value: number;
                    switch (metric) {
                      case 'Count': value = row.count; break;
                      case 'Mean': value = row.mean; break;
                      case 'Std': value = row.std; break;
                      case 'Min': value = row.min; break;
                      case 'Q25': value = row.q25; break;
                      case 'Median': value = row.median; break;
                      case 'Q75': value = row.q75; break;
                      case 'Max': value = row.max; break;
                      default: value = 0;
                    }
                    const formatted = metric === 'Count' 
                      ? value.toString() 
                      : value.toFixed(metric === 'Mean' || metric === 'Std' ? 4 : 2);
                    
                    return (
                      <td key={idx} className="border-r border-b p-2 text-center font-mono">
                        {formatted}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ScrollArea>
      <p className="text-xs text-muted-foreground p-2 bg-muted/20 border-t">
        Descriptive statistics of <strong>{varX}</strong> grouped by each level of <strong>{varY}</strong>
      </p>
    </div>
  );
}
