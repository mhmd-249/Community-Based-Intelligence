"use client";

import { useEffect, useRef } from "react";
import { io, type Socket } from "socket.io-client";
import { useAuthStore } from "@/stores/authStore";
import { useNotificationStore } from "@/stores/notificationStore";
import { useQueryClient } from "@tanstack/react-query";
import type { UrgencyLevel } from "@/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface NewAlertPayload {
  id: string;
  title: string;
  body: string;
  urgency: UrgencyLevel;
  reportId?: string;
  timestamp: string;
}

interface ReportUpdatedPayload {
  reportId: string;
}

export function useRealtime(): void {
  const socketRef = useRef<Socket | null>(null);
  const accessToken = useAuthStore((s) => s.accessToken);
  const addNotification = useNotificationStore((s) => s.addNotification);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!accessToken) return;

    const socket = io(WS_URL, {
      auth: { token: accessToken },
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
    });

    socketRef.current = socket;

    socket.on("connect", () => {
      console.log("[ws] connected:", socket.id);
    });

    socket.on("disconnect", (reason) => {
      console.log("[ws] disconnected:", reason);
    });

    socket.on("connect_error", (error) => {
      console.warn("[ws] connection error:", error.message);
    });

    socket.on("new_alert", (payload: NewAlertPayload) => {
      addNotification({
        id: payload.id,
        title: payload.title,
        body: payload.body,
        urgency: payload.urgency,
        reportId: payload.reportId,
        timestamp: new Date(payload.timestamp),
      });

      // Invalidate reports queries to refresh data
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    });

    socket.on("report_updated", (payload: ReportUpdatedPayload) => {
      // Invalidate the specific report and the reports list
      queryClient.invalidateQueries({ queryKey: ["reports", payload.reportId] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    });

    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, [accessToken, addNotification, queryClient]);
}
