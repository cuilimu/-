import { useState, useCallback, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { 
  GitCompare, 
  BarChart3,
  ScatterChart,
  FileText,
  Loader2,
  MousePointerClick,
} from 'lucide-react';
import { BivariateProfileTab } from './BivariateProfileTab';
import { BivariateReportTab } from './BivariateReportTab';
import { BivariateInteractionTab } from './BivariateInteractionTab';
import { generateBivariateHTML } from '@/lib/bivariateHtmlReport';
import { useBivariateAnalysis } from '@/hooks/useBivariateAnalysis';

interface BivariateAnalysisDashboardProps {
  data: Record<string, unknown>[];
}

export const BivariateAnalysisDashboard = ({ data }: BivariateAnalysisDashboardProps) => {
  const [varX, setVarX] = useState<string>('');
  const [varY, setVarY] = useState<string>('');

  // Get column names
  const columns = useMemo(() => {
    if (!data || data.length === 0) return [];
    return Object.keys(data[0]).filter(col => col && col.trim() !== '');
  }, [data]);

  // Use the async analysis hook with Y-caching
  const { 
    statistics, 
    isLoading, 
    progress, 
    progressStage, 
    progressSubStage,
    progressSubPercent,
    error, 
    columnTypes 
  } = useBivariateAnalysis(data, varX, varY, columns);

  // Export HTML
  const handleExportHTML = useCallback(() => {
    if (!statistics) return;
    const html = generateBivariateHTML(varX, varY, statistics, columnTypes);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bivariate-analysis-${varX}-${varY}.html`;
    a.click();
    URL.revokeObjectURL(url);
  }, [statistics, varX, varY, columnTypes]);

  if (!data || data.length === 0) {
    return (
      <Card className="max-w-2xl mx-auto">
        <CardHeader className="text-center">
          <div className="w-20 h-20 rounded-full bg-muted/50 flex items-center justify-center mx-auto mb-4">
            <GitCompare className="w-10 h-10 text-muted-foreground" />
          </div>
          <CardTitle className="text-2xl">Bivariate Analysis</CardTitle>
          <CardDescription className="text-base">
            No data available. Please upload a dataset first.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Variable Selection Header */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-6">
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-bold mb-1">Bivariate Analysis</h1>
              <p className="text-sm text-muted-foreground">
                Select two variables to analyze their relationship.
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Y variable (target)</Label>
              <Select value={varY} onValueChange={setVarY}>
                <SelectTrigger className="w-[260px]">
                  <SelectValue placeholder="Select Y variable first" />
                </SelectTrigger>
                <SelectContent>
                  {columns.map(col => (
                    <SelectItem key={col} value={col}>
                      <span className="flex items-center gap-2">
                        {col}
                        <Badge variant="outline" className="text-xs ml-auto">
                          {columnTypes[col]}
                        </Badge>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">X variable (predictor)</Label>
              <Select value={varX} onValueChange={setVarX} disabled={!varY}>
                <SelectTrigger className="w-[260px]">
                  <SelectValue placeholder={varY ? "Select X variable" : "Select Y first"} />
                </SelectTrigger>
                <SelectContent>
                  {columns.filter(col => col !== varY).map(col => (
                    <SelectItem key={col} value={col}>
                      <span className="flex items-center gap-2">
                        {col}
                        <Badge variant="outline" className="text-xs ml-auto">
                          {columnTypes[col]}
                        </Badge>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading State */}
      {isLoading && (
        <Card>
          <CardContent className="py-8">
            <div className="max-w-md mx-auto space-y-4">
              <div className="flex items-center justify-center gap-3">
                <Loader2 className="w-5 h-5 animate-spin text-primary" />
                <span className="text-sm font-medium">{progressStage}</span>
              </div>
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-center text-muted-foreground">
                {progress}% complete
              </p>
              {progressSubStage && (
                <div className="mt-3 space-y-2 px-4">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{progressSubStage}</span>
                    <span className="font-mono">{progressSubPercent}%</span>
                  </div>
                  <Progress value={progressSubPercent} className="h-1.5" />
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <Card>
          <CardContent className="py-8">
            <div className="text-center text-destructive">
              <p className="font-medium">Analysis Error</p>
              <p className="text-sm text-muted-foreground mt-1">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Analysis Results */}
      {statistics && !isLoading && (
        <Tabs defaultValue="profile" className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="profile" className="gap-2">
              <BarChart3 className="w-4 h-4" />
              Bivariate Analysis Profile
            </TabsTrigger>
            <TabsTrigger value="interaction" className="gap-2">
              <MousePointerClick className="w-4 h-4" />
              Interaction
            </TabsTrigger>
            <TabsTrigger value="report" className="gap-2">
              <FileText className="w-4 h-4" />
              Report
            </TabsTrigger>
          </TabsList>

          <TabsContent value="profile" className="space-y-4 mt-4">
            <BivariateProfileTab
              varX={varX}
              varY={varY}
              statistics={statistics}
              data={data}
              onExportHTML={handleExportHTML}
            />
          </TabsContent>

          <TabsContent value="interaction" className="mt-4">
            <BivariateInteractionTab
              data={data}
              varX={varX}
              varY={varY}
              xIsNumeric={statistics.xIsNumeric}
              yIsNumeric={statistics.yIsNumeric}
            />
          </TabsContent>

          <TabsContent value="report" className="mt-4">
            <BivariateReportTab 
              varX={varX}
              varY={varY}
              statistics={statistics}
            />
          </TabsContent>
        </Tabs>
      )}

      {/* Initial State */}
      {(!varX || !varY) && !isLoading && (
        <Card>
          <CardContent className="py-12">
            <div className="text-center max-w-md mx-auto">
              <div className="w-16 h-16 rounded-full bg-muted/50 flex items-center justify-center mx-auto mb-4">
                <GitCompare className="w-8 h-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold mb-2">
                {!varY ? 'Select Y Variable First' : 'Select X Variable'}
              </h3>
              <p className="text-sm text-muted-foreground">
                {!varY 
                  ? 'Choose a target variable (Y) to analyze against multiple predictors (X).' 
                  : 'Now choose an X variable to see its relationship with the selected Y.'}
              </p>
              <div className="mt-4 flex items-center justify-center gap-2 text-xs text-muted-foreground">
                <ScatterChart className="w-4 h-4" />
                <span>Tip: Y is cached for faster X switching</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
