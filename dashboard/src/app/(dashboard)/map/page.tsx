"use client";

import { useState, useMemo } from "react";
import dynamic from "next/dynamic";
import { Filter, Loader2 } from "lucide-react";
import { useReports } from "@/hooks/useReports";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { URGENCY_COLORS } from "@/components/map/MapMarker";
import type { UrgencyLevel } from "@/types";

// Dynamic import to avoid SSR issues with Leaflet
const IncidentMap = dynamic(
  () => import("@/components/map/IncidentMap").then((mod) => mod.IncidentMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center bg-muted/20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    ),
  }
);

const DISEASES = ["cholera", "dengue", "malaria", "unknown"] as const;
const URGENCIES: UrgencyLevel[] = ["critical", "high", "medium", "low"];

export default function MapPage() {
  const [showFilters, setShowFilters] = useState(true);
  const [selectedDiseases, setSelectedDiseases] = useState<Set<string>>(
    new Set(DISEASES)
  );
  const [selectedUrgencies, setSelectedUrgencies] = useState<Set<UrgencyLevel>>(
    new Set(URGENCIES)
  );

  // Fetch all reports (large page size for map view)
  const { data, isLoading } = useReports({ page: 1, pageSize: 500 });

  // Filter reports based on selected filters
  const filteredReports = useMemo(() => {
    if (!data?.items) return [];
    return data.items.filter((report) => {
      const disease = report.suspectedDisease || "unknown";
      return (
        selectedDiseases.has(disease) && selectedUrgencies.has(report.urgency)
      );
    });
  }, [data?.items, selectedDiseases, selectedUrgencies]);

  function toggleDisease(disease: string) {
    setSelectedDiseases((prev) => {
      const next = new Set(prev);
      if (next.has(disease)) {
        next.delete(disease);
      } else {
        next.add(disease);
      }
      return next;
    });
  }

  function toggleUrgency(urgency: UrgencyLevel) {
    setSelectedUrgencies((prev) => {
      const next = new Set(prev);
      if (next.has(urgency)) {
        next.delete(urgency);
      } else {
        next.add(urgency);
      }
      return next;
    });
  }

  const reportsWithCoords = filteredReports.filter((r) => r.locationCoords);

  return (
    <div className="relative h-[calc(100vh-theme(spacing.14)-theme(spacing.12))]">
      {/* Map */}
      {isLoading ? (
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <IncidentMap reports={filteredReports} className="h-full w-full rounded-lg" />
      )}

      {/* Filter toggle button (mobile) */}
      <Button
        variant="outline"
        size="icon"
        className="absolute right-4 top-4 z-[1000] lg:hidden bg-white"
        onClick={() => setShowFilters(!showFilters)}
      >
        <Filter className="h-4 w-4" />
      </Button>

      {/* Floating filter panel */}
      <Card
        className={`absolute right-4 top-4 z-[1000] w-64 p-4 transition-transform ${
          showFilters ? "translate-x-0" : "translate-x-[calc(100%+1rem)]"
        } hidden lg:block`}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-sm">Filters</h3>
          <span className="text-xs text-muted-foreground">
            {reportsWithCoords.length} on map
          </span>
        </div>

        {/* Disease filters */}
        <div className="mb-4">
          <p className="text-xs font-medium text-muted-foreground mb-2">
            Disease
          </p>
          <div className="space-y-2">
            {DISEASES.map((disease) => (
              <div key={disease} className="flex items-center gap-2">
                <Checkbox
                  id={`disease-${disease}`}
                  checked={selectedDiseases.has(disease)}
                  onCheckedChange={() => toggleDisease(disease)}
                />
                <Label
                  htmlFor={`disease-${disease}`}
                  className="text-sm capitalize cursor-pointer"
                >
                  {disease}
                </Label>
              </div>
            ))}
          </div>
        </div>

        {/* Urgency filters */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">
            Urgency
          </p>
          <div className="space-y-2">
            {URGENCIES.map((urgency) => (
              <div key={urgency} className="flex items-center gap-2">
                <Checkbox
                  id={`urgency-${urgency}`}
                  checked={selectedUrgencies.has(urgency)}
                  onCheckedChange={() => toggleUrgency(urgency)}
                />
                <Label
                  htmlFor={`urgency-${urgency}`}
                  className="text-sm capitalize cursor-pointer flex items-center gap-2"
                >
                  <span
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: URGENCY_COLORS[urgency] }}
                  />
                  {urgency}
                </Label>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Legend */}
      <Card className="absolute bottom-4 left-4 z-[1000] p-3">
        <p className="text-xs font-medium text-muted-foreground mb-2">Legend</p>
        <div className="flex flex-wrap gap-3">
          {URGENCIES.map((urgency) => (
            <div key={urgency} className="flex items-center gap-1.5">
              <span
                className="h-3 w-3 rounded-full"
                style={{ backgroundColor: URGENCY_COLORS[urgency] }}
              />
              <span className="text-xs capitalize">{urgency}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
