import { supabase } from "@/integrations/supabase/client";
import { BasicConfig, RunConfig } from "@/types/arimax-config";

export interface ConfigPayload {
  basic_config: BasicConfig;
  run_config: RunConfig;
  meta: {
    schema_version: string;
    created_at: string;
    app: string;
    engine: string;
  };
}

export function buildPayload(basic: BasicConfig, run: RunConfig): ConfigPayload {
  return {
    basic_config: { ...basic },
    run_config: { ...run },
    meta: {
      schema_version: "1.0",
      created_at: new Date().toISOString(),
      app: "arimax-wizard",
      engine: "pmdarima-autoarima",
    },
  };
}

export function validatePayload(payload: ConfigPayload): string | null {
  const { basic_config, run_config } = payload;

  if (!basic_config.TARGET || typeof basic_config.TARGET !== "string") {
    return "TARGET must be a non-empty string.";
  }
  if (!Array.isArray(basic_config.MEVS) || !basic_config.MEVS.every((m) => typeof m === "string")) {
    return "MEVS must be a list of strings.";
  }

  // Ensure run_config is JSON-serializable (no functions)
  try {
    JSON.stringify(run_config);
  } catch {
    return "run_config contains non-serializable values.";
  }

  return null;
}

export async function saveConfig(payload: ConfigPayload): Promise<{ id: string }> {
  const { data, error } = await (supabase as any)
    .from("arimax_configs")
    .insert({ payload })
    .select("id")
    .single();

  if (error) throw new Error(error.message);
  return { id: data.id };
}

export async function loadConfig(id: string): Promise<ConfigPayload> {
  const { data, error } = await (supabase as any)
    .from("arimax_configs")
    .select("payload")
    .eq("id", id)
    .single();

  if (error) throw new Error(error.message);
  return data.payload as ConfigPayload;
}
