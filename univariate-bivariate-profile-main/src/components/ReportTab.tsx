import { useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { FileText, Loader2, RefreshCw, Download } from 'lucide-react';
import jsPDF from 'jspdf';
import { DatasetPayload } from '@/lib/statistics';
import { useToast } from '@/hooks/use-toast';
import { getModelString } from '@/lib/aiModels';
import { useAISettings } from '@/contexts/AISettingsContext';

interface ReportTabProps {
  payload: DatasetPayload;
}

export function ReportTab({ payload }: ReportTabProps) {
  const [report, setReport] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState(false);
  const { toast } = useToast();
  const { globalModel } = useAISettings();

  const generateReport = useCallback(async () => {
    setIsGenerating(true);
    setReport('');

    try {
      const response = await fetch(
        `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/generate-report`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
          },
          body: JSON.stringify({ 
            payload,
            model: getModelString(globalModel),
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to generate report');
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let textBuffer = '';
      let reportContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        textBuffer += decoder.decode(value, { stream: true });

        let newlineIndex: number;
        while ((newlineIndex = textBuffer.indexOf('\n')) !== -1) {
          let line = textBuffer.slice(0, newlineIndex);
          textBuffer = textBuffer.slice(newlineIndex + 1);

          if (line.endsWith('\r')) line = line.slice(0, -1);
          if (line.startsWith(':') || line.trim() === '') continue;
          if (!line.startsWith('data: ')) continue;

          const jsonStr = line.slice(6).trim();
          if (jsonStr === '[DONE]') break;

          try {
            const parsed = JSON.parse(jsonStr);
            const content = parsed.choices?.[0]?.delta?.content;
            if (content) {
              reportContent += content;
              setReport(reportContent);
            }
          } catch {
            textBuffer = line + '\n' + textBuffer;
            break;
          }
        }
      }
    } catch (error) {
      console.error('Report generation error:', error);
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to generate report',
        variant: 'destructive',
      });
    } finally {
      setIsGenerating(false);
    }
  }, [payload, toast, globalModel]);

  const handleExport = () => {
    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 20;
    const maxWidth = pageWidth - margin * 2;
    let yPosition = 20;
    const lineHeight = 7;
    const headerHeight = 10;

    const lines = report.split('\n');

    lines.forEach((line) => {
      // Check if we need a new page
      if (yPosition > doc.internal.pageSize.getHeight() - 20) {
        doc.addPage();
        yPosition = 20;
      }

      if (line.startsWith('## ')) {
        // H2 Header
        doc.setFontSize(16);
        doc.setFont('helvetica', 'bold');
        yPosition += 5;
        doc.text(line.slice(3), margin, yPosition);
        yPosition += headerHeight;
        doc.setFontSize(11);
        doc.setFont('helvetica', 'normal');
      } else if (line.startsWith('### ')) {
        // H3 Header
        doc.setFontSize(13);
        doc.setFont('helvetica', 'bold');
        yPosition += 3;
        doc.text(line.slice(4), margin, yPosition);
        yPosition += lineHeight + 2;
        doc.setFontSize(11);
        doc.setFont('helvetica', 'normal');
      } else if (line.startsWith('- ')) {
        // Bullet point
        const bulletText = `• ${line.slice(2)}`;
        const splitText = doc.splitTextToSize(bulletText, maxWidth - 5);
        splitText.forEach((textLine: string) => {
          if (yPosition > doc.internal.pageSize.getHeight() - 20) {
            doc.addPage();
            yPosition = 20;
          }
          doc.text(textLine, margin + 5, yPosition);
          yPosition += lineHeight;
        });
      } else if (line.trim() === '') {
        // Empty line
        yPosition += 3;
      } else {
        // Regular paragraph - handle bold text
        const cleanLine = line.replace(/\*\*/g, '');
        const splitText = doc.splitTextToSize(cleanLine, maxWidth);
        splitText.forEach((textLine: string) => {
          if (yPosition > doc.internal.pageSize.getHeight() - 20) {
            doc.addPage();
            yPosition = 20;
          }
          doc.text(textLine, margin, yPosition);
          yPosition += lineHeight;
        });
      }
    });

    doc.save(`analysis_report_${payload.meta.source_file.replace('.csv', '')}_${new Date().toISOString().split('T')[0]}.pdf`);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">AI-Generated Analysis Report</h3>
          <p className="text-sm text-muted-foreground">
            Generate a comprehensive written analysis of your dataset using AI
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {report && (
            <Button variant="outline" onClick={handleExport} className="gap-2">
              <Download className="w-4 h-4" />
              Export PDF
            </Button>
          )}
          <Button onClick={generateReport} disabled={isGenerating} className="gap-2">
            {isGenerating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating...
              </>
            ) : report ? (
              <>
                <RefreshCw className="w-4 h-4" />
                Regenerate
              </>
            ) : (
              <>
                <FileText className="w-4 h-4" />
                Generate Report
              </>
            )}
          </Button>
        </div>
      </div>

      {!report && !isGenerating && (
        <Card className="h-64 flex items-center justify-center">
          <div className="text-center space-y-2">
            <FileText className="w-12 h-12 mx-auto text-muted-foreground/50" />
            <p className="text-muted-foreground">
              Click "Generate Report" to create an AI-powered analysis
            </p>
          </div>
        </Card>
      )}

      {(report || isGenerating) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Analysis Report
              {isGenerating && <Loader2 className="w-4 h-4 animate-spin" />}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[calc(100vh-400px)] pr-4">
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <MarkdownContent content={report} />
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  // Simple markdown rendering
  const lines = content.split('\n');
  
  return (
    <div className="space-y-2">
      {lines.map((line, idx) => {
        if (line.startsWith('## ')) {
          return <h2 key={idx} className="text-xl font-bold mt-6 mb-2 text-foreground">{line.slice(3)}</h2>;
        }
        if (line.startsWith('### ')) {
          return <h3 key={idx} className="text-lg font-semibold mt-4 mb-2 text-foreground">{line.slice(4)}</h3>;
        }
        if (line.startsWith('- ')) {
          return <li key={idx} className="ml-4 text-muted-foreground">{line.slice(2)}</li>;
        }
        if (line.startsWith('**') && line.endsWith('**')) {
          return <p key={idx} className="font-semibold text-foreground">{line.slice(2, -2)}</p>;
        }
        if (line.trim() === '') {
          return <div key={idx} className="h-2" />;
        }
        // Handle inline bold
        const formattedLine = line.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
          if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={i}>{part.slice(2, -2)}</strong>;
          }
          return part;
        });
        return <p key={idx} className="text-muted-foreground leading-relaxed">{formattedLine}</p>;
      })}
    </div>
  );
}
