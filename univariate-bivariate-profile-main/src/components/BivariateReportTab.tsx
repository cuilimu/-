import { useState, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { FileText, Download, Loader2, Sparkles, AlertCircle } from 'lucide-react';
import { useAISettings } from '@/contexts/AISettingsContext';
import { getModelString } from '@/lib/aiModels';
import jsPDF from 'jspdf';

interface BivariateReportTabProps {
  varX: string;
  varY: string;
  statistics: any;
}

export function BivariateReportTab({ varX, varY, statistics }: BivariateReportTabProps) {
  const [report, setReport] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { globalModel } = useAISettings();
  const selectedModel = getModelString(globalModel);

  const generateReport = useCallback(async () => {
    if (!varX || !varY || !statistics) return;
    
    setIsGenerating(true);
    setError(null);
    setReport('');

    try {
      const FUNCTION_URL = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/generate-bivariate-report`;
      
      const response = await fetch(FUNCTION_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
          'apikey': import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
        },
        body: JSON.stringify({
          payload: {
            varX,
            varY,
            statistics: {
              n: statistics.n,
              uniqueX: statistics.uniqueX,
              uniqueY: statistics.uniqueY,
              xIsNumeric: statistics.xIsNumeric,
              yIsNumeric: statistics.yIsNumeric,
              correlations: statistics.correlations,
              sampleCorrelations: statistics.sampleCorrelations,
              chiSquare: statistics.chiSquare,
              conditionalStats: statistics.conditionalStats?.slice(0, 20),
              // Send summarized crosstab to avoid stack overflow with large arrays
              crosstabSummary: statistics.crosstab ? (() => {
                const { xCategories, yCategories, marginalX, marginalY, total } = statistics.crosstab;
                // Find max marginals safely (avoid spread on large arrays)
                let maxXIdx = 0, maxYIdx = 0;
                for (let i = 1; i < marginalX.length; i++) {
                  if (marginalX[i] > marginalX[maxXIdx]) maxXIdx = i;
                }
                for (let i = 1; i < marginalY.length; i++) {
                  if (marginalY[i] > marginalY[maxYIdx]) maxYIdx = i;
                }
                return {
                  xCategoryCount: xCategories.length,
                  yCategoryCount: yCategories.length,
                  topXCategories: xCategories.slice(0, 10),
                  topYCategories: yCategories.slice(0, 10),
                  topXCategory: xCategories[maxXIdx],
                  topXCount: marginalX[maxXIdx],
                  topYCategory: yCategories[maxYIdx],
                  topYCount: marginalY[maxYIdx],
                  total,
                };
              })() : null,
            },
          },
          model: selectedModel,
        }),
      });

      if (!response.ok) {
        if (response.status === 429) {
          throw new Error('Rate limit exceeded. Please try again in a moment.');
        }
        if (response.status === 402) {
          throw new Error('AI usage limit reached. Please add credits to continue.');
        }
        throw new Error('Failed to generate report');
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      // Handle streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullContent = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // Process line by line
        let newlineIndex: number;
        while ((newlineIndex = buffer.indexOf('\n')) !== -1) {
          let line = buffer.slice(0, newlineIndex);
          buffer = buffer.slice(newlineIndex + 1);
          
          if (line.endsWith('\r')) line = line.slice(0, -1);
          if (line.startsWith(':') || line.trim() === '') continue;
          if (!line.startsWith('data: ')) continue;
          
          const jsonStr = line.slice(6).trim();
          if (jsonStr === '[DONE]') continue;
          
          try {
            const parsed = JSON.parse(jsonStr);
            const content = parsed.choices?.[0]?.delta?.content || '';
            if (content) {
              fullContent += content;
              setReport(fullContent);
            }
          } catch {
            // Incomplete JSON, put back in buffer
            buffer = line + '\n' + buffer;
            break;
          }
        }
      }

      // Final flush
      if (buffer.trim()) {
        for (let raw of buffer.split('\n')) {
          if (!raw) continue;
          if (raw.endsWith('\r')) raw = raw.slice(0, -1);
          if (raw.startsWith(':') || raw.trim() === '') continue;
          if (!raw.startsWith('data: ')) continue;
          const jsonStr = raw.slice(6).trim();
          if (jsonStr === '[DONE]') continue;
          try {
            const parsed = JSON.parse(jsonStr);
            const content = parsed.choices?.[0]?.delta?.content || '';
            if (content) {
              fullContent += content;
              setReport(fullContent);
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsGenerating(false);
    }
  }, [varX, varY, statistics, selectedModel]);

  const downloadPDF = useCallback(() => {
    if (!report) return;

    const pdf = new jsPDF();
    const pageWidth = pdf.internal.pageSize.getWidth();
    const margin = 20;
    const maxWidth = pageWidth - 2 * margin;
    
    // Title
    pdf.setFontSize(18);
    pdf.setFont('helvetica', 'bold');
    pdf.text('Bivariate Analysis Report', margin, 25);
    
    // Subtitle
    pdf.setFontSize(12);
    pdf.setFont('helvetica', 'normal');
    pdf.setTextColor(100);
    pdf.text(`${varX} vs ${varY}`, margin, 35);
    pdf.text(`Generated: ${new Date().toLocaleDateString()}`, margin, 42);
    
    pdf.setTextColor(0);
    
    // Content
    let yPos = 55;
    const lineHeight = 6;
    const lines = report.split('\n');
    
    for (const line of lines) {
      // Handle H1 headers
      if (line.startsWith('# ') && !line.startsWith('## ')) {
        if (yPos > 260) {
          pdf.addPage();
          yPos = 20;
        }
        yPos += 10;
        pdf.setFontSize(16);
        pdf.setFont('helvetica', 'bold');
        pdf.text(line.replace('# ', ''), margin, yPos);
        yPos += lineHeight + 4;
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        continue;
      }
      
      // Handle H2 headers
      if (line.startsWith('## ')) {
        if (yPos > 260) {
          pdf.addPage();
          yPos = 20;
        }
        yPos += 8;
        pdf.setFontSize(14);
        pdf.setFont('helvetica', 'bold');
        pdf.text(line.replace('## ', ''), margin, yPos);
        yPos += lineHeight + 2;
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        continue;
      }

      // Handle H3 headers
      if (line.startsWith('### ')) {
        if (yPos > 260) {
          pdf.addPage();
          yPos = 20;
        }
        yPos += 6;
        pdf.setFontSize(12);
        pdf.setFont('helvetica', 'bold');
        pdf.text(line.replace('### ', ''), margin, yPos);
        yPos += lineHeight + 1;
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        continue;
      }
      
      if (line.trim() === '') {
        yPos += lineHeight / 2;
        continue;
      }
      
      // Wrap text
      const cleanLine = line.replace(/\*\*/g, '').replace(/\*/g, '').replace(/`/g, '');
      const wrapped = pdf.splitTextToSize(cleanLine, maxWidth);
      
      for (const wrappedLine of wrapped) {
        if (yPos > 280) {
          pdf.addPage();
          yPos = 20;
        }
        pdf.text(wrappedLine, margin, yPos);
        yPos += lineHeight;
      }
    }
    
    pdf.save(`bivariate-report-${varX}-${varY}.pdf`);
  }, [report, varX, varY]);

  if (!varX || !varY) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <FileText className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
          <p className="text-muted-foreground">
            Select two variables to generate a bivariate analysis report.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <CardTitle className="text-lg flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-primary" />
                AI-Generated Bivariate Report
              </CardTitle>
              <CardDescription>
                Analyzing relationship between <strong>{varX}</strong> and <strong>{varY}</strong>
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                {selectedModel}
              </Badge>
              {!report ? (
                <Button 
                  onClick={generateReport} 
                  disabled={isGenerating}
                  className="gap-2"
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      Generate Report
                    </>
                  )}
                </Button>
              ) : (
                <>
                  <Button 
                    variant="outline" 
                    onClick={generateReport} 
                    disabled={isGenerating}
                    size="sm"
                  >
                    Regenerate
                  </Button>
                  <Button onClick={downloadPDF} className="gap-2" size="sm">
                    <Download className="w-4 h-4" />
                    Download PDF
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="flex items-center gap-2 p-4 mb-4 rounded-lg bg-destructive/10 text-destructive">
              <AlertCircle className="w-5 h-5" />
              <p className="text-sm">{error}</p>
            </div>
          )}
          
          {!report && !isGenerating && !error && (
            <div className="py-12 text-center">
              <FileText className="w-16 h-16 mx-auto mb-4 text-muted-foreground/50" />
              <p className="text-muted-foreground mb-2">
                Click "Generate Report" to create an AI-powered analysis
              </p>
              <p className="text-sm text-muted-foreground">
                The report will include relationship analysis, key findings, and recommendations.
              </p>
            </div>
          )}
          
          {(report || isGenerating) && (
            <ScrollArea className="h-[500px] pr-4">
              <div className="prose prose-sm dark:prose-invert max-w-none">
                {report.split('\n').map((line, idx) => {
                  if (line.startsWith('# ') && !line.startsWith('## ')) {
                    return (
                      <h1 key={idx} className="text-xl font-bold mt-6 mb-4 text-foreground">
                        {line.replace('# ', '')}
                      </h1>
                    );
                  }
                  if (line.startsWith('## ')) {
                    return (
                      <h2 key={idx} className="text-lg font-semibold mt-6 mb-3 text-foreground">
                        {line.replace('## ', '')}
                      </h2>
                    );
                  }
                  if (line.startsWith('### ')) {
                    return (
                      <h3 key={idx} className="text-base font-semibold mt-4 mb-2 text-foreground">
                        {line.replace('### ', '')}
                      </h3>
                    );
                  }
                  if (line.startsWith('* ') || line.startsWith('- ')) {
                    return (
                      <li key={idx} className="ml-4 text-sm text-foreground/90">
                        {line.replace(/^[*-] /, '').replace(/\*\*/g, '')}
                      </li>
                    );
                  }
                  if (line.trim() === '') {
                    return <br key={idx} />;
                  }
                  return (
                    <p key={idx} className="text-sm text-foreground/90 leading-relaxed">
                      {line.replace(/\*\*/g, '')}
                    </p>
                  );
                })}
                {isGenerating && (
                  <span className="inline-block w-2 h-4 bg-primary animate-pulse ml-1" />
                )}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
