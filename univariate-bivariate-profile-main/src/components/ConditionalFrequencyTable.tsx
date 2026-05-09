import { useState } from 'react';
import { CrosstabData } from '@/lib/bivariateStatistics';
import { Button } from '@/components/ui/button';
import { Download, ChevronDown, ChevronUp } from 'lucide-react';

interface ConditionalFrequencyTableProps {
  crosstab: CrosstabData;
  varX: string;
  varY: string;
}

export function ConditionalFrequencyTable({ crosstab, varX, varY }: ConditionalFrequencyTableProps) {
  const { xCategories, yCategories, jointFreq, marginalX, marginalY, total } = crosstab;
  const [showAll, setShowAll] = useState(false);
  
  const MAX_DISPLAY_ROWS = 20;
  const shouldTruncate = xCategories.length > MAX_DISPLAY_ROWS;
  
  // Get display rows: first 10 and last 10 if truncated
  const getDisplayIndices = (): number[] => {
    if (!shouldTruncate || showAll) {
      return xCategories.map((_, i) => i);
    }
    const first10 = Array.from({ length: Math.min(10, xCategories.length) }, (_, i) => i);
    const last10 = Array.from(
      { length: Math.min(10, xCategories.length) }, 
      (_, i) => xCategories.length - 10 + i
    ).filter(i => i >= 10); // Avoid duplicates
    return [...first10, -1, ...last10]; // -1 marks the separator row
  };
  
  const displayIndices = getDisplayIndices();
  
  const downloadCSV = () => {
    const headers = [varX, ...yCategories, 'Marginal X'];
    const rows = xCategories.map((xCat, xIdx) => [
      xCat,
      ...yCategories.map((_, yIdx) => jointFreq[xIdx][yIdx]),
      marginalX[xIdx]
    ]);
    rows.push(['Marginal Y', ...marginalY, total]);
    
    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `contingency_table_${varX}_${varY}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const formatPercent = (value: number) => {
    const pct = (value / total) * 100;
    return pct.toFixed(1) + '%';
  };

  return (
    <div className="border rounded-lg overflow-hidden bg-background">
      {/* Header with download button */}
      <div className="flex items-center justify-between p-2 bg-muted/30 border-b">
        <span className="text-xs text-muted-foreground">
          {xCategories.length} × {yCategories.length} table
          {shouldTruncate && !showAll && ` (showing first 10 and last 10 of ${xCategories.length} rows)`}
        </span>
        <Button variant="outline" size="sm" onClick={downloadCSV} className="h-7 text-xs gap-1">
          <Download className="w-3 h-3" />
          Download CSV
        </Button>
      </div>
      
      {/* Scrollable container with max dimensions */}
      <div className="relative max-h-[400px] overflow-auto">
        <table className="border-collapse text-xs w-full" style={{ minWidth: `${(yCategories.length + 2) * 80}px` }}>
          {/* Sticky Header Row */}
          <thead>
            <tr>
              {/* Top-left corner - sticky */}
              <th 
                className="sticky left-0 top-0 z-30 bg-muted border-r border-b p-2 text-left font-semibold min-w-[100px]"
                style={{ boxShadow: '2px 2px 4px rgba(0,0,0,0.05)' }}
              >
                <span className="truncate block" title={`${varX} \\ ${varY}`}>
                  {varX} \ {varY}
                </span>
              </th>
              
              {/* Y category headers - sticky top */}
              {yCategories.map((yCat, yIdx) => (
                <th 
                  key={yIdx}
                  className="sticky top-0 z-20 bg-muted/80 border-r border-b p-2 text-center font-medium min-w-[80px]"
                >
                  <span className="truncate block" title={yCat}>
                    {yCat.length > 10 ? yCat.slice(0, 10) + '…' : yCat}
                  </span>
                </th>
              ))}
              
              {/* Marginal X header - sticky top and right */}
              <th 
                className="sticky top-0 right-0 z-30 bg-primary/20 border-b p-2 text-center font-semibold min-w-[90px]"
                style={{ boxShadow: '-2px 2px 4px rgba(0,0,0,0.05)' }}
              >
                Marginal X
              </th>
            </tr>
          </thead>

          <tbody>
            {/* Data rows - with potential separator */}
            {displayIndices.map((xIdx, displayIdx) => {
              // Separator row
              if (xIdx === -1) {
                return (
                  <tr key="separator" className="bg-muted/30">
                    <td 
                      className="sticky left-0 z-10 bg-muted/50 border-r border-b p-2 text-center font-medium"
                      colSpan={1}
                    >
                      ⋮
                    </td>
                    {yCategories.map((_, yIdx) => (
                      <td key={yIdx} className="border-r border-b p-2 text-center text-muted-foreground">
                        ⋮
                      </td>
                    ))}
                    <td className="sticky right-0 z-10 bg-muted/50 border-b p-2 text-center">
                      ⋮
                    </td>
                  </tr>
                );
              }
              
              const xCat = xCategories[xIdx];
              return (
                <tr key={xIdx} className="hover:bg-muted/5">
                  {/* X category label - sticky left */}
                  <td 
                    className="sticky left-0 z-10 bg-background border-r border-b p-2 font-medium"
                    style={{ boxShadow: '2px 0 4px rgba(0,0,0,0.03)' }}
                  >
                    <span className="truncate block" title={xCat}>
                      {xCat.length > 12 ? xCat.slice(0, 12) + '…' : xCat}
                    </span>
                  </td>
                  
                  {/* Joint frequency cells */}
                  {yCategories.map((_, yIdx) => {
                    const count = jointFreq[xIdx][yIdx];
                    return (
                      <td 
                        key={yIdx}
                        className="border-r border-b p-2 text-center font-mono"
                      >
                        <span className="block font-semibold">{count}</span>
                        <span className="block text-muted-foreground text-[10px]">
                          ({formatPercent(count)})
                        </span>
                      </td>
                    );
                  })}
                  
                  {/* Marginal X value - sticky right */}
                  <td 
                    className="sticky right-0 z-10 bg-primary/10 border-b p-2 text-center font-mono"
                    style={{ boxShadow: '-2px 0 4px rgba(0,0,0,0.03)' }}
                  >
                    <span className="block font-semibold">{marginalX[xIdx]}</span>
                    <span className="block text-muted-foreground text-[10px]">
                      ({formatPercent(marginalX[xIdx])})
                    </span>
                  </td>
                </tr>
              );
            })}

            {/* Marginal Y row - sticky bottom */}
            <tr>
              {/* Marginal Y label - sticky left and bottom */}
              <td 
                className="sticky left-0 bottom-0 z-30 bg-primary/20 border-r p-2 font-semibold"
                style={{ boxShadow: '2px -2px 4px rgba(0,0,0,0.05)' }}
              >
                Marginal Y
              </td>
              
              {/* Marginal Y values - sticky bottom */}
              {yCategories.map((_, yIdx) => (
                <td 
                  key={yIdx}
                  className="sticky bottom-0 z-20 bg-primary/10 border-r p-2 text-center font-mono"
                >
                  <span className="block font-semibold">{marginalY[yIdx]}</span>
                  <span className="block text-muted-foreground text-[10px]">
                    ({formatPercent(marginalY[yIdx])})
                  </span>
                </td>
              ))}
              
              {/* Grand total - sticky bottom and right */}
              <td 
                className="sticky right-0 bottom-0 z-30 bg-primary/30 p-2 text-center font-mono font-bold"
                style={{ boxShadow: '-2px -2px 4px rgba(0,0,0,0.05)' }}
              >
                <span className="block">{total}</span>
                <span className="block text-muted-foreground text-[10px]">(100%)</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      {/* Show all / Show less toggle */}
      {shouldTruncate && (
        <div className="p-2 bg-muted/20 border-t flex justify-center">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAll(!showAll)}
            className="h-7 text-xs gap-1"
          >
            {showAll ? (
              <>
                <ChevronUp className="w-3 h-3" />
                Show first/last 10 rows
              </>
            ) : (
              <>
                <ChevronDown className="w-3 h-3" />
                Show all {xCategories.length} rows
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
