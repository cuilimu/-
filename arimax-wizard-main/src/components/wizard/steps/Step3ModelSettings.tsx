import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { FieldTooltip } from "../FieldTooltip";
import { Settings } from "lucide-react";
import { BasicConfig } from "@/types/arimax-config";

interface Props {
  basicConfig: BasicConfig;
  updateBasic: <K extends keyof BasicConfig>(key: K, value: BasicConfig[K]) => void;
}

export function Step3ModelSettings({ basicConfig, updateBasic }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Settings className="w-5 h-5 text-primary" />
          Model Settings
        </CardTitle>
        <CardDescription>Configure frequency, lags, and data transformation.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="space-y-2">
            <Label>Frequency <FieldTooltip text="Time series frequency: QE=quarterly, ME=monthly, W=weekly, D=daily." /></Label>
            <Select value={basicConfig.freq || ""} onValueChange={(v) => updateBasic("freq", v)}>
              <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>
                {["QE", "ME", "W", "D", "B", "YE"].map((f) => (
                  <SelectItem key={f} value={f}>{f}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Max Lag <FieldTooltip text="Maximum number of lags to consider for ARIMAX orders (1–12)." /></Label>
            <Input
              type="number" min={1} max={12}
              value={basicConfig.max_lag ?? ""}
              onChange={(e) => updateBasic("max_lag", e.target.value ? Number(e.target.value) : null)}
              placeholder="e.g. 3"
            />
          </div>

          <div className="space-y-2">
            <Label>Max Exogenous Variables <FieldTooltip text="Maximum number of exogenous variables to include in any single model." /></Label>
            <Input
              type="number" min={1}
              value={basicConfig.max_number_of_Exogenous_Variables}
              onChange={(e) => updateBasic("max_number_of_Exogenous_Variables", Number(e.target.value) || 1)}
            />
          </div>

          <div className="space-y-2">
            <Label>Transform <FieldTooltip text="Transformation applied to the target variable before fitting." /></Label>
            <Select value={basicConfig.transform} onValueChange={(v) => updateBasic("transform", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {["original", "log", "boxcox"].map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex flex-wrap gap-6 pt-2">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={basicConfig.include_non_lags} onCheckedChange={(v) => updateBasic("include_non_lags", v)} />
            Include Non-Lags <FieldTooltip text="When on, also considers exogenous variables at lag 0 (contemporaneous)." />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={basicConfig.trace} onCheckedChange={(v) => updateBasic("trace", v)} />
            Trace <FieldTooltip text="Print detailed fitting logs to the console." />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={basicConfig.use_tqdm} onCheckedChange={(v) => updateBasic("use_tqdm", v)} />
            Use tqdm <FieldTooltip text="Show a progress bar during the search." />
          </label>
        </div>
      </CardContent>
    </Card>
  );
}
