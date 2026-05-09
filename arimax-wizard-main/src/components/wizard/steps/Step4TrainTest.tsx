import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { FieldTooltip } from "../FieldTooltip";
import { SplitSquareHorizontal } from "lucide-react";
import { BasicConfig } from "@/types/arimax-config";

interface Props {
  basicConfig: BasicConfig;
  updateBasic: <K extends keyof BasicConfig>(key: K, value: BasicConfig[K]) => void;
}

export function Step4TrainTest({ basicConfig, updateBasic }: Props) {
  const trainPct = Math.round(basicConfig.train_threshold * 100);
  const testPct = 100 - trainPct;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SplitSquareHorizontal className="w-5 h-5 text-primary" />
          Train / Test Split
        </CardTitle>
        <CardDescription>Define how much data is used for training vs. testing.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-3">
          <Label>Train Threshold: {trainPct}% <FieldTooltip text="Fraction of the data used for training. The rest is held out for testing." /></Label>
          <Slider
            min={50} max={95} step={5}
            value={[trainPct]}
            onValueChange={([v]) => updateBasic("train_threshold", v / 100)}
          />
          <div className="flex h-4 rounded-full overflow-hidden border">
            <div className="bg-primary transition-all" style={{ width: `${trainPct}%` }} />
            <div className="bg-muted flex-1" />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Train {trainPct}%</span>
            <span>Test {testPct}%</span>
          </div>
        </div>

        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={basicConfig.oot_test} onCheckedChange={(v) => updateBasic("oot_test", v)} />
            Enable Out-of-Time (OOT) Test <FieldTooltip text="Hold out an additional slice of the most recent data for a final OOT validation." />
          </label>

          {basicConfig.oot_test && (
            <div className="space-y-2 pl-4 border-l-2 border-primary/20">
              <Label>OOT Threshold: {Math.round(basicConfig.oot_threshold * 100)}% <FieldTooltip text="Fraction of data before which the OOT holdout begins." /></Label>
              <Slider
                min={80} max={99} step={1}
                value={[Math.round(basicConfig.oot_threshold * 100)]}
                onValueChange={([v]) => updateBasic("oot_threshold", v / 100)}
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
