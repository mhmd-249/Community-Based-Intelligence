"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Officer } from "@/types";

interface AuthState {
  officer: Officer | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      officer: null,
      accessToken: null,
      isAuthenticated: false,

      login: async (email: string, password: string) => {
        const res = await fetch(`${API_URL}/api/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });

        if (!res.ok) {
          const error = await res.json().catch(() => ({
            detail: "Invalid credentials",
          }));
          throw new Error(error.detail || "Login failed");
        }

        const data = await res.json();
        const accessToken: string = data.accessToken;

        const meRes = await fetch(`${API_URL}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });

        if (!meRes.ok) {
          throw new Error("Failed to fetch officer profile");
        }

        const officer: Officer = await meRes.json();
        set({ officer, accessToken, isAuthenticated: true });
      },

      logout: () => {
        set({ officer: null, accessToken: null, isAuthenticated: false });
      },
    }),
    {
      name: "cbi-auth",
      partialize: (state) => ({
        officer: state.officer,
        accessToken: state.accessToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
