"use client";

import { useRouter } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import { BellOff } from "lucide-react";
import { useNotificationStore } from "@/stores/notificationStore";
import { cn } from "@/lib/utils";
import type { Notification } from "@/types";

const URGENCY_BORDER: Record<string, string> = {
  critical: "border-l-red-500",
  high: "border-l-amber-500",
  medium: "border-l-blue-500",
  low: "border-l-slate-400",
};

interface NotificationListProps {
  onNavigate?: () => void;
}

export function NotificationList({ onNavigate }: NotificationListProps) {
  const router = useRouter();
  const notifications = useNotificationStore((s) => s.notifications);
  const markAsRead = useNotificationStore((s) => s.markAsRead);

  if (notifications.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <BellOff className="h-8 w-8 mb-2" />
        <p className="text-sm">All caught up!</p>
      </div>
    );
  }

  function handleClick(notification: Notification): void {
    markAsRead(notification.id);
    if (notification.reportId) {
      router.push(`/reports/${notification.reportId}`);
      onNavigate?.();
    }
  }

  return (
    <div className="max-h-80 overflow-y-auto -mx-4">
      {notifications.map((notification) => (
        <button
          key={notification.id}
          type="button"
          className={cn(
            "w-full text-left px-4 py-3 border-l-4 hover:bg-muted/50 transition-colors",
            URGENCY_BORDER[notification.urgency] ?? "border-l-slate-400",
            !notification.read && "bg-muted/30"
          )}
          onClick={() => handleClick(notification)}
        >
          <div className="flex items-start justify-between gap-2">
            <p
              className={cn(
                "text-sm leading-tight",
                !notification.read && "font-semibold"
              )}
            >
              {notification.title}
            </p>
            {!notification.read && (
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-blue-500" />
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
            {notification.body}
          </p>
          <p className="text-[10px] text-muted-foreground mt-1">
            {formatDistanceToNow(new Date(notification.timestamp), {
              addSuffix: true,
            })}
          </p>
        </button>
      ))}
    </div>
  );
}
