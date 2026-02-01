"use client";

import { useAuthStore } from "@/stores/authStore";
import { apiClient } from "@/lib/api";
import type { AuthTokens, LoginCredentials, Officer } from "@/types";

export function useAuth() {
  const { officer, tokens, isAuthenticated, setAuth, clearAuth, setTokens } =
    useAuthStore();

  async function login(credentials: LoginCredentials): Promise<void> {
    const authTokens = await apiClient.post<AuthTokens>(
      "/api/v1/auth/login",
      credentials
    );
    // Store tokens first so getHeaders() picks them up for the /me call
    setTokens(authTokens);
    const officerData = await apiClient.get<Officer>("/api/v1/auth/me");
    setAuth(officerData, authTokens);
  }

  async function logout(): Promise<void> {
    if (tokens?.accessToken) {
      try {
        await apiClient.post("/api/v1/auth/logout");
      } catch {
        // Logout even if server call fails
      }
    }
    clearAuth();
  }

  async function refreshToken(): Promise<AuthTokens | null> {
    if (!tokens?.refreshToken) return null;
    try {
      const newTokens = await apiClient.post<AuthTokens>(
        "/api/v1/auth/refresh",
        { refreshToken: tokens.refreshToken }
      );
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
