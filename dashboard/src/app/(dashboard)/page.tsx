"use client";

import {
  AlertTriangle,
  Activity,
  MapPin,
  FileText,
} from "lucide-react";
import { StatsCard } from "@/components/dashboard/StatsCard";
import { CasesTrend } from "@/components/charts/CasesTrend";
import { DiseaseDistribution } from "@/components/charts/DiseaseDistribution";
import { RecentAlerts } from "@/components/dashboard/RecentAlerts";
import { useAnalytics, useRecentReports } from "@/hooks/useAnalytics";
import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardPage() {
  const { data: analytics, isLoading: analyticsLoading } = useAnalytics();
  const { data: reports, isLoading: reportsLoading } = useRecentReports();

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Health surveillance overview for your regions
        </p>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
        {analyticsLoading ? (
          <>
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </>
        ) : (
          <>
            <StatsCard
              title="Critical Alerts"
              value={analytics?.criticalAlerts ?? 0}
              icon={AlertTriangle}
              iconColor="text-red-600"
              iconBg="bg-red-100"
              trend={analytics?.criticalTrend}
            />
            <StatsCard
              title="Active Cases"
              value={analytics?.activeCases ?? 0}
              icon={Activity}
              iconColor="text-amber-600"
              iconBg="bg-amber-100"
              trend={analytics?.casesTrend}
            />
            <StatsCard
              title="Affected Regions"
              value={analytics?.affectedRegions ?? 0}
              icon={MapPin}
              iconColor="text-blue-600"
              iconBg="bg-blue-100"
            />
            <StatsCard
              title="Reports Today"
              value={analytics?.reportsToday ?? 0}
              icon={FileText}
              iconColor="text-green-600"
              iconBg="bg-green-100"
            />
          </>
        )}
      </div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2 mb-6">
        {analyticsLoading ? (
          <>
            <Skeleton className="h-80" />
            <Skeleton className="h-80" />
          </>
        ) : (
          <>
            <CasesTrend data={analytics?.trendData ?? []} />
            <DiseaseDistribution data={analytics?.diseaseData ?? []} />
          </>
        )}
      </div>

      {/* Recent alerts */}
      {reportsLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <RecentAlerts reports={reports ?? []} />
      )}
    </div>
  );
}
