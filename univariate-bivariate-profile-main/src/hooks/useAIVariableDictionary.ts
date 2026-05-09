import { useState, useCallback } from 'react';
import { VariableInfo } from '@/lib/statistics';
import { useToast } from '@/hooks/use-toast';

export interface AIVariableInference {
  inferred_type: string;
  inferred_definition: string;
  confidence: 'high' | 'medium' | 'low';
}

export type AIInferenceMap = Record<string, AIVariableInference>;

export interface AIInferenceResult {
  inferences: AIInferenceMap;
  datasetSummary: string | null;
}

interface VariableSummary {
  name: string;
  vtype: string;
  unique: number;
  missing_pct: number;
  sample_values: (string | number)[];
  min?: number;
  max?: number;
  zeros?: number;
}

export function useAIVariableDictionary() {
  const [inferences, setInferences] = useState<AIInferenceMap>({});
  const [datasetSummary, setDatasetSummary] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const inferVariables = useCallback(async (variables: Record<string, VariableInfo>, model?: string) => {
    setIsLoading(true);
    setError(null);

    try {
      // Build variable summaries for the AI
      const summaries: VariableSummary[] = Object.entries(variables).map(([name, v]) => {
        const summary: VariableSummary = {
          name,
          vtype: v.vtype,
          unique: v.unique,
          missing_pct: v.missing_pct,
          sample_values: [],
        };

        // Extract sample values based on type
        if (v.vtype === 'numeric' && 'common_values' in v.details) {
          const numericDetails = v.details as { common_values?: { value: string | number }[]; tab1?: { quantiles?: { min: number | null; max: number | null } }; zeros?: number | null };
          summary.sample_values = numericDetails.common_values?.slice(0, 10).map(cv => cv.value) || [];
          if (numericDetails.tab1?.quantiles) {
            summary.min = numericDetails.tab1.quantiles.min ?? undefined;
            summary.max = numericDetails.tab1.quantiles.max ?? undefined;
          }
          summary.zeros = numericDetails.zeros ?? undefined;
        } else if (v.vtype === 'categorical' && 'top_values' in v.details) {
          const catDetails = v.details as { top_values?: { value: string | number }[] };
          summary.sample_values = catDetails.top_values?.slice(0, 10).map(tv => tv.value) || [];
        } else if (v.vtype === 'boolean') {
          summary.sample_values = ['true', 'false'];
        }

        return summary;
      });

      const response = await fetch(
        `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/infer-variable-dictionary`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
          },
          body: JSON.stringify({ variables: summaries, model }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Request failed with status ${response.status}`);
      }

      const data = await response.json();
      
      // Convert array to map
      const inferenceMap: AIInferenceMap = {};
      if (data.inferences && Array.isArray(data.inferences)) {
        for (const inf of data.inferences) {
          inferenceMap[inf.name] = {
            inferred_type: inf.inferred_type,
            inferred_definition: inf.inferred_definition,
            confidence: inf.confidence,
          };
        }
      }

      setInferences(inferenceMap);
      setDatasetSummary(data.dataset_summary || null);
      toast({
        title: "Inference Complete",
        description: `Successfully inferred types for ${Object.keys(inferenceMap).length} variables.`,
      });

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to infer variable types';
      setError(message);
      toast({
        title: "Inference Failed",
        description: message,
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  const clearInferences = useCallback(() => {
    setInferences({});
    setDatasetSummary(null);
    setError(null);
  }, []);

  return {
    inferences,
    datasetSummary,
    isLoading,
    error,
    inferVariables,
    clearInferences,
  };
}
