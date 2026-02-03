"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import type { Report } from "@/types";

// Sudan center coordinates
const SUDAN_CENTER: L.LatLngExpression = [15.5007, 32.5599];
const DEFAULT_ZOOM = 6;

const URGENCY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#3b82f6",
  low: "#6b7280",
};

interface IncidentMapProps {
  reports: Report[];
  className?: string;
}

export function IncidentMap({ reports, className }: IncidentMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // If map already exists, just update markers
    if (mapRef.current) {
      return;
    }

    // Create map
    const map = L.map(containerRef.current, {
      center: SUDAN_CENTER,
      zoom: DEFAULT_ZOOM,
      scrollWheelZoom: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    mapRef.current = map;

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Update markers when reports change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Clear existing markers
    map.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) {
        map.removeLayer(layer);
      }
    });

    // Add markers for reports with coordinates
    reports.forEach((report) => {
      if (!report.locationCoords) return;

      const color = URGENCY_COLORS[report.urgency] || URGENCY_COLORS.low;
      const radius =
        report.urgency === "critical"
          ? 12
          : report.urgency === "high"
            ? 10
            : 8;

      const marker = L.circleMarker(
        [report.locationCoords.lat, report.locationCoords.lng],
        {
          radius,
          color,
          fillColor: color,
          fillOpacity: 0.7,
          weight: 2,
        }
      ).addTo(map);

      const disease = report.suspectedDisease || "Unknown";
      const location =
        report.locationNormalized || report.locationText || "Unknown location";
      const cases =
        report.casesCount !== null
          ? `<p>${report.casesCount} case${report.casesCount !== 1 ? "s" : ""} reported</p>`
          : "";

      marker.bindPopup(`
        <div style="min-width: 180px;">
          <p style="font-weight: 600; text-transform: capitalize; margin: 0 0 4px 0;">${disease}</p>
          <p style="color: #666; margin: 0 0 4px 0;">${location}</p>
          ${cases}
          <p style="margin: 0 0 8px 0;">Status: <span style="color: ${report.status === "resolved" ? "#16a34a" : report.status === "investigating" ? "#d97706" : "#2563eb"}">${report.status.replace("_", " ")}</span></p>
          <a href="/reports/${report.id}" style="color: #2563eb; text-decoration: none;">View details →</a>
        </div>
      `);
    });
  }, [reports]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ height: "100%", width: "100%" }}
    />
  );
}
