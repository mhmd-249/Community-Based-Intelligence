"use client";

import { MapContainer, TileLayer } from "react-leaflet";
import { MapMarker } from "./MapMarker";
import type { Report } from "@/types";

// Sudan center coordinates
const SUDAN_CENTER: [number, number] = [15.5007, 32.5599];
const DEFAULT_ZOOM = 6;

interface IncidentMapProps {
  reports: Report[];
  className?: string;
}

export function IncidentMap({ reports, className }: IncidentMapProps) {
  // Filter reports that have coordinates
  const reportsWithCoords = reports.filter((r) => r.locationCoords !== null);

  return (
    <MapContainer
      center={SUDAN_CENTER}
      zoom={DEFAULT_ZOOM}
      className={className}
      style={{ height: "100%", width: "100%" }}
      scrollWheelZoom={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {reportsWithCoords.map((report) => (
        <MapMarker key={report.id} report={report} />
      ))}
    </MapContainer>
  );
}
