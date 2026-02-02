"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const COLORS: Record<string, string> = {
  Cholera: "#3b82f6",
  Dengue: "#f59e0b",
  Malaria: "#10b981",
  Unknown: "#94a3b8",
};

const DEFAULT_COLOR = "#6b7280";

interface DiseaseDistributionProps {
  data: Array<{ name: string; value: number }>;
}

export function DiseaseDistribution({ data }: DiseaseDistributionProps) {
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Disease Distribution</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 || total === 0 ? (
          <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
            No disease data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
              >
                {data.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={COLORS[entry.name] ?? DEFAULT_COLOR}
                  />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => [value, "Cases"]}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
