"use client";

import { useState, useCallback } from "react";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReportFilters } from "@/components/reports/ReportFilters";
import { ReportTable } from "@/components/reports/ReportTable";
import { useReports, type ReportFilters as Filters } from "@/hooks/useReports";
import { apiClient } from "@/lib/api";
import type { Report } from "@/types";

const PAGE_SIZE = 20;

interface PaginatedReports {
  items: Report[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

function reportsToCsv(reports: Report[]): string {
  const headers = [
    "ID",
    "Disease",
    "Location",
    "Cases",
    "Deaths",
    "Urgency",
    "Status",
    "Alert Type",
    "Symptoms",
    "Onset Date",
    "Created At",
  ];

  const escape = (val: string | null | undefined): string => {
    if (val == null) return "";
    const s = String(val);
    if (s.includes(",") || s.includes('"') || s.includes("\n")) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };

  const rows = reports.map((r) =>
    [
      r.id,
      r.suspectedDisease,
      r.locationNormalized ?? r.locationText,
      r.casesCount,
      r.deathsCount,
      r.urgency,
      r.status,
      r.alertType,
      r.symptoms?.join("; "),
      r.onsetDate,
      r.createdAt,
    ]
      .map((v) => escape(v != null ? String(v) : null))
      .join(",")
  );

  return [headers.join(","), ...rows].join("\n");
}

function downloadCsv(csv: string, filename: string) {
  const blob = new Blob(["\uFEFF" + csv], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function ReportsPage() {
  const [filters, setFilters] = useState<Filters>({
    page: 1,
    pageSize: PAGE_SIZE,
  });
  const [exporting, setExporting] = useState(false);

  const { data, isLoading } = useReports(filters);
  const reports = data?.items ?? [];
  const total = data?.total ?? 0;
  const page = data?.page ?? 1;
  const pages = data?.pages ?? 1;

  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      // Fetch all reports matching current filters (up to 1000)
      const res = await apiClient.get<PaginatedReports>("/api/reports", {
        page: 1,
        page_size: 1000,
        status: filters.status || undefined,
        urgency: filters.urgency || undefined,
        disease: filters.disease || undefined,
        search: filters.search || undefined,
      });
      const allReports = res.items ?? [];
      if (allReports.length === 0) return;

      const csv = reportsToCsv(allReports);
      const date = new Date().toISOString().slice(0, 10);
      downloadCsv(csv, `cbi-reports-${date}.csv`);
    } catch (err) {
      console.error("Export failed:", err);
    } finally {
      setExporting(false);
    }
  }, [filters]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold">Reports</h1>
          <p className="text-muted-foreground mt-1">
            Manage health incident reports
          </p>
        </div>
        <Button variant="outline" onClick={handleExport} disabled={exporting}>
          {exporting ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Download className="h-4 w-4 mr-2" />
          )}
          {exporting ? "Exporting..." : "Export"}
        </Button>
      </div>

      <div className="space-y-4">
        <ReportFilters filters={filters} onChange={setFilters} />

        <ReportTable reports={reports} isLoading={isLoading} />

        {/* Pagination */}
        {total > 0 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Showing {from} to {to} of {total} reports
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() =>
                  setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))
                }
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pages}
                onClick={() =>
                  setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))
                }
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
