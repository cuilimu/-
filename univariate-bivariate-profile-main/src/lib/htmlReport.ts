import { DatasetPayload, formatNumber, formatPercent } from './statistics';

export interface AIVariableInference {
  inferred_type: string;
  inferred_definition: string;
  confidence: 'high' | 'medium' | 'low';
}

export type AIInferenceMap = Record<string, AIVariableInference>;

/**
 * Generates a standalone HTML report matching the Python notebook's dark theme output
 * @param payload - The analysis payload with metadata and variable info
 * @param rawData - Optional full dataset for interaction visualizations (limited to 5000 rows for performance)
 * @param aiInferences - Optional AI-inferred types and definitions
 */
export function generateHTMLReport(
  payload: DatasetPayload, 
  rawData?: Record<string, unknown>[],
  aiInferences?: AIInferenceMap
): string {
  const { meta, variables, repro, alerts, sample_data } = payload;
  // Limit raw data to 5000 rows for reasonable HTML file size
  const interactionData = rawData ? rawData.slice(0, 5000) : null;
  const payloadJson = JSON.stringify(payload, null, 2);
  const interactionDataJson = interactionData ? JSON.stringify(interactionData) : 'null';
  const aiInferencesJson = aiInferences ? JSON.stringify(aiInferences) : '{}';

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${meta.title} - ${meta.source_file}</title>
<style>
  :root {
    --bg: #f5f5f5;
    --panel: #ffffff;
    --panel2: #fafafa;
    --text: #171717;
    --muted: #525252;
    --line: rgba(0,0,0,.10);
    --chip: rgba(0,0,0,.04);
    --accent: #ea580c;
    --warn: #d97706;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    background: var(--bg); color: var(--text);
  }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 18px; }
  .header {
    background: linear-gradient(180deg, rgba(234,88,12,.08), rgba(255,255,255,0));
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 16px 18px;
  }
  .h-title { font-size: 20px; font-weight: 700; }
  .h-sub { color: var(--muted); margin-top: 6px; font-size: 13px; display:flex; gap:16px; flex-wrap: wrap; }
  .tabs { display:flex; gap:10px; margin-top: 14px; flex-wrap: wrap; }
  .tabbtn {
    padding: 9px 12px; border-radius: 12px; border: 1px solid var(--line);
    background: rgba(0,0,0,.02); color: var(--text);
    cursor: pointer; font-weight: 600; font-size: 13px;
  }
  .tabbtn.active { border-color: rgba(234,88,12,.65); background: rgba(234,88,12,.12); }
  .tab { display:none; margin-top: 14px; }
  .tab.active { display:block; }
  .grid2 { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .grid3 { display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
  .card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 14px;
  }
  .card h3 { margin: 0 0 10px; font-size: 14px; color: var(--muted); font-weight: 700; }
  .kv { display:grid; grid-template-columns: 190px 1fr; gap: 8px 12px; font-size: 13px; }
  .k { color: var(--muted); }
  .v { color: var(--text); overflow-wrap: anywhere; }
  .vars-layout { display:grid; grid-template-columns: 300px 1fr; gap: 12px; }
  .sidebar {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 12px;
    height: calc(100vh - 220px);
    position: sticky;
    top: 16px;
    overflow: hidden;
  }
  .search {
    width: 100%;
    padding: 10px 10px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--panel);
    color: var(--text);
    outline: none;
  }
  select.search {
    background: var(--panel);
    cursor: pointer;
  }
  select.search option {
    background: var(--panel);
    color: var(--text);
    padding: 8px;
  }
  select.search option:hover,
  select.search option:checked {
    background: rgba(234,88,12,.25);
    color: var(--text);
  }
  .varlist { margin-top: 10px; overflow: auto; height: calc(100% - 46px); padding-right: 6px; }
  .varitem {
    padding: 9px 10px;
    border-radius: 12px;
    border: 1px solid transparent;
    cursor: pointer;
    display:flex; justify-content: space-between; gap:10px;
    color: var(--text);
  }
  .varitem:hover { background: rgba(0,0,0,.03); }
  .varitem.active {
    background: rgba(234,88,12,.10);
    border-color: rgba(234,88,12,.55);
  }
  .badge {
    font-size: 11px; padding: 3px 8px;
    border-radius: 999px;
    background: var(--chip);
    color: var(--muted);
    border: 1px solid var(--line);
    white-space: nowrap;
  }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
  .chip {
    font-size: 12px; padding: 5px 10px;
    border-radius: 12px;
    background: var(--chip);
    border: 1px solid var(--line);
  }
  .section-title { font-size: 18px; font-weight: 700; margin-bottom: 10px; }
  .btn {
    padding: 9px 12px; border-radius: 12px; border: 1px solid var(--line);
    background: rgba(0,0,0,.02); color: var(--text);
    cursor: pointer; font-weight: 700; font-size: 13px;
    display:inline-flex; align-items:center; gap:8px;
  }
  .btn:hover { background: rgba(0,0,0,.04); }
  .subtabs { display:flex; gap:10px; flex-wrap: wrap; margin: 8px 0 10px; }
  .subtabbtn {
    padding: 7px 10px; border-radius: 12px; border: 1px solid var(--line);
    background: rgba(0,0,0,.02); color: var(--text);
    cursor: pointer; font-weight: 700; font-size: 12px;
  }
  .subtabbtn.active { border-color: rgba(234,88,12,.65); background: rgba(234,88,12,.12); }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th, td {
    border-bottom: 1px solid var(--line);
    padding: 8px 6px;
    vertical-align: middle;
  }
  th { color: var(--muted); text-align: left; font-weight: 800; }
  .barcell {
    position: relative;
    height: 18px;
    border-radius: 999px;
    background: rgba(0,0,0,.04);
    border: 1px solid rgba(0,0,0,.08);
    overflow: hidden;
  }
  .barfill {
    position: absolute; left: 0; top: 0; bottom: 0;
    background: rgba(234,88,12,.35);
  }
  .bartext {
    position: absolute; left: 8px; top: 50%;
    transform: translateY(-50%);
    font-size: 12px; color: var(--text); font-weight: 700;
  }
  .plotbox {
    border-radius: 16px;
    border: 1px solid var(--line);
    background: var(--panel2);
    padding: 10px;
    overflow: hidden;
  }
  .plot-svg {
    width: 100%;
    height: 200px;
  }
  .note {
    font-size: 12px; color: var(--muted);
    margin-top: 8px;
  }
  .overview-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .alerts-table { margin-top: 8px; }
  .corr-alert { padding: 4px 8px; border-radius: 8px; font-size: 11px; }
  .corr-alert.high { background: rgba(255,100,100,.2); color: #ff9999; }
  .sample-section { margin-top: 12px; }
  .sample-card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 14px;
    margin-top: 12px;
  }
  .sample-card h3 { margin: 0 0 10px; font-size: 14px; color: var(--muted); font-weight: 700; }
  .sample-tabs { display: flex; gap: 8px; margin-bottom: 10px; }
  .sample-tab-btn {
    padding: 7px 14px; border-radius: 12px; border: 1px solid var(--line);
    background: rgba(0,0,0,.02); color: var(--text);
    cursor: pointer; font-weight: 600; font-size: 12px;
  }
  .sample-tab-btn.active { border-color: rgba(234,88,12,.65); background: rgba(234,88,12,.12); }
  .sample-table-wrap {
    max-height: 350px;
    overflow: auto;
    border: 1px solid var(--line);
    border-radius: 12px;
  }
  .sample-table {
    width: max-content;
    min-width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .sample-table th, .sample-table td {
    border: 1px solid var(--line);
    padding: 6px 10px;
    white-space: nowrap;
  }
  .sample-table th {
    background: var(--panel2);
    position: sticky;
    top: 0;
    z-index: 1;
  }
  @media (max-width: 900px) {
    .vars-layout { grid-template-columns: 1fr; }
    .sidebar { position: static; height: auto; max-height: 300px; }
    .grid2, .grid3, .overview-layout { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div class="h-title">${meta.title}</div>
      <div class="h-sub">
        <div><span class="muted">Source:</span> ${meta.source_file}</div>
        <div><span class="muted">Generated:</span> ${meta.generated_at}</div>
        <div><span class="muted">Rows:</span> ${meta.rows}</div>
        <div><span class="muted">Columns:</span> ${meta.cols}</div>
      </div>

      <div class="tabs">
        <button class="tabbtn active" data-tab="tab-overview">Overview</button>
        <button class="tabbtn" data-tab="tab-variables">Variables</button>
        <button class="tabbtn" data-tab="tab-alerts">Alerts</button>
        <button class="tabbtn" data-tab="tab-interaction">Interaction</button>
        <button class="tabbtn" data-tab="tab-repro">Reproducibility</button>
      </div>
    </div>

    <div id="tab-overview" class="tab active">
      <div class="overview-layout">
        <div class="card">
          <h3>Dataset statistics</h3>
          <div class="kv">
            <div class="k">Missing cells</div><div class="v">${meta.missing_cells} (${formatPercent(meta.missing_pct)})</div>
            <div class="k">Duplicate rows</div><div class="v">${meta.duplicate_rows} (${formatPercent(meta.duplicate_pct)})</div>
          </div>
        </div>
        <div class="card">
          <h3>Variable types</h3>
          <div class="kv">
            <div class="k">Numeric</div><div class="v">${meta.type_counts.numeric}</div>
            <div class="k">Categorical</div><div class="v">${meta.type_counts.categorical}</div>
            <div class="k">Datetime</div><div class="v">${meta.type_counts.datetime}</div>
            <div class="k">Boolean</div><div class="v">${meta.type_counts.boolean}</div>
          </div>
        </div>
      </div>
      
      <div class="card" style="margin-top:12px;">
        <h3>Null Values by Column</h3>
        <p style="color:var(--muted);font-size:12px;margin-bottom:12px;">Distribution of missing values across all columns</p>
        <div id="null-values-chart"></div>
        <div style="display:flex;align-items:center;justify-content:center;gap:20px;margin-top:12px;font-size:11px;color:var(--muted);">
          <div style="display:flex;align-items:center;gap:6px;"><div style="width:12px;height:12px;border-radius:3px;background:rgba(234,88,12,0.7);"></div>Low (&lt;20%)</div>
          <div style="display:flex;align-items:center;gap:6px;"><div style="width:12px;height:12px;border-radius:3px;background:rgb(245,158,11);"></div>Medium (20-50%)</div>
          <div style="display:flex;align-items:center;gap:6px;"><div style="width:12px;height:12px;border-radius:3px;background:rgb(239,68,68);"></div>High (&gt;50%)</div>
        </div>
      </div>
      
      <div class="sample-section">
        <div class="sample-card">
          <h3>Sample Data Preview</h3>
          <div class="sample-tabs">
            <button class="sample-tab-btn active" data-sample="head">First 10 Rows</button>
            <button class="sample-tab-btn" data-sample="tail">Last 10 Rows</button>
          </div>
          <div id="sample-head" class="sample-table-wrap"></div>
          <div id="sample-tail" class="sample-table-wrap" style="display:none;"></div>
        </div>
      </div>
    </div>

    <div id="tab-variables" class="tab">
      <div class="card" id="var-dictionary-card" style="margin-bottom:12px;">
        <h3>Variable Dictionary</h3>
        <p style="color:var(--muted);font-size:12px;margin-bottom:12px;">AI-inferred semantic types and business definitions</p>
        <div style="max-height:300px;overflow:auto;border:1px solid var(--line);border-radius:12px;">
          <table id="var-dictionary-table" style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
              <tr>
                <th style="position:sticky;top:0;background:var(--panel2);padding:10px 8px;text-align:left;border-bottom:1px solid var(--line);">Variable</th>
                <th style="position:sticky;top:0;background:var(--panel2);padding:10px 8px;text-align:left;border-bottom:1px solid var(--line);">Type</th>
                <th style="position:sticky;top:0;background:var(--panel2);padding:10px 8px;text-align:left;border-bottom:1px solid var(--line);">Inferred Type</th>
                <th style="position:sticky;top:0;background:var(--panel2);padding:10px 8px;text-align:left;border-bottom:1px solid var(--line);">Inferred Definition</th>
              </tr>
            </thead>
            <tbody id="var-dictionary-tbody"></tbody>
          </table>
        </div>
      </div>
      <div class="vars-layout">
        <div class="sidebar">
          <input id="var-search" class="search" placeholder="Search variables..." />
          <div id="var-list" class="varlist"></div>
        </div>
        <div id="var-content"></div>
      </div>
    </div>

    <div id="tab-alerts" class="tab">
      <div class="card">
        <h3>Data Quality Alerts</h3>
        
        <div style="margin-top:10px;">
          <h4 style="color:var(--muted);font-size:13px;">Correlation Alerts</h4>
          <table class="alerts-table">
            <thead><tr><th>Message</th><th>Type</th></tr></thead>
            <tbody id="alerts-corr-tbody"></tbody>
          </table>
        </div>

        <div style="margin-top:18px;">
          <h4 style="color:var(--muted);font-size:13px;">Zero Value Alerts</h4>
          <table class="alerts-table">
            <thead><tr><th>Message</th><th>Type</th></tr></thead>
            <tbody id="alerts-zeros-tbody"></tbody>
          </table>
        </div>

        <div style="margin-top:18px;">
          <h4 style="color:var(--muted);font-size:13px;">Unique Value Alerts</h4>
          <table class="alerts-table">
            <thead><tr><th>Message</th><th>Type</th></tr></thead>
            <tbody id="alerts-unique-tbody"></tbody>
          </table>
        </div>

        <div style="margin-top:18px;">
          <h4 style="color:var(--muted);font-size:13px;">Uniform Distribution Alerts</h4>
          <table class="alerts-table">
            <thead><tr><th>Message</th><th>Type</th></tr></thead>
            <tbody id="alerts-uniform-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <div id="tab-interaction" class="tab">
      <div class="card">
        <h3>Interaction Analysis</h3>
        <div class="note" style="margin-bottom:16px;">Select numeric variables to explore relationships. Scatter plots show pairwise relationships; the correlation heatmap shows correlations among multiple variables.</div>
        
        <div class="subtabs">
          <button class="subtabbtn active" data-inttab="scatter">Scatter Plot</button>
          <button class="subtabbtn" data-inttab="heatmap">Correlation Heatmap</button>
        </div>
        
        <div id="int-scatter" class="int-content">
          <div class="grid2" style="margin-bottom:12px;">
            <div>
              <label style="color:var(--muted);font-size:12px;">X-Axis Variable</label>
              <select id="scatter-x" class="search" style="margin-top:4px;"></select>
            </div>
            <div>
              <label style="color:var(--muted);font-size:12px;">Y-Axis Variable</label>
              <select id="scatter-y" class="search" style="margin-top:4px;"></select>
            </div>
          </div>
          <div id="scatter-result"></div>
        </div>
        
        <div id="int-heatmap" class="int-content" style="display:none;">
          <div style="margin-bottom:12px;">
            <label style="color:var(--muted);font-size:12px;">Select up to 5 variables</label>
            <div id="heatmap-vars" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;"></div>
            <select id="heatmap-add" class="search" style="margin-top:8px;max-width:200px;"></select>
          </div>
          <div id="heatmap-result"></div>
        </div>
      </div>
    </div>

    <div id="tab-repro" class="tab">
      <div class="card">
        <h3>Reproducibility</h3>
        <div class="kv">
          <div class="k">Platform</div><div class="v">\${repro.platform}</div>
          <div class="k">Library</div><div class="v">\${repro.library}</div>
        </div>
      </div>
    </div>
  </div>

<script>
const PAYLOAD = ${payloadJson};
const INTERACTION_DATA = ${interactionDataJson};
const AI_INFERENCES = ${aiInferencesJson};

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/[&<>"']/g, (m) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
}

function fmtNum(x) {
  if (x === null || x === undefined) return "—";
  if (typeof x !== "number") return escapeHtml(x);
  if (!isFinite(x)) return "—";
  const ax = Math.abs(x);
  if (ax !== 0 && (ax < 1e-4 || ax >= 1e6)) return x.toExponential(4);
  return x.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function pct(x) {
  if (x === null || x === undefined || !isFinite(x)) return "—";
  return x.toFixed(3) + "%";
}

// Tab navigation
document.querySelectorAll(".tabbtn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabbtn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

// Build alerts tables
function renderAlerts(tbody, data) {
  if (!data || !data.length) {
    tbody.innerHTML = '<tr><td colspan="2" style="color:var(--muted)">No alerts</td></tr>';
    return;
  }
  tbody.innerHTML = data.map(r => \`
    <tr>
      <td>\${escapeHtml(r.Message)}</td>
      <td><span class="corr-alert high">\${escapeHtml(r["Alert type"])}</span></td>
    </tr>
  \`).join("");
}

renderAlerts(document.getElementById("alerts-corr-tbody"), PAYLOAD.alerts.correlation);
renderAlerts(document.getElementById("alerts-zeros-tbody"), PAYLOAD.alerts.zeros);
renderAlerts(document.getElementById("alerts-unique-tbody"), PAYLOAD.alerts.unique);
renderAlerts(document.getElementById("alerts-uniform-tbody"), PAYLOAD.alerts.uniform);

// Sample data rendering
function renderSampleTable(rows) {
  if (!rows || rows.length === 0) return '<div class="note">No data available.</div>';
  const cols = Object.keys(rows[0]);
  return \`
    <table class="sample-table">
      <thead><tr>\${cols.map(c => \`<th>\${escapeHtml(c)}</th>\`).join("")}</tr></thead>
      <tbody>
        \${rows.map(row => \`<tr>\${cols.map(c => \`<td>\${escapeHtml(row[c])}</td>\`).join("")}</tr>\`).join("")}
      </tbody>
    </table>
  \`;
}

document.getElementById("sample-head").innerHTML = renderSampleTable(PAYLOAD.sample_data?.head || []);
document.getElementById("sample-tail").innerHTML = renderSampleTable(PAYLOAD.sample_data?.tail || []);

document.querySelectorAll(".sample-tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sample-tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const which = btn.dataset.sample;
    document.getElementById("sample-head").style.display = which === "head" ? "block" : "none";
    document.getElementById("sample-tail").style.display = which === "tail" ? "block" : "none";
  });
});

// Build Null Values Chart
function renderNullValuesChart() {
  const chartEl = document.getElementById("null-values-chart");
  if (!chartEl) return;
  
  const varData = Object.entries(PAYLOAD.variables)
    .map(function(entry) {
      const name = entry[0];
      const v = entry[1];
      return {
        name: name.length > 20 ? name.slice(0, 20) + "…" : name,
        fullName: name,
        nullCount: v.missing_count,
        nullPct: v.missing_pct
      };
    })
    .sort(function(a, b) { return b.nullCount - a.nullCount; })
    .slice(0, 20); // Limit to top 20 for readability
  
  if (varData.length === 0) {
    chartEl.innerHTML = '<div class="note">No variables to display.</div>';
    return;
  }
  
  const maxCount = Math.max.apply(null, varData.map(function(d) { return d.nullCount; }));
  const barHeight = 24;
  const labelWidth = 150;
  const chartWidth = 600;
  const h = varData.length * (barHeight + 4) + 20;
  
  function getBarColor(pct) {
    if (pct > 50) return "rgb(239,68,68)";
    if (pct > 20) return "rgb(245,158,11)";
    return "rgba(234,88,12,0.7)";
  }
  
  var bars = varData.map(function(d, i) {
    var y = i * (barHeight + 4) + 10;
    var barW = maxCount > 0 ? (d.nullCount / maxCount) * (chartWidth - labelWidth - 60) : 0;
    var color = getBarColor(d.nullPct);
    return '<g>' +
      '<text x="' + (labelWidth - 8) + '" y="' + (y + barHeight / 2 + 4) + '" fill="var(--text)" font-size="11" text-anchor="end">' + escapeHtml(d.name) + '</text>' +
      '<rect x="' + labelWidth + '" y="' + y + '" width="' + barW + '" height="' + barHeight + '" fill="' + color + '" rx="4"/>' +
      '<text x="' + (labelWidth + barW + 8) + '" y="' + (y + barHeight / 2 + 4) + '" fill="var(--muted)" font-size="10">' + d.nullCount.toLocaleString() + ' (' + d.nullPct.toFixed(1) + '%)</text>' +
      '</g>';
  }).join("");
  
  chartEl.innerHTML = '<svg viewBox="0 0 ' + chartWidth + ' ' + h + '" style="width:100%;height:' + h + 'px;">' + bars + '</svg>';
}

renderNullValuesChart();

// Build variable list
const varNames = Object.keys(PAYLOAD.variables).sort();
const varListEl = document.getElementById("var-list");
const varSearchEl = document.getElementById("var-search");
const varContentEl = document.getElementById("var-content");

function renderVarList(filter = "") {
  const f = filter.toLowerCase();
  const items = varNames.filter(n => n.toLowerCase().includes(f));
  varListEl.innerHTML = items.map(n => {
    const v = PAYLOAD.variables[n];
    return \`
      <div class="varitem" data-var="\${escapeHtml(n)}">
        <div style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">\${escapeHtml(n)}</div>
        <div class="badge">\${escapeHtml(v.vtype)}</div>
      </div>
    \`;
  }).join("");
  
  varListEl.querySelectorAll(".varitem").forEach(el => {
    el.addEventListener("click", () => {
      varListEl.querySelectorAll(".varitem").forEach(x => x.classList.remove("active"));
      el.classList.add("active");
      renderVariable(el.dataset.var);
    });
  });
  
  if (items.length > 0 && !varContentEl.innerHTML) {
    varListEl.querySelector(".varitem")?.click();
  }
}

varSearchEl.addEventListener("input", () => renderVarList(varSearchEl.value));
renderVarList();

// Build Variable Dictionary Table
function renderVariableDictionary() {
  const tbody = document.getElementById("var-dictionary-tbody");
  if (!tbody) return;
  
  const varNames = Object.keys(PAYLOAD.variables).sort();
  const hasInferences = Object.keys(AI_INFERENCES).length > 0;
  
  tbody.innerHTML = varNames.map(name => {
    const v = PAYLOAD.variables[name];
    const inf = AI_INFERENCES[name];
    
    let inferredTypeCell = '<span style="color:var(--muted)">—</span>';
    let inferredDefCell = '<span style="color:var(--muted)">—</span>';
    
    if (inf) {
      const confColors = {
        high: 'background:rgba(34,197,94,0.2);color:#4ade80;border:1px solid rgba(34,197,94,0.3)',
        medium: 'background:rgba(234,179,8,0.2);color:#facc15;border:1px solid rgba(234,179,8,0.3)',
        low: 'background:rgba(249,115,22,0.2);color:#fb923c;border:1px solid rgba(249,115,22,0.3)'
      };
      const confStyle = confColors[inf.confidence] || confColors.low;
      inferredTypeCell = \`<span>\${escapeHtml(inf.inferred_type)}</span> <span style="font-size:10px;padding:2px 6px;border-radius:999px;\${confStyle};margin-left:6px;">\${inf.confidence}</span>\`;
      inferredDefCell = \`<span title="\${escapeHtml(inf.inferred_definition)}">\${escapeHtml(inf.inferred_definition)}</span>\`;
    }
    
    return \`
      <tr>
        <td style="padding:8px;border-bottom:1px solid var(--line);font-weight:500;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="\${escapeHtml(name)}">\${escapeHtml(name)}</td>
        <td style="padding:8px;border-bottom:1px solid var(--line);"><span class="badge">\${escapeHtml(v.vtype)}</span></td>
        <td style="padding:8px;border-bottom:1px solid var(--line);">\${inferredTypeCell}</td>
        <td style="padding:8px;border-bottom:1px solid var(--line);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">\${inferredDefCell}</td>
      </tr>
    \`;
  }).join("");
  
  // Show/hide card based on whether we have inferences
  const card = document.getElementById("var-dictionary-card");
  if (!hasInferences && card) {
    const note = document.createElement("p");
    note.style.cssText = "color:var(--muted);font-size:12px;text-align:center;padding:20px;";
    note.textContent = "Run 'Infer with AI' in the app to generate semantic types and definitions.";
    const tableWrap = card.querySelector("div[style*='max-height']");
    if (tableWrap && varNames.length > 0) {
      // Still show the table with empty inferred columns
    }
  }
}

renderVariableDictionary();

// SVG Plot rendering functions
function renderHistogramSVG(hist) {
  if (!hist || !hist.counts || hist.counts.length === 0) return '<div class="note">No histogram data.</div>';
  const w = 400, h = 180, pad = 30;
  const maxCount = Math.max(...hist.counts);
  const barW = (w - pad * 2) / hist.counts.length;
  const bars = hist.counts.map((c, i) => {
    const barH = maxCount > 0 ? (c / maxCount) * (h - pad * 2) : 0;
    const x = pad + i * barW;
    const y = h - pad - barH;
    return \`<rect x="\${x}" y="\${y}" width="\${barW - 1}" height="\${barH}" fill="rgba(234,88,12,0.6)"/>\`;
  }).join("");
  return \`<svg viewBox="0 0 \${w} \${h}" class="plot-svg">\${bars}<line x1="\${pad}" y1="\${h-pad}" x2="\${w-pad}" y2="\${h-pad}" stroke="var(--muted)" stroke-width="1"/><line x1="\${pad}" y1="\${pad}" x2="\${pad}" y2="\${h-pad}" stroke="var(--muted)" stroke-width="1"/></svg>\`;
}

function renderCDFSVG(cdf) {
  if (!cdf || !cdf.x || cdf.x.length === 0) return '<div class="note">No CDF data.</div>';
  const w = 400, h = 180, pad = 30;
  const xMin = Math.min(...cdf.x), xMax = Math.max(...cdf.x);
  const xRange = xMax - xMin || 1;
  const pts = cdf.x.map((x, i) => {
    const px = pad + ((x - xMin) / xRange) * (w - pad * 2);
    const py = h - pad - cdf.y[i] * (h - pad * 2);
    return \`\${px},\${py}\`;
  }).join(" ");
  return \`<svg viewBox="0 0 \${w} \${h}" class="plot-svg"><polyline points="\${pts}" fill="none" stroke="rgba(234,88,12,0.8)" stroke-width="2"/><line x1="\${pad}" y1="\${h-pad}" x2="\${w-pad}" y2="\${h-pad}" stroke="var(--muted)" stroke-width="1"/><line x1="\${pad}" y1="\${pad}" x2="\${pad}" y2="\${h-pad}" stroke="var(--muted)" stroke-width="1"/></svg>\`;
}

function renderQQSVG(qq) {
  if (!qq || !qq.x || qq.x.length === 0) return '<div class="note">No QQ data.</div>';
  const w = 400, h = 180, pad = 30;
  const xMin = Math.min(...qq.x), xMax = Math.max(...qq.x);
  const yMin = Math.min(...qq.y), yMax = Math.max(...qq.y);
  const xRange = xMax - xMin || 1, yRange = yMax - yMin || 1;
  const dots = qq.x.map((x, i) => {
    const px = pad + ((x - xMin) / xRange) * (w - pad * 2);
    const py = h - pad - ((qq.y[i] - yMin) / yRange) * (h - pad * 2);
    return \`<circle cx="\${px}" cy="\${py}" r="2" fill="rgba(234,88,12,0.7)"/>\`;
  }).join("");
  let line = "";
  if (qq.line && qq.line.slope !== null) {
    const lx1 = xMin, lx2 = xMax;
    const ly1 = qq.line.slope * lx1 + qq.line.intercept;
    const ly2 = qq.line.slope * lx2 + qq.line.intercept;
    const px1 = pad, px2 = w - pad;
    const py1 = h - pad - ((ly1 - yMin) / yRange) * (h - pad * 2);
    const py2 = h - pad - ((ly2 - yMin) / yRange) * (h - pad * 2);
    line = \`<line x1="\${px1}" y1="\${py1}" x2="\${px2}" y2="\${py2}" stroke="rgba(255,100,100,0.7)" stroke-width="1.5"/>\`;
  }
  return \`<svg viewBox="0 0 \${w} \${h}" class="plot-svg">\${dots}\${line}<line x1="\${pad}" y1="\${h-pad}" x2="\${w-pad}" y2="\${h-pad}" stroke="var(--muted)" stroke-width="1"/><line x1="\${pad}" y1="\${pad}" x2="\${pad}" y2="\${h-pad}" stroke="var(--muted)" stroke-width="1"/></svg>\`
}

function renderValueCountTable(rows) {
  if (!rows || rows.length === 0) return '<div class="note">No data.</div>';
  const maxPct = Math.max(...rows.map(r => r.freq_pct || 0));
  return \`
    <table>
      <thead><tr><th style="width:45%;">Value</th><th style="width:15%;">Count</th><th>Frequency (%)</th></tr></thead>
      <tbody>
        \${rows.map(r => \`
          <tr>
            <td>\${escapeHtml(r.value)}</td>
            <td>\${escapeHtml(r.count)}</td>
            <td>
              <div class="barcell">
                <div class="barfill" style="width:\${maxPct ? (r.freq_pct / maxPct * 100) : 0}%"></div>
                <div class="bartext">\${fmtNum(r.freq_pct)}%</div>
              </div>
            </td>
          </tr>
        \`).join("")}
      </tbody>
    </table>
  \`;
}

function renderVariable(varName) {
  const v = PAYLOAD.variables[varName];
  if (!v) return;
  
  const header = \`
    <div class="card">
      <div class="section-title">\${escapeHtml(v.name)}</div>
      <div class="chips">
        <div class="chip">Type: \${escapeHtml(v.vtype)}</div>
        <div class="chip">Dtype: \${escapeHtml(v.dtype)}</div>
        <div class="chip">Missing: \${escapeHtml(v.missing_count)} (\${pct(v.missing_pct)})</div>
        <div class="chip">Unique: \${escapeHtml(v.unique)}</div>
      </div>
    </div>
  \`;
  
  let content = "";
  
  if (v.vtype === "numeric") {
    const d = v.details;
    const q = d.tab1?.quantiles || {};
    const desc = d.tab1?.descriptive || {};
    
    content = \`
      <div class="grid3">
        <div class="card">
          <h3>Quality & Type</h3>
          <div class="kv">
            <div class="k">Missing</div><div class="v">\${escapeHtml(v.missing_count)} (\${pct(v.missing_pct)})</div>
            <div class="k">Zeros</div><div class="v">\${escapeHtml(d.zeros)}</div>
            <div class="k">Infinite</div><div class="v">\${escapeHtml(d.infs)}</div>
          </div>
        </div>
        <div class="card">
          <h3>Distribution & Size</h3>
          <div class="kv">
            <div class="k">Non-null</div><div class="v">\${escapeHtml(d.n_nonnull)}</div>
            <div class="k">Null</div><div class="v">\${escapeHtml(d.n_null)}</div>
            <div class="k">Total</div><div class="v">\${escapeHtml(d.n_total)}</div>
          </div>
        </div>
        <div class="card">
          <h3>At a glance</h3>
          <div class="kv">
            <div class="k">Min</div><div class="v">\${fmtNum(q.min)}</div>
            <div class="k">Median</div><div class="v">\${fmtNum(q.median)}</div>
            <div class="k">Max</div><div class="v">\${fmtNum(q.max)}</div>
          </div>
        </div>
      </div>
      
      <div class="card" style="margin-top:12px;">
        <h3>Statistics</h3>
        <div class="grid2">
          <div>
            <h4 style="color:var(--muted);font-size:12px;margin-bottom:8px;">Quantile Statistics</h4>
            <div class="kv">
              <div class="k">Minimum</div><div class="v">\${fmtNum(q.min)}</div>
              <div class="k">5-th percentile</div><div class="v">\${fmtNum(q.p05)}</div>
              <div class="k">Q1</div><div class="v">\${fmtNum(q.q1)}</div>
              <div class="k">Median</div><div class="v">\${fmtNum(q.median)}</div>
              <div class="k">Q3</div><div class="v">\${fmtNum(q.q3)}</div>
              <div class="k">95-th percentile</div><div class="v">\${fmtNum(q.p95)}</div>
              <div class="k">Maximum</div><div class="v">\${fmtNum(q.max)}</div>
              <div class="k">Range</div><div class="v">\${fmtNum(q.range)}</div>
              <div class="k">IQR</div><div class="v">\${fmtNum(q.iqr)}</div>
            </div>
          </div>
          <div>
            <h4 style="color:var(--muted);font-size:12px;margin-bottom:8px;">Descriptive Statistics</h4>
            <div class="kv">
              <div class="k">Standard deviation</div><div class="v">\${fmtNum(desc.std)}</div>
              <div class="k">CV</div><div class="v">\${fmtNum(desc.cv)}</div>
              <div class="k">Kurtosis</div><div class="v">\${fmtNum(desc.kurtosis)}</div>
              <div class="k">Mean</div><div class="v">\${fmtNum(desc.mean)}</div>
              <div class="k">MAD</div><div class="v">\${fmtNum(desc.mad)}</div>
              <div class="k">Skewness</div><div class="v">\${fmtNum(desc.skewness)}</div>
              <div class="k">Sum</div><div class="v">\${fmtNum(desc.sum)}</div>
              <div class="k">Variance</div><div class="v">\${fmtNum(desc.variance)}</div>
              <div class="k">Monotonicity</div><div class="v">\${desc.monotonicity === null ? "—" : fmtNum(desc.monotonicity)}</div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="card" style="margin-top:12px;">
        <h3>Distribution Plots</h3>
        <div class="grid3">
          <div class="plotbox">
            <h4 style="color:var(--muted);font-size:11px;margin:0 0 6px;">Histogram</h4>
            \${renderHistogramSVG(d.plots?.hist)}
          </div>
          <div class="plotbox">
            <h4 style="color:var(--muted);font-size:11px;margin:0 0 6px;">CDF</h4>
            \${renderCDFSVG(d.plots?.cdf)}
          </div>
          <div class="plotbox">
            <h4 style="color:var(--muted);font-size:11px;margin:0 0 6px;">Q-Q Plot</h4>
            \${renderQQSVG(d.plots?.qq)}
          </div>
        </div>
      </div>
      
      <div class="card" style="margin-top:12px;">
        <h3>Common Values (Top 10)</h3>
        \${renderValueCountTable(d.common_values || [])}
      </div>
      
      <div class="card" style="margin-top:12px;">
        <h3>Extreme Values</h3>
        <div class="grid2">
          <div>
            <h4 style="color:var(--muted);font-size:12px;margin-bottom:8px;">Minimum 10 values</h4>
            \${renderValueCountTable(d.extremes?.min10 || [])}
          </div>
          <div>
            <h4 style="color:var(--muted);font-size:12px;margin-bottom:8px;">Maximum 10 values</h4>
            \${renderValueCountTable(d.extremes?.max10 || [])}
          </div>
        </div>
      </div>
    \`;
  } else if (v.vtype === "categorical" || v.vtype === "boolean") {
    const d = v.details;
    content = \`
      <div class="grid2">
        <div class="card">
          <h3>Quality & Type</h3>
          <div class="kv">
            <div class="k">Missing</div><div class="v">\${escapeHtml(v.missing_count)} (\${pct(v.missing_pct)})</div>
            <div class="k">Unique</div><div class="v">\${escapeHtml(v.unique)}</div>
          </div>
        </div>
        <div class="card">
          <h3>Top values</h3>
          \${renderValueCountTable(d.top_values || [])}
        </div>
      </div>
    \`;
  } else if (v.vtype === "datetime") {
    const d = v.details;
    content = \`
      <div class="grid2">
        <div class="card">
          <h3>Quality & Type</h3>
          <div class="kv">
            <div class="k">Missing</div><div class="v">\${escapeHtml(v.missing_count)} (\${pct(v.missing_pct)})</div>
            <div class="k">Min</div><div class="v">\${escapeHtml(d.min)}</div>
            <div class="k">Max</div><div class="v">\${escapeHtml(d.max)}</div>
          </div>
        </div>
      </div>
    \`;
  } else {
    content = \`
      <div class="card">
        <h3>Unsupported type</h3>
        <div class="note">\${escapeHtml(v.details?.note || "No details available.")}</div>
      </div>
    \`;
  }
  
  varContentEl.innerHTML = header + content;
}

// ========== INTERACTION TAB LOGIC ==========

// Get numeric variable names
const numericVars = Object.entries(PAYLOAD.variables)
  .filter(([name, v]) => v.vtype === "numeric" && name.trim() !== "")
  .map(([name]) => name)
  .sort();

// Interaction sub-tab navigation
document.querySelectorAll(".subtabbtn[data-inttab]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".subtabbtn[data-inttab]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const which = btn.dataset.inttab;
    document.getElementById("int-scatter").style.display = which === "scatter" ? "block" : "none";
    document.getElementById("int-heatmap").style.display = which === "heatmap" ? "block" : "none";
  });
});

// Pearson correlation calculation
function pearsonCorr(x, y) {
  if (x.length !== y.length || x.length < 2) return null;
  const n = x.length;
  const sumX = x.reduce((a, b) => a + b, 0);
  const sumY = y.reduce((a, b) => a + b, 0);
  const sumXY = x.reduce((a, v, i) => a + v * y[i], 0);
  const sumX2 = x.reduce((a, v) => a + v * v, 0);
  const sumY2 = y.reduce((a, v) => a + v * v, 0);
  const num = n * sumXY - sumX * sumY;
  const den = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
  return den === 0 ? null : num / den;
}

// Get paired numeric values from sample data
function getPairedVals(data, col1, col2) {
  return data
    .map(row => {
      const v1 = row[col1], v2 = row[col2];
      if (v1 == null || v1 === "" || v2 == null || v2 === "") return null;
      const n1 = Number(v1), n2 = Number(v2);
      if (!isFinite(n1) || !isFinite(n2)) return null;
      return { x: n1, y: n2 };
    })
    .filter(v => v !== null);
}

// Render scatter plot SVG
function renderScatterSVG(data, xLabel, yLabel, corr) {
  if (!data || data.length === 0) return '<div class="note">No valid data points for selected variables.</div>';
  const w = 500, h = 350, pad = 50;
  const xs = data.map(d => d.x), ys = data.map(d => d.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xRange = xMax - xMin || 1, yRange = yMax - yMin || 1;
  
  let plotData = data;
  if (data.length > 500) {
    const step = Math.ceil(data.length / 500);
    plotData = data.filter((_, i) => i % step === 0);
  }
  
  const dots = plotData.map(d => {
    const px = pad + ((d.x - xMin) / xRange) * (w - pad * 2);
    const py = h - pad - ((d.y - yMin) / yRange) * (h - pad * 2);
    return '<circle cx="' + px + '" cy="' + py + '" r="3" fill="rgba(234,88,12,0.6)"/>';
  }).join("");
  
  const corrText = corr !== null ? 'r = ' + corr.toFixed(4) : "";
  
  return '<div class="plotbox">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">' +
    '<span style="color:var(--muted);font-size:12px;">' + escapeHtml(xLabel) + ' vs ' + escapeHtml(yLabel) + '</span>' +
    '<span class="badge">' + corrText + '</span>' +
    '</div>' +
    '<svg viewBox="0 0 ' + w + ' ' + h + '" style="width:100%;height:300px;">' +
    dots +
    '<line x1="' + pad + '" y1="' + (h-pad) + '" x2="' + (w-pad) + '" y2="' + (h-pad) + '" stroke="var(--muted)" stroke-width="1"/>' +
    '<line x1="' + pad + '" y1="' + pad + '" x2="' + pad + '" y2="' + (h-pad) + '" stroke="var(--muted)" stroke-width="1"/>' +
    '<text x="' + (w/2) + '" y="' + (h-10) + '" fill="var(--muted)" font-size="11" text-anchor="middle">' + escapeHtml(xLabel) + '</text>' +
    '<text x="15" y="' + (h/2) + '" fill="var(--muted)" font-size="11" text-anchor="middle" transform="rotate(-90, 15, ' + (h/2) + ')">' + escapeHtml(yLabel) + '</text>' +
    '</svg>' +
    '<div class="note">' + plotData.length.toLocaleString() + ' points displayed</div>' +
    '</div>';
}

// Populate scatter dropdowns
const scatterXSel = document.getElementById("scatter-x");
const scatterYSel = document.getElementById("scatter-y");
const scatterResult = document.getElementById("scatter-result");

scatterXSel.innerHTML = '<option value="">Select variable</option>' + numericVars.map(n => '<option value="' + escapeHtml(n) + '">' + escapeHtml(n) + '</option>').join("");
scatterYSel.innerHTML = '<option value="">Select variable</option>' + numericVars.map(n => '<option value="' + escapeHtml(n) + '">' + escapeHtml(n) + '</option>').join("");

function updateScatter() {
  const xVar = scatterXSel.value, yVar = scatterYSel.value;
  if (!xVar || !yVar || xVar === yVar) {
    scatterResult.innerHTML = '<div class="note">Select two different variables to generate scatter plot.</div>';
    return;
  }
  const dataSource = INTERACTION_DATA || [...(PAYLOAD.sample_data?.head || []), ...(PAYLOAD.sample_data?.tail || [])];
  const paired = getPairedVals(dataSource, xVar, yVar);
  const corr = paired.length >= 2 ? pearsonCorr(paired.map(p => p.x), paired.map(p => p.y)) : null;
  scatterResult.innerHTML = renderScatterSVG(paired, xVar, yVar, corr);
}

scatterXSel.addEventListener("change", updateScatter);
scatterYSel.addEventListener("change", updateScatter);

// ========== HEATMAP LOGIC ==========
let heatmapSelected = [];

function getCorrelationColor(value) {
  if (value === null) return "var(--chip)";
  const clamped = Math.max(-1, Math.min(1, value));
  if (clamped >= 0) {
    const intensity = Math.round(clamped * 255);
    return 'rgb(255, ' + (255 - intensity) + ', ' + (255 - intensity) + ')';
  } else {
    const intensity = Math.round(-clamped * 255);
    return 'rgb(' + (255 - intensity) + ', ' + (255 - intensity) + ', 255)';
  }
}

function renderHeatmapSVG(vars, matrix) {
  if (vars.length < 2 || !matrix) return '<div class="note">Select at least 2 variables to generate correlation heatmap.</div>';
  
  const cellSize = 60, pad = 100;
  const n = vars.length;
  const w = pad + n * cellSize + 20, h = pad + n * cellSize + 40;
  
  let cells = "";
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const val = matrix[i][j];
      const x = pad + j * cellSize, y = pad + i * cellSize;
      const color = getCorrelationColor(val);
      const textColor = val !== null && Math.abs(val) > 0.5 ? "white" : "var(--text)";
      cells += '<rect x="' + x + '" y="' + y + '" width="' + (cellSize-2) + '" height="' + (cellSize-2) + '" fill="' + color + '" rx="4"/>';
      cells += '<text x="' + (x + cellSize/2 - 1) + '" y="' + (y + cellSize/2 + 4) + '" fill="' + textColor + '" font-size="11" text-anchor="middle">' + (val !== null ? val.toFixed(2) : "N/A") + '</text>';
    }
  }
  
  let rowLabels = vars.map((v, i) => {
    const y = pad + i * cellSize + cellSize / 2 + 4;
    const label = v.length > 10 ? v.slice(0, 10) + "…" : v;
    return '<text x="' + (pad - 6) + '" y="' + y + '" fill="var(--muted)" font-size="10" text-anchor="end">' + escapeHtml(label) + '</text>';
  }).join("");
  
  let colLabels = vars.map((v, j) => {
    const x = pad + j * cellSize + cellSize / 2;
    const label = v.length > 10 ? v.slice(0, 10) + "…" : v;
    return '<text x="' + x + '" y="' + (pad - 8) + '" fill="var(--muted)" font-size="10" text-anchor="middle">' + escapeHtml(label) + '</text>';
  }).join("");
  
  const legendY = pad + n * cellSize + 15;
  const legend = '<text x="' + pad + '" y="' + legendY + '" fill="var(--muted)" font-size="10">-1</text>' +
    '<rect x="' + (pad + 15) + '" y="' + (legendY - 10) + '" width="100" height="12" rx="2" fill="url(#corrGradient)"/>' +
    '<text x="' + (pad + 120) + '" y="' + legendY + '" fill="var(--muted)" font-size="10">+1</text>' +
    '<defs><linearGradient id="corrGradient" x1="0%" y1="0%" x2="100%" y2="0%">' +
    '<stop offset="0%" style="stop-color:rgb(0,0,255);stop-opacity:1" />' +
    '<stop offset="50%" style="stop-color:rgb(255,255,255);stop-opacity:1" />' +
    '<stop offset="100%" style="stop-color:rgb(255,0,0);stop-opacity:1" />' +
    '</linearGradient></defs>';
  
  return '<div class="plotbox">' +
    '<svg viewBox="0 0 ' + w + ' ' + h + '" style="width:100%;max-width:' + w + 'px;height:auto;">' +
    cells + rowLabels + colLabels + legend +
    '</svg></div>';
}

function updateHeatmap() {
  const heatmapVarsEl = document.getElementById("heatmap-vars");
  const heatmapResult = document.getElementById("heatmap-result");
  const heatmapAdd = document.getElementById("heatmap-add");
  
  heatmapVarsEl.innerHTML = heatmapSelected.map(v => 
    '<span class="chip" style="display:inline-flex;align-items:center;gap:4px;">' +
    escapeHtml(v) +
    '<button onclick="removeHeatmapVar(\\'' + escapeHtml(v) + '\\')" style="background:none;border:none;color:var(--muted);cursor:pointer;padding:0;">✕</button>' +
    '</span>'
  ).join("");
  
  const remaining = numericVars.filter(n => !heatmapSelected.includes(n));
  heatmapAdd.innerHTML = '<option value="">Add variable</option>' + remaining.map(n => '<option value="' + escapeHtml(n) + '">' + escapeHtml(n) + '</option>').join("");
  heatmapAdd.disabled = heatmapSelected.length >= 5;
  
  if (heatmapSelected.length < 2) {
    heatmapResult.innerHTML = '<div class="note">Select at least 2 variables to generate correlation heatmap.</div>';
    return;
  }
  
  const dataSource = INTERACTION_DATA || [...(PAYLOAD.sample_data?.head || []), ...(PAYLOAD.sample_data?.tail || [])];
  const matrix = [];
  for (let i = 0; i < heatmapSelected.length; i++) {
    matrix[i] = [];
    for (let j = 0; j < heatmapSelected.length; j++) {
      if (i === j) {
        matrix[i][j] = 1;
      } else {
        const paired = getPairedVals(dataSource, heatmapSelected[i], heatmapSelected[j]);
        matrix[i][j] = paired.length >= 2 ? pearsonCorr(paired.map(p => p.x), paired.map(p => p.y)) : null;
      }
    }
  }
  
  heatmapResult.innerHTML = renderHeatmapSVG(heatmapSelected, matrix);
}

window.removeHeatmapVar = function(v) {
  heatmapSelected = heatmapSelected.filter(x => x !== v);
  updateHeatmap();
};

document.getElementById("heatmap-add").addEventListener("change", function() {
  if (this.value && heatmapSelected.length < 5 && !heatmapSelected.includes(this.value)) {
    heatmapSelected.push(this.value);
    updateHeatmap();
  }
  this.value = "";
});

updateHeatmap();
</script>
</body>
</html>`;
}
