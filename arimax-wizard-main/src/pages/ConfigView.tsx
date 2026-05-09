import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { loadConfig, ConfigPayload } from "@/lib/save-config";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Copy, ArrowLeft, FileJson } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function ConfigView() {
  const { id } = useParams<{ id: string }>();
  const { toast } = useToast();
  const [payload, setPayload] = useState<ConfigPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    loadConfig(id)
      .then(setPayload)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied!", description: `${label} copied to clipboard.` });
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">Loading config…</div>;
  if (error) return <div className="min-h-screen flex items-center justify-center text-destructive">Error: {error}</div>;
  if (!payload) return null;

  const basicJson = JSON.stringify(payload.basic_config, null, 2);
  const runJson = JSON.stringify(payload.run_config, null, 2);

  return (
    <div className="min-h-screen bg-background py-8 px-4">
      <div className="max-w-3xl mx-auto space-y-6">
        <header className="space-y-2">
          <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="w-4 h-4" /> Back to Wizard
          </Link>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Saved Config</h1>
          <p className="text-sm text-muted-foreground font-mono">{id}</p>
          <p className="text-xs text-muted-foreground">Created: {payload.meta.created_at}</p>
        </header>

        {[{ label: "basic_config", json: basicJson }, { label: "run_config", json: runJson }].map(({ label, json }) => (
          <Card key={label}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FileJson className="w-5 h-5 text-primary" />
                {label}
              </CardTitle>
              <CardDescription>Schema v{payload.meta.schema_version} · {payload.meta.engine}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea className="font-mono text-xs min-h-[200px]" value={json} readOnly />
              <Button size="sm" onClick={() => copy(json, label)} className="gap-2">
                <Copy className="w-4 h-4" /> Copy
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
