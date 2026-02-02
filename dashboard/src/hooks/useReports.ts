"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { Report } from "@/types";

export interface ReportFilters {
  search?: string;
  status?: string;
  urgency?: string;
  disease?: string;
  page?: number;
  pageSize?: number;
}

interface PaginatedReports {
  items: Report[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

export function useReports(filters: ReportFilters = {}) {
  return useQuery<PaginatedReports>({
    queryKey: ["reports", filters],
    queryFn: () =>
      apiClient.get<PaginatedReports>("/api/reports", {
        page: filters.page ?? 1,
        page_size: filters.pageSize ?? 20,
        search: filters.search || undefined,
        status: filters.status || undefined,
        urgency: filters.urgency || undefined,
        disease: filters.disease || undefined,
      }),
    staleTime: 30000,
  });
}

export function useReport(id: string) {
  return useQuery<Report>({
    queryKey: ["reports", id],
    queryFn: () => apiClient.get<Report>(`/api/reports/${id}`),
    enabled: !!id,
  });
}

export function useUpdateReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Report> }) =>
      apiClient.patch<Report>(`/api/reports/${id}`, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(["reports", updated.id], updated);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}
