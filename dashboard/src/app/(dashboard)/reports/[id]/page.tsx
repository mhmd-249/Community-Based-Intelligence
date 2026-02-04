"use client";

import { useState, use } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ConversationView } from "@/components/reports/ConversationView";
import { useReport, useUpdateReport } from "@/hooks/useReports";
import { cn } from "@/lib/utils";
import type { ReportStatus } from "@/types";

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

export default function ReportDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: report, isLoading } = useReport(id);
  const updateReport = useUpdateReport();
  const [notes, setNotes] = useState("");

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        Report not found
      </div>
    );
  }

  function handleStatusChange(status: string) {
    updateReport.mutate({ id, data: { status: status as ReportStatus } });
  }

  // Normalize conversation messages from the backend
  const messages =
    report.rawConversation && Array.isArray(report.rawConversation)
      ? (report.rawConversation as Array<{ role: "user" | "assistant"; content: string; timestamp: string }>)
      : report.rawConversation?.messages ?? [];

  return (
    <div>
      {/* Back + header */}
      <div className="mb-6">
        <Link
          href="/reports"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to reports
        </Link>

        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold capitalize">
            {report.suspectedDisease ?? "Unknown Disease"}
          </h1>
          <Badge className={cn("capitalize", URGENCY_STYLES[report.urgency])}>
            {report.urgency}
          </Badge>
          <Badge className={cn("capitalize", STATUS_STYLES[report.status])}>
            {report.status.replace("_", " ")}
          </Badge>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left column */}
        <div className="space-y-6">
          {/* Case information */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Case Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Row label="Symptoms">
                {report.symptoms?.length > 0
                  ? report.symptoms.join(", ")
                  : "—"}
              </Row>
              <Row label="Cases">{report.casesCount ?? "—"}</Row>
              <Row label="Deaths">{report.deathsCount ?? "—"}</Row>
              <Row label="Onset">
                {report.onsetText ?? report.onsetDate ?? "—"}
              </Row>
            </CardContent>
          </Card>

          {/* Location */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Location</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Row label="Reported">{report.locationText ?? "—"}</Row>
              <Row label="Normalized">
                {report.locationNormalized ?? "—"}
              </Row>
              {report.locationCoords && (
                <Row label="Coordinates">
                  {report.locationCoords.lat.toFixed(4)},{" "}
                  {report.locationCoords.lng.toFixed(4)}
                </Row>
              )}
            </CardContent>
          </Card>

          {/* Classification */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Classification</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Row label="Completeness">
                {report.dataCompleteness != null
                  ? `${Math.round(report.dataCompleteness * 100)}%`
                  : "—"}
              </Row>
              <Row label="Alert Type">
                {report.alertType?.replace("_", " ") ?? "—"}
              </Row>
            </CardContent>
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Conversation */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Conversation History
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ConversationView messages={messages} />
            </CardContent>
          </Card>

          {/* Investigation notes */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Investigation Notes</CardTitle>
            </CardHeader>
            <CardContent>
              <textarea
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring min-h-[100px] resize-y"
                placeholder="Add investigation notes..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </CardContent>
          </Card>

          {/* Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Change Status
                </label>
                <Select
                  value={report.status}
                  onValueChange={handleStatusChange}
                  disabled={updateReport.isPending}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="investigating">
                      Investigating
                    </SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="false_alarm">False Alarm</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {updateReport.isPending && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Updating...
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-right">{children}</span>
    </div>
  );
}
