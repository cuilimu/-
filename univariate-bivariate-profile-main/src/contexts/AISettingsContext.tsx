import { createContext, useContext, useState, ReactNode } from 'react';
import { ModelProvider } from '@/lib/aiModels';

interface AISettingsContextType {
  globalModel: ModelProvider;
  setGlobalModel: (model: ModelProvider) => void;
}

const AISettingsContext = createContext<AISettingsContextType | undefined>(undefined);

export function AISettingsProvider({ children }: { children: ReactNode }) {
  const [globalModel, setGlobalModel] = useState<ModelProvider>('google');

  return (
    <AISettingsContext.Provider value={{ globalModel, setGlobalModel }}>
      {children}
    </AISettingsContext.Provider>
  );
}

export function useAISettings() {
  const context = useContext(AISettingsContext);
  if (!context) {
    throw new Error('useAISettings must be used within an AISettingsProvider');
  }
  return context;
}
