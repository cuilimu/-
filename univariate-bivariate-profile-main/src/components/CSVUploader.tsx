import { useCallback, useState } from 'react';
import Papa from 'papaparse';
import { Upload, FileSpreadsheet, X, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface CSVUploaderProps {
  onDataLoaded: (data: Record<string, unknown>[], fileName: string) => void;
  isLoading?: boolean;
}

export function CSVUploader({ onDataLoaded, isLoading }: CSVUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [parseProgress, setParseProgress] = useState(0);

  const processFile = useCallback((file: File) => {
    setError(null);
    setIsParsing(true);
    setParseProgress(0);
    
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a CSV file');
      setIsParsing(false);
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      setError('File size must be less than 100MB');
      setIsParsing(false);
      return;
    }

    setFileName(file.name);

    // Use streaming with chunk callback to track progress
    const allData: Record<string, unknown>[] = [];
    let bytesRead = 0;
    const fileSize = file.size;

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      dynamicTyping: true,
      chunk: (results, parser) => {
        // Accumulate parsed data
        allData.push(...(results.data as Record<string, unknown>[]));
        
        // Calculate progress based on bytes processed
        bytesRead += results.meta.cursor - bytesRead;
        const progress = Math.min(Math.round((bytesRead / fileSize) * 100), 99);
        setParseProgress(progress);
      },
      complete: () => {
        setParseProgress(100);
        
        if (allData.length === 0) {
          setError('No data found in the CSV file');
          setIsParsing(false);
          return;
        }

        // Small delay to show 100% before transitioning
        setTimeout(() => {
          setIsParsing(false);
          onDataLoaded(allData, file.name);
        }, 200);
      },
      error: (err) => {
        setError(`Failed to parse CSV: ${err.message}`);
        setIsParsing(false);
      }
    });
  }, [onDataLoaded]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      processFile(file);
    }
  }, [processFile]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file);
    }
  }, [processFile]);

  const clearFile = useCallback(() => {
    setFileName(null);
    setError(null);
    setIsParsing(false);
    setParseProgress(0);
  }, []);

  return (
    <Card className="w-full">
      <CardContent className="p-6">
        <div
          className={cn(
            "relative border-2 border-dashed rounded-lg p-8 transition-all duration-200",
            isDragging 
              ? "border-primary bg-primary/5" 
              : "border-muted-foreground/25 hover:border-primary/50",
            (isLoading || isParsing) && "pointer-events-none"
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            type="file"
            accept=".csv"
            onChange={handleFileSelect}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            disabled={isLoading}
          />

          <div className="flex flex-col items-center gap-4 text-center">
            {isParsing ? (
              <>
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <Loader2 className="w-8 h-8 text-primary animate-spin" />
                </div>
                <div className="w-full max-w-xs space-y-2">
                  <p className="text-lg font-medium">Processing {fileName}...</p>
                  <Progress value={parseProgress} className="h-2" />
                  <p className="text-sm text-muted-foreground">{parseProgress}% complete</p>
                </div>
              </>
            ) : fileName ? (
              <>
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <FileSpreadsheet className="w-8 h-8 text-primary" />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-medium">{fileName}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={(e) => {
                      e.preventDefault();
                      clearFile();
                    }}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
                  <Upload className="w-8 h-8 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-lg font-medium">
                    Drag and drop your CSV file here
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    or click to browse (max 100MB)
                  </p>
                </div>
              </>
            )}
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 mt-4 p-3 bg-destructive/10 text-destructive rounded-lg">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm">{error}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
