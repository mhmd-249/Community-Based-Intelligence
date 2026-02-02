import { create } from "zustand";
import type { Notification } from "@/types";

const MAX_NOTIFICATIONS = 50;

function playAlertSound(): void {
  if (typeof window === "undefined") return;

  try {
    const audio = new Audio("/sounds/alert.mp3");
    audio.volume = 0.5;
    audio.play().catch(() => {
      // Fallback: generate a beep using Web Audio API
      try {
        const ctx = new AudioContext();
        const oscillator = ctx.createOscillator();
        const gain = ctx.createGain();
        oscillator.connect(gain);
        gain.connect(ctx.destination);
        oscillator.frequency.value = 880;
        oscillator.type = "sine";
        gain.gain.value = 0.3;
        oscillator.start();
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
        oscillator.stop(ctx.currentTime + 0.5);
      } catch {
        // Audio not available
      }
    });
  } catch {
    // Audio not available in this environment
  }
}

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  addNotification: (notification: Omit<Notification, "read">) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  setNotifications: (notifications: Notification[]) => void;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  unreadCount: 0,
  addNotification: (notification) => {
    // Play alert sound for critical urgency
    if (notification.urgency === "critical") {
      playAlertSound();
    }

    set((state) => {
      const newNotification: Notification = { ...notification, read: false };
      const notifications = [newNotification, ...state.notifications].slice(
        0,
        MAX_NOTIFICATIONS
      );
      return {
        notifications,
        unreadCount: notifications.filter((n) => !n.read).length,
      };
    });
  },
  markAsRead: (id) =>
    set((state) => {
      const notifications = state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      );
      return {
        notifications,
        unreadCount: notifications.filter((n) => !n.read).length,
      };
    }),
  markAllAsRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),
  setNotifications: (notifications) =>
    set({
      notifications: notifications.slice(0, MAX_NOTIFICATIONS),
      unreadCount: notifications.filter((n) => !n.read).length,
    }),
}));
