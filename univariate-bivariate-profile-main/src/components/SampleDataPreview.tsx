import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface SampleDataPreviewProps {
  head: Record<string, unknown>[];
  tail: Record<string, unknown>[];
}

export function SampleDataPreview({ head, tail }: SampleDataPreviewProps) {
  const [activeTab, setActiveTab] = useState<'head' | 'tail'>('head');

  const data = activeTab === 'head' ? head : tail;
  const columns = data.length > 0 ? Object.keys(data[0]) : [];

  const formatCellValue = (value: unknown): string => {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'number') {
      if (!isFinite(value)) return '—';
      return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
    }
    return String(value);
  };

  return (
    <Card className="mt-4">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Sample Data Preview</CardTitle>
          <div className="flex gap-2">
            <Button
              variant={activeTab === 'head' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setActiveTab('head')}
            >
              First 10 Rows
            </Button>
            <Button
              variant={activeTab === 'tail' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setActiveTab('tail')}
            >
              Last 10 Rows
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[350px] w-full rounded-b-lg border-t">
          <div className="min-w-max">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12 sticky left-0 bg-muted z-10">#</TableHead>
                  {columns.map((col) => (
                    <TableHead key={col} className="whitespace-nowrap">
                      {col}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((row, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="font-medium sticky left-0 bg-background z-10">
                      {activeTab === 'head' ? idx + 1 : `...${idx + 1}`}
                    </TableCell>
                    {columns.map((col) => (
                      <TableCell key={col} className="whitespace-nowrap">
                        {formatCellValue(row[col])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
