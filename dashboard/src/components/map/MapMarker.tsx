"use client";

import { CircleMarker, Popup } from "react-leaflet";
import Link from "next/link";
import type { Report, UrgencyLevel } from "@/types";

const URGENCY_COLORS: Record<UrgencyLevel, string> = {
  critical: "#ef4444", // red-500
  high: "#f97316", // orange-500
  medium: "#3b82f6", // blue-500
  low: "#6b7280", // gray-500
};

interface MapMarkerProps {
  report: Report;
}

export function MapMarker({ report }: MapMarkerProps) {
  if (!report.locationCoords) return null;

  const color = URGENCY_COLORS[report.urgency];
  const position: [number, number] = [
    report.locationCoords.lat,
    report.locationCoords.lng,
  ];

  return (
    <CircleMarker
      center={position}
      radius={report.urgency === "critical" ? 12 : report.urgency === "high" ? 10 : 8}
      pathOptions={{
        color,
        fillColor: color,
        fillOpacity: 0.7,
        weight: 2,
      }}
    >
      <Popup>
        <div className="min-w-[180px] text-sm">
          <p className="font-semibold capitalize">
            {report.suspectedDisease || "Unknown Disease"}
          </p>
          <p className="text-muted-foreground mt-1">
            {report.locationNormalized || report.locationText || "Unknown location"}
          </p>
          {report.casesCount !== null && (
            <p className="mt-1">
              <span className="font-medium">{report.casesCount}</span> case
              {report.casesCount !== 1 ? "s" : ""} reported
            </p>
          )}
          <p className="mt-1">
            Status:{" "}
            <span
              className={
                report.status === "resolved"
                  ? "text-green-600"
                  : report.status === "investigating"
                    ? "text-amber-600"
                    : "text-blue-600"
              }
            >
              {report.status.replace("_", " ")}
            </span>
          </p>
          <Link
            href={`/reports/${report.id}`}
            className="mt-2 inline-block text-blue-600 hover:underline"
          >
            View details →
          </Link>
        </div>
      </Popup>
    </CircleMarker>
  );
}

export { URGENCY_COLORS };
