import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FieldTooltip } from "../FieldTooltip";
import { Target, Layers } from "lucide-react";
import { BasicConfig, RunConfig } from "@/types/arimax-config";

interface Props {
  columns: string[];
  basicConfig: BasicConfig;
  runConfig: RunConfig;
  updateBasic: <K extends keyof BasicConfig>(key: K, value: BasicConfig[K]) => void;
}

export function Step2Variables({ columns, basicConfig, updateBasic, runConfig }: Props) {
  const nonDateCols = columns.filter((c) => c !== runConfig.ds_column);

  const toggleMev = (col: string, checked: boolean) => {
    const newMevs = checked
      ? [...basicConfig.MEVS, col]
      : basicConfig.MEVS.filter((m) => m !== col);
    updateBasic("MEVS", newMevs);

    // clean up guide
    if (!checked) {
      const newGuide = { ...basicConfig.MEVS_Guide };
      delete newGuide[col];
      updateBasic("MEVS_Guide", newGuide);
    }
  };

  const setGuide = (col: string, method: string) => {
    updateBasic("MEVS_Guide", { ...basicConfig.MEVS_Guide, [col]: method });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="w-5 h-5 text-primary" />
          Target & Exogenous Variables
        </CardTitle>
        <CardDescription>Pick your target variable and the macro-economic variables (MEVs) to include.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label>Target Variable <FieldTooltip text="The dependent variable your model will forecast." /></Label>
          <Select value={basicConfig.TARGET || ""} onValueChange={(v) => updateBasic("TARGET", v)}>
            <SelectTrigger><SelectValue placeholder="Select target" /></SelectTrigger>
            <SelectContent>
              {nonDateCols.map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Exogenous Variables (MEVs) <FieldTooltip text="Select the external predictors to include in candidate models." /></Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 p-3 border rounded-lg max-h-48 overflow-y-auto">
            {nonDateCols
              .filter((c) => c !== basicConfig.TARGET)
              .map((col) => (
                <label key={col} className="flex items-center gap-2 text-sm cursor-pointer">
                  <Checkbox
                    checked={basicConfig.MEVS.includes(col)}
                    onCheckedChange={(checked) => toggleMev(col, !!checked)}
                  />
                  {col}
                </label>
              ))}
          </div>
        </div>

        {basicConfig.MEVS.length > 0 && (
          <div className="space-y-2">
            <Label className="flex items-center">
              <Layers className="w-4 h-4 mr-1.5 text-primary" />
              MEVS Transformation Guide
              <FieldTooltip text="Specify how each MEV should be transformed before modeling: log_diff, diff, or none." />
            </Label>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Variable</TableHead>
                  <TableHead>Transformation</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {basicConfig.MEVS.map((mev) => (
                  <TableRow key={mev}>
                    <TableCell className="font-medium">{mev}</TableCell>
                    <TableCell>
                      <Select
                        value={basicConfig.MEVS_Guide[mev] || "none"}
                        onValueChange={(v) => setGuide(mev, v)}
                      >
                        <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          <SelectItem value="diff">diff</SelectItem>
                          <SelectItem value="log_diff">log_diff</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
