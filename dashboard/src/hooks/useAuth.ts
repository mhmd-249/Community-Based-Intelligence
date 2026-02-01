"use client";

import { useAuthStore } from "@/stores/authStore";
import { api } from "@/lib/api";
import type { AuthTokens, LoginCredentials, Officer } from "@/types";

export function useAuth() {
  const { officer, tokens, isAuthenticated, setAuth, clearAuth, setTokens } =
    useAuthStore();

  async function login(credentials: LoginCredentials): Promise<void> {
    const authTokens = await api.post<AuthTokens>(
      "/api/v1/auth/login",
      credentials
    );
    const officerData = await api.get<Officer>("/api/v1/auth/me", {
      token: authTokens.accessToken,
    });
    setAuth(officerData, authTokens);
  }

  async function logout(): Promise<void> {
    if (tokens?.accessToken) {
      try {
        await api.post("/api/v1/auth/logout", null, {
          token: tokens.accessToken,
        });
      } catch {
        // Logout even if server call fails
      }
    }
    clearAuth();
  }

  async function refreshToken(): Promise<AuthTokens | null> {
    if (!tokens?.refreshToken) return null;
    try {
      const newTokens = await api.post<AuthTokens>("/api/v1/auth/refresh", {
        refreshToken: tokens.refreshToken,
      });
      setTokens(newTokens);
      return newTokens;
    } catch {
      clearAuth();
      return null;
    }
  }

  return {
    officer,
    tokens,
    isAuthenticated,
    login,
    logout,
    refreshToken,
  };
}
