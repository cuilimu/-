import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Settings2, Sparkles } from 'lucide-react';
import { useAISettings } from '@/contexts/AISettingsContext';
import { MODEL_OPTIONS, ModelProvider } from '@/lib/aiModels';

export function GlobalAISettings() {
  const { globalModel, setGlobalModel } = useAISettings();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Sparkles className="w-4 h-4" />
          <span className="hidden sm:inline">AI Settings</span>
          <Settings2 className="w-4 h-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64" align="end">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            <h4 className="font-medium">Global AI Model</h4>
          </div>
          <p className="text-xs text-muted-foreground">
            Set the default AI model for all features
          </p>
          <Select value={globalModel} onValueChange={(v: ModelProvider) => setGlobalModel(v)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODEL_OPTIONS.map(opt => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Applies to: AI Guide, Report Generation, Variable Dictionary
          </p>
        </div>
      </PopoverContent>
    </Popover>
  );
}
