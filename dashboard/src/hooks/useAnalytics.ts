"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { AnalyticsSummary, Report } from "@/types";

interface ReportsStatsResponse {
  total: number;
  open: number;
  critical: number;
  resolved: number;
  affectedRegions: number;
  byDisease: Record<string, number>;
  byUrgency: Record<string, number>;
}

function mapStatsToSummary(stats: ReportsStatsResponse): AnalyticsSummary {
  const diseaseData = Object.entries(stats.byDisease).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
  }));

  return {
    criticalAlerts: stats.critical,
    criticalTrend: 0,
    activeCases: stats.open,
    casesTrend: 0,
    affectedRegions: stats.affectedRegions ?? 0,
    reportsToday: stats.total,
    trendData: [],
    diseaseData,
  };
}

export function useAnalytics() {
  return useQuery<AnalyticsSummary>({
    queryKey: ["analytics", "summary"],
    queryFn: async () => {
      const stats = await apiClient.get<ReportsStatsResponse>(
        "/api/reports/stats"
      );
      return mapStatsToSummary(stats);
    },
    staleTime: 60000,
  });
}

export function useRecentReports() {
  return useQuery<Report[]>({
    queryKey: ["reports", "recent"],
    queryFn: async () => {
      const res = await apiClient.get<{ items: Report[] }>(
        "/api/reports",
        { page: 1, page_size: 10 }
      );
      return res.items ?? [];
    },
    staleTime: 60000,
  });
}
