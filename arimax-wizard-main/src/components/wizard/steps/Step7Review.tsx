import { useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Copy, Download, RotateCcw, FileJson, CloudUpload, Check, ExternalLink } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { BasicConfig, RunConfig } from "@/types/arimax-config";
import { buildPayload, validatePayload, saveConfig } from "@/lib/save-config";

interface Props {
  basicConfig: BasicConfig;
  runConfig: RunConfig;
  onReset: () => void;
}

/** Convert JSON to Python-friendly format: true→True, false→False, null→None, raw→pd.read_csv(...) */
function toPythonJson(obj: unknown, dsColumn?: string | null): string {
  let result = JSON.stringify(obj, null, 4)
    .replace(/\btrue\b/g, "True")
    .replace(/\bfalse\b/g, "False")
    .replace(/\bnull\b/g, "None");
  if (dsColumn !== undefined) {
    const dsVal = dsColumn ? `"${dsColumn}"` : '"DATE"';
    const readCsv = (path: string) =>
      `pd.read_csv(\n        "${path}",\n        index_col=${dsVal},\n        parse_dates=[${dsVal}]\n    )`;
    result = result.replace(/"raw":\s*"([^"]+)"/, (_, p) => `"raw": ${readCsv(p)}`);
    result = result.replace(/"raw":\s*None/, `"raw": ${readCsv("YOUR_FILE.csv")}`);
  }
  return result;
}

export function Step7Review({ basicConfig, runConfig, onReset }: Props) {
  const { toast } = useToast();

  const basicText = useMemo(() => toPythonJson(basicConfig), [basicConfig]);
  const runText = useMemo(() => toPythonJson(runConfig, runConfig.ds_column), [runConfig]);

  const [basicEdited, setBasicEdited] = useState(basicText);
  const [runEdited, setRunEdited] = useState(runText);
  const [prevBasicText, setPrevBasicText] = useState(basicText);
  const [prevRunText, setPrevRunText] = useState(runText);

  // Save state
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);

  if (basicText !== prevBasicText) {
    setPrevBasicText(basicText);
    setBasicEdited(basicText);
  }
  if (runText !== prevRunText) {
    setPrevRunText(runText);
    setRunEdited(runText);
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied!", description: `${label} copied to clipboard.` });
  };

  const downloadJson = (text: string, filename: string) => {
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSave = async () => {
    const payload = buildPayload(basicConfig, runConfig);
    const validationError = validatePayload(payload);
    if (validationError) {
      toast({ title: "Validation Error", description: validationError, variant: "destructive" });
      return;
    }

    setSaving(true);
    try {
      const { id } = await saveConfig(payload);
      setSavedId(id);
      toast({ title: "Saved!", description: "Config saved to cloud." });

      // Handle callback redirect if URL params are present
      const params = new URLSearchParams(window.location.search);
      const returnUrl = params.get("return_url");
      const state = params.get("state");
      if (returnUrl) {
        const redirectUrl = new URL(returnUrl);
        redirectUrl.searchParams.set("config_id", id);
        if (state) redirectUrl.searchParams.set("state", state);
        window.location.href = redirectUrl.toString();
      }
    } catch (e: any) {
      toast({ title: "Save Failed", description: e.message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const shareUrl = savedId ? `${window.location.origin}/config/${savedId}` : null;

  const apiUrl = savedId
    ? `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/get-config/${savedId}`
    : "";

  const pythonFetchSnippet = savedId
    ? `import requests\n\nconfig = requests.get("${apiUrl}").json()`
    : "";

  return (
    <div className="space-y-6">
      {/* basic_config */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileJson className="w-5 h-5 text-primary" />
            basic_config
          </CardTitle>
          <CardDescription>
            Use with: <code className="text-xs bg-muted px-1.5 py-0.5 rounded">basic = basic_config.copy()</code> then <code className="text-xs bg-muted px-1.5 py-0.5 rounded">basic.update(…)</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            className="font-mono text-xs min-h-[260px]"
            value={basicEdited}
            onChange={(e) => setBasicEdited(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => copyToClipboard(basicEdited, "basic_config")} className="gap-2">
              <Copy className="w-4 h-4" /> Copy
            </Button>
            <Button size="sm" variant="secondary" onClick={() => downloadJson(basicEdited, "basic_config.json")} className="gap-2">
              <Download className="w-4 h-4" /> Download
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* run_config */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileJson className="w-5 h-5 text-primary" />
            run_config
          </CardTitle>
          <CardDescription>
            Use with: <code className="text-xs bg-muted px-1.5 py-0.5 rounded">run_cfg = run_config.copy()</code> then <code className="text-xs bg-muted px-1.5 py-0.5 rounded">run_cfg.update(…)</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            className="font-mono text-xs min-h-[260px]"
            value={runEdited}
            onChange={(e) => setRunEdited(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => copyToClipboard(runEdited, "run_config")} className="gap-2">
              <Copy className="w-4 h-4" /> Copy
            </Button>
            <Button size="sm" variant="secondary" onClick={() => downloadJson(runEdited, "run_config.json")} className="gap-2">
              <Download className="w-4 h-4" /> Download
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Save to Cloud */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <CloudUpload className="w-5 h-5 text-primary" />
            Save to Cloud
          </CardTitle>
          <CardDescription>
            Store this config in the cloud and get a shareable link.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!savedId ? (
            <Button onClick={handleSave} disabled={saving} className="gap-2">
              <CloudUpload className="w-4 h-4" />
              {saving ? "Saving…" : "Save Config"}
            </Button>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm text-primary">
                <Check className="w-4 h-4" /> Saved successfully
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">Config ID</label>
                <div className="flex items-center gap-2">
                  <code className="text-xs bg-muted px-2 py-1 rounded font-mono flex-1 truncate">{savedId}</code>
                  <Button size="sm" variant="outline" onClick={() => copyToClipboard(savedId, "Config ID")} className="gap-1 shrink-0">
                    <Copy className="w-3 h-3" /> Copy ID
                  </Button>
                </div>
              </div>

              {shareUrl && (
                <div className="space-y-2">
                  <label className="text-xs font-medium text-muted-foreground">Share Link</label>
                  <div className="flex items-center gap-2">
                    <code className="text-xs bg-muted px-2 py-1 rounded font-mono flex-1 truncate">{shareUrl}</code>
                    <Button size="sm" variant="outline" onClick={() => copyToClipboard(shareUrl, "Share link")} className="gap-1 shrink-0">
                      <ExternalLink className="w-3 h-3" /> Copy
                    </Button>
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">Python fetch snippet</label>
                <Textarea className="font-mono text-xs min-h-[60px]" value={pythonFetchSnippet} readOnly />
                <Button size="sm" variant="outline" onClick={() => copyToClipboard(pythonFetchSnippet, "Python snippet")} className="gap-1">
                  <Copy className="w-3 h-3" /> Copy snippet
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Reset */}
      <div className="flex justify-end">
        <Button onClick={onReset} variant="outline" className="gap-2">
          <RotateCcw className="w-4 h-4" /> Reset Wizard
        </Button>
      </div>
    </div>
  );
}
