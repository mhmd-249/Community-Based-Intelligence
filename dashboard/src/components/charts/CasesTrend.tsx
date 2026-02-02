"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DISEASE_COLORS = {
  cholera: "#3b82f6",
  dengue: "#f59e0b",
  malaria: "#10b981",
};

interface CasesTrendProps {
  data: Array<{
    date: string;
    cholera: number;
    dengue: number;
    malaria: number;
  }>;
}

export function CasesTrend({ data }: CasesTrendProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cases Trend (7 days)</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
            No trend data available
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
              />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="cholera"
                name="Cholera"
                stroke={DISEASE_COLORS.cholera}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
              <Line
                type="monotone"
                dataKey="dengue"
                name="Dengue"
                stroke={DISEASE_COLORS.dengue}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
              <Line
                type="monotone"
                dataKey="malaria"
                name="Malaria"
                stroke={DISEASE_COLORS.malaria}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
