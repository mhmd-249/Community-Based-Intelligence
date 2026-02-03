"use client";

import { useRouter } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Report } from "@/types";
import { cn } from "@/lib/utils";

const URGENCY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-200",
  high: "bg-amber-100 text-amber-800 border-amber-200",
  medium: "bg-blue-100 text-blue-800 border-blue-200",
  low: "bg-slate-100 text-slate-800 border-slate-200",
};

const STATUS_STYLES: Record<string, string> = {
  open: "bg-green-100 text-green-800 border-green-200",
  investigating: "bg-purple-100 text-purple-800 border-purple-200",
  resolved: "bg-slate-100 text-slate-800 border-slate-200",
  false_alarm: "bg-gray-100 text-gray-500 border-gray-200",
};

interface ReportTableProps {
  reports: Report[];
  isLoading?: boolean;
}

export function ReportTable({ reports, isLoading }: ReportTableProps) {
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border py-12 text-sm text-muted-foreground">
        No reports found
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-white overflow-x-auto">
      <Table className="min-w-[700px]">
        <TableHeader>
          <TableRow>
            <TableHead>Disease</TableHead>
            <TableHead>Location</TableHead>
            <TableHead className="text-center">Cases</TableHead>
            <TableHead>Urgency</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Reported</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reports.map((report) => (
            <TableRow
              key={report.id}
              className="cursor-pointer"
              onClick={() => router.push(`/reports/${report.id}`)}
            >
              <TableCell className="font-medium capitalize">
                {report.suspectedDisease ?? "Unknown"}
              </TableCell>
              <TableCell>
                {report.locationNormalized ?? report.locationText ?? "—"}
              </TableCell>
              <TableCell className="text-center">
                {report.casesCount ?? "—"}
              </TableCell>
              <TableCell>
                <Badge
                  className={cn(
                    "capitalize",
                    URGENCY_STYLES[report.urgency]
                  )}
                >
                  {report.urgency}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge
                  className={cn(
                    "capitalize",
                    STATUS_STYLES[report.status]
                  )}
                >
                  {report.status.replace("_", " ")}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {formatDistanceToNow(new Date(report.createdAt), {
                  addSuffix: true,
                })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
