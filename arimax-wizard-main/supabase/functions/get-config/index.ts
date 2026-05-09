import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

/** Convert a JS value to Python-friendly string: true→True, false→False, null→None */
function toPythonRepr(obj: unknown, indent = 0): string {
  const pad = " ".repeat(indent);
  const pad1 = " ".repeat(indent + 4);

  if (obj === null || obj === undefined) return "None";
  if (obj === true) return "True";
  if (obj === false) return "False";
  if (typeof obj === "number") return String(obj);
  if (typeof obj === "string") return JSON.stringify(obj);

  if (Array.isArray(obj)) {
    if (obj.length === 0) return "[]";
    const items = obj.map((v) => `${pad1}${toPythonRepr(v, indent + 4)}`);
    return `[\n${items.join(",\n")}\n${pad}]`;
  }

  if (typeof obj === "object") {
    const entries = Object.entries(obj as Record<string, unknown>);
    if (entries.length === 0) return "{}";
    const items = entries.map(
      ([k, v]) => `${pad1}${JSON.stringify(k)}: ${toPythonRepr(v, indent + 4)}`
    );
    return `{\n${items.join(",\n")}\n${pad}}`;
  }

  return String(obj);
}

/** Build Python-formatted run_config with pd.read_csv() for the raw field */
function buildPythonRunConfig(runConfig: Record<string, unknown>): string {
  const dsCol = (runConfig.ds_column as string) || "DATE";
  const filePath = (runConfig.raw as string) || "YOUR_FILE.csv";

  const entries = Object.entries(runConfig).map(([k, v]) => {
    if (k === "raw") {
      return `    "raw": pd.read_csv(\n        "${filePath}",\n        index_col="${dsCol}",\n        parse_dates=["${dsCol}"]\n    )`;
    }
    return `    ${JSON.stringify(k)}: ${toPythonRepr(v, 4)}`;
  });

  return `{\n${entries.join(",\n")}\n}`;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  const url = new URL(req.url);
  const segments = url.pathname.split("/").filter(Boolean);
  const configId = segments[segments.length - 1];

  if (!configId || configId === "get-config") {
    return new Response(
      JSON.stringify({ error: "Missing config_id. Use /get-config/<config_id>" }),
      { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
  );

  const { data, error } = await supabase
    .from("arimax_configs")
    .select("payload")
    .eq("id", configId)
    .single();

  if (error || !data) {
    return new Response(
      JSON.stringify({ error: "Config not found" }),
      { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  const format = url.searchParams.get("format");

  // Python format: returns executable Python text with pd.read_csv(), True/False/None
  if (format === "python") {
    const payload = data.payload as Record<string, unknown>;
    const basicConfig = payload.basic_config as Record<string, unknown>;
    const runConfig = payload.run_config as Record<string, unknown>;

    let pythonText = `import pandas as pd

basic_config = ${toPythonRepr(basicConfig)}

run_config = ${buildPythonRunConfig(runConfig)}
`;

    // Safety net: catch any stray JSON literals that slipped through
    pythonText = pythonText
      .replace(/\bnull\b/g, "None")
      .replace(/\btrue\b/g, "True")
      .replace(/\bfalse\b/g, "False");

    return new Response(pythonText, {
      headers: { ...corsHeaders, "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  // Default: raw JSON
  return new Response(JSON.stringify(data.payload), {
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
});
