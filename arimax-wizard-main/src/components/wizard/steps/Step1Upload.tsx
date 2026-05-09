import { useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FieldTooltip } from "../FieldTooltip";
import { Upload, FileSpreadsheet } from "lucide-react";
import { BasicConfig, RunConfig } from "@/types/arimax-config";

interface Props {
  columns: string[];
  setColumns: (cols: string[]) => void;
  runConfig: RunConfig;
  updateRun: <K extends keyof RunConfig>(key: K, value: RunConfig[K]) => void;
}

export function Step1Upload({ columns, setColumns, runConfig, updateRun }: Props) {
  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result as string;
        const firstLine = text.split("\n")[0];
        const headers = firstLine.split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
        setColumns(headers);
      };
      reader.readAsText(file);
    },
    [setColumns]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileSpreadsheet className="w-5 h-5 text-primary" />
          Upload Your Data
        </CardTitle>
        <CardDescription>
          Upload a CSV file so we can auto-detect your column names.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label>CSV File <FieldTooltip text="Upload the CSV file containing your time series and exogenous variables. Column headers will be used throughout the wizard." /></Label>
          <label className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-muted-foreground/30 rounded-lg p-8 cursor-pointer hover:border-primary/50 transition-colors">
            <Upload className="w-8 h-8 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Click to upload CSV</span>
            <input type="file" accept=".csv" className="hidden" onChange={handleFileUpload} />
          </label>
          {columns.length > 0 && (
            <p className="text-sm text-muted-foreground">{columns.length} columns detected</p>
          )}
        </div>

        {columns.length > 0 && (
          <>
            <div className="space-y-2">
              <Label>Date Column <FieldTooltip text="Select the column that contains your date/time index (e.g. 'DATE')." /></Label>
              <Select value={runConfig.ds_column || ""} onValueChange={(v) => updateRun("ds_column", v)}>
                <SelectTrigger><SelectValue placeholder="Select date column" /></SelectTrigger>
                <SelectContent>
                  {columns.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>File Path for JSON <FieldTooltip text="The file path your Python script will use to load this data. Embedded in the exported config." /></Label>
              <Input
                placeholder="e.g. ./data/raw.csv"
                value={runConfig.raw || ""}
                onChange={(e) => updateRun("raw", e.target.value)}
              />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
