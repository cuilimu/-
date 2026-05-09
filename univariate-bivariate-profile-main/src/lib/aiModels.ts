export type ModelProvider = 'openai' | 'google';

export interface ModelOption {
  value: ModelProvider;
  label: string;
  model: string;
}

export const MODEL_OPTIONS: ModelOption[] = [
  { value: 'google', label: 'Gemini', model: 'google/gemini-3-flash-preview' },
  { value: 'openai', label: 'GPT-5', model: 'openai/gpt-5-mini' },
];

export function getModelString(provider: ModelProvider): string {
  return MODEL_OPTIONS.find(m => m.value === provider)?.model || 'google/gemini-3-flash-preview';
}
