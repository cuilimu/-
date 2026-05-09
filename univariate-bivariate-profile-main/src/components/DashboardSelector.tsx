import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { BarChart3, GitCompare } from 'lucide-react';

interface DashboardSelectorProps {
  columnCount: number;
  onSelectUnivariate: () => void;
  onSelectBivariate: () => void;
}

export const DashboardSelector = ({ 
  columnCount, 
  onSelectUnivariate, 
  onSelectBivariate 
}: DashboardSelectorProps) => {
  return (
    <div className="flex flex-col items-center justify-center py-12 space-y-8">
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-semibold">Select Analysis Type</h2>
        <p className="text-muted-foreground">
          Choose which type of statistical analysis you'd like to explore
        </p>
      </div>
      
      <div className="flex flex-col md:flex-row gap-6">
        {/* Univariate Analysis Card */}
        <Card 
          className="w-[320px] cursor-pointer transition-all hover:shadow-lg hover:border-primary/50 hover:-translate-y-1"
          onClick={onSelectUnivariate}
        >
          <CardHeader className="text-center pb-4">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <BarChart3 className="w-8 h-8 text-primary" />
            </div>
            <CardTitle className="text-xl">Univariate Analysis</CardTitle>
            <CardDescription>
              Analyze individual variables independently to understand their distributions and characteristics
            </CardDescription>
          </CardHeader>
        </Card>

        {/* Bivariate Analysis Card */}
        <Card 
          className="w-[320px] cursor-pointer transition-all hover:shadow-lg hover:border-primary/50 hover:-translate-y-1"
          onClick={onSelectBivariate}
        >
          <CardHeader className="text-center pb-4">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <GitCompare className="w-8 h-8 text-primary" />
            </div>
            <CardTitle className="text-xl">Bivariate Analysis</CardTitle>
            <CardDescription>
              Explore relationships between pairs of variables through correlation and cross-tabulation
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
};
