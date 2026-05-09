// Bivariate Analysis HTML Report Generator

interface Statistics {
  n: number;
  uniqueX: number;
  uniqueY: number;
  xIsNumeric: boolean;
  yIsNumeric: boolean;
  yUniqueCount: number;
  crosstab: {
    xCategories: string[];
    yCategories: string[];
    jointFreq: number[][];
    marginalX: number[];
    marginalY: number[];
    total: number;
  };
  chiSquare: {
    chiSquare: number;
    cramersV: number;
    contingencyCoefficient: number;
    phiCoefficient: number | null;
    degreesOfFreedom: number;
  };
  correlations: {
    pearson: number | null;
    spearman: number | null;
    kendall: number | null;
    covariance: number | null;
  } | null;
  sampleCorrelations?: {
    pearson: number | null;
    spearman: number | null;
    kendall: number | null;
  } | null;
  conditionalStats: {
    y: string;
    count: number;
    mean: number;
    std: number;
    min: number;
    q25: number;
    median: number;
    q75: number;
    max: number;
  }[] | null;
  boxPlotData: {
    category: string;
    min: number;
    q1: number;
    median: number;
    q3: number;
    max: number;
    mean: number;
    count: number;
    outliers: number[];
  }[] | null;
}

export function generateBivariateHTML(
  varX: string,
  varY: string,
  statistics: Statistics,
  columnTypes: Record<string, 'numeric' | 'categorical'>
): string {
  const formatNum = (n: number | null | undefined, decimals = 4) => 
    n != null ? n.toFixed(decimals) : 'N/A';

  const formatPercent = (value: number, total: number) => 
    ((value / total) * 100).toFixed(1) + '%';

  // Generate conditional frequency table HTML
  const generateCrosstabHTML = () => {
    const { xCategories, yCategories, jointFreq, marginalX, marginalY, total } = statistics.crosstab;
    
    let html = `<table class="freq-table">
      <thead>
        <tr>
          <th class="corner">${varX} \\ ${varY}</th>
          ${yCategories.slice(0, 15).map(y => `<th>${y.length > 10 ? y.slice(0, 10) + '…' : y}</th>`).join('')}
          <th class="marginal">Marginal X</th>
        </tr>
      </thead>
      <tbody>`;
    
    xCategories.slice(0, 20).forEach((xCat, xIdx) => {
      html += `<tr>
        <td class="row-label">${xCat.length > 12 ? xCat.slice(0, 12) + '…' : xCat}</td>
        ${yCategories.slice(0, 15).map((_, yIdx) => {
          const count = jointFreq[xIdx][yIdx];
          return `<td class="cell"><span class="count">${count}</span><br><span class="pct">(${formatPercent(count, total)})</span></td>`;
        }).join('')}
        <td class="marginal"><span class="count">${marginalX[xIdx]}</span><br><span class="pct">(${formatPercent(marginalX[xIdx], total)})</span></td>
      </tr>`;
    });
    
    html += `<tr class="marginal-row">
      <td class="row-label">Marginal Y</td>
      ${yCategories.slice(0, 15).map((_, yIdx) => 
        `<td class="marginal"><span class="count">${marginalY[yIdx]}</span><br><span class="pct">(${formatPercent(marginalY[yIdx], total)})</span></td>`
      ).join('')}
      <td class="total"><span class="count">${total}</span><br><span class="pct">(100%)</span></td>
    </tr>`;
    
    html += '</tbody></table>';
    return html;
  };

  // Generate statistics description table
  const generateStatsTableHTML = () => {
    if (!statistics.conditionalStats || statistics.conditionalStats.length === 0) {
      return '<p class="muted">No conditional statistics available.</p>';
    }

    const metrics = ['Count', 'Mean', 'Std', 'Min', 'Q25', 'Median', 'Q75', 'Max'];
    const data = statistics.conditionalStats.slice(0, 15);

    let html = `<table class="stats-table">
      <thead>
        <tr>
          <th>${varY} →</th>
          ${data.map(d => `<th>${d.y.length > 10 ? d.y.slice(0, 10) + '…' : d.y}</th>`).join('')}
        </tr>
      </thead>
      <tbody>`;

    metrics.forEach((metric, idx) => {
      html += `<tr class="${idx % 2 === 0 ? 'alt' : ''}">
        <td class="metric">${metric}</td>
        ${data.map(d => {
          let val: number;
          switch (metric) {
            case 'Count': val = d.count; break;
            case 'Mean': val = d.mean; break;
            case 'Std': val = d.std; break;
            case 'Min': val = d.min; break;
            case 'Q25': val = d.q25; break;
            case 'Median': val = d.median; break;
            case 'Q75': val = d.q75; break;
            case 'Max': val = d.max; break;
            default: val = 0;
          }
          return `<td class="value">${metric === 'Count' ? val : formatNum(val, 2)}</td>`;
        }).join('')}
      </tr>`;
    });

    html += '</tbody></table>';
    return html;
  };

  // Generate box plot SVG
  const generateBoxPlotSVG = () => {
    if (!statistics.boxPlotData || statistics.boxPlotData.length === 0) {
      return '<p class="muted">No box plot data available.</p>';
    }

    const data = statistics.boxPlotData.slice(0, 8);
    let minVal = Infinity, maxVal = -Infinity;
    data.forEach(d => {
      minVal = Math.min(minVal, d.min, ...d.outliers);
      maxVal = Math.max(maxVal, d.max, ...d.outliers);
    });
    const padding = (maxVal - minVal) * 0.1 || 1;
    minVal -= padding;
    maxVal += padding;

    const chartHeight = 280;
    const margin = { top: 20, right: 60, bottom: 50, left: 50 };
    const plotHeight = chartHeight - margin.top - margin.bottom;
    const boxWidth = 40;
    const boxGap = 15;
    const plotWidth = data.length * (boxWidth + boxGap);
    const totalWidth = margin.left + plotWidth + margin.right;

    const scaleY = (val: number) => {
      const ratio = (maxVal - val) / (maxVal - minVal);
      return margin.top + ratio * plotHeight;
    };

    let svg = `<svg width="${Math.max(totalWidth, 400)}" height="${chartHeight}" class="box-plot-svg">
      <rect x="${margin.left}" y="${margin.top}" width="${plotWidth}" height="${plotHeight}" fill="#f8f8f8" rx="4"/>`;

    // Y-axis
    for (let i = 0; i < 5; i++) {
      const val = minVal + (i * (maxVal - minVal)) / 4;
      const y = scaleY(val);
      svg += `<line x1="${margin.left}" y1="${y}" x2="${margin.left + plotWidth}" y2="${y}" stroke="#ddd" stroke-dasharray="4,4"/>
        <text x="${margin.left - 5}" y="${y}" text-anchor="end" alignment-baseline="middle" font-size="10" fill="#666">${val.toFixed(1)}</text>`;
    }

    // Box plots
    data.forEach((d, i) => {
      const cx = margin.left + i * (boxWidth + boxGap) + (boxWidth + boxGap) / 2;
      const halfBox = boxWidth / 2;
      
      const yMin = scaleY(d.min);
      const yQ1 = scaleY(d.q1);
      const yMedian = scaleY(d.median);
      const yQ3 = scaleY(d.q3);
      const yMax = scaleY(d.max);
      const yMean = scaleY(d.mean);

      svg += `
        <line x1="${cx}" y1="${yMin}" x2="${cx}" y2="${yQ1}" stroke="#333" stroke-width="1.5"/>
        <line x1="${cx - halfBox * 0.4}" y1="${yMin}" x2="${cx + halfBox * 0.4}" y2="${yMin}" stroke="#333" stroke-width="1.5"/>
        <line x1="${cx}" y1="${yQ3}" x2="${cx}" y2="${yMax}" stroke="#333" stroke-width="1.5"/>
        <line x1="${cx - halfBox * 0.4}" y1="${yMax}" x2="${cx + halfBox * 0.4}" y2="${yMax}" stroke="#333" stroke-width="1.5"/>
        <rect x="${cx - halfBox}" y="${Math.min(yQ1, yQ3)}" width="${boxWidth}" height="${Math.abs(yQ1 - yQ3)}" fill="rgba(234, 88, 12, 0.2)" stroke="#ea580c" stroke-width="2" rx="2"/>
        <line x1="${cx - halfBox}" y1="${yMedian}" x2="${cx + halfBox}" y2="${yMedian}" stroke="#ea580c" stroke-width="2.5"/>
        <polygon points="${cx},${yMean - 4} ${cx + 4},${yMean} ${cx},${yMean + 4} ${cx - 4},${yMean}" fill="#333"/>
        <text x="${cx}" y="${margin.top + plotHeight + 15}" text-anchor="middle" font-size="10" fill="#333">${d.category.length > 8 ? d.category.slice(0, 8) + '…' : d.category}</text>
        <text x="${cx}" y="${margin.top + plotHeight + 28}" text-anchor="middle" font-size="9" fill="#666">n=${d.count}</text>`;

      d.outliers.forEach(o => {
        svg += `<circle cx="${cx}" cy="${scaleY(o)}" r="3" fill="none" stroke="#dc2626" stroke-width="1.5"/>`;
      });
    });

    svg += '</svg>';
    return svg;
  };

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bivariate Analysis: ${varX} vs ${varY}</title>
  <style>
    :root {
      --primary: #ea580c;
      --primary-light: #fed7aa;
      --bg: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --border: #e5e7eb;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; padding: 2rem; max-width: 1200px; margin: 0 auto; }
    h1 { color: var(--primary); margin-bottom: 0.5rem; font-size: 1.75rem; }
    h2 { color: var(--text); font-size: 1.1rem; margin: 1.5rem 0 0.75rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--primary-light); }
    h3 { color: var(--muted); font-size: 0.9rem; margin: 1rem 0 0.5rem; }
    .subtitle { color: var(--muted); margin-bottom: 1.5rem; }
    .card { background: white; border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
    .kpi-grid { display: flex; gap: 2rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .kpi { text-align: left; }
    .kpi-label { font-size: 0.75rem; color: var(--muted); }
    .kpi-value { font-size: 1.25rem; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    th, td { padding: 0.5rem; text-align: center; border: 1px solid var(--border); }
    th { background: #f9fafb; font-weight: 600; }
    .freq-table .corner { background: var(--primary-light); }
    .freq-table .row-label { text-align: left; font-weight: 500; background: #fafafa; }
    .freq-table .marginal { background: rgba(234, 88, 12, 0.1); font-weight: 600; }
    .freq-table .total { background: rgba(234, 88, 12, 0.2); font-weight: 700; }
    .freq-table .cell .count { font-weight: 600; }
    .freq-table .cell .pct, .freq-table .marginal .pct { font-size: 0.7rem; color: var(--muted); }
    .freq-table .marginal-row td { background: rgba(234, 88, 12, 0.1); }
    .stats-table .metric { text-align: left; font-weight: 500; background: #fafafa; }
    .stats-table .value { font-family: monospace; }
    .stats-table .alt { background: #fafafa; }
    .measure-table { max-width: 400px; }
    .measure-table td:first-child { text-align: left; }
    .measure-table td:last-child { text-align: right; font-family: monospace; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    .muted { color: var(--muted); font-size: 0.85rem; }
    .overflow-x { overflow-x: auto; }
    .box-plot-svg { display: block; margin: 0 auto; }
    footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border); font-size: 0.75rem; color: var(--muted); text-align: center; }
  </style>
</head>
<body>
  <h1>Bivariate Analysis Report</h1>
  <p class="subtitle">${varX} (${columnTypes[varX]}) vs ${varY} (${columnTypes[varY]})</p>

  <div class="card">
    <h3>Joint Empirical Distributions</h3>
    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-label">Sample size (n)</div><div class="kpi-value">${statistics.n.toLocaleString()}</div></div>
      <div class="kpi"><div class="kpi-label">Unique X values</div><div class="kpi-value">${statistics.uniqueX}</div></div>
      <div class="kpi"><div class="kpi-label">Unique Y values</div><div class="kpi-value">${statistics.uniqueY}</div></div>
      <div class="kpi"><div class="kpi-label">Cells in crosstab</div><div class="kpi-value">${statistics.uniqueX * statistics.uniqueY}</div></div>
    </div>
  </div>

  <h2>Conditional Frequency Table</h2>
  <div class="card overflow-x">
    ${generateCrosstabHTML()}
  </div>

  ${statistics.xIsNumeric ? `
  <h2>Statistics Description</h2>
  <p class="muted">${varX} grouped by ${varY}</p>
  <div class="card overflow-x">
    ${generateStatsTableHTML()}
  </div>

  <h2>Box Plot: ${varX} by ${varY}</h2>
  <div class="card overflow-x">
    ${generateBoxPlotSVG()}
  </div>
  ` : ''}

  <h2>Correlation Measures</h2>
  <div class="grid">
    <div class="card">
      <h3>Association (contingency-based)</h3>
      <table class="measure-table">
        <tr><td>Chi-square (χ²)</td><td>${formatNum(statistics.chiSquare.chiSquare, 6)}</td></tr>
        <tr><td>Cramér's V</td><td>${formatNum(statistics.chiSquare.cramersV, 6)}</td></tr>
        <tr><td>Contingency Coefficient</td><td>${formatNum(statistics.chiSquare.contingencyCoefficient, 6)}</td></tr>
        ${statistics.chiSquare.phiCoefficient != null ? `<tr><td>Phi (φ)</td><td>${formatNum(statistics.chiSquare.phiCoefficient, 6)}</td></tr>` : ''}
      </table>
    </div>
    <div class="card">
      <h3>Chi-square Test Details</h3>
      <table class="measure-table">
        <tr><td>Chi-square statistic</td><td>${formatNum(statistics.chiSquare.chiSquare, 6)}</td></tr>
        <tr><td>Degrees of freedom</td><td>${statistics.chiSquare.degreesOfFreedom}</td></tr>
      </table>
    </div>
  </div>

  ${statistics.correlations ? `
  <div class="card">
    <h3>Correlations (full data)</h3>
    <table class="measure-table">
      <tr><td>Pearson</td><td>${formatNum(statistics.correlations.pearson, 6)}</td></tr>
      <tr><td>Spearman</td><td>${formatNum(statistics.correlations.spearman, 6)}</td></tr>
      <tr><td>Kendall's tau</td><td>${formatNum(statistics.correlations.kendall, 6)}</td></tr>
      <tr><td>Covariance</td><td>${formatNum(statistics.correlations.covariance, 6)}</td></tr>
    </table>
  </div>
  ` : '<p class="muted">Correlations not available (X and Y must both be numeric).</p>'}

  <footer>
    Generated on ${new Date().toLocaleString()} | Bivariate Analysis Profile
  </footer>
</body>
</html>`;
}
