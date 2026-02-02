"use client";

import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ReportFilters as Filters } from "@/hooks/useReports";

interface ReportFiltersProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

export function ReportFilters({ filters, onChange }: ReportFiltersProps) {
  const [search, setSearch] = useState(filters.search ?? "");

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      onChange({ ...filters, search, page: 1 });
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const activeCount = [filters.status, filters.urgency, filters.disease].filter(
    Boolean
  ).length;

  function clearAll() {
    setSearch("");
    onChange({ page: 1, pageSize: filters.pageSize });
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-white p-4">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search reports..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Status */}
      <Select
        value={filters.status ?? "all"}
        onValueChange={(v) =>
          onChange({ ...filters, status: v === "all" ? undefined : v, page: 1 })
        }
      >
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Status</SelectItem>
          <SelectItem value="open">Open</SelectItem>
          <SelectItem value="investigating">Investigating</SelectItem>
          <SelectItem value="resolved">Resolved</SelectItem>
          <SelectItem value="false_alarm">False Alarm</SelectItem>
        </SelectContent>
      </Select>

      {/* Urgency */}
      <Select
        value={filters.urgency ?? "all"}
        onValueChange={(v) =>
          onChange({
            ...filters,
            urgency: v === "all" ? undefined : v,
            page: 1,
          })
        }
      >
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="Urgency" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Urgency</SelectItem>
          <SelectItem value="critical">Critical</SelectItem>
          <SelectItem value="high">High</SelectItem>
          <SelectItem value="medium">Medium</SelectItem>
          <SelectItem value="low">Low</SelectItem>
        </SelectContent>
      </Select>

      {/* Disease */}
      <Select
        value={filters.disease ?? "all"}
        onValueChange={(v) =>
          onChange({
            ...filters,
            disease: v === "all" ? undefined : v,
            page: 1,
          })
        }
      >
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="Disease" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Diseases</SelectItem>
          <SelectItem value="cholera">Cholera</SelectItem>
          <SelectItem value="dengue">Dengue</SelectItem>
          <SelectItem value="malaria">Malaria</SelectItem>
          <SelectItem value="unknown">Unknown</SelectItem>
        </SelectContent>
      </Select>

      {/* Active filter count & clear */}
      {activeCount > 0 && (
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{activeCount} active</Badge>
          <Button variant="ghost" size="sm" onClick={clearAll}>
            <X className="h-4 w-4 mr-1" />
            Clear
          </Button>
        </div>
      )}
    </div>
  );
}
