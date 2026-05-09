import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const systemPrompt = `You are an expert data analyst and statistician. Your task is to write a comprehensive, professional bivariate analysis report based on the provided statistics for two selected variables.

Structure your report with these sections:

## Executive Summary
A brief 2-3 sentence overview of the relationship between the two variables and the key finding.

## Variables Overview
Describe the two variables being analyzed:
- Variable names and types (numeric/categorical)
- Sample size and unique value counts

## Relationship Analysis
Based on the variable types, analyze their relationship:

For Numeric-Numeric pairs:
- Discuss correlation coefficients (Pearson, Spearman, Kendall) and their interpretations
- Comment on the strength and direction of the linear relationship
- Note any differences between full data and sample correlations
- Describe what the confidence ellipse coverage suggests about data distribution

For Categorical-Categorical pairs:
- Interpret Chi-square test results and statistical significance
- Explain Cramér's V and what it indicates about association strength
- Discuss the contingency coefficient
- Analyze the joint frequency distribution patterns

For Mixed (Numeric-Categorical) pairs:
- Summarize conditional statistics (mean, std, median by category)
- Compare distributions across categories using box plot insights
- Identify categories with notably different distributions

## Distribution Insights
Describe patterns observed in the joint or conditional distributions:
- Most frequent combinations or categories
- Outliers or unusual patterns
- Marginal frequency distributions

## Key Findings
Bullet points of the most important discoveries from this analysis.

## Recommendations
Suggest follow-up analyses or considerations based on findings.

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

    const { varX, varY, statistics } = payload;
    
    // Build context from statistics
    let dataContext = `
Bivariate Analysis Report
========================

Variables:
- X: ${varX} (${statistics.xIsNumeric ? 'Numeric' : 'Categorical'})
- Y: ${varY} (${statistics.yIsNumeric ? 'Numeric' : 'Categorical'})

Sample Size: ${statistics.n}
Unique X values: ${statistics.uniqueX}
Unique Y values: ${statistics.uniqueY}
`;

    // Add correlation data if both numeric
    if (statistics.correlations) {
      dataContext += `
Correlations (Full Data):
- Pearson: ${statistics.correlations.pearson?.toFixed(6) ?? 'N/A'}
- Spearman: ${statistics.correlations.spearman?.toFixed(6) ?? 'N/A'}
- Kendall's tau: ${statistics.correlations.kendall?.toFixed(6) ?? 'N/A'}
- Covariance: ${statistics.correlations.covariance?.toFixed(6) ?? 'N/A'}
`;
    }

    if (statistics.sampleCorrelations) {
      dataContext += `
Correlations (Sample):
- Pearson: ${statistics.sampleCorrelations.pearson?.toFixed(6) ?? 'N/A'}
- Spearman: ${statistics.sampleCorrelations.spearman?.toFixed(6) ?? 'N/A'}
- Kendall's tau: ${statistics.sampleCorrelations.kendall?.toFixed(6) ?? 'N/A'}
`;
    }

    // Chi-square and association measures
    if (statistics.chiSquare) {
      dataContext += `
Association Measures:
- Chi-square (χ²): ${statistics.chiSquare.chiSquare.toFixed(6)}
- Cramér's V: ${statistics.chiSquare.cramersV.toFixed(6)}
- Contingency Coefficient: ${statistics.chiSquare.contingencyCoefficient.toFixed(6)}
${statistics.chiSquare.phiCoefficient !== null ? `- Phi (φ): ${statistics.chiSquare.phiCoefficient.toFixed(6)}` : ''}
- Degrees of Freedom: ${statistics.chiSquare.degreesOfFreedom}
`;
    }

    // Conditional stats if available
    if (statistics.conditionalStats && statistics.conditionalStats.length > 0) {
      dataContext += `
Conditional Statistics (X grouped by Y):
`;
      const statsToShow = statistics.conditionalStats.slice(0, 20);
      statsToShow.forEach((stat: any) => {
        dataContext += `- ${stat.y}: n=${stat.count}, mean=${stat.mean.toFixed(4)}, std=${stat.std.toFixed(4)}, median=${stat.median.toFixed(2)}\n`;
      });
      if (statistics.conditionalStats.length > 20) {
        dataContext += `... and ${statistics.conditionalStats.length - 20} more categories\n`;
      }
    }

    // Crosstab summary (pre-computed on client to avoid stack overflow)
    if (statistics.crosstabSummary) {
      const summary = statistics.crosstabSummary;
      dataContext += `
Crosstab Summary:
- X categories: ${summary.xCategoryCount} (first 10: ${summary.topXCategories.join(', ')})
- Y categories: ${summary.yCategoryCount} (first 10: ${summary.topYCategories.join(', ')})
- Top X marginal: "${summary.topXCategory}" with count ${summary.topXCount}
- Top Y marginal: "${summary.topYCategory}" with count ${summary.topYCount}
- Total observations: ${summary.total}
`;
    }

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
          { role: "user", content: `Please analyze the relationship between these two variables and write a comprehensive bivariate analysis report:\n\n${dataContext}` },
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
    console.error("Generate bivariate report error:", error);
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : "Unknown error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
