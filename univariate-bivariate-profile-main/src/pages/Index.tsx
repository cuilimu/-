import { useState, useCallback } from 'react';
import { CSVUploader } from '@/components/CSVUploader';
import { DataPreview } from '@/components/DataPreview';
import { AnalysisDashboard } from '@/components/AnalysisDashboard';
import { DashboardSelector } from '@/components/DashboardSelector';
import { BivariateAnalysisDashboard } from '@/components/BivariateAnalysisDashboard';
import { AIGuide } from '@/components/AIGuide';
import { GlobalAISettings } from '@/components/GlobalAISettings';
import { AISettingsProvider } from '@/contexts/AISettingsContext';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { buildUnivariatePayloadAsync, DatasetPayload } from '@/lib/statistics';
import { BarChart3, Play, RotateCcw, FileSpreadsheet, ArrowLeft } from 'lucide-react';
import pwcLogo from '@/assets/pwc-logo.png';

type AppState = 'upload' | 'preview' | 'analyzing' | 'dashboard-select' | 'univariate' | 'bivariate';
const Index = () => {
  const [state, setState] = useState<AppState>('upload');
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [fileName, setFileName] = useState('');
  const [payload, setPayload] = useState<DatasetPayload | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressStage, setProgressStage] = useState('');
  const handleDataLoaded = useCallback((loadedData: Record<string, unknown>[], name: string) => {
    setData(loadedData);
    setFileName(name);
    setState('preview');
  }, []);
  const handleAnalyze = useCallback(async () => {
    setState('analyzing');
    setProgress(0);
    setProgressStage('Starting analysis...');

    // Run async analysis which yields to browser for UI updates
    const analysisPayload = await buildUnivariatePayloadAsync(data, fileName, (p, stage) => {
      setProgress(p);
      setProgressStage(stage);
    });
    setProgress(100);
    setProgressStage('Complete!');
    setTimeout(() => {
      setPayload(analysisPayload);
      setState('dashboard-select');
    }, 300);
  }, [data, fileName]);

  const handleBackToDashboards = useCallback(() => {
    setState('dashboard-select');
  }, []);
  const handleReset = useCallback(() => {
    setData([]);
    setFileName('');
    setPayload(null);
    setProgress(0);
    setProgressStage('');
    setState('upload');
  }, []);
  return (
    <AISettingsProvider>
      <div className="min-h-screen bg-background">
        {/* Header */}
        <header className="border-b bg-card">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-px h-8 bg-border" />
              <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <BarChart3 className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h1 className="text-xl font-bold">
                      {state === 'univariate' ? 'Univariate Analysis' : 
                       state === 'bivariate' ? 'Bivariate Analysis' : 
                       'Analysis Profiler'}
                    </h1>
                    <p className="text-sm text-muted-foreground">Credit Risk Modeling Tool</p>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <GlobalAISettings />
                {(state === 'univariate' || state === 'bivariate') && (
                  <Button variant="outline" onClick={handleBackToDashboards} className="gap-2">
                    <ArrowLeft className="w-4 h-4" />
                    Back to Dashboards
                  </Button>
                )}
                {state !== 'upload' && (
                  <Button variant="outline" onClick={handleReset} className="gap-2">
                    <RotateCcw className="w-4 h-4" />
                    New Analysis
                  </Button>
                )}
              </div>
            </div>
          </div>
        </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {state === 'upload' && <div className="max-w-2xl mx-auto space-y-8 relative">
            {/* Background Logo */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none -z-10">
              <img src={pwcLogo} alt="" className="w-[500px] h-auto opacity-[0.08]" />
            </div>
            <div className="text-center space-y-3">
              <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto">
                <FileSpreadsheet className="w-8 h-8 text-primary" />
              </div>
              <h2 className="text-2xl font-semibold">Upload Your Dataset</h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                Upload a CSV file to generate comprehensive univariate statistical analysis 
                for credit risk modeling.
              </p>
            </div>
            <CSVUploader onDataLoaded={handleDataLoaded} />
          </div>}

        {state === 'preview' && <div className="space-y-6">
            <DataPreview data={data} fileName={fileName} />
            <div className="flex justify-center">
              <Button size="lg" onClick={handleAnalyze} className="gap-2">
                <Play className="w-5 h-5" />
                Generate Analysis
              </Button>
            </div>
          </div>}

        {state === 'analyzing' && <div className="flex flex-col items-center justify-center py-20 space-y-6 max-w-md mx-auto">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center animate-pulse">
              <BarChart3 className="w-8 h-8 text-primary" />
            </div>
            <h2 className="text-xl font-semibold">Analyzing Dataset...</h2>
            <div className="w-full space-y-2">
              <Progress value={progress} className="h-2" />
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground truncate max-w-[70%]">{progressStage}</span>
                <span className="text-primary font-medium">{progress}%</span>
              </div>
            </div>
            <p className="text-muted-foreground text-sm">
              Processing {data.length.toLocaleString()} rows × {Object.keys(data[0] || {}).length} columns
            </p>
          </div>}

        {state === 'dashboard-select' && payload && (
          <DashboardSelector 
            columnCount={Object.keys(data[0] || {}).length}
            onSelectUnivariate={() => setState('univariate')}
            onSelectBivariate={() => setState('bivariate')}
          />
        )}

        {state === 'univariate' && payload && <AnalysisDashboard payload={payload} rawData={data} />}
        
        {state === 'bivariate' && <BivariateAnalysisDashboard data={data} />}
      </main>

        {/* AI Guide - always visible */}
        <AIGuide />
      </div>
    </AISettingsProvider>
  );
};
export default Index;