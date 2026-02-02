"use client";

import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Report } from "@/types";
import { cn } from "@/lib/utils";

const URGENCY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-200",
  high: "bg-orange-100 text-orange-800 border-orange-200",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-slate-100 text-slate-800 border-slate-200",
};

interface RecentAlertsProps {
  reports: Report[];
}

export function RecentAlerts({ reports }: RecentAlertsProps) {
  const alerts = reports
    .filter((r) => r.urgency === "critical" || r.urgency === "high")
    .slice(0, 5);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recent Alerts</CardTitle>
      </CardHeader>
      <CardContent>
        {alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <AlertTriangle className="h-8 w-8 mb-2" />
            <p className="text-sm">No recent alerts</p>
          </div>
        ) : (
          <div className="space-y-3">
            {alerts.map((report) => (
              <Link
                key={report.id}
                href={`/reports/${report.id}`}
                className="flex items-center justify-between rounded-lg border p-3 transition-colors hover:bg-muted/50"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Badge
                    className={cn(
                      "shrink-0 capitalize",
                      URGENCY_STYLES[report.urgency]
                    )}
                  >
                    {report.urgency}
                  </Badge>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {report.suspectedDisease
                        ? report.suspectedDisease.charAt(0).toUpperCase() +
                          report.suspectedDisease.slice(1)
                        : "Unknown"}
                      {report.locationNormalized &&
                        ` — ${report.locationNormalized}`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {report.casesCount
                        ? `${report.casesCount} case${report.casesCount > 1 ? "s" : ""}`
                        : "Cases unknown"}
                    </p>
                  </div>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground ml-2">
                  {formatDistanceToNow(new Date(report.createdAt), {
                    addSuffix: true,
                  })}
                </span>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
