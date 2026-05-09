import { useMemo } from 'react';
import { BoxPlotData } from '@/lib/bivariateStatistics';

interface BoxPlotChartProps {
  data: BoxPlotData[];
  maxCategories?: number;
}

export function BoxPlotChart({ data, maxCategories = 10 }: BoxPlotChartProps) {
  const displayData = useMemo(() => data.slice(0, maxCategories), [data, maxCategories]);
  
  // Calculate scales
  const { minVal, maxVal } = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    displayData.forEach(d => {
      min = Math.min(min, d.min, ...d.outliers);
      max = Math.max(max, d.max, ...d.outliers);
    });
    const padding = (max - min) * 0.1 || 1;
    return {
      minVal: min - padding,
      maxVal: max + padding,
    };
  }, [displayData]);

  // Responsive dimensions
  const chartHeight = 280;
  const margin = { top: 20, right: 20, bottom: 55, left: 55 };
  const plotHeight = chartHeight - margin.top - margin.bottom;
  
  // Calculate box width based on number of categories
  const availableWidth = Math.max(350, displayData.length * 55);
  const boxWidth = Math.min(45, Math.max(25, (availableWidth - margin.left - margin.right) / displayData.length - 10));
  const boxGap = Math.max(8, (availableWidth - margin.left - margin.right - displayData.length * boxWidth) / (displayData.length + 1));
  const plotWidth = displayData.length * boxWidth + (displayData.length + 1) * boxGap;
  const totalWidth = margin.left + plotWidth + margin.right;

  // Scale value to Y position
  const scaleY = (val: number) => {
    const ratio = (maxVal - val) / (maxVal - minVal);
    return margin.top + ratio * plotHeight;
  };

  // Generate Y-axis ticks
  const yTicks = useMemo(() => {
    const tickCount = 5;
    const step = (maxVal - minVal) / (tickCount - 1);
    return Array.from({ length: tickCount }, (_, i) => minVal + step * i);
  }, [minVal, maxVal]);

  // Colors
  const boxFill = 'hsl(24 85% 55% / 0.25)';
  const boxStroke = 'hsl(24 85% 50%)';
  const medianColor = 'hsl(24 90% 45%)';
  const whiskerColor = 'hsl(var(--foreground) / 0.7)';
  const meanColor = 'hsl(var(--foreground))';
  const outlierColor = 'hsl(0 70% 50%)';

  return (
    <div className="w-full">
      <div className="overflow-x-auto">
        <svg 
          width={Math.max(totalWidth, 350)} 
          height={chartHeight}
          className="font-sans mx-auto block"
          style={{ minWidth: '100%' }}
        >
          {/* Background */}
          <rect 
            x={margin.left} 
            y={margin.top} 
            width={plotWidth} 
            height={plotHeight}
            fill="hsl(var(--muted) / 0.2)"
            rx={4}
          />

          {/* Y-axis grid lines and labels */}
          {yTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={margin.left}
                y1={scaleY(tick)}
                x2={margin.left + plotWidth}
                y2={scaleY(tick)}
                stroke="hsl(var(--border))"
                strokeWidth={1}
                strokeDasharray={i === 0 || i === yTicks.length - 1 ? '0' : '3,3'}
                opacity={0.5}
              />
              <text
                x={margin.left - 8}
                y={scaleY(tick)}
                textAnchor="end"
                alignmentBaseline="middle"
                className="fill-muted-foreground"
                fontSize="10"
              >
                {tick >= 1000 ? tick.toFixed(0) : tick >= 100 ? tick.toFixed(0) : tick.toFixed(1)}
              </text>
            </g>
          ))}

          {/* Y-axis line */}
          <line
            x1={margin.left}
            y1={margin.top}
            x2={margin.left}
            y2={margin.top + plotHeight}
            stroke="hsl(var(--border))"
            strokeWidth={1}
          />

          {/* X-axis line */}
          <line
            x1={margin.left}
            y1={margin.top + plotHeight}
            x2={margin.left + plotWidth}
            y2={margin.top + plotHeight}
            stroke="hsl(var(--border))"
            strokeWidth={1}
          />

          {/* Box plots */}
          {displayData.map((d, i) => {
            const centerX = margin.left + boxGap + i * (boxWidth + boxGap) + boxWidth / 2;
            const halfBox = boxWidth / 2;
            
            const yMin = scaleY(d.min);
            const yQ1 = scaleY(d.q1);
            const yMedian = scaleY(d.median);
            const yQ3 = scaleY(d.q3);
            const yMax = scaleY(d.max);
            const yMean = scaleY(d.mean);

            return (
              <g key={i}>
                {/* Lower whisker (min to Q1) */}
                <line
                  x1={centerX}
                  y1={yMin}
                  x2={centerX}
                  y2={yQ1}
                  stroke={whiskerColor}
                  strokeWidth={1.5}
                />
                {/* Min cap */}
                <line
                  x1={centerX - halfBox * 0.35}
                  y1={yMin}
                  x2={centerX + halfBox * 0.35}
                  y2={yMin}
                  stroke={whiskerColor}
                  strokeWidth={1.5}
                />

                {/* Upper whisker (Q3 to max) */}
                <line
                  x1={centerX}
                  y1={yQ3}
                  x2={centerX}
                  y2={yMax}
                  stroke={whiskerColor}
                  strokeWidth={1.5}
                />
                {/* Max cap */}
                <line
                  x1={centerX - halfBox * 0.35}
                  y1={yMax}
                  x2={centerX + halfBox * 0.35}
                  y2={yMax}
                  stroke={whiskerColor}
                  strokeWidth={1.5}
                />

                {/* Box (Q1 to Q3) */}
                <rect
                  x={centerX - halfBox}
                  y={Math.min(yQ1, yQ3)}
                  width={boxWidth}
                  height={Math.max(1, Math.abs(yQ1 - yQ3))}
                  fill={boxFill}
                  stroke={boxStroke}
                  strokeWidth={1.5}
                  rx={2}
                />

                {/* Median line */}
                <line
                  x1={centerX - halfBox}
                  y1={yMedian}
                  x2={centerX + halfBox}
                  y2={yMedian}
                  stroke={medianColor}
                  strokeWidth={2.5}
                />

                {/* Mean marker (diamond) */}
                <polygon
                  points={`${centerX},${yMean - 4} ${centerX + 4},${yMean} ${centerX},${yMean + 4} ${centerX - 4},${yMean}`}
                  fill={meanColor}
                />

                {/* Outliers */}
                {d.outliers.slice(0, 10).map((outlier, oi) => (
                  <circle
                    key={oi}
                    cx={centerX}
                    cy={scaleY(outlier)}
                    r={3}
                    fill="none"
                    stroke={outlierColor}
                    strokeWidth={1.5}
                  />
                ))}

                {/* Category label */}
                <text
                  x={centerX}
                  y={margin.top + plotHeight + 14}
                  textAnchor="middle"
                  className="fill-foreground"
                  fontSize="10"
                  fontWeight="500"
                >
                  {d.category.length > 8 ? d.category.slice(0, 8) + '…' : d.category}
                </text>

                {/* Count label */}
                <text
                  x={centerX}
                  y={margin.top + plotHeight + 26}
                  textAnchor="middle"
                  className="fill-muted-foreground"
                  fontSize="9"
                >
                  n={d.count}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-5 mt-3 text-xs text-muted-foreground flex-wrap">
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-0.5" style={{ backgroundColor: medianColor }}></div>
          <span>Median</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rotate-45" style={{ backgroundColor: meanColor }}></div>
          <span>Mean</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-3 rounded-sm" style={{ backgroundColor: boxFill, border: `1.5px solid ${boxStroke}` }}></div>
          <span>IQR</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full border-2" style={{ borderColor: outlierColor }}></div>
          <span>Outliers</span>
        </div>
      </div>
    </div>
  );
}
