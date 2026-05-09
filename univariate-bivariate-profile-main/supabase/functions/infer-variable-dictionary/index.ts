import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const systemPrompt = `You are a data analyst expert. Given variable metadata from a dataset, infer the semantic type and business definition for each variable, and provide a one-sentence summary of what the dataset is about.

For each variable, determine:
1. **inferred_type**: The semantic meaning, which may differ from the technical type. Common semantic types include:
   - "Identifier" - IDs, keys, codes that uniquely identify records (even if stored as numeric)
   - "Binary Flag (Yes/No)" - Variables with only 0/1 or two values representing yes/no, true/false
   - "Ordinal Category" - Numeric values representing ordered categories (e.g., rating 1-5)
   - "Nominal Category" - Categorical values with no inherent order
   - "Continuous Numeric" - True continuous measurements
   - "Count" - Integer counts of occurrences
   - "Monetary" - Currency/money values
   - "Percentage" - Values representing percentages (0-100 or 0-1)
   - "Ratio" - Ratios between quantities
   - "Date" - Date values
   - "Timestamp" - Date with time
   - "Text/Free-form" - Unstructured text

2. **inferred_definition**: A concise business definition (1-2 sentences) explaining what this variable likely represents in a business context.

3. **confidence**: "high", "medium", or "low" based on how certain you are about the inference.

4. **dataset_summary**: A single sentence describing the overall theme/topic of the dataset based on the variables present (e.g., "This dataset contains daily stock trading data for a financial instrument.").

Key patterns to recognize:
- Numeric columns with very few unique values (2-10) are often categorical
- Columns named with "id", "code", "key", "num" suffixes are often identifiers
- Columns with only 0 and 1 values are binary flags
- Columns with small integer ranges (1-5, 1-10) are often ordinal ratings`;

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { variables, model } = await req.json();
    
    if (!variables || !Array.isArray(variables)) {
      return new Response(
        JSON.stringify({ error: "Missing variables array" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    if (!LOVABLE_API_KEY) {
      throw new Error("LOVABLE_API_KEY is not configured");
    }
    
    const selectedModel = model || "openai/gpt-5-mini";

    // Build context for AI
    const variableContext = variables.map((v: {
      name: string;
      vtype: string;
      unique: number;
      missing_pct: number;
      sample_values: (string | number)[];
      min?: number;
      max?: number;
      zeros?: number;
    }) => {
      let info = `Variable: "${v.name}"
  - Technical Type: ${v.vtype}
  - Unique Values: ${v.unique}
  - Missing: ${v.missing_pct.toFixed(2)}%
  - Sample Values: ${v.sample_values.slice(0, 10).join(", ")}`;
      
      if (v.min !== undefined && v.max !== undefined) {
        info += `\n  - Range: ${v.min} to ${v.max}`;
      }
      if (v.zeros !== undefined) {
        info += `\n  - Zero Count: ${v.zeros}`;
      }
      return info;
    }).join("\n\n");

    const userPrompt = `Analyze these variables and provide semantic type inference, business definitions, and a one-sentence dataset summary:

${variableContext}

Return your analysis with variable inferences AND a dataset_summary field.`;

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
          { role: "user", content: userPrompt },
        ],
        tools: [
          {
            type: "function",
            function: {
              name: "provide_variable_inferences",
              description: "Provide semantic type inference, business definitions for variables, and a dataset summary",
              parameters: {
                type: "object",
                properties: {
                  inferences: {
                    type: "array",
                    items: {
                      type: "object",
                      properties: {
                        name: { type: "string", description: "Variable name" },
                        inferred_type: { type: "string", description: "Semantic type of the variable" },
                        inferred_definition: { type: "string", description: "Business definition of the variable" },
                        confidence: { type: "string", enum: ["high", "medium", "low"] },
                      },
                      required: ["name", "inferred_type", "inferred_definition", "confidence"],
                      additionalProperties: false,
                    },
                  },
                  dataset_summary: {
                    type: "string",
                    description: "A one-sentence summary describing the overall theme/topic of the dataset",
                  },
                },
                required: ["inferences", "dataset_summary"],
                additionalProperties: false,
              },
            },
          },
        ],
        tool_choice: { type: "function", function: { name: "provide_variable_inferences" } },
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(
          JSON.stringify({ error: "Rate limit exceeded. Please try again later." }),
          { status: 429, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }
      if (response.status === 402) {
        return new Response(
          JSON.stringify({ error: "AI credits exhausted. Please add credits to continue." }),
          { status: 402, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }
      const errorText = await response.text();
      console.error("AI gateway error:", response.status, errorText);
      throw new Error(`AI gateway error: ${response.status}`);
    }

    const result = await response.json();
    
    // Extract the tool call result - try multiple formats for compatibility
    let parsed: { inferences: Array<{ name: string; inferred_type: string; inferred_definition: string; confidence: string }>; dataset_summary?: string };
    
    const toolCall = result.choices?.[0]?.message?.tool_calls?.[0];
    if (toolCall?.function?.arguments) {
      // OpenAI-style tool call response
      parsed = JSON.parse(toolCall.function.arguments);
    } else {
      // Fallback: try to extract JSON from text content (for models that don't support tool calls well)
      const textContent = result.choices?.[0]?.message?.content;
      if (textContent) {
        // Try to parse JSON from the response
        const jsonMatch = textContent.match(/\[[\s\S]*\]/);
        if (jsonMatch) {
          const inferences = JSON.parse(jsonMatch[0]);
          parsed = { inferences };
        } else {
          // Try parsing as a JSON object with inferences key
          const objectMatch = textContent.match(/\{[\s\S]*"inferences"[\s\S]*\}/);
          if (objectMatch) {
            parsed = JSON.parse(objectMatch[0]);
          } else {
            console.error("Could not parse AI response:", textContent);
            throw new Error("Could not parse AI response as JSON");
          }
        }
      } else {
        console.error("No valid response format found:", JSON.stringify(result));
        throw new Error("No tool call or text response received");
      }
    }
    
    return new Response(
      JSON.stringify({ inferences: parsed.inferences, dataset_summary: parsed.dataset_summary || null }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );

  } catch (error) {
    console.error("Error in infer-variable-dictionary:", error);
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : "Unknown error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
