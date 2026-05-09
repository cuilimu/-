import { useState, useCallback } from "react";
import {
  BasicConfig,
  RunConfig,
  DEFAULT_BASIC_CONFIG,
  DEFAULT_RUN_CONFIG,
} from "@/types/arimax-config";

export function useWizardState() {
  const [step, setStep] = useState(0);
  const [columns, setColumns] = useState<string[]>([]);
  const [basicConfig, setBasicConfig] = useState<BasicConfig>({ ...DEFAULT_BASIC_CONFIG });
  const [runConfig, setRunConfig] = useState<RunConfig>({ ...DEFAULT_RUN_CONFIG });

  const updateBasic = useCallback(<K extends keyof BasicConfig>(key: K, value: BasicConfig[K]) => {
    setBasicConfig((prev) => ({ ...prev, [key]: value }));
  }, []);

  const updateRun = useCallback(<K extends keyof RunConfig>(key: K, value: RunConfig[K]) => {
    setRunConfig((prev) => ({ ...prev, [key]: value }));
  }, []);

  const reset = useCallback(() => {
    setStep(0);
    setColumns([]);
    setBasicConfig({ ...DEFAULT_BASIC_CONFIG });
    setRunConfig({ ...DEFAULT_RUN_CONFIG });
  }, []);

  const next = useCallback(() => setStep((s) => Math.min(s + 1, 6)), []);
  const back = useCallback(() => setStep((s) => Math.max(s - 1, 0)), []);

  return {
    step, setStep, columns, setColumns,
    basicConfig, runConfig,
    updateBasic, updateRun,
    next, back, reset,
  };
}
