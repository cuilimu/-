import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FieldTooltip } from "../FieldTooltip";
import { ShieldCheck } from "lucide-react";
import { BasicConfig, RunConfig } from "@/types/arimax-config";
import { cn } from "@/lib/utils";

interface Props {
  basicConfig: BasicConfig;
  runConfig: RunConfig;
  updateRun: <K extends keyof RunConfig>(key: K, value: RunConfig[K]) => void;
}

export function Step5HardRules({ basicConfig, runConfig, updateRun }: Props) {
  const disabled = !runConfig.apply_hard;

  const setSign = (mev: string, sign: string) => {
    const current = runConfig.expected_sign || {};
    updateRun("expected_sign", { ...current, [mev]: sign });
  };

  const toggleEnforceSig = (mev: string, checked: boolean) => {
    const current = runConfig.enforce_sig_for || [];
    updateRun(
      "enforce_sig_for",
      checked ? [...current, mev] : current.filter((m) => m !== mev)
    );
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-primary" />
            Hard Rules
          </CardTitle>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={runConfig.apply_hard} onCheckedChange={(v) => updateRun("apply_hard", v)} />
            Apply
          </label>
        </div>
        <CardDescription>Constraints that candidate models must satisfy.</CardDescription>
      </CardHeader>
      <CardContent className={cn("space-y-5 transition-opacity", disabled && "opacity-40 pointer-events-none")}>
        {basicConfig.MEVS.length > 0 && (
          <div className="space-y-2">
            <Label>Expected Sign per MEV <FieldTooltip text="The expected direction of each variable's coefficient: + (positive), - (negative), or undetermined." /></Label>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Variable</TableHead>
                  <TableHead>Sign</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {basicConfig.MEVS.map((mev) => (
                  <TableRow key={mev}>
                    <TableCell className="font-medium">{mev}</TableCell>
                    <TableCell>
                      <Select
                        value={runConfig.expected_sign?.[mev] || "undetermined"}
                        onValueChange={(v) => setSign(mev, v)}
                      >
                        <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="+">+ (positive)</SelectItem>
                          <SelectItem value="-">- (negative)</SelectItem>
                          <SelectItem value="undetermined">undetermined</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="space-y-2">
            <Label>Alpha <FieldTooltip text="Significance level for coefficient p-values (default 0.05)." /></Label>
            <Input type="number" step={0.01} min={0.001} max={0.5} value={runConfig.alpha} onChange={(e) => updateRun("alpha", Number(e.target.value))} />
          </div>
          <div className="space-y-2">
            <Label>VIF Max <FieldTooltip text="Maximum Variance Inflation Factor allowed. Leave blank for no constraint." /></Label>
            <Input type="number" min={1} value={runConfig.vif_max ?? ""} onChange={(e) => updateRun("vif_max", e.target.value ? Number(e.target.value) : null)} placeholder="e.g. 10" />
          </div>
          <div className="space-y-2">
            <Label>Max Absolute AR <FieldTooltip text="Maximum absolute value of AR roots. Leave blank for no constraint." /></Label>
            <Input type="number" step={0.1} value={runConfig.max_abs_ar ?? ""} onChange={(e) => updateRun("max_abs_ar", e.target.value ? Number(e.target.value) : null)} placeholder="e.g. 1.8" />
          </div>
          <div className="space-y-2">
            <Label>Max Absolute MA <FieldTooltip text="Maximum absolute value of MA roots. Leave blank for no constraint." /></Label>
            <Input type="number" step={0.1} value={runConfig.max_abs_ma ?? ""} onChange={(e) => updateRun("max_abs_ma", e.target.value ? Number(e.target.value) : null)} placeholder="e.g. 1" />
          </div>
        </div>

        <div className="flex flex-wrap gap-6">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={runConfig.require_stationary} onCheckedChange={(v) => updateRun("require_stationary", v)} />
            Require Stationary <FieldTooltip text="Reject models with non-stationary AR polynomial." />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={runConfig.require_invertible} onCheckedChange={(v) => updateRun("require_invertible", v)} />
            Require Invertible <FieldTooltip text="Reject models with non-invertible MA polynomial." />
          </label>
        </div>

        {basicConfig.MEVS.length > 0 && (
          <div className="space-y-2">
            <Label>Enforce Significance For <FieldTooltip text="Optionally require these specific MEVs to have significant coefficients." /></Label>
            <div className="flex flex-wrap gap-3 p-3 border rounded-lg">
              {basicConfig.MEVS.map((mev) => (
                <label key={mev} className="flex items-center gap-1.5 text-sm">
                  <Checkbox
                    checked={runConfig.enforce_sig_for?.includes(mev) || false}
                    onCheckedChange={(checked) => toggleEnforceSig(mev, !!checked)}
                  />
                  {mev}
                </label>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
