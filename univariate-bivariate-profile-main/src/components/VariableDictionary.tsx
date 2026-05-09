import { VariableInfo } from '@/lib/statistics';
import { AIInferenceMap } from '@/hooks/useAIVariableDictionary';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Sparkles, Loader2, Info, FileDown } from 'lucide-react';
import { getModelString } from '@/lib/aiModels';
import { useAISettings } from '@/contexts/AISettingsContext';

interface VariableDictionaryProps {
  variables: Record<string, VariableInfo>;
  inferences: AIInferenceMap;
  datasetSummary: string | null;
  isLoading: boolean;
  onInfer: (model: string) => void;
}

const confidenceColors: Record<string, string> = {
  high: 'bg-green-500/20 text-green-400 border-green-500/30',
  medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  low: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
};

export function VariableDictionary({
  variables,
  inferences,
  datasetSummary,
  isLoading,
  onInfer,
}: VariableDictionaryProps) {
  const { globalModel } = useAISettings();
  const variableNames = Object.keys(variables).sort();
  const hasInferences = Object.keys(inferences).length > 0;

  const handleInfer = () => {
    onInfer(getModelString(globalModel));
  };

  const handleDownloadPDF = () => {
    // Create a printable HTML document for PDF generation
    const printContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Variable Dictionary</title>
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
            color: #1a1a1a;
          }
          h1 {
            font-size: 24px;
            margin-bottom: 20px;
            color: #1a1a1a;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
          }
          th, td {
            border: 1px solid #ddd;
            padding: 10px 12px;
            text-align: left;
          }
          th {
            background-color: #f5f5f5;
            font-weight: 600;
          }
          tr:nth-child(even) {
            background-color: #fafafa;
          }
          .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
          }
          .type-badge {
            background-color: #e5e5e5;
            color: #525252;
          }
          .confidence-high {
            background-color: #dcfce7;
            color: #166534;
          }
          .confidence-medium {
            background-color: #fef9c3;
            color: #854d0e;
          }
          .confidence-low {
            background-color: #ffedd5;
            color: #c2410c;
          }
          .footer {
            margin-top: 20px;
            font-size: 11px;
            color: #666;
          }
        </style>
      </head>
      <body>
        <h1>Variable Dictionary</h1>
        <table>
          <thead>
            <tr>
              <th style="width: 20%">Variable</th>
              <th style="width: 12%">Type</th>
              <th style="width: 20%">Inferred Type</th>
              <th style="width: 10%">Confidence</th>
              <th style="width: 38%">Inferred Definition</th>
            </tr>
          </thead>
          <tbody>
            ${variableNames.map((name) => {
              const variable = variables[name];
              const inference = inferences[name];
              return `
                <tr>
                  <td><strong>${name}</strong></td>
                  <td><span class="badge type-badge">${variable.vtype}</span></td>
                  <td>${inference ? inference.inferred_type : '—'}</td>
                  <td>${inference ? `<span class="badge confidence-${inference.confidence}">${inference.confidence}</span>` : '—'}</td>
                  <td>${inference ? inference.inferred_definition : '—'}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
        <div class="footer">
          Generated on ${new Date().toLocaleString()}
        </div>
      </body>
      </html>
    `;

    // Open print dialog for PDF
    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(printContent);
      printWindow.document.close();
      printWindow.onload = () => {
        printWindow.print();
      };
    }
  };

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            Variable Dictionary
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <Info className="w-4 h-4 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p>AI-powered inference of semantic types and business definitions. Detects when numeric variables should be treated as categorical (IDs, flags, ordinal codes).</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
          <div className="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    onClick={handleDownloadPDF}
                    disabled={!hasInferences || isLoading}
                    size="sm"
                    variant="outline"
                    className="gap-2"
                  >
                    <FileDown className="w-4 h-4" />
                    Download PDF
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{hasInferences ? 'Download dictionary as PDF' : 'Run inference first to download'}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Button
              onClick={handleInfer}
              disabled={isLoading}
              size="sm"
              className="gap-2"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Inferring...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Infer with AI
                </>
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {datasetSummary && (
          <div className="mb-3 p-3 bg-primary/5 border border-primary/20 rounded-md">
            <p className="text-sm text-foreground flex items-start gap-2">
              <Sparkles className="w-4 h-4 text-primary mt-0.5 flex-shrink-0" />
              <span>{datasetSummary}</span>
            </p>
          </div>
        )}
        <ScrollArea className="h-[300px] rounded-md border">
          <div className="min-w-[800px]">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[180px] sticky left-0 bg-background z-10">Variable</TableHead>
                  <TableHead className="w-[100px]">Type</TableHead>
                  <TableHead className="w-[180px]">Inferred Type</TableHead>
                  <TableHead className="w-[100px]">Confidence</TableHead>
                  <TableHead className="min-w-[300px]">Inferred Definition</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {variableNames.map((name) => {
                  const variable = variables[name];
                  const inference = inferences[name];

                  return (
                    <TableRow key={name}>
                      <TableCell className="font-medium sticky left-0 bg-background z-10">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger className="text-left truncate block max-w-[160px]">
                              {name}
                            </TooltipTrigger>
                            <TooltipContent>
                              <p>{name}</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {variable.vtype}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {isLoading ? (
                          <div className="h-4 w-24 bg-muted animate-pulse rounded" />
                        ) : inference ? (
                          <span className="text-sm font-medium">
                            {inference.inferred_type}
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-sm">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {isLoading ? (
                          <div className="h-4 w-16 bg-muted animate-pulse rounded" />
                        ) : inference ? (
                          <Badge
                            variant="outline"
                            className={`text-xs ${confidenceColors[inference.confidence]}`}
                          >
                            {inference.confidence}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground text-sm">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {isLoading ? (
                          <div className="h-4 w-full bg-muted animate-pulse rounded" />
                        ) : inference ? (
                          <span className="text-sm text-muted-foreground">
                            {inference.inferred_definition}
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-sm">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
        {!hasInferences && !isLoading && (
          <p className="text-sm text-muted-foreground text-center mt-3">
            Click "Infer with AI" to generate semantic types and definitions for all variables.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
