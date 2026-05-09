import { DatasetPayload, formatNumber, formatPercent } from '@/lib/statistics';
import { VariableCard } from './VariableCard';
import { SampleDataPreview } from './SampleDataPreview';
import { ReportTab } from './ReportTab';
import { InteractionTab } from './InteractionTab';
import { NullValuesChart } from './NullValuesChart';
import { VariableDictionary } from './VariableDictionary';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Download, FileText, Layers, Hash, Type, Calendar, ToggleLeft, AlertTriangle, Search, Sparkles, GitCompare } from 'lucide-react';
import { useState, useMemo, useCallback } from 'react';
import { generateHTMLReport } from '@/lib/htmlReport';
import { useAIVariableDictionary, AIInferenceMap } from '@/hooks/useAIVariableDictionary';

interface AnalysisDashboardProps {
  payload: DatasetPayload;
  rawData: Record<string, unknown>[];
}

export function AnalysisDashboard({ payload, rawData }: AnalysisDashboardProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedVariable, setSelectedVariable] = useState<string | null>(null);
  
  const { meta, variables, alerts, sample_data } = payload;
  
  const {
    inferences,
    datasetSummary,
    isLoading: isInferring,
    inferVariables,
  } = useAIVariableDictionary();

  const handleInferVariables = useCallback((model: string) => {
    inferVariables(variables, model);
  }, [inferVariables, variables]);
  
  const variableNames = useMemo(() => 
    Object.keys(variables).filter(name => 
      name.toLowerCase().includes(searchTerm.toLowerCase())
    ).sort(),
    [variables, searchTerm]
  );

  const totalAlerts = alerts.correlation.length + alerts.zeros.length + alerts.unique.length + alerts.uniform.length;

  const handleExportHTML = () => {
    const htmlContent = generateHTMLReport(payload, rawData, inferences);
    const blob = new Blob([htmlContent], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `univariate_analysis_${meta.source_file.replace('.csv', '')}_${new Date().toISOString().split('T')[0]}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <Tabs defaultValue="overview" className="w-full">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-4">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="variables">Variables</TabsTrigger>
            <TabsTrigger value="alerts">
              Alerts {totalAlerts > 0 && <Badge variant="secondary" className="ml-1">{totalAlerts}</Badge>}
            </TabsTrigger>
            <TabsTrigger value="interaction" className="gap-1">
              <GitCompare className="w-3 h-3" />
              Interaction
            </TabsTrigger>
            <TabsTrigger value="report" className="gap-1">
              <Sparkles className="w-3 h-3" />
              Report
            </TabsTrigger>
          </TabsList>
          <Button onClick={handleExportHTML} className="gap-2">
            <Download className="w-4 h-4" />
            Export HTML
          </Button>
        </div>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-xl">{meta.title}</CardTitle>
              <p className="text-sm text-muted-foreground">
                Source: {meta.source_file} | Generated: {meta.generated_at}
              </p>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <Layers className="w-5 h-5 text-primary" />
                  <div>
                    <p className="text-xs text-muted-foreground">Rows</p>
                    <p className="font-semibold">{formatNumber(meta.rows, 0)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <FileText className="w-5 h-5 text-primary" />
                  <div>
                    <p className="text-xs text-muted-foreground">Columns</p>
                    <p className="font-semibold">{meta.cols}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-yellow-600" />
                  <div>
                    <p className="text-xs text-muted-foreground">Missing Cells</p>
                    <p className="font-semibold">{meta.missing_cells} ({formatPercent(meta.missing_pct)})</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <Layers className="w-5 h-5 text-orange-600" />
                  <div>
                    <p className="text-xs text-muted-foreground">Duplicates</p>
                    <p className="font-semibold">{meta.duplicate_rows} ({formatPercent(meta.duplicate_pct)})</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-red-600" />
                  <div>
                    <p className="text-xs text-muted-foreground">Alerts</p>
                    <p className="font-semibold">{totalAlerts}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Dataset Statistics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Missing cells</span>
                  <span>{meta.missing_cells} ({formatPercent(meta.missing_pct)})</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Duplicate rows</span>
                  <span>{meta.duplicate_rows} ({formatPercent(meta.duplicate_pct)})</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Variable Types</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between items-center">
                  <span className="flex items-center gap-2"><Hash className="w-4 h-4" /> Numeric</span>
                  <Badge variant="secondary">{meta.type_counts.numeric}</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="flex items-center gap-2"><Type className="w-4 h-4" /> Categorical</span>
                  <Badge variant="secondary">{meta.type_counts.categorical}</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="flex items-center gap-2"><Calendar className="w-4 h-4" /> Datetime</span>
                  <Badge variant="secondary">{meta.type_counts.datetime}</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="flex items-center gap-2"><ToggleLeft className="w-4 h-4" /> Boolean</span>
                  <Badge variant="secondary">{meta.type_counts.boolean}</Badge>
                </div>
              </CardContent>
          </Card>
          </div>

          {/* Null Values Bar Chart */}
          <NullValuesChart variables={variables} />

          {/* Sample Data Preview */}
          <SampleDataPreview head={sample_data.head} tail={sample_data.tail} />
        </TabsContent>

        {/* Variables Tab */}
        <TabsContent value="variables">
          {/* Variable Dictionary at the top */}
          <VariableDictionary
            variables={variables}
            inferences={inferences}
            datasetSummary={datasetSummary}
            isLoading={isInferring}
            onInfer={handleInferVariables}
          />
          
          <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4">
            <Card className="h-[calc(100vh-300px)] sticky top-4">
              <CardHeader className="pb-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search variables..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9"
                  />
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <ScrollArea className="h-[calc(100vh-400px)]">
                  <div className="p-2 space-y-1">
                    {variableNames.map(name => {
                      const v = variables[name];
                      return (
                        <button
                          key={name}
                          onClick={() => setSelectedVariable(name)}
                          className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center justify-between gap-2 transition-colors ${
                            selectedVariable === name 
                              ? 'bg-primary/10 border border-primary/50' 
                              : 'hover:bg-muted'
                          }`}
                        >
                          <span className="truncate">{name}</span>
                          <Badge variant="outline" className="text-xs shrink-0">
                            {v.vtype}
                          </Badge>
                        </button>
                      );
                    })}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            <div>
              {selectedVariable ? (
                <VariableCard variable={variables[selectedVariable]} />
              ) : (
                <Card className="h-64 flex items-center justify-center">
                  <p className="text-muted-foreground">Select a variable to view details</p>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="space-y-4">
          {alerts.correlation.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Correlation Alerts</CardTitle>
                <p className="text-xs text-muted-foreground">
                  High correlation (|r| ≥ 0.95) detected between variables
                </p>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {alerts.correlation.map((alert, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-muted/50 rounded-lg text-sm">
                      <span>{alert.Message}</span>
                      <Badge variant="destructive">{alert['Alert type']}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {alerts.zeros.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Zero Value Alerts</CardTitle>
                <p className="text-xs text-muted-foreground">
                  Columns with significant zero values (≥10%)
                </p>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {alerts.zeros.map((alert, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-muted/50 rounded-lg text-sm">
                      <span>{alert.Message}</span>
                      <Badge variant="secondary">{alert['Alert type']}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {alerts.unique.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Unique Value Alerts</CardTitle>
                <p className="text-xs text-muted-foreground">
                  Columns with too many unique values (≥80% of rows)
                </p>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {alerts.unique.map((alert, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-muted/50 rounded-lg text-sm">
                      <span>{alert.Message}</span>
                      <Badge variant="secondary">{alert['Alert type']}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {alerts.uniform.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Uniform Distribution Alerts</CardTitle>
                <p className="text-xs text-muted-foreground">
                  Columns with approximately uniform distribution
                </p>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {alerts.uniform.map((alert, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-muted/50 rounded-lg text-sm">
                      <span>{alert.Message}</span>
                      <Badge variant="outline">{alert['Alert type']}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {totalAlerts === 0 && (
            <Card className="h-32 flex items-center justify-center">
              <p className="text-muted-foreground">No alerts detected</p>
            </Card>
          )}
        </TabsContent>

        {/* Interaction Tab */}
        <TabsContent value="interaction">
          <InteractionTab payload={payload} rawData={rawData} />
        </TabsContent>

        {/* Report Tab */}
        <TabsContent value="report">
          <ReportTab payload={payload} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
