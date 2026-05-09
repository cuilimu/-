import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldTooltip } from "../FieldTooltip";
import { BarChart3 } from "lucide-react";
import { RunConfig } from "@/types/arimax-config";

const SOFT_METHODS = ["weighted", "mse", "mae", "rmse", "mape", "smape", "mase"] as const;

// Default weight keys for weighted method
const WEIGHT_KEYS = ["mse", "mae", "rmse", "mape", "smape", "mase"] as const;

interface Props {
  runConfig: RunConfig;
  updateRun: <K extends keyof RunConfig>(key: K, value: RunConfig[K]) => void;
}

export function Step6SoftRules({ runConfig, updateRun }: Props) {
  const isWeighted = runConfig.soft_method === "weighted";

  const setWeight = (key: string, val: number) => {
    const current = runConfig.weights || {};
    updateRun("weights", { ...current, [key]: val });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-primary" />
          Soft Rules & Ranking
        </CardTitle>
        <CardDescription>How candidate models are scored and ranked after passing hard rules.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="space-y-2">
            <Label>Soft Method <FieldTooltip text="Metric used to rank surviving models. 'weighted' combines multiple metrics." /></Label>
            <Select value={runConfig.soft_method} onValueChange={(v) => updateRun("soft_method", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {SOFT_METHODS.map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Top N <FieldTooltip text="Number of top-ranked models to return." /></Label>
            <Input type="number" min={1} value={runConfig.top_n} onChange={(e) => updateRun("top_n", Number(e.target.value) || 1)} />
          </div>
        </div>

        {isWeighted && (
          <div className="space-y-3">
            <Label>Weights <FieldTooltip text="Assign weights to each error metric. They will be normalized internally." /></Label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {WEIGHT_KEYS.map((key) => (
                <div key={key} className="space-y-1">
                  <Label className="text-xs text-muted-foreground">{key}</Label>
                  <Input
                    type="number" min={0} step={0.1}
                    value={runConfig.weights?.[key] ?? ""}
                    onChange={(e) => setWeight(key, Number(e.target.value))}
                    placeholder="0"
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
