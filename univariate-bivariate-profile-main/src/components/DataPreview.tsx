import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

interface DataPreviewProps {
  data: Record<string, unknown>[];
  fileName: string;
}

export function DataPreview({ data, fileName }: DataPreviewProps) {
  if (data.length === 0) return null;

  const columns = Object.keys(data[0]);
  const previewRows = data.slice(0, 10);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Data Preview</CardTitle>
          <div className="flex gap-2">
            <Badge variant="secondary">{data.length} rows</Badge>
            <Badge variant="secondary">{columns.length} columns</Badge>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">{fileName}</p>
      </CardHeader>
      <CardContent>
        <ScrollArea className="w-full whitespace-nowrap rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((col) => (
                  <TableHead key={col} className="font-semibold">
                    {col}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {previewRows.map((row, idx) => (
                <TableRow key={idx}>
                  {columns.map((col) => (
                    <TableCell key={col} className="max-w-[200px] truncate">
                      {row[col] !== null && row[col] !== undefined
                        ? String(row[col])
                        : <span className="text-muted-foreground italic">null</span>
                      }
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
        {data.length > 10 && (
          <p className="text-sm text-muted-foreground mt-2 text-center">
            Showing first 10 of {data.length} rows
          </p>
        )}
      </CardContent>
    </Card>
  );
}
