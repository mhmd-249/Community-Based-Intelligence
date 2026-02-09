"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/authStore";
import { useNotificationStore } from "@/stores/notificationStore";
import { useQueryClient } from "@tanstack/react-query";
import type { UrgencyLevel } from "@/types";

const BASE_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

// Convert http(s) to ws(s)
function toWsUrl(base: string, token: string): string {
  const url = base.replace(/^http/, "ws").replace(/\/$/, "");
  return `${url}/ws?token=${encodeURIComponent(token)}`;
}

interface WsMessage {
  type: string;
  // Nested data from RealtimeService wrapper
  data?: {
    type?: string;
    id?: string;
    title?: string;
    body?: string;
    urgency?: UrgencyLevel;
    reportId?: string;
    report_id?: string;
    timestamp?: string;
    update_type?: string;
    conversation_id?: string;
  };
  // Top-level fields (for flat messages)
  id?: string;
  title?: string;
  body?: string;
  urgency?: UrgencyLevel;
  reportId?: string;
  timestamp?: string;
  report_id?: string;
}

const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_BASE_DELAY = 2000;

export function useRealtime(): void {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const accessToken = useAuthStore((s) => s.accessToken);
  const addNotification = useNotificationStore((s) => s.addNotification);
  const queryClient = useQueryClient();

  const connect = useCallback(
    (token: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      const url = toWsUrl(BASE_URL, token);
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("[ws] connected");
        reconnectAttempts.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data);

          // RealtimeService wraps payloads: {"type": "broadcast"|"notification", "data": {...}}
          // Extract the inner payload for notification/broadcast types
          const inner = msg.data;
          const msgType = inner?.type ?? msg.type;

          if (
            msgType === "new_alert" ||
            msg.type === "notification" ||
            msg.type === "broadcast"
          ) {
            const notif = inner ?? msg;
            if (notif.title && notif.body) {
              addNotification({
                id: notif.id ?? crypto.randomUUID(),
                title: notif.title,
                body: notif.body,
                urgency: notif.urgency ?? "medium",
                reportId: notif.reportId ?? notif.report_id,
                timestamp: new Date(
                  notif.timestamp ?? msg.timestamp ?? Date.now()
                ),
              });
              queryClient.invalidateQueries({ queryKey: ["reports"] });
              queryClient.invalidateQueries({
                queryKey: ["analytics", "summary"],
              });
            }
          } else if (
            msgType === "report_updated" ||
            msg.type === "report_update"
          ) {
            const reportId =
              inner?.report_id ?? msg.reportId ?? msg.report_id;
            if (reportId) {
              queryClient.invalidateQueries({
                queryKey: ["reports", reportId],
              });
            }
            queryClient.invalidateQueries({ queryKey: ["reports"] });
          }
        } catch {
          // Ignore non-JSON messages (e.g. ping/pong)
        }
      };

      ws.onclose = (event) => {
        console.log("[ws] disconnected:", event.code, event.reason);
        wsRef.current = null;

        // Reconnect unless intentionally closed (1000) or auth failed (4001/4003)
        if (
          event.code !== 1000 &&
          event.code !== 4001 &&
          event.code !== 4003 &&
          reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS
        ) {
          const delay =
            RECONNECT_BASE_DELAY * Math.pow(1.5, reconnectAttempts.current);
          reconnectAttempts.current += 1;
          console.log(
            `[ws] reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts.current})`
          );
          reconnectTimer.current = setTimeout(() => connect(token), delay);
        }
      };

      ws.onerror = () => {
        // onclose will fire after this, handling reconnect
      };
    },
    [addNotification, queryClient]
  );

  useEffect(() => {
    if (!accessToken) return;

    connect(accessToken);

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close(1000, "unmount");
        wsRef.current = null;
      }
      reconnectAttempts.current = 0;
    };
  }, [accessToken, connect]);
}
