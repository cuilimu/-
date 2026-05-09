import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const systemPrompt = `You are an expert data analyst and credit risk consultant. Your task is to write a comprehensive, professional written analysis report based on the provided dataset statistics.

Structure your report with these sections:

## Executive Summary
A brief 2-3 sentence overview of the dataset and key findings.

## Dataset Overview
Describe the dataset dimensions, data types distribution, and overall data quality (missing values, duplicates).

## Key Variable Insights
Analyze the most important variables based on:
- Numeric variables: distribution shape, central tendency, outliers, zero values
- Categorical variables: cardinality, most frequent values, missing patterns
- Highlight any variables that may need special attention

## Data Quality Assessment
- Missing data patterns and implications
- Duplicate records analysis
- Variables with high unique ratios (potential ID columns)
- Variables with uniform distributions (low information content)

## Correlation Analysis
Discuss any high correlations between variables and their implications for modeling.

## Recommendations
Provide actionable recommendations for:
- Data cleaning steps
- Variable transformations
- Variables to consider dropping or investigating further
- Next steps for analysis

Keep the tone professional and suitable for a consulting report. Use specific numbers and percentages from the data. Be concise but thorough.`;

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { payload, model } = await req.json();
    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    const selectedModel = model || "openai/gpt-5-mini";
    
    if (!LOVABLE_API_KEY) {
      throw new Error("LOVABLE_API_KEY is not configured");
    }

    // Build a concise summary of the payload for the AI
    const { meta, variables, alerts } = payload;
    
    // Summarize variables (limit detail to avoid token overflow)
    const variableSummaries = Object.entries(variables).slice(0, 50).map(([name, v]: [string, any]) => {
      const summary: any = {
        name,
        type: v.vtype,
        missing_pct: v.missing_pct,
        unique_count: v.unique,
      };
      
      if (v.vtype === 'numeric' && v.details) {
        const details = v.details;
        if (details.tab1) {
          summary.mean = details.tab1.descriptive?.mean;
          summary.std = details.tab1.descriptive?.std;
          summary.min = details.tab1.quantiles?.min;
          summary.max = details.tab1.quantiles?.max;
          summary.skewness = details.tab1.descriptive?.skewness;
        }
        summary.zeros = details.zeros;
        summary.zeros_pct = details.n_nonnull > 0 ? ((details.zeros || 0) / details.n_nonnull * 100) : 0;
      } else if (v.vtype === 'categorical' && v.details?.top_values?.length > 0) {
        summary.top_value = v.details.top_values[0].value;
        summary.top_freq = v.details.top_values[0].freq_pct;
      }
      
      return summary;
    });

    const dataContext = `
Dataset: ${meta.source_file}
Rows: ${meta.rows}
Columns: ${meta.cols}
Missing Cells: ${meta.missing_cells} (${(meta.missing_pct * 100).toFixed(2)}%)
Duplicate Rows: ${meta.duplicate_rows} (${(meta.duplicate_pct * 100).toFixed(2)}%)

Variable Types:
- Numeric: ${meta.type_counts.numeric}
- Categorical: ${meta.type_counts.categorical}
- Datetime: ${meta.type_counts.datetime}
- Boolean: ${meta.type_counts.boolean}

Alerts:
- High Correlations: ${alerts.correlation.length}
- High Zero Values: ${alerts.zeros.length}
- High Unique Ratios: ${alerts.unique.length}
- Uniform Distributions: ${alerts.uniform.length}

${alerts.correlation.length > 0 ? `Correlation Alerts:\n${alerts.correlation.map((a: any) => `- ${a.Message}`).join('\n')}` : ''}

${alerts.zeros.length > 0 ? `Zero Value Alerts:\n${alerts.zeros.map((a: any) => `- ${a.Message}`).join('\n')}` : ''}

${alerts.unique.length > 0 ? `Unique Value Alerts:\n${alerts.unique.map((a: any) => `- ${a.Message}`).join('\n')}` : ''}

Variable Summaries:
${JSON.stringify(variableSummaries, null, 2)}
`;

    const response = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${LOVABLE_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: selectedModel,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: `Please analyze this dataset and write a comprehensive report:\n\n${dataContext}` },
        ],
        stream: true,
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(
          JSON.stringify({ error: "Rate limit exceeded. Please try again in a moment." }),
          { status: 429, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }
      if (response.status === 402) {
        return new Response(
          JSON.stringify({ error: "AI usage limit reached. Please add credits to continue." }),
          { status: 402, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }
      const errorText = await response.text();
      console.error("AI gateway error:", response.status, errorText);
      return new Response(
        JSON.stringify({ error: "Failed to generate report" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    return new Response(response.body, {
      headers: { ...corsHeaders, "Content-Type": "text/event-stream" },
    });
  } catch (error) {
    console.error("Generate report error:", error);
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : "Unknown error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
